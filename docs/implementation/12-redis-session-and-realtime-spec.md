# Technical Specification: Redis Session Caching, Worker Liveness & Real-Time Event Expansion

- **Specification ID**: SPEC-REDIS-EXP-01
- **Status**: APPROVED FOR IMPLEMENTATION
- **Target Subsystems**: `services/api/mark_api`, `services/worker`, `mark_engine/adapters/redis_cache.py`, `web/src/hooks`
- **Target Host**: Production server `10.153.90.17` (Docker Compose) & Dev workstation `10.151.97.18`

---

## 1. Problem & Architecture Goals

### 1.1 Problems Addressed
1. **Connection Pool Bottleneck**: Every API request currently queries PostgreSQL (`SELECT * FROM app_session JOIN app_user`) to authenticate. At 10 concurrent requests, the 10-connection pool (`ThreadedConnectionPool`) becomes exhausted.
2. **Worker Blindness**: The web application cannot distinguish between an idle worker, a processing worker, and a crashed worker without inspecting logs or database tables.
3. **Coarse-Grained Real-Time Updates**: WebSocket events only fire on revision completion. Scan batches and multi-job operations have no progress reporting.
4. **IP-Shared Rate Limiting**: NGINX limits requests per client IP, throttling multiple engineers operating behind the same factory proxy.

### 1.2 Architectural Goals
- Reduce PostgreSQL auth query traffic by **100%** on cache hits.
- Reduce session verification latency to **< 0.5ms**.
- Provide sub-second worker heartbeat and real-time active job visibility.
- Broadcast multi-event progress streaming to frontend over WebSocket without page reloads.
- Strict constraint: **Redis RAM capped at 256MB with `allkeys-lru` eviction** and zero disk persistence (`--save ""`).

---

## 2. Pillar Specifications

### Pillar 1: User Session Caching & Invalidation (P0)

#### Key Design:
- **Redis Key**: `mark:session:{sha256(mark_session_token)}`
- **Type**: JSON String
- **Default TTL**: 900 seconds (15 minutes), with **Sliding Expiration** (renewed on every active request).

#### Data Payload:
```json
{
  "user_id": 2,
  "username": "qa_engineer",
  "display_name": "QA Engineer",
  "role": "engineer",
  "csrf_hash": "a1b2c3d4...",
  "active": true,
  "expires_at": "2026-11-07T12:00:00+00:00",
  "cached_at": "2026-11-07T08:15:00+00:00"
}
```

#### Invalidation Rules:
1. **User Logout** (`POST /api/auth/logout`):
   - Delete key `mark:session:{token_hash}` immediately.
2. **Admin User Deactivation / Lock / Unlock** (`/api/admin/users/...`):
   - Invalidate all active sessions for the targeted `user_id`.
3. **Session Expiry**:
   - Natural TTL expiration handled by Redis.

#### Graceful Fallback Contract:
```python
def get_cached_session(client, token_hash, load_db_fn):
    if client is not None:
        try:
            cached = client.get(f"mark:session:{token_hash}")
            if cached:
                client.expire(f"mark:session:{token_hash}", 900)  # Sliding TTL
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis session read failed: {e}")
    # Fallback to direct DB query
    user_data = load_db_fn(token_hash)
    if client is not None and user_data:
        try:
            client.set(f"mark:session:{token_hash}", json.dumps(user_data), ex=900)
        except Exception:
            pass
    return user_data
```

---

### Pillar 2: Worker Liveness & Active Job Tracking (P1)

#### 1. Worker Heartbeat:
- **Redis Key**: `mark:worker:heartbeat`
- **Type**: JSON String: `{"worker_id": "worker-1", "pid": 1, "last_beat": "2026-11-07T08:15:30Z", "version": "0.2.0"}`
- **TTL**: 30 seconds
- **Behavior**: Background loop in `services/worker/main.py` updates key every 10 seconds.
- **Consumption**: `/api/ready` checks whether `mark:worker:heartbeat` exists. If missing for >30s, reports worker degraded/stalled.

#### 2. Active Job State:
- **Redis Key**: `mark:job:active:{elr_no}`
- **Type**: JSON String: `{"run_id": 27, "elr_no": "ADI2607006", "started_at": "...", "worker_id": "worker-1"}`
- **TTL**: 120 seconds (safety auto-expiry if worker abruptly dies).
- **Lifecycle**:
  - Set when worker claims job from `mark_app.elr_job`.
  - Deleted when worker completes revision write or logs failure.
  - Consumed by `/api/elrs/{elr_no}`: returns `"is_processing": true` in UI.

---

### Pillar 3: Real-Time Event Streaming & WebSocket Progress (P1)

#### Redis Pub/Sub Channel: `mark_events`

Standardized Event Envelope:
```json
{
  "event": "job_progress" | "revision_saved" | "scan_started" | "scan_completed",
  "timestamp": "2026-11-07T08:15:30.123Z",
  "data": { ... }
}
```

#### Event Schemas:
1. `scan_started`:
   ```json
   { "event": "scan_started", "data": { "scan_id": 142, "total_elrs": 45, "run_id": 27 } }
   ```
