# Implementation Plan: Redis Integration for Mark Web

> **Context**: Mark Web is fully deployed in production on `10.153.90.17:8093`. Currently, background job tracking uses PostgreSQL (`FOR UPDATE SKIP LOCKED`), and rate limiting uses NGINX. 
> **Objective**: Integrate Redis (v7 Alpine) as a high-performance in-memory layer for:
> 1. **Metadata & Layout Spec Caching**: Caching Oracle layout specifications (`MARK_ID`) to reduce Oracle 10g round-trips by >80%.
> 2. **Dashboard Query Caching**: Caching heavy aggregation queries (`dashboard_cards`) with smart TTL.
> 3. **Real-time Pub/Sub & WebSocket Engine**: Streaming live inspection completions and notifications to the React frontend without polling.
> 4. **Distributed Locks**: Fast atomic locks for scan triggers and work items.

---

## 1. Overview & Objectives

- **Target Host**: Production server `10.153.90.17` (Docker Compose stack).
- **Resource Footprint**: Lightweight `redis:7-alpine` container capped at **256MB RAM** with `volatile-lru` / `allkeys-lru` eviction.
- **Expected Technical Impact**:
  - Sub-millisecond response for cached Oracle layouts and dashboard statistics.
  - Reduced load on Oracle 10g (`10.151.26.3`) and PostgreSQL (`10.151.28.2`).
  - True real-time UI updates via WebSocket (`/ws/events`) backed by Redis Pub/Sub.

---

## 2. Proposed Architecture & Design Changes

```
                           ┌───────────────────────────────┐
                           │      React Web Frontend       │
                           └───────────────┬───────────────┘
                                           │ WebSocket / REST
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Docker Compose on .17                            │
│                                                                             │
│    ┌──────────────┐         Pub/Sub         ┌──────────────────────────┐    │
│    │ mark-web-api │ ◄─────────────────────► │        mark-redis        │    │
│    └──────┬───────┘     Cache & Locks       │     (redis:7-alpine)     │    │
│           │                                 │      Port 6379 (int)     │    │
│           │                                 └─────────────▲────────────┘    │
│           │                                               │                 │
│           ▼                                               │ Pub / Cache     │
│    ┌──────────────┐                                       │                 │
│    │   worker     │ ──────────────────────────────────────┘                 │
│    └──────────────┘                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
          │                                           │
          ▼                                           ▼
  PostgreSQL (Persistent DB)                  Oracle 10g (Master Specs)
```

### Key Components to Add/Modify:
1. `docker-compose.yml`:
   - Add `redis` service (`redis:7-alpine`, internal network only, restart: unless-stopped).
   - Configure memory cap: `--maxmemory 256mb --maxmemory-policy allkeys-lru`.
2. Python Dependency:
   - Add `redis>=5.0.0` to `pyproject.toml`.
3. Cache & Lock Modules:
   - `services/api/mark_api/redis_client.py`: Async/Sync Redis connection pool with automatic fallback if Redis is unavailable.
   - `mark_engine/adapters/redis_cache.py`: Cache decorators for Oracle layouts and dashboard stats.
4. WebSocket & Pub/Sub:
   - `services/api/mark_api/routers/ws.py`: FastAPI WebSocket endpoint connected to Redis Pub/Sub channel `mark_events`.
   - Frontend `web/src/hooks/useEvents.ts`: Auto-reconnecting WebSocket listener for instant card & queue updates.

---

## 3. User Review Checkpoints

- [ ] **Gate 1: Schema & Compose Review**: Approve the Redis service configuration and memory limits in `docker-compose.yml`.
- [ ] **Gate 2: Dev Environment Validation**: Verify all unit tests (503+ tests) pass locally on `10.151.97.18` with Redis fallback enabled.
- [ ] **Gate 3: Production Deployment on .17**: Deploy via Jenkins Build #13 on `10.153.90.17` and verify port 8093 health.

---

## 4. Phased Implementation Steps

