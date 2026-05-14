"""
Exercise 1 — WebSocket: echo, then broadcast via a connection manager.

Time:   ~2 hours.
Goal:   Stand up a FastAPI WebSocket endpoint that (a) echoes inbound text
        back to the same client, (b) registers connections in a process-local
        ConnectionManager so a separate HTTP POST can broadcast to every
        connected client. Confirm the RFC 6455 handshake on the wire with
        curl; observe disconnects in the server logs; write three asserts
        with FastAPI's TestClient.websocket_connect.

Run:
    fastapi dev exercise-01-websocket-echo-and-manager.py
    # or:
    uvicorn exercise-01-websocket-echo-and-manager:app --reload --port 8000

Try (in another terminal):
    # WebSocket client via wscat (npm install -g wscat) or websocat
    wscat -c ws://localhost:8000/ws/echo
    > hello
    < echo: hello

    # HTTP broadcast (in a third terminal)
    curl -X POST http://localhost:8000/broadcast \
         -H "Content-Type: application/json" \
         -d '{"text": "everyone hear this"}'
    # Every wscat session connected to /ws/feed sees the message.

Cited:
    - https://datatracker.ietf.org/doc/html/rfc6455
    - https://fastapi.tiangolo.com/advanced/websockets/
    - https://www.starlette.io/websockets/
    - https://fastapi.tiangolo.com/advanced/testing-websockets/

The TASK comments below mark prompts you should fill in or answer in
SOLUTIONS.md. The skeleton compiles as-is.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from pydantic import BaseModel, Field

logger = logging.getLogger("ws_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Part A — App and shared state
# ---------------------------------------------------------------------------

app = FastAPI(
    title="C16 W8 Exercise 1 — WebSocket echo and broadcast",
    description=(
        "Two WebSocket endpoints (echo, feed) plus one HTTP broadcast route. "
        "The point is to observe the RFC 6455 handshake and the process-local "
        "ConnectionManager pattern."
    ),
    version="0.1.0",
)


class BroadcastBody(BaseModel):
    """The payload accepted on POST /broadcast."""

    text: str = Field(min_length=1, max_length=1000, description="The message to fan out.")


# ---------------------------------------------------------------------------
# Part B — The ConnectionManager
# ---------------------------------------------------------------------------
#
# A process-local registry of accepted WebSocket connections. The limit
# (single worker only) motivates Challenge 1's Redis Pub/Sub broadcaster.


class ConnectionManager:
    """A process-local set of accepted WebSocket connections."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Accept the handshake and register the connection."""
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("connected; total=%d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove the connection from the registry. Idempotent."""
        async with self._lock:
            self._connections.discard(ws)
        logger.info("disconnected; total=%d", len(self._connections))

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """Send the payload as JSON to every connected client.

        Returns the count of successful sends. Failed sends are swallowed;
        the corresponding client will be removed when its receive loop
        notices the disconnect.
        """
        async with self._lock:
            connections = list(self._connections)
        sent = 0
        for ws in connections:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:  # noqa: BLE001 — slow client or half-open TCP
                logger.warning("send failed; will be reaped on next receive")
        return sent

    @property
    def count(self) -> int:
        """The current connection count. Read without the lock — fine for a gauge."""
        return len(self._connections)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Part C — Endpoint 1: /ws/echo
# ---------------------------------------------------------------------------
#
# A trivial echo. The point is the handshake and the receive/send loop.


@app.websocket("/ws/echo")
async def ws_echo(ws: WebSocket) -> None:
    """Echo every inbound text frame back, prefixed with 'echo: '.

    TASK 1: With the server running, open a second terminal and run:
        curl --include --no-buffer \\
             --header 'Connection: Upgrade' \\
             --header 'Upgrade: websocket' \\
             --header 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \\
             --header 'Sec-WebSocket-Version: 13' \\
             http://localhost:8000/ws/echo

    Record the response status code and the value of Sec-WebSocket-Accept
    in SOLUTIONS.md. Compute the expected Sec-WebSocket-Accept manually
    with `openssl dgst -sha1 -binary | base64` and verify they match.
    """
    await ws.accept()
    try:
        while True:
            text = await ws.receive_text()
            await ws.send_text(f"echo: {text}")
    except WebSocketDisconnect as exc:
        logger.info("echo disconnect; code=%s reason=%r", exc.code, exc.reason)


# ---------------------------------------------------------------------------
# Part D — Endpoint 2: /ws/feed (broadcast subscriber)
# ---------------------------------------------------------------------------


@app.websocket("/ws/feed")
async def ws_feed(ws: WebSocket) -> None:
    """Register this connection on the manager; relay broadcasts.

    TASK 2: Open three terminals running `wscat -c ws://localhost:8000/ws/feed`.
    In a fourth terminal, POST to /broadcast. All three wscat sessions should
    print the same JSON message. Record the count of clients reached
    (from the POST response) in SOLUTIONS.md.
    """
    await manager.connect(ws)
    try:
        while True:
            # We do not expect inbound traffic, but await receive so the
            # disconnect propagates as WebSocketDisconnect rather than
            # leaving us hanging on a dead TCP connection.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Part E — Endpoint 3: POST /broadcast
# ---------------------------------------------------------------------------


@app.post("/broadcast")
async def http_broadcast(body: BroadcastBody) -> dict[str, int]:
    """Fan the payload out to every WS client connected on /ws/feed.

    TASK 3: What status code does FastAPI return when the body has an empty
    'text'? Cite the RFC. Note it in SOLUTIONS.md.
    """
    count = await manager.broadcast({"event": "broadcast", "text": body.text})
    return {"sent": count, "total": manager.count}


# ---------------------------------------------------------------------------
# Part F — Endpoint 4: /ws/auth (auth via Authorization header)
# ---------------------------------------------------------------------------


def _is_valid_token(token: str) -> bool:
    """A toy validator. Week 9 will issue real tokens."""
    return token == "demo-token"


@app.websocket("/ws/auth")
async def ws_auth_required(ws: WebSocket) -> None:
    """Reject the handshake with close code 1008 on missing/invalid token.

    TASK 4: Connect from a browser console with:
        new WebSocket("ws://localhost:8000/ws/auth")
    Observe the connection failing. Then connect with wscat passing the
    header:
        wscat -c ws://localhost:8000/ws/auth -H "Authorization: Bearer demo-token"
    The connection succeeds. Why does the browser have no way to pass
    a custom Authorization header here? Answer in SOLUTIONS.md.
    """
    auth = ws.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not _is_valid_token(token):
        # Close codes 1008 = policy violation. RFC 6455 §7.4.
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    await ws.accept()
    try:
        await ws.send_json({"event": "welcome", "user": "demo"})
        while True:
            text = await ws.receive_text()
            await ws.send_text(f"auth-echo: {text}")
    except WebSocketDisconnect:
        return


# ---------------------------------------------------------------------------
# Part G — A health check, for completeness
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str | int]:
    return {"status": "ok", "ws_count": manager.count}


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
#
# Run `python3 -m py_compile exercise-01-websocket-echo-and-manager.py`.
# It must succeed silently. The lint check that follows is optional but
# recommended:
#
#   ruff check exercise-01-websocket-echo-and-manager.py
#
# TASK 5: Write a pytest-asyncio integration test in tests/test_exercise_01.py
# that uses fastapi.testclient.TestClient.websocket_connect to:
#   - connect to /ws/echo, send "hi", assert the echo is "echo: hi"
#   - connect twice to /ws/feed, POST to /broadcast, assert both clients
#     received the broadcast message
#   - confirm that /ws/auth without the Authorization header is rejected
# Document the test in SOLUTIONS.md.
