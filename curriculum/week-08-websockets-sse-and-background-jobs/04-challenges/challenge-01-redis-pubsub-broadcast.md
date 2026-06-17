# Challenge 1 — Redis Pub/Sub broadcaster for multi-worker WebSocket fan-out

> **Time:** 2-3 hours. **Goal:** Replace Exercise 1's process-local `ConnectionManager` with a `RedisBroadcaster` that fans out via Redis Pub/Sub, so a message published from any FastAPI worker reaches every connected client on every worker. Prove it works by running two `uvicorn` worker processes and observing that a broadcast from worker A reaches a client on worker B.

This challenge is the production fix to the limitation called out in Lecture 1 §5. The process-local manager works on a single worker; the moment you scale to `uvicorn --workers 4`, three quarters of your audience stops hearing broadcasts. The Redis Pub/Sub broadcaster is the standard pattern, used (with minor variations) by every chat-style service that scales beyond one box.

## What you build

A `RedisBroadcaster` class with the same external API as Exercise 1's `ConnectionManager`:

- `await broadcaster.start()` and `await broadcaster.stop()` — lifecycle hooks, wired into FastAPI's `lifespan`.
- `await broadcaster.connect(ws)` — accept the handshake and register the connection.
- `await broadcaster.disconnect(ws)` — deregister.
- `await broadcaster.publish(payload)` — fan out to **every** connected client across **every** worker.

The internal design uses two Redis primitives:

1. **`PUBLISH channel payload`** — sends the payload to every subscriber of `channel`, on every machine talking to that Redis. The cost is one Redis round-trip per publish.
2. **`SUBSCRIBE channel`** — on each FastAPI worker, opens a long-lived subscription. The broadcaster maintains a background task that reads messages off the subscription and fans them out to the local connection set.

## Required behaviour

- `broadcaster.publish({"text": "hello"})` from any worker results in every connected client (on any worker) receiving the JSON payload.
- A client disconnect on any worker results in that client being removed from the local set; the other workers do not need to know.
- A worker restart re-subscribes to the channel on startup (via `lifespan`) and unsubscribes on shutdown.
- The local `_connections` set is guarded by an `asyncio.Lock`; the lock is held only long enough to add/remove/snapshot.
- The Redis subscription loop runs as a background `asyncio.Task` started in `start()` and cancelled in `stop()`.
- The broadcaster gracefully handles a temporary Redis disconnect: the loop catches the connection error, logs it, sleeps for ~1 second, and re-subscribes.

## Required files

```text
challenge-01-redis-pubsub-broadcast/
├── broadcaster.py          (the RedisBroadcaster class)
├── app.py                  (FastAPI app using the broadcaster)
├── tests/
│   ├── conftest.py         (a fakeredis fixture)
│   └── test_broadcast.py   (an end-to-end test)
└── README.md               (how to run, how to verify the multi-worker proof)
```

## Step-by-step

### Step 1 — The `RedisBroadcaster` class

Start from the skeleton in Lecture 1 §6. The class signature:

```python
class RedisBroadcaster:
    def __init__(self, redis_url: str, channel: str) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def connect(self, ws: WebSocket) -> None: ...
    async def disconnect(self, ws: WebSocket) -> None: ...
    async def publish(self, payload: dict[str, Any]) -> None: ...
```

The internal `_pubsub_loop` (the background task) is the load-bearing piece:

```python
async def _pubsub_loop(self) -> None:
    backoff = 1.0
    while not self._stopped:
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(self._channel)
            backoff = 1.0  # reset on successful (re)subscribe
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                payload = json.loads(message["data"])
                await self._fanout_local(payload)
        except Exception as exc:
            logger.warning("pubsub loop error: %s; reconnecting in %.1fs", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)  # cap at 30s
```

### Step 2 — Wire into FastAPI's lifespan

```python
broadcaster = RedisBroadcaster("redis://localhost:6379/0", "ws-broadcast")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await broadcaster.start()
    try:
        yield
    finally:
        await broadcaster.stop()


app = FastAPI(lifespan=lifespan)
```

### Step 3 — Wire the WebSocket endpoint and the HTTP publish endpoint

The endpoints look exactly like Exercise 1's, except they call `broadcaster.publish` instead of `manager.broadcast`. The asymmetry is a feature: from the application's point of view, the broadcaster behaves identically to the in-process manager. The Redis hop is an implementation detail.

### Step 4 — The multi-worker proof

Open four terminals:

