"""Authenticated WebSocket notifications."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from mark_api.auth import can, login_state, session_status
from mark_api.deps import get_cookie_name, get_repo, session_for_token
from mark_api.redis_client import get_async_redis

router = APIRouter()
logger = logging.getLogger(__name__)
EVENT_CHANNEL = "mark_events"
REVALIDATE_INTERVAL = 60


def _session_authorized(socket: WebSocket) -> bool:
    token = socket.cookies.get(get_cookie_name("mark_session")) or socket.cookies.get("mark_session")
    if not token:
        return False
    repo_factory = socket.app.dependency_overrides.get(get_repo, get_repo)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = session_for_token(repo_factory(), digest, sliding=False)
    now = datetime.now(timezone.utc)
    return bool(result and session_status(result[0], now) == "ok"
                and login_state(result[1], now) == "OK"
                and can(result[1].get("role", ""), "read"))


@router.websocket("/ws/events")
async def events(socket: WebSocket):
    origin = socket.headers.get("origin", "")
    host = socket.headers.get("x-forwarded-host") or socket.headers.get("host", "")
    if not origin or urlsplit(origin).netloc.lower() != host.lower():
        await socket.close(code=1008)
        return
    try:
        if not await asyncio.to_thread(_session_authorized, socket):
            await socket.close(code=1008)
            return
    except Exception:
        await socket.close(code=1008)
        return
    client = get_async_redis()
    if client is None:
        await socket.close(code=1013)
        return
    pubsub = client.pubsub()
    receiver = None
    try:
        await pubsub.subscribe(EVENT_CHANNEL)
        await socket.accept()
        receiver = asyncio.create_task(socket.receive())
        # Recheck expiry and permissions without extending the idle session.
        deadline = asyncio.get_running_loop().time() + REVALIDATE_INTERVAL
        while True:
            if receiver.done():
                if receiver.result().get("type") == "websocket.disconnect":
                    break
                receiver = asyncio.create_task(socket.receive())
            if asyncio.get_running_loop().time() >= deadline:
                if not await asyncio.to_thread(_session_authorized, socket):
                    await socket.close(code=1008)
                    break
                deadline = asyncio.get_running_loop().time() + REVALIDATE_INTERVAL
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if message and message.get("type") == "message":
                await socket.send_json(json.loads(message["data"]))
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("Redis websocket disconnected")
        try:
            await socket.close(code=1013)
        except Exception:
            pass
    finally:
        if receiver is not None:
            receiver.cancel()
        try:
            await pubsub.aclose()
        except Exception:
            pass