2. `job_progress`:
   ```json
   { "event": "job_progress", "data": { "scan_id": 142, "completed": 12, "total": 45, "current_elr": "ADI2607006", "percent": 26.6 } }
   ```
3. `revision_saved`:
   ```json
   { "event": "revision_saved", "data": { "run_id": 27, "elr_no": "ADI2607006", "revision": 6, "result": "TRUE" } }
   ```

#### WebSocket Consumer:
- `services/api/mark_api/routers/ws.py` reads from Redis Pub/Sub and broadcasts JSON envelope directly to connected browser clients.
- `web/src/hooks/useEvents.ts` dispatches events to React Query invalidation and UI state hooks.

---

### Pillar 4: User-Level Sliding Window Rate Limiting (P2)

#### Purpose:
Prevent deliberate or accidental trigger flooding (e.g. rapid clicking on "Recheck" or "Trigger Scan") on a per-user basis without punishing other users on the same subnet.

#### Algorithm:
Redis Sorted Set (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`, `EXPIRE`):
1. **Key**: `mark:ratelimit:user:{user_id}:{action}`
2. **Window**: 60 seconds.
3. **Thresholds**:
   - `action=scan_trigger`: 5 requests per 60 seconds per user.
   - `action=recheck_elr`: 10 requests per 60 seconds per user.
4. **Behavior on Breach**: Returns HTTP 429 Too Many Requests with header `Retry-After: <seconds>`.

---

## 3. Redis Memory Budget & Safety Guardrails

| Key Pattern | Projected Count | Avg Size | Total RAM | Max TTL | Eviction Policy |
|---|:---:|:---:|:---:|:---:|:---:|
| `mark:session:*` | 100 – 1,000 | 400 B | ~0.4 MB | 900s | `allkeys-lru` |
| `mark:worker:heartbeat` | 1 | 120 B | < 1 KB | 30s | `allkeys-lru` |
| `mark:job:active:*` | 1 – 10 | 250 B | < 5 KB | 120s | `allkeys-lru` |
| `mark:dashboard:*` | 20 – 50 | 2 KB | ~0.1 MB | 30s | `allkeys-lru` |
| `mark:layout:*` | 500 – 2,000 | 1.5 KB | ~3.0 MB | 86,400s | `allkeys-lru` |
| `mark:ratelimit:*` | 10 – 100 | 500 B | ~0.05 MB | 60s | `allkeys-lru` |
| **Total Projected Footprint** | | | **< 5 MB** | | **Capped at 256 MB (2%)** |

---

## 4. Implementation Checklist

- [ ] `mark_engine/adapters/redis_cache.py`: Add session, heartbeat, active job, and rate-limit helpers.
- [ ] `services/api/mark_api/deps.py`: Wrap `current_user()` and `_session_authorized()` with session cache.
- [ ] `services/api/mark_api/routers/auth.py`: Add cache invalidation on logout.
- [ ] `services/api/mark_api/routers/admin.py`: Add cache invalidation on user lock/unlock.
- [ ] `services/worker/main.py`: Add worker heartbeat loop and active job markers.
- [ ] `web/src/hooks/useEvents.ts`: Add typed event dispatching.
- [ ] `tests/unit/test_redis_session.py`: Comprehensive unit tests.

## 5. Implementation and deployment constraints

- Session cache coherence is supported for the deployed **single API process and
  single API replica** (`uvicorn --workers 1` in the API Dockerfile and the
  default Compose replica count). Each process trusts only sessions that it
  loaded from PostgreSQL itself. Revocation and cache fills are serialized in
  that process; restart and Redis errors discard that process's trust. Do not
  add API workers or replicas until invalidation is coordinated across them.
- User session, password, role, and activation changes must use the API while
  it is running. In particular, password resets use `python
  scripts/create_app_user.py USER --reset --api-url http://HOST:PORT`; the
  command prompts for administrator credentials and calls the admin API. Direct
  SQL changes or older reset scripts bypass process-local invalidation.
- Cached session JSON contains only `user_id`, `username`, `role`, `csrf_hash`,
  `active`, and `expires_at`. `/auth/me` fetches the display name from
  PostgreSQL when necessary. Session activity is persisted to PostgreSQL at
  most once per minute; WebSocket revalidation does not renew idle time.
- If Redis is unavailable, ELR liveness is read from the worker's
  transaction-scoped PostgreSQL advisory lock. The rate limiter falls back to
  recent successful scan/recheck audit records. That fallback is best effort:
  failed requests are not all present in the audit log, and concurrent checks
  are not atomic. Redis is required for the strict sliding-window guarantee.
- `/api/worker/status` reports `alive`, `degraded` when Redis is reachable but
  the heartbeat is absent, or `unknown` when Redis is unavailable. A heartbeat
  reflects process liveness; it does not prove that a particular job is making
  progress.
- The existing scan endpoint is `/api/scans`; `/api/scans/trigger` is an alias
  with the same authorization and per-user rate limit. Web clients use the
  existing event-driven refetch hook (this application does not use React
  Query).