```bash
# Terminal 1
uvicorn app:app --port 8000 --workers 1

# Terminal 2
uvicorn app:app --port 8001 --workers 1

# Terminal 3 — connect to worker 1
wscat -c ws://localhost:8000/ws/feed

# Terminal 4 — connect to worker 2 AND publish on worker 1
wscat -c ws://localhost:8001/ws/feed
# (in a separate sub-shell)
curl -X POST http://localhost:8000/broadcast \
     -H "Content-Type: application/json" \
     -d '{"text": "cross-worker"}'
```

Both wscat sessions print the same JSON. Note the publish hit worker 1's HTTP endpoint, but worker 2's WS client also received the message. Without Redis, only Terminal 3 would have seen it.

### Step 5 — Tests with `fakeredis`

`fakeredis` is a pure-Python Redis emulator that supports Pub/Sub. The test:

```python
import asyncio

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def test_broadcast_reaches_subscriber(fake_redis, monkeypatch) -> None:
    # Patch the broadcaster to use the fake redis instance.
    # ...
    pass
```

The test verifies that `publish` from outside the WS endpoint causes the connected WS client to receive the payload, end-to-end through the (fake) Redis Pub/Sub.

## Acceptance criteria

- [ ] `broadcaster.py` defines `RedisBroadcaster` with the API shape in Step 1.
- [ ] `start()` creates the Redis client, launches the pubsub loop as an `asyncio.Task`, and is idempotent (calling twice has no extra effect).
- [ ] `stop()` cancels the pubsub loop, unsubscribes, and closes the Redis client.
- [ ] `publish(payload)` calls `redis.publish(channel, json.dumps(payload))`.
- [ ] `_fanout_local(payload)` iterates a snapshot of `_connections` outside the lock; failed `send_json` calls are swallowed.
- [ ] A temporary Redis disconnect (kill `redis-server`, wait 2s, restart it) results in the broadcaster reconnecting; no client is dropped; messages published after the reconnect reach all clients.
- [ ] The multi-worker proof from Step 4 succeeds. Document the wscat output in the README.
- [ ] The `fakeredis`-based test passes.
- [ ] All Python files `py_compile` clean.

## Stretch criteria

- [ ] **Per-channel subscriptions.** Add a `subscribe(client, channel)` and `unsubscribe(client, channel)` so different WS clients can subscribe to different channels (e.g. one per article ID). Use Redis `PSUBSCRIBE` with patterns.
- [ ] **Backpressure.** Each WS client gets an `asyncio.Queue(maxsize=64)`. The broadcaster pushes payloads onto the queue; a per-client send task drains the queue. On queue overflow, the client is disconnected with code 1008 ("policy violation — slow consumer").
- [ ] **Sharded Pub/Sub.** For Redis 7+, use `SSUBSCRIBE` / `SPUBLISH` (sharded pub/sub) so the channel can be horizontally scaled across Redis cluster nodes.
- [ ] **`broadcaster` library comparison.** Read the `broadcaster` library source (<https://github.com/encode/broadcaster>) and write one paragraph on the design choices that differ from yours.

## References

- **Redis Pub/Sub**: <https://redis.io/docs/latest/develop/interact/pubsub/>
- **`redis-py` async usage**: <https://redis-py.readthedocs.io/en/stable/advanced_features.html#publish-subscribe>
- **The `broadcaster` library** (~400 lines, the cleanest reference implementation of this pattern): <https://github.com/encode/broadcaster>
- **`fakeredis`**: <https://github.com/cunla/fakeredis-py>
- **Starlette WebSockets**: <https://www.starlette.io/websockets/>
- **FastAPI WebSockets tutorial**: <https://fastapi.tiangolo.com/advanced/websockets/>

## Submission

Push the `challenge-01-redis-pubsub-broadcast/` directory to your `crunchreader-api` repository. The README should explain:

1. How to run the multi-worker proof.
2. What happens during a Redis restart (with timing).
3. The two-paragraph defence of the design choice: why Pub/Sub and not Redis Streams.

The two-paragraph defence is graded. The honest answer involves the trade-off between delivery guarantees (Streams: at-least-once with durable consumer groups; Pub/Sub: fire-and-forget) and operational complexity (Streams: more moving parts; Pub/Sub: one command). For a WebSocket broadcast where missing a message during a 2-second restart is acceptable, Pub/Sub wins on simplicity. If "every message must reach every connected client even across restarts" is a requirement, Streams (or a Kafka-shaped broker) is the right tool.
