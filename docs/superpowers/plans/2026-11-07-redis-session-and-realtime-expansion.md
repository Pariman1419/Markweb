# Implementation Plan: Redis Session Caching, Worker Liveness, and Real-Time Event Expansion

> **Context**: Mark Web is successfully operating in production on `10.153.90.17:8093` with Redis 7 Alpine caching Oracle layout specs and Dashboard cards (Jenkins Build #14, commit `68f4dae`).
> **Problem Statement**:
> 1. Load testing revealed that every incoming request executes `SELECT * FROM app_session JOIN app_user` on PostgreSQL (`10.151.28.2`), consuming up to 50% of the `ThreadedConnectionPool(1, 10)`. Under high concurrency (10+ threads), this causes connection pool exhaustion and elevated latency.
> 2. The API and frontend have no direct visibility into worker process health or active job execution state in real time.
> 3. WebSocket Pub/Sub is currently limited to post-revision events without progress streaming or scan lifecycle notifications.
> 4. Rate limiting is currently IP-based at NGINX, which shared across factory NAT/proxy environments.
>
> **Objective**: Expand Redis into an authoritative, high-performance in-memory coordination and caching layer covering:
> - **Pillar 1 (P0)**: User Session Caching & Immediate Invalidation (Eliminating 50% of PostgreSQL auth traffic).
> - **Pillar 2 (P1)**: Worker Liveness Heartbeat & Active Job Tracking.
> - **Pillar 3 (P1)**: Extended Pub/Sub Lifecycle & Real-Time Progress Streaming.
> - **Pillar 4 (P2)**: User-Level Sliding Window Rate Limiting for scan/recheck triggers.

---

## 1. Overview & Objectives

- **Target Host**: Production server `10.153.90.17` (Docker Compose stack).
- **Resource Footprint**: Strictly constrained within existing `redis:7-alpine` container capped at **256MB RAM** with `allkeys-lru` eviction.
- **Expected Technical Impact**:
  - Session verification latency drops from ~8-15ms (PostgreSQL TCP roundtrip) to **<0.5ms** (Redis RAM).
  - PostgreSQL connection pool contention eliminated; supports **30+ concurrent users** without pool exhaustion.
  - Sub-second UI updates for active worker jobs and multi-job scan progress bars.
  - Zero downtime: Graceful fallback to PostgreSQL/disk if Redis ever goes offline.

---

## 2. Proposed Architecture & Design Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            React Web Frontend                               │
│            (Live Badges, Progress Bars, Real-Time Notifications)            │
└───────────────────────┬─────────────────────────────▲───────────────────────┘
                        │ HTTP / REST                 │ WebSocket (/api/ws/events)
                        ▼                             │
┌─────────────────────────────────────────────────────┼───────────────────────┐
│                    NGINX Reverse Proxy (:8093)      │                       │
└───────────────────────┬─────────────────────────────┼───────────────────────┘
                        ▼                             │
┌─────────────────────────────────────────────────────┴───────────────────────┐
│                      Docker Compose on 10.153.90.17                         │
│                                                                             │
│   ┌──────────────────────────┐             ┌────────────────────────────┐   │
│   │       mark-web-api       │ ◄──────────►│         mark-redis         │   │
│   │   (FastAPI Application)  │             │      (redis:7-alpine)      │   │
│   └─────────────┬────────────┘             │      Maxmemory: 256MB      │   │
│                 │                          └─────────────▲──────────────┘   │
│                 │                                        │                  │
│                 ▼                                        │ Pub/Sub & State  │
│   ┌──────────────────────────┐                           │                  │
│   │     mark-web-worker      │ ──────────────────────────┘                  │
│   │   (Background Daemon)    │                                              │
│   └─────────────┬────────────┘                                              │
└─────────────────┼───────────────────────────────────────────────────────────┘
                  ▼
      PostgreSQL Persistent DB (10.151.28.2) & Oracle 10g (10.151.26.3)
```

### Redis Key Namespace & Data Life Cycle

| Key Pattern | Data Structure | TTL | Eviction Policy | Purpose |
|---|:---:|:---:|:---:|---|
| `mark:session:{token_hash}` | JSON String | 15 mins (Sliding) | `allkeys-lru` | Cached user profile & permissions |
| `mark:worker:heartbeat` | String | 30 seconds | `allkeys-lru` | Worker liveness status for `/api/ready` |
| `mark:job:active:{elr_no}` | JSON String | 120 seconds | `allkeys-lru` | Active ELR being processed by worker |
| `mark:dashboard:{run_id}` | Hash (v, data) | 30 seconds | `allkeys-lru` | Cached dashboard aggregate cards |
| `mark:layout:{mark_id}` | JSON String | 24 hours | `allkeys-lru` | Cached Oracle layout specifications |
| `mark:ratelimit:user:{id}:{action}` | Sorted Set | 60 seconds | `allkeys-lru` | Sliding window user rate limit |

### Key Files Modified / Added:
1. `mark_engine/adapters/redis_cache.py`:
   - Add `cache_session()`, `invalidate_session()`, `invalidate_user_sessions()`.
   - Add `worker_heartbeat()`, `get_worker_status()`.
   - Add `set_active_job()`, `clear_active_job()`.
   - Add `check_rate_limit()`.
2. `services/api/mark_api/deps.py`:
   - Wrap `current_user()` and `_session_authorized()` with `cache_session()`.
3. `services/api/mark_api/routers/auth.py`:
   - Invalidate session in Redis upon logout and password/account changes.
4. `services/api/mark_api/routers/admin.py`:
   - Invalidate user session cache when account is locked/unlocked.
5. `services/worker/main.py`:
   - Send Redis heartbeat every 10 seconds.
   - Set/clear `mark:job:active:{elr_no}` during execution.
6. `web/src/hooks/useEvents.ts` & `Dashboard.tsx`:
   - Listen to `job_progress` and `worker_status` events.

---

## 3. User Review Checkpoints

- [ ] **Gate 1: Session Security & Invalidation Approval**: Confirm that caching user sessions in Redis with 15-minute sliding TTL and instant invalidation on logout complies with internal security rules.
- [ ] **Gate 2: Unit & Integration Test Verification**: Verify that all 519+ tests pass locally with session cache mocks and fallback scenarios.
- [ ] **Gate 3: Load Test Verification under High Concurrency**: Validate with `scripts/test_load_performance.py --concurrency 10 --requests 100` that 100% of requests return HTTP 200 without PostgreSQL connection pool exhaustion.

---

## 4. Phased Implementation Steps

### Phase 1: User Session Caching & Invalidation (P0)
- [ ] **Step 1.1**: In `mark_engine/adapters/redis_cache.py`, implement:
  ```python
  def cache_session(client, token_hash: str, ttl: int, load_fn: Callable):
      # Checks 'mark:session:{token_hash}', falls back to load_fn, stores non-sensitive profile
  def invalidate_session(client, token_hash: str):
      # Deletes 'mark:session:{token_hash}'
  ```
- [ ] **Step 1.2**: In `services/api/mark_api/deps.py`:
  - Update `current_user()` to resolve user from Redis session cache before querying PostgreSQL `repo.session_user()`.
  - Ensure sliding expiration: refresh Redis key TTL on active requests.
- [ ] **Step 1.3**: In `services/api/mark_api/routers/auth.py`:
  - Hook `invalidate_session()` into `/api/auth/logout`.
- [ ] **Step 1.4**: In `services/api/mark_api/routers/admin.py`:
  - Invalidate session cache when user account is modified or unlocked.
- [ ] **Step 1.5**: Write unit tests in `tests/unit/test_redis_session.py`:
  - Test session cache hit, cache miss, expiration, logout invalidation, and PostgreSQL fallback when Redis is offline.
- **Verification**: `python -m pytest tests/unit/test_redis_session.py -v` (All pass).

---

### Phase 2: Worker Heartbeat & Real-Time Job Tracking (P1)
- [ ] **Step 2.1**: In `mark_engine/adapters/redis_cache.py`, implement `record_worker_heartbeat()` and `get_worker_heartbeat()`.
- [ ] **Step 2.2**: In `services/worker/main.py`:
  - In the main worker polling loop, record a heartbeat timestamp to `mark:worker:heartbeat` with TTL 30s.
  - When picking up a job: `set_active_job(elr_no, run_id, worker_info)` (TTL 120s).
  - When completing/failing a job: `clear_active_job(elr_no)`.
- [ ] **Step 2.3**: In `services/api/mark_api/routers/mark.py` and `app.py`:
  - Expose worker health in `/api/ready` or `/api/worker/status`.
  - Add `active_job` indicator in ELR detail response.
- **Verification**: Trigger a manual recheck on `ADI2607006` and verify `mark:job:active:ADI2607006` exists in Redis during processing and is deleted on completion.

---

### Phase 3: Expanded Pub/Sub & Real-Time Event Streaming (P1)
- [ ] **Step 3.1**: In `services/worker/results.py` and `scans.py`:
  - Standardize event publication over Redis channel `mark_events` with typed payloads:
    * `scan_started`: `{ "type": "scan_started", "scan_id": ..., "total": ... }`
    * `job_progress`: `{ "type": "job_progress", "completed": ..., "total": ..., "current_elr": ... }`
    * `revision_saved`: `{ "type": "revision_saved", "run_id": ..., "elr_no": ..., "status": ... }`
- [ ] **Step 3.2**: In `web/src/hooks/useEvents.ts`:
  - Expand WebSocket event handler to dispatch typed notifications and refresh relevant queries.
- [ ] **Step 3.3**: In `web/src/pages/Dashboard.tsx`:
  - Display live notification toast or badge when a job completes without requiring page refresh.
- **Verification**: Verify WebSocket receives `job_progress` and `revision_saved` JSON events within <50ms of worker completion.

---

### Phase 4: User-Level Sliding Window Rate Limiting (P2)
- [ ] **Step 4.1**: In `mark_engine/adapters/redis_cache.py`, implement `check_rate_limit(client, user_id, action, limit, window_sec)` using Redis sorted sets (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`).
- [ ] **Step 4.2**: Apply rate limiter decorator on sensitive write endpoints:
  - `/api/scans/trigger`: max 5 requests / minute per user.
  - `/api/recheck`: max 10 requests / minute per user.
