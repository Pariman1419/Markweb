# Redis integration

Redis is an optional cache and notification layer. PostgreSQL advisory and
queue row locks remain the source of truth even if a Redis lock is unavailable,
contended, expired, or evicted. The service is internal to the Compose network;
its configured data limit is 256 MiB with allkeys-lru and snapshotting disabled.

Oracle layouts use a 24-hour cache. Dashboard results use a 30-second cache;
revision, review, and approval events invalidate the corresponding dashboard key.
Dashboard cache fills are guarded against concurrent invalidation by a per-entry
token and an atomic Redis script. Redis failures bypass the cache and use the
databases directly. Redis Pub/Sub is best effort: the browser refetches state on
reconnection to account for messages lost while disconnected.

The browser connects to `/api/ws/events`: the existing HttpOnly session cookie
is scoped to `/api`, so it is not sent by browsers to `/ws/events`. Both routes
are registered by the API, and the browser-facing route checks the session and
same-origin header. Sessions are periodically revalidated without renewing them.
