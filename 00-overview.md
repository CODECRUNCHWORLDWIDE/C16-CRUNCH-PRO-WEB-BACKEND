# C16 · Crunch Pro — Python Web Backend

> A 12-week open-source course on building production-grade Python web backends with **Django** and **FastAPI** — from your first view to a deployed, observable, multi-tenant service.

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Built in the open](https://img.shields.io/badge/built-in%20the%20open-B98F3E.svg)](https://github.com/CODECRUNCHWORLDWIDE)

This is the senior-engineer track for Python on the web. It assumes you have completed **C1 · Code Crunch Convos** (or have equivalent Python proficiency) and the equivalent of Week 9 of C1 (basic Flask). C16 takes you from "I made a Flask app" to "I run a Python web service in production."

---

## What you will be able to do at the end of 12 weeks

- Design and ship a **Django application** with auth, admin, templates, forms, the ORM, migrations, signals, the test client, and a production-grade settings layout.
- Design and ship a **FastAPI service** with Pydantic models, dependency injection, async views, background tasks, OpenAPI docs, and JWT auth.
- Operate **PostgreSQL** comfortably: schema design, indexes, transactions, JSONB, full-text search, EXPLAIN ANALYZE.
- Write **integration tests** that hit a real database in <1s and run in CI on every PR.
- Set up **Redis** as a cache, queue broker (Celery / Arq), and rate limiter.
- Deploy with **Docker + Gunicorn/Uvicorn**, behind **Nginx**, with **HTTPS**, **structured logging**, and **Prometheus metrics**.
- Pick the right tool: when to use Django, when to use FastAPI, and when to use them together.
- Read and contribute to real open-source Django/FastAPI codebases without intimidation.

---

## Prerequisites

You should have completed, or be able to do everything in, **C1 · Code Crunch Convos** weeks 1–11. Specifically you need:

- Comfortable with **functions, classes, exceptions, decorators, generators**.
- Used **pip + venv** or a similar dependency manager.
- Written a **basic Flask app** (Week 9 of C1) — `@app.route`, templates, forms.
- Worked with **SQL** at the SELECT/INSERT/JOIN level (Week 10 of C1).
- Written **pytest** unit tests with at least one fixture (Week 11 of C1).
- Used **Git/GitHub** to push branches and open PRs.

If you cannot do any one of those, do that week of C1 first. C16 will not slow down to re-teach them.

---

## What this course is NOT

- **Not a frontend course.** We render server-side HTML in Django (Jinja2 in FastAPI) and serve JSON APIs. For React/Vue/Svelte, see C8.
- **Not a tutorial graveyard.** Every week builds on the previous week's project. By Week 12 you have a single deployable, tested service — not 12 disconnected toy apps.
- **Not a framework comparison.** We use Django *and* FastAPI together because in real life you do too. Django ships the admin, the ORM, and the conventions; FastAPI ships the async APIs and the typed contracts. We teach you when each is right.
- **Not vendor-locked.** No AWS-specific lessons. No Heroku buttons. Everything runs on a $5/month VPS, locally on Docker Compose, or free-tier on Fly.io/Railway. Pick what you like.

---

## Weekly breakdown

| Phase | Weeks | Outcome |
|-------|-------|---------|
| **Phase 1 — HTTP & Django basics** | 01 – 03 | Ship a working Django blog with auth, admin, tests |
| **Phase 2 — Data & the ORM** | 04 – 06 | PostgreSQL, migrations, complex queries, performance |
| **Phase 3 — FastAPI & APIs** | 07 – 09 | A typed, async JSON API consumed by your Django app |
| **Phase 4 — Production** | 10 – 12 | Docker, CI/CD, monitoring, security hardening, capstone |

See [`curriculum/SYLLABUS.md`](curriculum/SYLLABUS.md) for the full week-by-week plan.

---

## How to start

1. Confirm you meet the prerequisites above.
2. Open [`curriculum/SYLLABUS.md`](curriculum/SYLLABUS.md) and read it cover to cover (20 min).
3. Go to [`curriculum/week-01-http-and-the-modern-python-web/`](curriculum/week-01-http-and-the-modern-python-web/) and start.
4. Each week is self-contained: a README orients you, lectures explain the concepts, exercises drill the muscles, challenges stretch you, the quiz checks comprehension, the homework hits real-world scenarios, and the mini-project lets you ship.
5. Push your work to a public GitHub repo. Future-you (and future employers) will thank you.

---

## Weekly cadence

Same as all Code Crunch tracks (~36 hrs/week full-time, scalable down to 9 hrs/week part-time):

| Component | Full-time | Half-time | Part-time |
|-----------|----------:|----------:|----------:|
| Lectures / readings | 6h | 6h | 6h |
| Hands-on exercises | 8h | 4h | 2h |
| Coding challenges | 4h | 2h | 1h |
| Quiz + readings | 3h | 1.5h | 1h |
| Homework problems | 6h | 3h | 1.5h |
| Mini-project | 7h | 3.5h | 1.5h |
| Self-study & review | 2h | 1h | 0.5h |
| **Total / week** | **36h** | **21h** | **13.5h** |
| **Length** | 12 weeks | 20 weeks | ~9 months |

---

## What you ship

By the end of Week 12, your GitHub will contain a single deployable application: **`crunchwriter`** — a multi-author publishing platform with:

- Django admin for editorial staff
- Server-rendered marketing/article pages
- FastAPI for the public read API and webhooks
- PostgreSQL with full-text search
- Redis cache + Celery background image processing
- Stripe-style webhook handling
- JWT auth for the API, session auth for the admin
- Dockerfile + docker-compose + GitHub Actions CI
- Deployed to a $5/mo VPS or free Fly.io tier
- 80%+ test coverage with a fast integration test suite
- Prometheus `/metrics` endpoint and structured JSON logs

That's the thing you point employers at.

---

## Tools we use

Every tool is **free** and **open-source**. No proprietary IDEs, no paid SaaS dependencies for the course itself.

| Tool | Role | Why |
|------|------|-----|
| **Python 3.11+** | Language | Modern speedups, better error messages |
| **Django 5.x** | Full-stack framework | Admin, ORM, templates, batteries-included |
| **FastAPI** | Async API framework | Pydantic-typed, OpenAPI for free |
| **PostgreSQL 16** | Database | Real SQL, real concurrency, JSONB |
| **Redis 7** | Cache / queue | Industry standard |
| **Celery** | Background jobs (Django side) | The canonical Python job runner |
| **Arq** | Background jobs (FastAPI side) | Async-native, Redis-backed |
| **Pytest** | Testing | The standard |
| **Ruff** | Linter / formatter | Fast, replaces black + flake8 |
| **mypy** | Type checking | Catches bugs before runtime |
| **Docker / Compose** | Local dev + deployment | One-command spin-up |
| **GitHub Actions** | CI/CD | Free for public repos |
| **Fly.io / Railway / VPS** | Hosting | Cheap, real, your choice |
| **VS Code** | Editor | Free, great Python support |

---

## License

GPL-3.0. See [LICENSE](LICENSE). You may fork, adapt, teach, and remix. Improvements back to the project are welcomed via PR.

---

## Next track

After C16, the natural progressions are:

- **C15 · Crunch DevOps** — take the service you built and learn to operate it at scale (Kubernetes, observability, IaC).
- **C17 · Crunch Pro Python Advanced** — go deep on async internals, performance, C extensions, and the parts of Python that separate senior from staff.

---

*C16 is part of the Code Crunch open-source curriculum.* [Master catalog ↗](../MASTER-CURRICULUM.md)


---

<!-- CCWW:AUTO-INDEX:START — generated by scripts/restructure_course_repos.py; edit ABOVE this marker -->

## Course at a glance

| Section | Count |
| --- | --- |
| Curriculum entries | 13 |
| Projects | 0 |
| Past sessions | 0 |

## Curriculum

- [SYLLABUS](curriculum/SYLLABUS.md)
- [week 01 http and the modern python web](./curriculum/week-01-http-and-the-modern-python-web/00-overview.md)
- [week 02 django models orm admin](./curriculum/week-02-django-models-orm-admin/00-overview.md)
- [week 03 views templates forms auth](./curriculum/week-03-views-templates-forms-auth/00-overview.md)
- [week 04 postgresql for app developers](./curriculum/week-04-postgresql-for-app-developers/00-overview.md)
- [week 05 django orm deep dive](./curriculum/week-05-django-orm-deep-dive/00-overview.md)
- [week 06 migrations jobs caching](./curriculum/week-06-migrations-jobs-caching/00-overview.md)
- [week 07 fastapi fundamentals](./curriculum/week-07-fastapi-fundamentals/00-overview.md)
- [week 08 websockets sse and background jobs](./curriculum/week-08-websockets-sse-and-background-jobs/00-overview.md)
- [week 09 caching with redis](./curriculum/week-09-caching-with-redis/00-overview.md)
- [week 10 search fts opensearch meilisearch](./curriculum/week-10-search-fts-opensearch-meilisearch/00-overview.md)
- [week 11 multi tenancy](./curriculum/week-11-multi-tenancy/00-overview.md)
- [week 12 capstone production backend](./curriculum/week-12-capstone-production-backend/00-overview.md)

## In this course

- **Community** — [community/](community/)
- **Curriculum** — [curriculum/](curriculum/)
- **Projects** — [projects/](projects/)
- **Resources** — [resources/](resources/)
- **Past sessions** — [past-sessions/](past-sessions/)

<!-- CCWW:AUTO-INDEX:END -->
