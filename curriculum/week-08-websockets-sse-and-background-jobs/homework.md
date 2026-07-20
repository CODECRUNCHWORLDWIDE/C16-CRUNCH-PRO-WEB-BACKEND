# Week 8 — Homework

Six problems, approximately **6 hours total**. The point of homework is to practise the patterns; the point of the mini-project is to integrate them. Save each answer under `c16-week-08/homework/` in your `crunchreader-api` repo (or a new `crunchexports` repo if you prefer to keep this week's work separate).

---

## Problem 1 — The WebSocket handshake, by hand (45 min)

Write `homework/01_handshake.py` containing a small script that, given a `Sec-WebSocket-Key` value, computes the corresponding `Sec-WebSocket-Accept` value per RFC 6455 §4.2.2. The function signature:

```python
def compute_accept(key: str) -> str:
    """Return the Sec-WebSocket-Accept value for the given client key."""
```

Cite the line in RFC 6455 that defines the algorithm. Use Python's `hashlib.sha1` and `base64.b64encode`.

Then write `homework/01_handshake.md` answering:

1. What is the value of the constant GUID concatenated to the client key, and where is it specified?
2. Is the GUID a secret? If not, what is its purpose?
3. Verify your function on the example from RFC 6455 §1.3: a client key of `dGhlIHNhbXBsZSBub25jZQ==` should produce an accept value of `s3pPLMBiTxaQ9kYGzzhZRbK+xOo=`. Paste the test output.

Reference: <https://datatracker.ietf.org/doc/html/rfc6455#section-4.2.2>.

---

## Problem 2 — SSE frame parser (45 min)

Write `homework/02_sse_parse.py` containing a function:

```python
def parse_sse(text: str) -> list[dict[str, str]]:
    """Parse a text/event-stream body into a list of event dicts.

    Each dict has keys 'event', 'data', 'id' (any of which may be absent).
    Comment lines (starting with ':') are ignored.
    Events are separated by blank lines.
    """
```

The parsing rules are in the [HTML living standard SSE section](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream). The relevant subset:

- A line is everything up to a `\n` (the spec also accepts `\r` and `\r\n`; you may handle only `\n`).
- A field is `name: value`. The space after the colon is optional and consumed if present.
- Multiple `data:` lines in one event concatenate with `\n` as the separator.
- A blank line terminates the event and dispatches it.

In `homework/02_sse_parse.md`:

1. Run the parser on the output of `curl --no-buffer http://localhost:8000/sse/counter?limit=3` (from Exercise 2). Paste the parsed event list.
2. Explain why the spec requires the *blank line* and not just the next field-name to terminate an event. (Hint: events span multiple lines; an empty `data:` line is still a `data:` line.)
3. Show one event in the parsed output where the `data:` field's value is JSON. Why does the SSE spec say nothing about the format of `data:`? (Hint: layer separation.)

---

## Problem 3 — A WebSocket-vs-SSE design memo (45 min)

You are designing the live-collaboration features for a Google-Docs-like editor. Three features need a real-time channel from the server to the connected clients:

- **F1 — Document changes.** When user A types, every other user with the document open sees the change within ~200 ms.
- **F2 — Presence.** When a user joins or leaves, every other user sees an avatar appear/disappear.
- **F3 — Notifications.** When the document's owner shares it with a new user, the owner's other open tabs show a notification within a few seconds.

In `homework/03_design_memo.md`, write one paragraph per feature (~150 words each) defending a choice of either WebSocket or SSE. Each defence must cite at least one specific property from the decision matrix in Lecture 2 §5.

Then write a short concluding paragraph naming the deployment architecture: how many WebSocket endpoints? How many SSE endpoints? Where does each one fit in the FastAPI routing?

There is no single right answer to this prompt. The grader looks for *coherent* reasoning. An answer that says "WebSocket for F1 because it is bidirectional; SSE for F3 because it is one-way and infrequent" is acceptable. An answer that says "WebSocket for everything because it is more general" is not — generalisation is not free.

---

## Problem 4 — ARQ idempotency (45 min)

Write `homework/04_idempotent_task.py` containing an ARQ task that does the following:

- Accepts an `order_id: str` argument.
- Performs a side effect that *must not happen twice* — appending one line to `homework/orders.log`.
- Is safe to retry: a second invocation with the same `order_id` is a no-op, not a duplicate line.

Use a Redis dedupe key with `SET ... NX EX` to guard the side effect. The task signature:

```python
async def append_order(ctx: dict[str, Any], order_id: str) -> dict[str, str]: ...
```

Then write `homework/04_idempotent_task.md` answering:

1. What TTL did you set on the dedupe key, and why? (Lecture 3 §3.4 has the answer: the worst plausible runtime of the task.)
2. Why is `SET key value NX EX <ttl>` the right primitive for this, and not `SETNX` followed by `EXPIRE`? (Hint: atomicity.)
3. What happens if your task crashes after the side effect but before deleting the dedupe key? Is that a problem? Why not?

Reference: <https://redis.io/commands/set/>.

---

## Problem 5 — Read the ARQ source (45 min)

Open `arq/worker.py` in the ARQ source: <https://github.com/python-arq/arq/blob/main/arq/worker.py>.

Find the `Worker.async_run` method (or the equivalent main loop). In `homework/05_arq_source.md`:

1. Quote the line(s) where the worker pops a job off the Redis queue.
2. Quote the line where the worker calls the user-provided function.
3. Find where retries are scheduled. Explain the backoff formula in your own words.
4. Find where the result is written to Redis. What key format does ARQ use?
5. ARQ is about 1 500 lines. Estimate the proportion that is "core loop" versus "tuning knobs and observability". One sentence.

The goal is not to memorise the source but to demystify it. After 45 minutes you should be able to say: "ARQ is a Redis `BLPOP` loop plus retry/result handling; everything else is configuration."

---

## Problem 6 — Compare three job queues for one real workload (1.5 h)

Pick a workload from your own life or work. Examples:

- "Render a PDF report from a Postgres query, then email it as an attachment."
- "Resize an uploaded image into five thumbnails and store them on S3."
- "Run an LLM call against a user's text input and store the result, with a retry on rate-limit errors."

In `homework/06_queue_compare.md`, write a structured comparison:

For your chosen workload, sketch an implementation in three job runners:

1. ARQ — show the `WorkerSettings` class and the task function.
2. Celery — show the `Celery(...)` app instance and the `@app.task` function.
3. RQ — show the worker invocation and the enqueue call.

For each, evaluate on five dimensions:

1. Lines of code for the task + worker config.
2. How retries are configured (decorator argument? settings class? per-call?).
3. How the result is stored and retrieved.
4. How the worker is launched in a Docker container.
5. The honest production failure mode you would most worry about.

Conclude with a paragraph naming the runner you would actually deploy and the condition under which you would switch. The defence must be specific to *your* workload, not a generic "ARQ is async".

References:

- ARQ: <https://arq-docs.helpmanual.io/>
- Celery: <https://docs.celeryq.dev/en/stable/userguide/tasks.html>
- RQ: <https://python-rq.org/>

---

## Submission

All six problems under `c16-week-08/homework/` in your repository. One commit with the message:

```text
c16-w8 homework: handshake, SSE parser, design memo, idempotency, ARQ source, queue compare
```

The grader looks for: every prompt answered, every code file `py_compile`-clean, every citation linked.

## Rubric (30 points)

| Problem | Points | Pass bar                                                                 |
|--------:|-------:|--------------------------------------------------------------------------|
| 1       | 4      | Function returns the RFC 6455 example accept value bit-perfectly         |
| 2       | 5      | Parser handles multi-line `data:`, blank-line termination, comment lines |
| 3       | 5      | Each feature defended with a property cited from Lecture 2's matrix      |
| 4       | 5      | `SET NX EX` used atomically; TTL justified; failure-mode answered        |
| 5       | 4      | All five source-reading prompts answered with line references            |
| 6       | 7      | All three runners shown; five-dimension comparison; defensible choice    |

Late submissions: 10% per day, capped at 50%. Code that does not `py_compile` is graded as if the file did not exist; fix and resubmit.