- [ ] **Step 4.3**: Add unit tests in `tests/unit/test_redis_ratelimit.py`.
- **Verification**: Simulate 6 rapid scan triggers for a user; verify the 6th returns HTTP 429 with informative error while other users are unaffected.

---

### Phase 5: Verification, Benchmarking & Deployment
- [ ] **Step 5.1**: Run full unit test suite:
  ```bash
  python -m pytest tests -q --ignore=tests/regression
  ```
  *(Expected: 525+ passed, 0 failed)*
- [ ] **Step 5.2**: Run database read-only integrity check:
  ```bash
  python scripts/check_trial_readonly.py --run 19
  ```
  *(Expected: 8/8 PASS)*
- [ ] **Step 5.3**: Run live production E2E suite:
  ```bash
  python scripts/test_e2e_suite.py --url http://10.153.90.17:8093
  ```
  *(Expected: 7/7 PASS)*
- [ ] **Step 5.4**: Run High-Concurrency Load Benchmark:
  ```bash
  python scripts/test_load_performance.py --concurrency 10 --requests 100 --url http://10.153.90.17:8093
  ```
  *(Expected: Zero errors, 100% HTTP 200, P95 < 50ms for session-cached queries)*
- [ ] **Step 5.5**: Git commit, push to `phase2/trial`, and verify Jenkins Build #15 on `10.153.90.17`.

---

## 5. Potential Risks & Mitigation

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Redis Outage / Unreachable** | Medium | **Strict Graceful Fallback**: Every Redis call (`cache_session`, `worker_heartbeat`, `check_rate_limit`) is wrapped in try/except with 0.3s timeout. If Redis is down, authentication seamlessly falls back to PostgreSQL `repo.session_user()` with zero 500 errors. |
| **Stale Session After Revocation** | High | Immediate invalidation: `/api/auth/logout` explicitly deletes the Redis key. Admin account lock/unlock calls `invalidate_user_sessions()`. |
| **Redis Memory Exhaustion** | Medium | Hard cap `--maxmemory 256mb` and `--maxmemory-policy allkeys-lru`. Every key has an explicit TTL (sessions max 15m, heartbeats max 30s). Total memory consumption for 1,000 sessions is <1MB. |
| **Cross-Host Clock Drift** | Low | All TTLs and timestamps use UTC (`datetime.now(timezone.utc)`) and Redis relative expiration (`EXPIRE` in seconds) rather than absolute timestamps. |
