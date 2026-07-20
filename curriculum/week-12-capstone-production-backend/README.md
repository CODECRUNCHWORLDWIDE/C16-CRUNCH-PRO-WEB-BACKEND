# Week 12 — Capstone: ship a production-grade multi-tenant Python backend

> *Eleven weeks ago you wrote your first `request.GET` parser. This week you ship a service that holds tenant data behind a row-level-security policy, indexes documents in the background for full-text search, pushes a live event over a WebSocket the instant a row changes, caches the hot path in Redis under a tenant-namespaced key, runs a migration on a fresh production database without dropping a single request, and answers the question "where is this article" in under fifty milliseconds at the ninety-fifth percentile. The twelve-week arc had a shape, and the shape was this. Every previous week was a layer; this week is the wiring diagram that proves the layers compose.*

Welcome to **Week 12 — the final week of C16 · Crunch Pro Web Backend**. There is no Week 13. After Sunday's defence you have shipped a backend service that an employer can read, an investor can demo, and a regulator can audit. The capstone is the artefact. The repository is the artefact. The deployed URL is the artefact. The post-mortem of the one production incident you induced on purpose to prove the rollback runbook is the artefact. Twelve weeks of curriculum collapse into a single deliverable: **`MultiTenantContentHub`** — a content-management backend that any one of three sample tenants can sign up for, log into, post articles into, search across, subscribe to live updates from, and never see another tenant's bytes through.

The capstone exercises every prior week with no exceptions. **Week 1** is the HTTP surface — every route is HTTP/1.1 over TLS, every payload is JSON, every status code is the one the [HTTP semantics RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) prescribes. **Week 2** is the Django ORM that models the canonical content side (`Tenant`, `User`, `Article`, `Tag`, `Revision`) with `Meta.constraints` enforcing the cross-table invariants. **Week 3** is the Django views, forms, and authentication layer that serves the admin dashboard at `/admin/`. **Week 4** is the PostgreSQL database — schema design, `EXPLAIN ANALYZE` for every query that joins more than two tables, the right index on every foreign key. **Week 5** is the ORM deep work — `select_related`, `prefetch_related`, `Subquery`, `OuterRef`, the `annotate` queries that pre-compute counts. **Week 6** is migrations, scheduled jobs, and the Django cache framework — zero-downtime migrations using the "add column, backfill, set not-null" pattern, ARQ jobs for the search-index update, the Django cache backend pointed at Redis. **Week 7** is FastAPI for the high-throughput public API — `async def` end to end, Pydantic v2 models for every request and response, OpenAPI generated from the type hints. **Week 8** is WebSockets for the live activity feed and Server-Sent Events for the slow-burn notification stream, plus ARQ workers for the index-refresh fan-out. **Week 9** is Redis for the read-through cache on the article-detail endpoint, the per-tenant rate limiter, and the WebSocket pub/sub backplane. **Week 10** is PostgreSQL full-text search with `tsvector`, `tsquery`, `GIN` indices, and the optional bridge to Meilisearch for the typo-tolerant variant. **Week 11** is multi-tenancy with the shared-schema `tenant_id` column, the `FORCE ROW LEVEL SECURITY` policy on every tenant-scoped table, and the per-tenant Redis namespace. And **Week 12** is the integration — the wiring, the deployment, the runbook, the defence.

