# C16 · Crunch Pro Web Backend — Syllabus

**12 weeks · ~36 hrs/week full-time (or scaled) · C1 graduate (+ basic Flask) → senior Python backend engineer**

The production-Python-on-the-web track: Django, FastAPI, PostgreSQL, Redis, and the operations that turn a toy app into a deployed service.

---

**Prerequisites:** C1 weeks 1–11 — functions, classes, decorators, generators; pip + venv; a basic Flask app (C1 Week 9); SQL at the SELECT/INSERT/JOIN level (C1 Week 10); pytest with a fixture (C1 Week 11); Git/GitHub branches and PRs. If you can't do one of those, do that week of C1 first — C16 will not re-teach them.

**Assessment is honor-based.** No proctor, no grades. Each week you certify your own completion: the exercises run, the quiz is answered, the mini-project ships to a public GitHub repo. The capstone is the only thing an employer sees — grade yourself the way a hiring manager would.

---

## Program at a glance

| Phase | Weeks | Outcome |
|-------|-------|---------|
| **Phase 1 — HTTP & Django basics** | 01 – 03 | A working Django blog with auth, admin, tests |
| **Phase 2 — Data & the ORM** | 04 – 06 | PostgreSQL, migrations, complex queries, background jobs |
| **Phase 3 — FastAPI & real-time** | 07 – 09 | A typed async API with WebSockets/SSE and a Redis cache |
| **Phase 4 — Scale & production** | 10 – 12 | Search, multi-tenancy, deployed capstone |

---

## Weekly breakdown

**Week 1 — HTTP and the Modern Python Web.** What HTTP actually is, the request/response cycle in detail, WSGI vs ASGI, the 2026 framework landscape. A Django project set up from scratch with no `startproject` magic.

- *Mini-project:* A no-magic Django project — every file written by hand, the URL/view round-trip explained byte by byte.

**Week 2 — Django Models, the ORM, and the Admin.** Models, fields, relationships (FK / M2M / OneToOne), migrations, querysets, `ModelAdmin` customization. The N+1 problem on day one.

- *Mini-project:* `crunchwriter` v0 — authors, articles, categories. Admin-only.

**Week 3 — Views, Templates, Forms, and Auth.** Function vs class-based views, Django templates, model forms, sessions and the auth system, `LoginRequiredMixin`, CSRF, `{% url %}` / reverse.

- *Mini-project:* `crunchwriter` v1 — public article reader plus an author dashboard with login.

**Week 4 — PostgreSQL for Application Developers.** `psql`, real schema design, indexes (B-tree, GIN, partial, expression), `EXPLAIN ANALYZE`, transactions and isolation, JSONB, full-text search. When ORMs lie to you.

- *Mini-project:* Take a slow query in `crunchwriter`, profile it, fix it with an index, measure the win.

**Week 5 — Django ORM Deep Dive.** `select_related` vs `prefetch_related`, `annotate`/`aggregate`, `Subquery`/`OuterRef`, `Q` and `F` expressions, custom managers, bulk operations, raw-SQL escape hatches.

- *Mini-project:* The `crunchwriter` analytics dashboard — top authors by views, articles by category, one query each.

**Week 6 — Migrations, Background Jobs, and Caching.** Real-world migrations (non-null columns, renames, data migrations, reversibility), Redis caching, Celery (broker, worker, beat), async views vs Celery.

- *Mini-project:* Image upload plus async thumbnail generation in `crunchwriter`.

**Week 7 — FastAPI Fundamentals.** Why FastAPI, Pydantic v2 in depth, path/query/body parameters, request validation, response models, dependency injection, the free OpenAPI doc.

- *Mini-project:* `crunchreader-api` — a standalone FastAPI service that reads from the same database `crunchwriter` writes to.

**Week 8 — WebSockets, Server-Sent Events, and Background Jobs.** Three answers to "this work is longer than one HTTP round-trip": a WebSocket endpoint with a Redis Pub/Sub broadcaster, an SSE progress stream, and an ARQ Redis-backed job runner. Choosing between them on the merits.

- *Mini-project:* `crunchexports` — a FastAPI app that exports CSV reports via ARQ and streams progress over SSE.

**Week 9 — Caching with Redis.** Data types and patterns, eviction and invalidation, the cache stampede (request-coalescing and probabilistic early expiration), sessions. Measure-then-fix discipline.

- *Mini-project:* `crunchcache` — a measure-then-fix cache layer on the Week 7 service, with a `BENCHMARK.md` of the numbers.

**Week 10 — Search: Postgres FTS, OpenSearch, Meilisearch.** Three backends, one query, three latency curves and precision-at-5 numbers, one defended pick behind a single `/search` endpoint with a backend flag.

- *Mini-project:* `crunchsearch` — three search backends behind one `/search` endpoint, with a `BENCHMARK.md`.

**Week 11 — Multi-tenancy.** Shared schema, schema-per-tenant, database-per-tenant, and PostgreSQL row-level security. Per-tenant Redis namespacing, per-tenant rate limits, tenant onboarding.

- *Mini-project:* `crunchtenant` — a multi-tenant article service with RLS, per-tenant rate limits, and a tenant-onboarding endpoint.

**Week 12 — Capstone: a production-grade multi-tenant backend.** Every prior layer wired together, deployed to a free tier (Fly.io / Render / Railway) behind HTTPS, with monitoring, a runbook, and a deliberately induced production incident.

- *Capstone:* `MultiTenantContentHub` — a deployed multi-tenant content backend with RLS, background-indexed search, live WebSocket updates, a tenant-namespaced Redis cache, a zero-downtime migration, and an `incident-001` post-mortem proving the rollback runbook.

---

## Weekly load

| Component | hrs/wk |
|-----------|------:|
| Lectures / readings | 6 |
| Hands-on exercises | 8 |
| Coding challenges | 4 |
| Quiz + readings | 3 |
| Homework | 6 |
| Mini-project | 7 |
| Self-study & review | 2 |
| **Total** | **36** |

Scalable down: half-time ≈ 21 hrs/wk over 20 weeks, part-time ≈ 13.5 hrs/wk over ~9 months.

---

## Outcome

A single deployable, tested service on your GitHub — Django admin, server-rendered pages, a typed async FastAPI read layer, PostgreSQL full-text search, a Redis cache, background jobs, multi-tenant isolation, Docker + CI, HTTPS, and a `/metrics` endpoint. The thing you point employers at.

---

## License

GPL-3.0.
