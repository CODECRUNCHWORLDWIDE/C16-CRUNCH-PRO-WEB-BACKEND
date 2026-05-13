"""
Exercise 2 — A stdlib HTTP server (no frameworks).

Goal: Write a working HTTP server in <50 lines using only `http.server`
from the Python standard library. No Flask, no Django, no FastAPI.

Estimated time: 30 minutes.

Acceptance criteria:
- `python exercise-02-stdlib-server.py` starts a server on port 8000.
- `curl http://localhost:8000/` returns 200 and an HTML body.
- `curl http://localhost:8000/json` returns 200 and a JSON body with
  the correct Content-Type.
- `curl -X POST http://localhost:8000/echo -d "hello"` returns 200 and
  echoes the body back.
- Anything else returns 404.

What you learn:
- The shape of `BaseHTTPRequestHandler` — `do_GET`, `do_POST`, etc.
- Writing status lines and headers correctly.
- Reading the request body via `self.rfile`.
- Why this is fine for learning and bad for production (single-threaded,
  no auth, no security headers, no graceful shutdown).

TO COMPLETE: Fill in the `do_GET` and `do_POST` methods below. Do not look
at the hint until you've tried at least 15 minutes.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8000


class Handler(BaseHTTPRequestHandler):
    # ----- GET routes -----
    def do_GET(self) -> None:
        if self.path == "/":
            # TODO: respond 200 with an HTML page that says "Hello, stdlib"
            #       set Content-Type to text/html; charset=utf-8
            raise NotImplementedError("Implement GET /")

        if self.path == "/json":
            # TODO: respond 200 with the JSON body {"hello": "stdlib"}
            #       set Content-Type to application/json
            raise NotImplementedError("Implement GET /json")

        self._not_found()

    # ----- POST routes -----
    def do_POST(self) -> None:
        if self.path == "/echo":
            # TODO: read the request body using self.rfile and Content-Length
            #       respond 200 with the body echoed back
            raise NotImplementedError("Implement POST /echo")

        self._not_found()

    # ----- helpers -----
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._send(404, b"Not Found\n", "text/plain")

    # Silence the default log to make the output cleaner.
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def main() -> None:
    server = HTTPServer(("", PORT), Handler)
    print(f"Listening on http://localhost:{PORT} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        server.server_close()


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# HINT (read only if stuck for >15 min)
# -----------------------------------------------------------------------------
#
# do_GET for "/":
#     body = b"<!doctype html><h1>Hello, stdlib</h1>"
#     self._send(200, body, "text/html; charset=utf-8")
#
# do_GET for "/json":
#     body = json.dumps({"hello": "stdlib"}).encode("utf-8")
#     self._send(200, body, "application/json")
#
# do_POST for "/echo":
#     length = int(self.headers.get("Content-Length") or 0)
#     body = self.rfile.read(length)
#     self._send(200, body, "application/octet-stream")
#
# -----------------------------------------------------------------------------
# WHY THIS IS NOT PRODUCTION
# -----------------------------------------------------------------------------
# - Single-threaded. One slow request blocks every other client.
# - No HTTPS, no CSRF, no rate limiting, no security headers.
# - No logging, no metrics, no graceful shutdown.
# - `BaseHTTPRequestHandler` is documented as "not recommended for production"
#   by Python's own docs.
# Use this for learning. For real apps, run Django/FastAPI behind
# Gunicorn or Uvicorn behind nginx.