### Phase 1: Infrastructure & Dependencies Setup
- [ ] **Step 1.1**: Add `redis:7-alpine` to `docker-compose.yml`:
  ```yaml
    redis:
      image: redis:7-alpine
      restart: unless-stopped
      command: ["redis-server", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru", "--save", ""]
      expose:
        - "6379"
      logging:
        driver: json-file
        options:
          max-size: "10m"
          max-file: "5"
  ```
- [ ] **Step 1.2**: Wire `REDIS_URL=redis://redis:6379/0` into `api` and `worker` environments.
- [ ] **Step 1.3**: Add `redis>=5.0.0` to `pyproject.toml` dependencies.
- **Verification**: `docker compose up -d redis && docker compose exec redis redis-cli ping` returns `PONG`.

---

### Phase 2: Redis Client & Fallback Architecture
- [ ] **Step 2.1**: Implement `services/api/mark_api/redis_client.py`:
  - Singleton Redis client supporting graceful degradation (if Redis is down, calls bypass to PostgreSQL/Oracle without throwing 500 errors).
- [ ] **Step 2.2**: Implement Layout Caching in `services/worker/main.py`:
  - Key: `mark:layout:{top_mark_id}` (TTL: 86,400s / 24 hours).
  - Before querying Oracle `fetch_layout()`, check Redis. On cache hit, parse directly.
- [ ] **Step 2.3**: Implement Dashboard Cards Caching in `services/api/mark_api/routers/mark.py`:
  - Key: `mark:dashboard:{run_id}` (TTL: 30 seconds).
  - Invalidate key immediately whenever a worker commits a new revision or review.
- **Verification**: Unit tests `tests/unit/test_redis_cache.py` verifying cache hit, cache miss, and graceful fallback when Redis is offline.

---

### Phase 3: Real-Time Pub/Sub & WebSocket Integration
- [ ] **Step 3.1**: Update `services/worker/results.py`:
  - In `notify_for()`, publish JSON event to Redis channel `mark_events` alongside PostgreSQL `NOTIFY`.
- [ ] **Step 3.2**: Implement WebSocket router `/ws/events` in `services/api/mark_api/routers/ws.py`:
  - Listens to Redis Pub/Sub and broadcasts to all active browser connections.
- [ ] **Step 3.3**: Update NGINX configuration (`web/nginx.conf`) to proxy `/ws/` with HTTP/1.1 `Upgrade` headers.
- [ ] **Step 3.4**: Connect React frontend:
  - Add WebSocket hook in React to automatically update Dashboard badges and live ELR preview when a recheck completes.
- **Verification**: Trigger manual recheck on `ADI2607006` and observe WebSocket event received within <100ms.

---

### Phase 4: Production Deployment & Verification
- [ ] **Step 4.1**: Commit changes to `phase2/trial` and push to GitHub.
- [ ] **Step 4.2**: Trigger Jenkins Build on `10.153.90.17`:
  - Verify Preflight, Python tests, Web build, and Docker build (`api`, `web`, `worker`, `redis`).
  - Verify Smoke test (`http://localhost:8093/api/ready`) passes.
  - Verify Real-DB check passes (8/8).
- [ ] **Step 4.3**: End-to-end verification on `10.153.90.17:8093`:
  - Check Redis memory usage: `docker exec mark-web-redis-1 redis-cli info memory`.
  - Verify live WebSocket connection in browser developer tools (Network -> WS).
  - Confirm `check_trial_readonly.py --run 19` remains 8/8 OK.

---

## 5. Potential Risks & Mitigation

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Redis Memory Exhaustion** | Medium | Enforce strict `--maxmemory 256mb` and `--maxmemory-policy allkeys-lru` in command args. Disable disk persistence (`--save ""`) since data is purely cache/events. |
| **Redis Service Outage** | Low | Design all cache and pub/sub helpers with **Graceful Degradation**: if Redis throws `ConnectionError`, fall back silently to direct DB query. |
| **Cache Invalidation Drift** | Low | Keep TTLs short (30s for stats, 24h for layouts) and explicitly invalidate `mark:dashboard:{run_id}` upon revision write. |
| **Port Conflicts** | None | Redis port `6379` is only exposed internally on Docker network `mark-web_default`; not bound to host IP. |
