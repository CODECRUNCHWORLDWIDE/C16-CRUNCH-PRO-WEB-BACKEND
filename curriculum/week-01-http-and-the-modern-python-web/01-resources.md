# Week 1 — Resources

Every resource on this page is **free** and **publicly accessible**. No paywalled books, no proprietary PDFs. If a link breaks, please open an issue.

## Required reading (work it into your week)

- **MDN — An overview of HTTP** — start here, the most accessible intro:
  <https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview>
- **MDN — HTTP request methods**:
  <https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods>
- **MDN — HTTP response status codes**:
  <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status>
- **PEP 3333 — Python Web Server Gateway Interface (WSGI)**:
  <https://peps.python.org/pep-3333/>
- **ASGI Specification v2.x**:
  <https://asgi.readthedocs.io/en/latest/specs/main.html>

## The RFCs (skim, don't memorize)

The IETF documents are the *normative* reference. Modern HTTP is RFC 9110 (semantics), 9111 (caching), 9112 (HTTP/1.1), 9113 (HTTP/2), 9114 (HTTP/3). Skim 9110 and 9112 this week.

- **RFC 9110 — HTTP Semantics**: <https://www.rfc-editor.org/rfc/rfc9110>
- **RFC 9112 — HTTP/1.1 (wire format)**: <https://www.rfc-editor.org/rfc/rfc9112>
- **RFC 9111 — Caching**: <https://www.rfc-editor.org/rfc/rfc9111>
- **RFC 6265 — Cookies**: <https://www.rfc-editor.org/rfc/rfc6265>

You will never read all of these in detail. But the first time someone in a code review writes "per RFC 9110 §9.3.4, a `PUT` is idempotent" you will know what they mean.

## Official Python docs

- **`http.server`** — the standard-library HTTP server:
  <https://docs.python.org/3/library/http.server.html>
- **`http.client`** — making HTTP requests from the stdlib:
  <https://docs.python.org/3/library/http.client.html>
- **`wsgiref`** — a reference WSGI implementation in the stdlib:
  <https://docs.python.org/3/library/wsgiref.html>
- **`socket`** — TCP sockets in Python:
  <https://docs.python.org/3/library/socket.html>
- **`urllib.parse`** — URL parsing:
  <https://docs.python.org/3/library/urllib.parse.html>

## Framework documentation (you'll bounce between these all course)

- **Django 5.x docs**: <https://docs.djangoproject.com/en/stable/>
- **Django Tutorial (the official one — it's good)**: <https://docs.djangoproject.com/en/stable/intro/tutorial01/>
- **FastAPI**: <https://fastapi.tiangolo.com/>
- **Starlette** (FastAPI's foundation): <https://www.starlette.io/>
- **Flask**: <https://flask.palletsprojects.com/>
- **Litestar**: <https://docs.litestar.dev/>
- **Sanic**: <https://sanic.dev/>
- **Tornado**: <https://www.tornadoweb.org/>

## Free books (chapter-level, not whole books)

- **High Performance Browser Networking** by Ilya Grigorik — free online edition; chapters 9–12 are the HTTP deep dive:
  <https://hpbn.co/>
- **The Python Tutorial** (official) — refresh if needed:
  <https://docs.python.org/3/tutorial/>
- **Real Python — "Python Web Server"** primer:
  <https://realpython.com/python-web-applications/>
  *Note:* Real Python is free for the article you'll need this week. Some content is paywalled; we only reference the free articles.

## Open courseware

- **CS50W — Harvard's web programming course** (free, full video):
  <https://cs50.harvard.edu/web/>
- **MIT 6.046 — Algorithms** (background, not direct): <https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/>

## Tools you'll use this week

- **curl** — installed by default on macOS/Linux; available for Windows. Cheatsheet:
  <https://curl.se/docs/manual.html>
- **nc / netcat** — `nc -l 8000` opens a listening socket; `nc example.com 80` opens a client connection. macOS ships one (a fork). On Linux, `apt install netcat-openbsd`.
- **HTTPie** — friendlier `curl`. Install with `pip install httpie`. Docs:
  <https://httpie.io/docs>
- **VS Code REST Client extension** — write requests in a `.http` file, click "Send Request":
  <https://marketplace.visualstudio.com/items?itemName=humao.rest-client>

## Videos (free, no signup)

- **HTTP Crash Course** — Traversy Media (29 min):
  <https://www.youtube.com/watch?v=iYM2zFP3Zn0>
  *(Or pick any 20–30 minute "HTTP basics" video on YouTube — they're all the same; the protocol hasn't changed.)*
- **Django at a glance** — DjangoCon, various years; the framework overview talks are usually accessible on the [Django YouTube channel](https://www.youtube.com/@djangoproject).

## Open-source projects to read this week

You can learn more from one hour reading other people's code than from three hours of tutorials. Pick one this week and just scroll through the README and the entry-point file:

- **Django** itself — `django/django` on GitHub: <https://github.com/django/django>
- **FastAPI** — `fastapi/fastapi`: <https://github.com/fastapi/fastapi>
- **httpie** — the curl alternative: <https://github.com/httpie/cli>
- **uvicorn** — the ASGI server: <https://github.com/encode/uvicorn>

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **HTTP** | The plain-text protocol that web browsers and servers use to talk |
| **TCP** | The reliable, ordered transport layer that HTTP rides on |
| **TLS** | Encryption + identity layer that turns HTTP into HTTPS |
| **WSGI** | The Python standard for synchronous web apps (Django, Flask use it) |
| **ASGI** | The Python standard for async-capable web apps (FastAPI, Django 5 async use it) |
| **gunicorn** | A WSGI server; serves your WSGI app in production |
| **uvicorn** | An ASGI server; serves your ASGI app in production |
| **nginx** | A reverse proxy that sits in front of your app server |
| **idempotent** | Same effect whether called once or many times (`PUT`, `DELETE`) |
| **safe (HTTP)** | No state changes on the server (`GET`, `HEAD`) |
| **CORS** | Cross-Origin Resource Sharing — browser-enforced rules for which domains can call your API |
| **MIME type** | The `Content-Type` value, e.g. `application/json` or `text/html` |

---

*If a link 404s, please [open an issue](https://github.com/CODECRUNCHWORLDWIDE) so we can replace it.*
