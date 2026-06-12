# C16 · Crunch Pro Web Backend — Full Syllabus

**12 weeks · ~432 hours full-time · ~36 hours/week · C1 graduate → senior backend engineer**

This is the **table of contents** for the entire C16 track. Each week links to its own README with detailed objectives, materials, exercises, challenges, quiz, homework, and a mini-project that feeds into the capstone `crunchwriter` application.

---

## Program at a glance

| Phase | Weeks | Outcome |
|-------|-------|---------|
| **Phase 1 — HTTP & Django basics** | 01 – 03 | Ship a working Django blog with auth, admin, tests |
| **Phase 2 — Data & the ORM** | 04 – 06 | PostgreSQL, migrations, complex queries, performance |
| **Phase 3 — FastAPI & APIs** | 07 – 09 | A typed, async JSON API integrated with the Django app |
| **Phase 4 — Production** | 10 – 12 | Docker, CI/CD, monitoring, security, capstone deploy |

---

## How the weekly load adds up (full-time pace)

| Component | hrs/wk |
|-----------|------:|
| Lectures / readings | 6 |
| Hands-on exercises | 8 |
| Coding challenges | 4 |
| Quiz + readings | 3 |
| Homework problems | 6 |
| Mini-project | 7 |
| Self-study & review | 2 |
| **Total** | **36** |

Each week is modular — instructors can adjust pacing without breaking later weeks.

---

## Weekly breakdown

### Phase 1 — HTTP & Django basics

#### [Week 1 — HTTP and the Modern Python Web](week-01-http-and-the-modern-python-web/)

What HTTP actually is. The request/response cycle in painful detail. WSGI vs ASGI. The Python web framework landscape in 2026 (Django, FastAPI, Flask, Starlette, Litestar) and how to choose. You set up a Django project from scratch, no `startproject` magic, and serve your first view.

- **Mini-project:** A no-magic Django project — every file written by hand, the URL/view round-trip explained byte by byte.

#### [Week 2 — Django Models, the ORM, and the Admin](week-02-django-models-orm-admin/)

Models, fields, relationships (FK / M2M / OneToOne), migrations, querysets, `.filter()` vs `.get()` vs `.all()`, the admin site, `ModelAdmin` customization. The N+1 problem on day one.

- **Mini-project:** `crunchwriter` v0 — authors, articles, categories. Admin-only.

#### [Week 3 — Views, Templates, Forms, and Auth](week-03-views-templates-forms-auth/)

Function views vs class-based views. Django templates. Forms (regular and model forms). The session and auth systems. `LoginRequiredMixin`. CSRF protection. The reverse / `{% url %}` pair.

- **Mini-project:** `crunchwriter` v1 — public article reader + author dashboard with login.

---

### Phase 2 — Data & the ORM

#### [Week 4 — PostgreSQL for Application Developers](week-04-postgresql-for-app-developers/)

`psql`, schema design beyond toy examples, indexes (B-tree, GIN, partial, expression), `EXPLAIN ANALYZE`, transactions and isolation levels, JSONB, full-text search. When ORMs lie to you.

- **Mini-project:** Take a slow query in `crunchwriter`, profile it, fix it with an index, measure the win.

#### [Week 5 — Django ORM Deep Dive](week-05-django-orm-deep-dive/)

`select_related` vs `prefetch_related`, `annotate`/`aggregate`, `Subquery`/`OuterRef`, `Q` objects, raw SQL escape hatches, custom managers, `update()` vs `save()`, bulk operations, `F` expressions.

- **Mini-project:** Build the `crunchwriter` analytics dashboard — top authors by views, articles by category, all in 1 query each.

#### [Week 6 — Migrations, Background Jobs, and Caching](week-06-migrations-jobs-caching/)

Real-world migrations: adding non-null columns, renaming, data migrations, reversibility. Redis caching. Celery: broker, worker, beat. When to choose async views vs Celery.

- **Mini-project:** Image upload + async thumbnail generation in `crunchwriter`.

---

### Phase 3 — FastAPI & APIs

#### [Week 7 — FastAPI Fundamentals](week-07-fastapi-fundamentals/)

Why FastAPI. Pydantic v2 in depth. Path / query / body parameters. Request validation. Response models. Dependency injection. The OpenAPI doc you get for free.

- **Mini-project:** A standalone FastAPI service `crunchreader-api` that reads from the same database `crunchwriter` writes to.

#### [Week 8 — Async, Sync, and the GIL](week-08-async-sync-and-the-gil/)

