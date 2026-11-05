# Login audit, admin unlock and manager activity dashboard — design

Date: 2026-11-05 · Branch: `phase2/trial` · Builds on: `2026-11-05-phase2-trial-design.md` (§ auth, logging, schema `mark_app`)

## 1. Why

During the trial, the user expects two recurring needs:

1. **"I can't log in."** When someone reports this, the user or an admin must find the cause from the DB within a few minutes, without digging through container logs. Look-ups are by person (`user_id`) or by time window.
2. **A manager overview.** A manager wants an overall picture of the trial: who is reviewing and approving, how much is left, and whether login problems are common.

Today neither works:
- **Missing events:** `mark_app.audit_log` records only `auth.login_ok`, `auth.logout`, `review.saved` and `approval.saved`. Failed logins, lockouts and expired sessions go only to stdout.
- **No link to logs:** audit rows carry no IP or `request_id`, so they cannot be matched to NGINX or API log lines.
- **Logs are lost on deploy:** container logs disappear every time Jenkins redeploys (`docker compose up` recreates the containers).
- **No unlock:** an admin cannot unlock a user except by waiting 15 minutes or editing the DB.

## 2. Goals

- **G1. Explain a failed login from the DB.** Every login outcome is recorded with time, IP and `request_id`, so these causes can be told apart:
  - unknown username
  - wrong password, and the count so far
  - locked, and until when
  - inactive
  - session expired, by absolute age or by idle time
- **G2. Admin user list:** each user's state (role, active, failed count, locked until, last login) and an **Unlock** action, which is itself audited.
- **G3. Manager activity page** (admin role), showing for a chosen date range:
  - reviews and approvals per user per day
  - progress of the current run: ELRs approved, rejected, or still without a decision
  - login problems per day: failed attempts, lockouts, expired sessions
  - the latest auth events (paged), for the "can't log in" check
- **G4. API logs survive redeploys.** They are written to a host folder with rotation.
- **G5. An admin account exists.** The user creates it with the existing `scripts/create_app_user.py --role admin`; the password is typed by the user and never by the agent.

## 3. Non-goals

