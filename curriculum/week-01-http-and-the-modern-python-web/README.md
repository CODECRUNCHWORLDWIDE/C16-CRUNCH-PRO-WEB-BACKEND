# Week 1 — HTTP and the Modern Python Web

Welcome to **C16 · Crunch Pro Web Backend**. Week 1 is unusual: we will not build "a real app" yet. Instead, we go down to the protocol level so that everything you do for the rest of the course rests on a real understanding of *what is actually happening on the wire*.

Most Python web courses skip this. They start with `pip install django`, scaffold a project, and you walk away three months later able to ship CRUD apps without ever knowing what an HTTP request is. We are not doing that. By Friday of Week 1 you will be able to **read a raw HTTP request and write a valid raw HTTP response with your bare hands**, and only then will we let a framework do it for us.

The other half of the week is a tour of the modern Python web framework landscape — Django, FastAPI, Flask, Starlette, Litestar, and the WSGI/ASGI standards that hold them all together. You will leave the week with a clear, defensible answer to "which framework should I use for X?".

## Learning objectives

By the end of this week, you will be able to:

- **Explain** what HTTP is, what verbs and status codes mean, and how a request/response cycle works at the byte level.
- **Speak** raw HTTP/1.1 over a TCP socket with `nc` (netcat), `telnet`, or `curl --verbose` — without a browser.
- **Distinguish** between the **WSGI** and **ASGI** standards, and explain which frameworks implement each.
- **Compare** the four mainstream Python web frameworks (Django, FastAPI, Flask, Starlette) on five dimensions: speed, batteries-included-ness, async support, learning curve, and ecosystem maturity.
- **Choose** the right framework for a given problem statement, with a reason you can defend in code review.
- **Build** a minimal HTTP server from scratch using only the standard library (`http.server`), and a second minimal HTTP server using a WSGI-compliant function with `wsgiref` — and explain why the second is more portable.
- **Set up** a clean, reproducible Django project from a blank folder, by hand, *without* using `django-admin startproject`, so you understand exactly what every generated file does.

## Prerequisites

This week assumes you have completed **C1 weeks 1–11**, or have equivalent skill. Specifically:

- Comfortable in a terminal (you can `cd`, `ls`, run `python` and `pip`).
- You've written a working Flask app at least once.
- You can read and write basic SQL `SELECT` statements.
- You understand functions, classes, decorators, and exceptions in Python.

If any of those are shaky, **stop** and review the relevant C1 week before continuing. C16 will not slow down.

## Topics covered

- The 30-second history of the web: ARPANET → TCP/IP → HTTP/0.9 → HTTP/1.1 → HTTP/2 → HTTP/3
- The TCP/IP layer cake — what each layer is responsible for
- HTTP/1.1 request anatomy: method, path, version, headers, blank line, body
- HTTP/1.1 response anatomy: version, status code, reason phrase, headers, body
- The most-used HTTP methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`
- Status code families: `1xx`, `2xx`, `3xx`, `4xx`, `5xx` — and the ones you'll use daily
- Content negotiation: `Accept`, `Content-Type`, `Content-Length`, `Transfer-Encoding`
- Cookies and the `Set-Cookie` header — the seed of session auth (we go deep on auth in Week 9)
- Connection management: `Keep-Alive`, pipelining (and why nobody actually pipelines)
- Idempotency, safety, cacheability — what these terms actually mean
- WSGI (PEP 3333) — the synchronous Python web standard, born 2010
- ASGI — the async-capable successor, born 2018
- The framework landscape in 2026: Django, FastAPI, Flask, Starlette, Litestar, Sanic, Tornado
- When server-rendered HTML beats a JSON API (and vice versa)
- How to set up Python projects properly with `uv` or `pip-tools` (we use both)
- Building a Django project by hand, one file at a time, no scaffolding

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target. Some sections will click in 20 minutes, others will need 3 hours. That's fine.

| Day       | Focus                                         | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-----------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | History, TCP/IP, raw HTTP                     |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Methods, status codes, headers, cookies       |    2h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0h      |     6.5h    |
| Wednesday | WSGI vs ASGI, hand-built servers              |    2h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     7h      |
| Thursday  | Framework landscape, when to use what         |    0h    |    1h     |     1h     |    0.5h   |   1h     |     2h       |    0.5h    |     6h      |
| Friday    | Build a Django project by hand                |    0h    |    1.5h   |     1h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Saturday  | Mini-project deep work                        |    0h    |    0h     |     0h     |    0h     |   1h     |     3h       |    0h      |     4h      |
| Sunday    | Quiz, review, polish                          |    0h    |    0h     |     0h     |    0.5h   |   0h     |     0h       |    0h      |     0.5h    |
| **Total** |                                               | **6h**   | **8h**    | **4h**     | **3h**    | **6h**   | **7h**       | **2h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated readings, RFCs, free books, official docs |
| [lecture-notes/01-the-anatomy-of-http.md](./lecture-notes/01-the-anatomy-of-http.md) | What HTTP actually is, byte by byte |
| [lecture-notes/02-wsgi-asgi-and-the-python-web-standards.md](./lecture-notes/02-wsgi-asgi-and-the-python-web-standards.md) | Why two standards exist, and what they mean for your code |
| [lecture-notes/03-the-python-web-framework-landscape.md](./lecture-notes/03-the-python-web-framework-landscape.md) | Django, FastAPI, Flask, and friends — when to use which |
| [exercises/README.md](./exercises/README.md) | Index of short coding exercises |
| [exercises/exercise-01-raw-http-with-netcat.md](./exercises/exercise-01-raw-http-with-netcat.md) | Make an HTTP request by typing it character by character |
| [exercises/exercise-02-stdlib-server.py](./exercises/exercise-02-stdlib-server.py) | A 30-line HTTP server using only `http.server` |
| [exercises/exercise-03-wsgi-hello-world.py](./exercises/exercise-03-wsgi-hello-world.py) | A WSGI app served by `wsgiref` |
| [challenges/README.md](./challenges/README.md) | Index of weekly challenges |
| [challenges/challenge-01-status-code-explorer.md](./challenges/challenge-01-status-code-explorer.md) | Trigger every status code family from a single test harness |
| [challenges/challenge-02-write-the-response.md](./challenges/challenge-02-write-the-response.md) | Hand-write a valid HTTP/1.1 response and verify it with `curl` |
| [quiz.md](./quiz.md) | 10 multiple-choice questions |
| [homework.md](./homework.md) | Six practice problems for the week |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "Django By Hand" mini-project |
| [mini-project/starter/](./mini-project/) | Starter files for the mini-project |

## Stretch goals

If you finish early and want to push further, try any of the following:

- Read RFC 9110 (HTTP Semantics) end-to-end — the new normative reference: <https://www.rfc-editor.org/rfc/rfc9110>
- Implement a toy HTTP/1.1 server in <100 lines of pure Python that handles `Keep-Alive`.
- Read PEP 3333 (WSGI) and write a 1-page summary in your own words: <https://peps.python.org/pep-3333/>
- Skim the ASGI spec and identify three things WSGI cannot do: <https://asgi.readthedocs.io/en/latest/>
- Browse the Django source for `django.core.handlers.wsgi.WSGIHandler` and trace one request from raw bytes to the view function.

## Up next

Continue to [Week 2 — Django Models, the ORM, and the Admin](../week-02-django-models-orm-admin/) once you've pushed your mini-project to GitHub.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