The deployment target is a **free tier**. We support three: [Fly.io](https://fly.io/docs/about/pricing/) (the Postgres + Redis + Python combination that we recommend in the lecture), [Render](https://render.com/pricing) (the simpler dashboard), and [Railway](https://railway.app/pricing) (the cleanest provisioning). Each gives you a Postgres instance, a Redis instance, and a Python web service for zero dollars per month at the capstone's scale. We will not lecture on Kubernetes; the W12 service runs on one process with one worker, and that is enough to demonstrate every concept.

By Sunday you will have:

1. **A live URL** — `https://multitenantcontenthub-<your-handle>.fly.dev/` (or the Render/Railway equivalent) — that serves three sample tenants (`acme`, `globex`, `initech`) each with their own subdomain or `X-Tenant` header, their own seeded articles, and their own admin user.
2. **A repository** at `https://github.com/<your-handle>/multitenantcontenthub` with a `README.md` an employer can read in two minutes, a `Makefile` that boots the service in one command, an `infra/` directory with the `fly.toml` (or `render.yaml` / `railway.json`), a `migrations/` directory with the Django and the FastAPI Alembic-style migrations both present, and a `runbook.md` with the four on-call procedures (deploy, roll back, rotate the database password, evict a misbehaving tenant).
3. **A test suite** — `pytest -q` runs end-to-end in under sixty seconds; covers the auth flow, the article CRUD, the search query, the WebSocket live-update path, and the RLS isolation invariant (the "tenant A cannot read tenant B" assertion is a literal test).
4. **A capstone post-mortem** — `docs/postmortem-incident-001.md` — describing the one production incident you induced on purpose (drop the Redis container, watch the service fall back to direct Postgres, document the latency regression and the recovery), with a timeline, a root cause, and a "what we changed" section.
5. **A defence document** — `docs/defence.md` — answering ten questions an interviewer would ask: "Why FastAPI and not Django for the public API? Why shared-schema and not database-per-tenant? Why Redis and not Memcached? Why Postgres full-text search and not Elasticsearch?" Two paragraphs per answer, cite the [FastAPI docs](https://fastapi.tiangolo.com/), the [Django docs](https://docs.djangoproject.com/), the [Postgres docs](https://www.postgresql.org/docs/), and the [Redis docs](https://redis.io/docs/latest/) where appropriate.
6. **A recorded walkthrough** — three minutes, no slides, screen recording — of you logging into the deployed service as the `acme` admin, creating an article, watching the WebSocket toast fire on the `acme` user's browser, switching to the `globex` admin, confirming `globex` cannot see `acme`'s article, and showing the structured log line that proves the search index updated in the background. Upload to YouTube unlisted; link from the repo `README.md`.

The week is the integration. Lectures are sparse — only three, and they are short. The exercise track is mostly verification of the prior weeks under the integrated harness. The mini-project *is* the week. By Wednesday evening the service should deploy. By Friday evening the WebSocket should be wired through. By Saturday evening the post-mortem and defence are written. Sunday is the quiz, the wrap-up, and the celebration.

## Learning objectives

By the end of this week, you will be able to:

- **Compose** an end-to-end Python backend that uses Django for the admin and the canonical ORM, FastAPI for the public async API, asyncpg for direct queries that bypass the ORM where appropriate, Redis for caching and pub/sub, and PostgreSQL for the storage and the search engine. Articulate the boundary between the Django stack and the FastAPI stack: Django owns the migrations and the admin; FastAPI owns the public reads and the WebSocket; both speak to the same Postgres. Cite the [FastAPI deployment guide](https://fastapi.tiangolo.com/deployment/) and the [Django deployment checklist](https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/).
- **Deploy** a multi-process Python service to a free-tier platform-as-a-service. The Fly.io path: `fly launch` from the repo, declare a Postgres app with `fly postgres create`, declare a Redis app with `fly redis create`, set secrets with `fly secrets set`, ship with `fly deploy`. The Render path: a `render.yaml` blueprint with two services and two managed databases. The Railway path: a `railway.json` with the same. Cite the [Fly.io Postgres docs](https://fly.io/docs/postgres/), the [Render blueprint reference](https://render.com/docs/blueprint-spec), and the [Railway docs](https://docs.railway.app/).
- **Operate** the service end-to-end. Deploy a fix without downtime. Roll the deploy back. Rotate the database password without dropping connections. Evict a tenant whose rate limit is being violated. Each operation is a section of `docs/runbook.md`; each is exercised on the live service before Sunday.
- **Demonstrate** the multi-tenant isolation invariant under integration. A test creates two tenants, an article in each, then queries the `/articles/{id}` endpoint with the wrong tenant header and asserts a `404`. The test passes because the RLS policy filters the row out before the application sees it. The test is a literal `pytest` test; the assertion is one line.
- **Demonstrate** the live-update path under integration. A test opens a WebSocket connection as the `acme` user, POSTs an article as the `acme` admin via the HTTP API, and asserts that the WebSocket receives an `article.created` event within five hundred milliseconds. The Redis pub/sub backplane is exercised; the asynchronous fan-out is exercised; the WebSocket handler is exercised; one test covers the path.
- **Demonstrate** the search-index lag under control. A test creates an article, polls the `/search?q=...` endpoint until the article appears, and asserts that the lag is under two seconds. The ARQ worker updates the `tsvector` column; the test proves the worker keeps up. The two-second bound is a service-level objective documented in `docs/sla.md`.
- **Articulate** the cost of every dependency. Postgres is free on Fly.io up to 3 GB; Redis is free up to 256 MB; the Python process is free up to 256 MB of RAM. The capstone sits inside every free-tier ceiling. Articulate the failure mode when the service grows past the ceiling — what you would swap in (the next tier, the dedicated Postgres, the multi-region Redis) and what it would cost.
- **Defend** the architectural choices in a written document. Why FastAPI for the public API and Django for the admin (the FastAPI async story is the right tool for the WebSocket; the Django admin is forty staff-hours of free dashboard). Why shared-schema multi-tenancy and not database-per-tenant (the customer mix is small-to-medium; the cost of per-tenant databases is a full-time DBA we do not have). Why Postgres FTS and not Elasticsearch (one fewer service to operate; the FTS quality is good enough for the corpus size). Why Redis and not Memcached (Redis has pub/sub; Memcached does not; the WebSocket backplane needs pub/sub). Cite the docs at every claim.
- **Reflect** on the twelve-week arc. The artefact you ship in Week 12 is the artefact you could not have built in Week 1, in Week 6, even in Week 11 — because the integration *is* the skill. Write the reflection. Submit the reflection. Read it again in twelve months when you are deciding whether to take the C17 advanced track or to ship your own SaaS.

## Topics covered

- The capstone architecture: Django for the admin, FastAPI for the public API, asyncpg for the async DB layer, Redis for caching and pub/sub, Postgres for storage and search
- Free-tier deployment on Fly.io: `fly launch`, `fly postgres create`, `fly redis create`, `fly secrets set`, `fly deploy`; the same on Render and Railway
- The `Dockerfile` for a multi-process Python service: the Gunicorn + Uvicorn worker pattern for Django, the Uvicorn-only pattern for FastAPI, the ARQ worker as a separate process
- Database migrations under multi-tenancy: the Django migrations for the admin tables, the schema migrations for the FastAPI public tables, the per-tenant data backfill jobs
- The integration test pyramid for a capstone: unit tests for the ORM, integration tests for the FastAPI handlers, end-to-end tests across the Django + FastAPI + Redis + Postgres stack
- The WebSocket integration path: FastAPI WebSocket handler, Redis pub/sub channel, ARQ worker that publishes on row insert, browser-side reconnect logic
- The search integration path: Postgres `tsvector` column, GIN index, ARQ worker that recomputes the vector on row insert and update, the `/search?q=` endpoint with rank-ordering
- The cache integration path: Redis read-through cache on the article-detail endpoint, the tenant-namespaced key, the cache stampede prevention via `SET NX EX`
- The rate-limit integration path: the per-tenant token bucket in Redis, the FastAPI dependency that consumes a token per request, the 429 response with `Retry-After`
- The RLS integration path: the `SET LOCAL app.current_tenant` per request, the `FORCE ROW LEVEL SECURITY` on every tenant-scoped table, the test that proves cross-tenant queries return zero rows
- The runbook: the deploy procedure, the rollback procedure, the password-rotation procedure, the tenant-eviction procedure
- The post-mortem: the structure (timeline, root cause, what went well, what did not, what we changed); the incident you induced on purpose; the document you keep
- The defence: ten questions, two paragraphs each, every claim cited
- The twelve-week wrap-up: the W1 to W12 sidebar, the "what you learned" map, the "what comes next" pointer

## Weekly schedule

The schedule below totals approximately **40 hours** — the largest week of C16 because the integration is the deliverable. There are only three short lectures (under five hours combined); the rest is build, deploy, test, document.

| Day       | Focus                                                                                | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | The capstone architecture; the Django + FastAPI boundary; the deployment target picker | 2h       | 1h        | 0h         | 0.5h      | 0.5h     | 2h           | 0.5h       | 6.5h        |
| Tuesday   | Integration testing across the stack; the test pyramid; the end-to-end harness         | 1.5h     | 2h        | 0h         | 0.5h      | 0.5h     | 2h           | 0.5h       | 7h          |
| Wednesday | The free-tier deploy: Fly.io / Render / Railway; the Dockerfile; the secrets          | 1h       | 1h        | 1h         | 0.5h      | 0.5h     | 3h           | 0.5h       | 7.5h        |
| Thursday  | Wire the WebSocket; wire the search index; wire the cache; wire the rate limiter      | 0h       | 0h        | 1h         | 0h        | 0.5h     | 4h           | 0.5h       | 6h          |
| Friday    | The runbook (deploy, roll back, rotate, evict); the on-call drill                     | 0h       | 0h        | 0h         | 0.5h      | 0.5h     | 3.5h         | 0h         | 4.5h        |
| Saturday  | The post-mortem (one induced incident); the defence (ten questions)                   | 0h       | 0h        | 0h         | 0h        | 0.5h     | 4h           | 0h         | 4.5h        |
| Sunday    | The final exam; the wrap-up; the walkthrough recording; the celebration                | 0h       | 0h        | 0h         | 1.5h      | 0.5h     | 2h           | 0h         | 4h          |
| **Total** |                                                                                      | **4.5h** | **4h**    | **2h**     | **3.5h**  | **3.5h** | **20.5h**    | **2h**     | **40h**     |

The mini-project consumes half the week. There is no week-thirteen safety net. If the deploy is not green by Wednesday night, the rest of the week compresses; if the deploy is green by Wednesday night, Thursday through Saturday is craft and polish.

## The twelve-week sidebar (W1 through W12)

| Week | Title | Headline artefact |
|-----:|-------|-------------------|
| 1 | HTTP and the modern Python web | A WSGI-style handler that parses an HTTP/1.1 request by hand |
| 2 | Django models, ORM, admin | A Django project with `Tenant`, `User`, `Article` and the auto-generated admin |
| 3 | Django views, templates, forms, auth | A login-protected article CRUD with Django forms |
| 4 | PostgreSQL for app developers | A normalised schema with the right indexes, validated via `EXPLAIN ANALYZE` |
| 5 | Django ORM deep dive | `select_related`, `prefetch_related`, `Subquery`, `Window` |
| 6 | Migrations, scheduled jobs, caching | Zero-downtime migrations; ARQ workers; the Django cache framework |
| 7 | FastAPI fundamentals | An async public API with Pydantic v2 and asyncpg |
| 8 | WebSockets, SSE, and background jobs | A live-update channel with Redis pub/sub and ARQ fan-out |
| 9 | Caching with Redis | Read-through caching; rate limiting; pub/sub; the cache stampede control |
| 10 | Search: FTS, OpenSearch, Meilisearch | Postgres `tsvector` with a `GIN` index; the Meilisearch bridge |
| 11 | Multi-tenancy with RLS | Shared schema with `tenant_id`; `FORCE ROW LEVEL SECURITY`; per-tenant Redis keys |
| 12 | **Capstone — production-grade backend** | **`MultiTenantContentHub` deployed to a free tier with a live URL** |

Every prior week contributes a layer. The capstone composes the layers.

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | The FastAPI, Django, Postgres, Redis, Fly.io, Render, and Railway docs; the W1 through W12 reference list |
| [lecture-notes/01-the-capstone-architecture.md](./lecture-notes/01-the-capstone-architecture.md) | The Django + FastAPI boundary; the asyncpg + Redis layer; the Postgres + RLS substrate |
| [lecture-notes/02-deploy-to-a-free-tier.md](./lecture-notes/02-deploy-to-a-free-tier.md) | The Fly.io, Render, and Railway paths; the `Dockerfile`; the secrets; the rollback |
| [lecture-notes/03-the-twelve-week-wrap-up.md](./lecture-notes/03-the-twelve-week-wrap-up.md) | What every prior week contributed; the map of the field; where C17 picks up |
| [exercises/exercise-01-end-to-end-test-harness.py](./exercises/exercise-01-end-to-end-test-harness.py) | The end-to-end test that proves the auth, the CRUD, the search, the WebSocket all work |
| [exercises/exercise-02-rls-cross-tenant-assertion.py](./exercises/exercise-02-rls-cross-tenant-assertion.py) | The literal test that proves tenant A cannot read tenant B |
| [exercises/exercise-03-deploy-dry-run.py](./exercises/exercise-03-deploy-dry-run.py) | The pre-deploy checklist as a runnable script; the `fly.toml` / `render.yaml` linter |
| [exercises/exercise-04-runbook-drill.py](./exercises/exercise-04-runbook-drill.py) | The runbook exercised as a script: rollback, rotate, evict |
| [exercises/exercise-05-capstone-schema.sql](./exercises/exercise-05-capstone-schema.sql) | The full capstone schema with the RLS policies, the indexes, the seed data |
| [exercises/SOLUTIONS.md](./exercises/SOLUTIONS.md) | Worked solutions for the four scripts and the SQL file |
| [challenges/challenge-01-induce-an-incident.md](./challenges/challenge-01-induce-an-incident.md) | Drop Redis on the live service; recover; write the post-mortem |
| [challenges/challenge-02-defend-the-architecture.md](./challenges/challenge-02-defend-the-architecture.md) | Answer ten interviewer questions; cite docs; two paragraphs each |
| [quiz.md](./quiz.md) | The final exam: 20 questions covering W1 through W12 |
| [homework.md](./homework.md) | Four problems (~3.5 h) — the deploy, the test, the runbook, the reflection |
| [mini-project/README.md](./mini-project/README.md) | The capstone spec: `MultiTenantContentHub` end-to-end |
| [mini-project/starter/](./mini-project/starter/) | The skeleton: Django project, FastAPI app, Dockerfile, Makefile, fly.toml |

## Before Monday — verify you are ready to ship

Twelve checks. One per prior week. If any fails, go back to that week before opening Lecture 1.

```bash
# W1: HTTP semantics
python3 -c "from urllib.parse import urlparse; print(urlparse('https://example.test/x?q=1').path)"

# W2: Django + ORM
python3 -c "import django; print(django.get_version())"
# 5.1.x or 5.2.x

# W3: Django auth + forms (verify the module imports)
python3 -c "from django.contrib.auth.models import User; print('ok')"

# W4: Postgres reachable
psql -h localhost -U postgres -c 'SELECT version();' | head -1

# W5: Django ORM deep-dive features
python3 -c "from django.db.models import Subquery, OuterRef, Window; print('ok')"

# W6: ARQ for background jobs
python3 -c "import arq; print(arq.__version__)"

# W7: FastAPI + Pydantic v2 + asyncpg
python3 -c "import fastapi, pydantic, asyncpg; print(fastapi.__version__, pydantic.VERSION)"

# W8: WebSockets (the websockets library)
python3 -c "import websockets; print(websockets.__version__)"

# W9: Redis
redis-cli ping
# PONG

# W10: Postgres full-text search
psql -h localhost -U postgres -c "SELECT to_tsvector('english', 'the quick brown fox');" | head -3

# W11: RLS (verify the non-superuser application role exists from W11)
psql -h localhost -U postgres -c "SELECT rolname, rolbypassrls, rolsuper FROM pg_roles WHERE rolname='crunchreader_app';"

# W12: A deployment CLI is installed for at least one of the three targets
fly version 2>/dev/null || render --version 2>/dev/null || railway --version 2>/dev/null || echo "Install at least one"
```

If you do not have *any* of `fly`, `render`, or `railway` installed yet, install `fly` first: `curl -L https://fly.io/install.sh | sh`. It is the lecture path and the smallest CLI of the three.

## The habit to install this week

Four practices, applied to every commit from here forward:

1. **Every commit deploys.** Not every commit *should* deploy; every commit *can* deploy. CI green on `main` means production-deployable. If you cannot push to main, you cannot ship. The discipline this builds is the discipline of "every line of code is a candidate release". The cost is the test suite; the test suite is W12 exercise 1.
2. **Every endpoint has a runbook entry.** If the endpoint can be operationally broken (it can — they all can), there is a line in `runbook.md` describing what breaks and how to recover. The day you forget is the day the on-call engineer (you, in six months) has to derive the recovery from first principles at 3am.
3. **Every architectural choice has a defence.** When you choose FastAPI, write the one paragraph that says why FastAPI. When you choose Redis, write the one paragraph. Two paragraphs becomes ten becomes the `docs/defence.md` file becomes the talking points for the interview that asks "tell me about your capstone".
4. **Every prod incident has a post-mortem.** Even the induced ones. Even the trivial ones. The discipline of writing the timeline, the root cause, the "what we changed" — that discipline does not start on the day of the big incident. It starts on the day of the small one.

The first practice keeps the artefact shippable. The second keeps the artefact operable. The third keeps the artefact defensible. The fourth keeps the artefact improving.

## Stretch goals

- Deploy to **two** free-tier targets, not one. Fly.io plus Render is the typical pair. The exercise teaches you that the `Dockerfile` is portable and the platform-specific config is small; the experience teaches you that "the deploy is one shell command" is the entire promise of platform-as-a-service.
- Add **OpenTelemetry tracing** end-to-end. The W12 service already emits structured logs; add `opentelemetry-instrumentation-fastapi` and `opentelemetry-instrumentation-django` and export to a free [Honeycomb](https://www.honeycomb.io/pricing) account or to the Fly.io built-in tracing. The traces show a request crossing from FastAPI to Postgres to Redis and back; the picture is what observability looks like in 2026.
- Add a **multi-region deploy**. Fly.io's `fly regions add fra,sin,iad` adds three more regions to your deploy at zero cost on the free tier. The Postgres becomes a primary in one region and read-replicas in the others; the Redis is regional; the WebSocket backplane has to be re-thought. Document the trade-off. The work is half a day; the lesson is enormous.
- Read **the [Twelve-Factor App](https://12factor.net/)** end to end (the modern revision). The W12 capstone is a near-pure Twelve-Factor app; the document is the most-cited backend manifesto of the last fifteen years; the exercise of "find every factor in your repo" is the cleanest review of the term.
- Read **[Designing Data-Intensive Applications](https://dataintensive.net/)** by Martin Kleppmann, chapter one. Free preview. The book is the C17 prerequisite reading; the first chapter is a gentle introduction to the trade-offs every backend engineer makes daily.

## After Sunday — you have shipped

There is no Week 13. The next step is the C17 advanced track if you want it (the prerequisites are this capstone, a clean test suite, and a green production deploy that has survived at least one induced incident). Or the next step is your own thing — a side project, a contracting gig, a job application that links to the deployed URL and the repo.

You wrote 4 500 lines of Python. You ran 200 tests. You deployed twice (once to validate the path; once to ship). You wrote one post-mortem. You answered ten interviewer questions. You have a live URL on the public internet running a service you understand end to end.

Twelve weeks. One backend. Yours.
