# Challenge 2 — Hand-Written HTTP Response

**Time estimate:** ~75 minutes.

## Problem statement

Most exercises this week had you write *requests*. This one flips it: you'll write a complete, byte-correct HTTP/1.1 *response* by hand, save it as a file, and use a small TCP server to play it back to real HTTP clients (`curl`, your browser).

Your goal: produce a `response.http` file whose contents are a valid HTTP/1.1 response with a non-trivial HTML body. When clients connect to your replay server, they receive your file verbatim and render it correctly.

## What you'll build

Two files:

1. **`response.http`** — a hand-written HTTP/1.1 response. Headers in plain text. CRLF line endings. Body is HTML.
2. **`replay_server.py`** — a small Python script (~30 lines) that opens a TCP socket on port 8002, accepts a connection, reads the request (so the client doesn't get confused), then writes your `response.http` byte-for-byte back to the socket.

## Acceptance criteria

- [ ] `response.http` exists, has CRLF line endings, and begins with `HTTP/1.1 200 OK\r\n`.
- [ ] `response.http` includes at minimum these headers: `Content-Type`, `Content-Length`, `Date`, `Connection: close`.
- [ ] The body is valid HTML — open it in a browser as a `.html` file and it renders.
- [ ] `Content-Length` exactly matches the byte count of your body. Off-by-one will hang the browser.
- [ ] `replay_server.py` listens on port 8002, accepts a connection, and writes the file's bytes back.
- [ ] `curl http://localhost:8002/` returns your HTML and `curl -v` shows the correct status line and headers.
- [ ] Visiting `http://localhost:8002/` in a real browser renders the HTML.
- [ ] You handle the `Content-Length` correctly using `os.path.getsize` or `len(file_bytes)` — not by counting characters in your head.

## Stretch

- Make `replay_server.py` configurable with `argparse`: `--file response.http --port 8002`.
- Add a `404.http` file. If the request line starts with anything other than `GET /` or `GET / `, send `404.http` instead.
- Use a `--keep-alive` flag that, when set, removes `Connection: close` and keeps the socket open for multiple requests.

## Hints

<details>
<summary>How to write CRLF line endings in Python</summary>

When you write a file in Python, by default it uses your OS's native line ending. To force CRLF you must:

- Open the file with `open(path, "wb")` and write `bytes` with `\r\n` explicitly, OR
- Open with `open(path, "w", newline="")` and write strings — Python won't translate.

Easiest: type your `response.http` in VS Code, then in the bottom right click "LF" → "CRLF" and save.

</details>

<details>
<summary>The skeleton of a valid response</summary>

```
HTTP/1.1 200 OK\r\n
Content-Type: text/html; charset=utf-8\r\n
Content-Length: 119\r\n
Date: Mon, 13 May 2026 14:00:00 GMT\r\n
Connection: close\r\n
\r\n
<!doctype html>
<html><head><title>Hand-written</title></head>
<body><h1>Hello!</h1><p>I was typed by hand.</p></body>
</html>
```

Notes:
- The `\r\n` at the end of `Connection: close` and again before `<!doctype` are both required.
- `Content-Length` must equal the exact byte count of the body (from `<!doctype` to the end). Use `wc -c` to verify.
- `Date` should be in [RFC 7231 §7.1.1.1](https://www.rfc-editor.org/rfc/rfc7231) format. The server isn't strict about this in 2026, but get used to it.

</details>

<details>
<summary>The replay server skeleton</summary>

```python
import socket
from pathlib import Path

PORT = 8002
RESPONSE_FILE = Path("response.http")

def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("", PORT))
        srv.listen()
        print(f"Listening on http://localhost:{PORT}")
        body = RESPONSE_FILE.read_bytes()
        while True:
            conn, addr = srv.accept()
            with conn:
                # Read (and discard) the request so the client doesn't get
                # confused. 4096 bytes is enough for almost any GET.
                conn.recv(4096)
                conn.sendall(body)

if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>If `curl` says "transfer closed with X bytes remaining to read"</summary>

Your `Content-Length` is too high. `curl` is waiting for bytes that don't exist. Recount the body, set it correctly.

</details>

<details>
<summary>If the browser hangs forever</summary>

Same problem, opposite direction: missing `Connection: close` and possibly missing the blank line between headers and body.

</details>

## Submission

Commit `response.http`, `replay_server.py`, and a `README.md` explaining how to run it to your Week 1 GitHub repo under `challenges/challenge-02/`.

## Why this matters

You will spend the rest of your career letting frameworks generate responses for you. Doing it once by hand, knowing that you typed every byte, demystifies HTTP forever. The next time a response is "weird" — wrong status, wrong header, mangled body — you'll have the mental model to debug it.
