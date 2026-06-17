"""
Exercise 3 — A WSGI app from scratch, served by `wsgiref`.

Goal: Write a real WSGI application (callable with `environ` and
`start_response`) without any framework, then serve it on a real HTTP
server using the stdlib's `wsgiref.simple_server`.

Estimated time: 25 minutes.

Why this matters: Every Django and Flask app is, at its core, a WSGI
callable. Once you've written one by hand, the framework's internals
stop feeling magical.

Acceptance criteria:
- `python exercise-03-wsgi-hello-world.py` starts a server on port 8001.
- GET /              -> 200 text/html with "<h1>Hello, WSGI</h1>"
- GET /json          -> 200 application/json with {"hello": "wsgi"}
- GET /headers       -> 200 text/plain listing every request header
- POST /echo (body)  -> 200 echoing the body back
- Anything else      -> 404
- Code passes `python -m py_compile exercise-03-wsgi-hello-world.py`.

TO COMPLETE: Fill in the function body below. Do not look at the hint
unless stuck for >15 minutes.
"""

from __future__ import annotations

import json
from typing import Iterable
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

PORT = 8001


# WSGI types:
# - environ:        dict-like of CGI-style variables plus wsgi.* keys
# - start_response: callable(status: str, headers: list[tuple[str, str]])
# - return:         iterable of bytes


def app(
    environ: dict,
    start_response,
) -> Iterable[bytes]:
    method = environ["REQUEST_METHOD"]
    path = environ["PATH_INFO"]

    # ----- GET / -----
    if method == "GET" and path == "/":
        # TODO
        raise NotImplementedError("Implement GET /")

    # ----- GET /json -----
    if method == "GET" and path == "/json":
        # TODO: return application/json
        raise NotImplementedError("Implement GET /json")

    # ----- GET /headers -----
    if method == "GET" and path == "/headers":
        # TODO: walk environ for keys starting with "HTTP_" and return them
        #       as a plain-text listing. Strip the "HTTP_" prefix and replace
        #       underscores with dashes to recover the original header name.
        raise NotImplementedError("Implement GET /headers")

    # ----- POST /echo -----
    if method == "POST" and path == "/echo":
        # TODO: read environ["CONTENT_LENGTH"] bytes from environ["wsgi.input"]
        #       and return them back.
        raise NotImplementedError("Implement POST /echo")

    # ----- 404 fallback -----
    return _send(start_response, "404 Not Found", b"Not Found\n", "text/plain")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _send(
    start_response,
    status: str,
    body: bytes,
    content_type: str,
) -> list[bytes]:
    """Tiny shortcut: call start_response and return the body."""
    start_response(
        status,
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def main() -> None:
    server = make_server("", PORT, app)
    print(f"WSGI app listening on http://localhost:{PORT} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        server.server_close()


if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# HINT (read only if stuck >15 min)
# -----------------------------------------------------------------------------
#
# GET /:
#     return _send(start_response, "200 OK",
#                  b"<h1>Hello, WSGI</h1>",
#                  "text/html; charset=utf-8")
#
# GET /json:
#     body = json.dumps({"hello": "wsgi"}).encode("utf-8")
#     return _send(start_response, "200 OK", body, "application/json")
#
# GET /headers:
#     lines = []
#     for k, v in environ.items():
#         if k.startswith("HTTP_"):
#             name = k[5:].replace("_", "-").title()
#             lines.append(f"{name}: {v}")
#     body = "\n".join(lines).encode("utf-8") + b"\n"
#     return _send(start_response, "200 OK", body, "text/plain; charset=utf-8")
#
# POST /echo:
#     length = int(environ.get("CONTENT_LENGTH") or 0)
#     body = environ["wsgi.input"].read(length)
#     return _send(start_response, "200 OK", body, "application/octet-stream")
#
# -----------------------------------------------------------------------------
# DEEPER: try replacing `make_server` with Gunicorn:
#
#   pip install gunicorn
#   gunicorn exercise-03-wsgi-hello-world:app -w 4 --bind 0.0.0.0:8001
#
# Same app, different server. That's WSGI's whole point.
# -----------------------------------------------------------------------------