What `async def` actually does. Why `time.sleep` blocks your event loop. `asyncio`, `await`, `gather`, `TaskGroup`. The async database story (`asyncpg`, `databases`, Django 5 async). When async helps and when it just adds complexity.

- **Mini-project:** Add an async webhook receiver to `crunchreader-api` that fans out to 3 downstream services concurrently.

#### [Week 9 — Auth, OAuth, and JWT](week-09-auth-oauth-jwt/)

Session vs token auth. JWT structure, signing, common pitfalls. OAuth 2.0 + OIDC. Implementing login-with-GitHub. Refresh tokens. Storing secrets. Hashing passwords with Argon2.

- **Mini-project:** JWT auth for `crunchreader-api`, GitHub OAuth login for `crunchwriter`, single sign-on between them.

---

### Phase 4 — Production

#### [Week 10 — Docker, Compose, and the 12-Factor App](week-10-docker-compose-12-factor/)

Multi-stage Dockerfiles. `docker-compose` for local dev (web + db + redis + worker). The 12-factor app principles applied. Environment variables, secrets, `.env` files done safely. Healthchecks.

- **Mini-project:** One command (`docker compose up`) brings up the entire `crunchwriter` + `crunchreader-api` stack with seed data.

#### [Week 11 — Testing, CI, and Observability](week-11-testing-ci-observability/)

Pytest in big codebases. Fast integration tests against real Postgres. Factory Boy. CI on GitHub Actions: matrix testing, caching, deploy on merge. Structured logging (JSON, `structlog`). Prometheus metrics. Sentry for errors.

- **Mini-project:** 80% test coverage + CI green + `/metrics` endpoint scraped by Prometheus locally.

#### [Week 12 — Security, Deployment, and Capstone](week-12-security-deployment-capstone/)

OWASP Top 10 for Python web apps. CSRF, XSS, SQL injection, SSRF, IDOR. Rate limiting. Content-Security-Policy. HTTPS with Caddy or Nginx + Let's Encrypt. Deploying to a $5/mo VPS or Fly.io.

- **Capstone:** `crunchwriter` + `crunchreader-api` live on the public internet, on your own domain, behind HTTPS, with monitoring and a README that would make a hiring manager read past the first paragraph.

---

## Skills progression chart

```text
W1  ─ HTTP, WSGI/ASGI, framework landscape
W2  │ Django models, ORM basics, admin
W3  ─ views, templates, forms, auth
W4  ─ PostgreSQL deep
W5  │ Django ORM deep (N+1, joins, aggregation)
W6  ─ migrations, Redis cache, Celery
W7  ─ FastAPI + Pydantic
W8  │ async/await + the GIL
W9  ─ JWT, OAuth, OIDC
W10 ─ Docker + 12-factor
W11 │ testing, CI, observability
W12 ─ security + deploy + CAPSTONE
```

---

## Adapting the syllabus

- **Part-time (18 hrs/wk):** Each "week" becomes 2 weeks. Total = 24 weeks (~6 months).
- **University semester (15 weeks × 9 hrs/wk):** Drop the homework problems and one challenge per week. Use Weeks 1–11; treat Week 12 capstone as a final project.
- **Self-paced (9 hrs/wk evening pace):** ~9 months total. Most working learners finish here.

---

## What this track depends on

C16 directly references and assumes completion of:

- **C1 Weeks 1–7** — Python language, OOP, exceptions
- **C1 Week 9** — Flask basics (we compare/contrast a lot in Week 1)
- **C1 Week 10** — SQL fundamentals
- **C1 Week 11** — pytest fundamentals

If you can't do those, do them first.

---

## What you won't learn (but should later)

To keep this track focused, C16 does not cover:

- **Kubernetes / orchestration at scale** — see [C15 · Crunch DevOps](../../C15-CRUNCH-DEVOPS/).
- **C extensions, performance internals, async deep magic** — see [C17 · Crunch Pro Python Advanced](../../C17-CRUNCH-PRO-PYTHON-ADVANCED/).
- **Frontend frameworks** — see [C8 · Crunch Labs Web Dev](../../C8-CRUNCH-LABS-WEB-DEV/).
- **GraphQL** — Mentioned in Week 7 stretch reading; not required.
- **Microservices, event sourcing, CQRS** — Beyond scope. We build a well-modeled monolith first because that's what most jobs want.

---

## License

GPL-3.0. Fork, adapt, teach. If you improve it, [PR the improvement](https://github.com/CODECRUNCHWORLDWIDE) back so the next learner benefits.