- No new role and no change to the role matrix for review or approve. The **manager uses the `admin` role**, which already has `read` and `metrics`. *(Builder's call, settled in design.)*
- No charts library change. Reuse the patterns already in `web/src/components` (`MonthlyChart`, `StatusCards`).
- No user create/edit UI. Users are still created with the script.
- No retention job. Trial volume is small, and `audit_log` already has a `created_at` index.
- WebSocket live updates are out of scope; they were deferred earlier.
- NGINX logs are not persisted. A 429 rate-limit is visible to the user as "too many attempts", and NGINX stdout is enough for the trial.

## 4. Anti-goals (would be a failure even if it works)

- **Logging what someone typed.** A typed username that matches no account is never stored, in the DB or in logs (existing rule). Such rows have `user_id = null` and carry the IP. Passwords and tokens are never logged.
- **Spoofable IPs.** A client must not be able to set the IP it is recorded with. The IP comes from `X-Real-IP`, which NGINX sets to `$remote_addr` and which overrides anything the client sent.
- **Slow login.** At most one audit insert per login attempt, and an audit failure must not turn a correct login into an error. Wrap it and log `db.error` instead.
- **Slow dashboard.** One fixed set of grouped queries per request, never one per user or per day. The date range is capped at 92 days.

## 5. Design

### 5.1 Schema — `migrations/0006_audit_context.sql`

Additive only and idempotent (`if not exists`):

```sql
alter table mark_app.audit_log add column if not exists client_ip inet;
alter table mark_app.audit_log add column if not exists request_id text;
create index if not exists audit_log_action_created_idx on mark_app.audit_log (action, created_at);
```

- No new tables.
- Grants are unchanged: role `mark_app` already has `insert` and `select` on `audit_log`. It needs `update` on `app_user`, which it already has for `record_login`.

### 5.2 Audit actions

All rows carry `client_ip` and `request_id`.

| action | user_id | detail |
|---|---|---|
| `auth.login_ok` | user | – |
| `auth.login_failed` | user, or null | `{"reason": "unknown_user" \| "bad_password" \| "locked" \| "inactive", "failed_count": n}` (count only for bad_password) |
| `auth.locked` | user | `{"locked_until": iso}` (written when the 5th failure locks the account) |
| `auth.session_expired` | user | `{"why": "absolute" \| "idle"}` (written once; the session row is deleted at the same time) |
| `auth.logout` | user | – |
| `admin.unlock` | admin | `{"target_user_id": id}` |
| `review.saved`, `approval.saved` | unchanged | unchanged |

**Request context for audit rows:**
- `Repo.audit(...)` gains `client_ip` and `request_id` keyword parameters. Routers pass them from `request.state.request_id` and from `X-Real-IP` (falling back to the socket peer).
- A small helper `audit_ctx(request) -> dict` builds both values.

**Session expiry:**
- `auth.session_valid` returns a bool today. It becomes `session_status(...) -> "ok" | "absolute" | "idle"`, and `session_valid` keeps working as `session_status(...) == "ok"`, so existing tests stay valid.

### 5.3 API (new router `routers/admin.py`, prefix `/api/admin`)

Every route requires the new action `"admin"`. It is added to the role matrix for `admin` only.

**`GET /api/admin/users`** returns a list of:
`{user_id, username, display_name, role, active, failed_count, locked_until, last_login_at, state}`
- `state` is `OK`, `LOCKED` or `INACTIVE`, from `login_state`.
- `last_login_at` is the latest `auth.login_ok` from `audit_log`, found in one grouped query.

**`POST /api/admin/users/{user_id}/unlock`**
- Sets `failed_count = 0` and `locked_until = null`, then writes audit `admin.unlock`.
- Returns 404 for an unknown id.
- It is a POST, so the CSRF and Origin rules already apply.

**`GET /api/admin/activity?from=YYYY-MM-DD&to=YYYY-MM-DD&run_id=`**
- Defaults: the last 14 days, and the latest run.
- Returns 422 if the range is over 92 days or `from > to`.
- Response:
  - `per_user_day`: `[{day, user_id, display_name, reviews, approvals}]` (from `audit_log` `review.saved` / `approval.saved`)
  - `run_progress`: `{run_id, total_elrs, approved, rejected, undecided}` (the latest decision per ELR, from `approval`)
  - `auth_per_day`: `[{day, login_ok, login_failed, locked, session_expired}]`

**`GET /api/admin/events?from=&to=&user_id=&action=&page=`**
- 50 rows per page, newest first.
- Each row: `{created_at, action, user_id, display_name, client_ip, request_id, detail}`.

**Days** are calendar days in `Asia/Bangkok`. The SQL groups on `(created_at at time zone 'Asia/Bangkok')::date`.

### 5.4 Web

- **New route `/admin`**, a lazy-loaded page like Preview, shown only when `me.role === 'admin'`. The Dashboard header gets an "Admin" link for admins.
- **Section 1, "ผู้ใช้" (users):** a table built from `/admin/users`, with a state badge. When the state is LOCKED, an **Unlock** button calls the unlock endpoint and refreshes the table.
- **Section 2, "ภาพรวม" (overview):**
  - a date-range input (default 14 days)
  - run progress cards: total, approved, rejected, undecided (reusing the `StatusCards` style)
  - a reviews/approvals per-day chart (reusing `MonthlyChart`)
  - a per-user totals table
  - an auth-problems per-day chart
- **Section 3, "เหตุการณ์ล่าสุด" (latest events):** the paged events table, filterable by user and action. This is the "can't log in" look-up.
- **Existing app:** the engineer and approver flows do not change. Admin users opening `/` keep today's behaviour: they can read, and the API already refuses review/approve for them with 403.

### 5.5 Persistent API logs

- **Log file:** `mark_api/logging.py` adds an optional `RotatingFileHandler` when `MARK_LOG_DIR` is set. It writes `api.jsonl`, 10 MB × 5 files, with the same JSON lines as stdout.
- **Compose:** sets `MARK_LOG_DIR=/app/logs` and mounts `${MARK_LOG_HOST_DIR:-./logs}:/app/logs`. `logs/` is git-ignored and listed in `.dockerignore`.
- **Container user:** the API image runs as root today (`services/api/Dockerfile` has no `USER`), so the bind mount is writable. Hardening to a non-root user is out of scope here.

### 5.6 Admin account (G5)

- No code is needed.
- **Step for the user:** in their own terminal, run `python scripts/create_app_user.py <username> --name "<display>" --role admin`. It prompts for the password twice, with a minimum of 12 characters.
- The agent never types or sees the password.

## 6. Tests (only what is new; no duplicates of existing auth tests)

- **Unit, `tests/unit/test_api_core.py`:**
  - `session_status` returns `absolute` or `idle` correctly.
  - `can("admin", "admin")` is true; it is false for engineer and approver.
- **Routes, `tests/unit/test_api_routes.py`, with the fake repo:**
  1. An unknown user → audit `auth.login_failed` with `user_id=None` and `reason=unknown_user`, and no username anywhere in the audit or log.
  2. A bad password reaching the 5th failure → `auth.login_failed` and `auth.locked`, both with `client_ip` taken from `X-Real-IP` and the request's `request_id`.
  3. An expired session → 401 and one `auth.session_expired`.
  4. `/api/admin/*` → 403 for engineer, 200 for admin. Unlock clears the lock and writes `admin.unlock`. Unlocking an unknown id → 404.
  5. `/api/admin/activity` with a range over 92 days → 422.
  6. An audit insert that raises does not break a correct login (200).
- **SQL:** the grouped queries run once against the real DB in the manual check, not in unit tests, because the repo fake has no SQL.
- **Web:** `npm run build` passes. The admin page is checked by hand.

## 7. Rollout

1. Migration 0006 runs on `mark_web` at 10.151.28.2, which is shared, as postgres. **It needs the user's go-ahead**, the same as the Phase 2 [USER] steps.
2. Code is merged to `phase2/trial`. Jenkins builds and deploys to localhost:8088.
3. The user creates the admin account (§5.6) and checks `/admin`.
4. HANDOFF §4 and QA_LOG are updated with each commit.

## 8. Builder's calls (made in this design; the user may override)

- The manager uses the existing `admin` role. No new role.
- No username is stored for unknown-user attempts.
- Day boundaries are Asia/Bangkok.
- Defaults are 14 days, a 92-day cap, and 50 rows per page.
- NGINX logs are not persisted for the trial; only API logs are.
