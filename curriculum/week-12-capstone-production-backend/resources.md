# Week 12 — Resources

The W12 reading list is the union of the prior eleven, distilled down to the load-bearing references plus the new ones the capstone introduces: free-tier hosting, deployment, and the production-readiness checklists. Every link in this file is free.

## The core canon — one entry per prior week

| Week | Primary reference | Why it is the one to keep open |
|-----:|-------------------|--------------------------------|
| 1 | [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) | The HTTP message model. Status codes, method semantics, header rules. The reference every API design conversation circles back to. |
| 2 | [Django models — the docs](https://docs.djangoproject.com/en/5.1/topics/db/models/) | The ORM contract, the field types, the `Meta.constraints`, the model inheritance model. |
| 3 | [Django authentication](https://docs.djangoproject.com/en/5.1/topics/auth/) | `AbstractUser`, login, logout, the permission framework, the session middleware. |
| 4 | [PostgreSQL — Performance Tips](https://www.postgresql.org/docs/current/performance-tips.html) | `EXPLAIN ANALYZE`, the cost model, the `random_page_cost` and `effective_cache_size` knobs. |
| 5 | [Django QuerySet API reference](https://docs.djangoproject.com/en/5.1/ref/models/querysets/) | `select_related`, `prefetch_related`, `annotate`, `Subquery`, `OuterRef`, `Window`. |
| 6 | [Django migrations — the docs](https://docs.djangoproject.com/en/5.1/topics/migrations/) | `makemigrations`, `migrate`, the operation set, the zero-downtime pattern. |
| 7 | [FastAPI — the official tutorial](https://fastapi.tiangolo.com/tutorial/) | The minimum you need to be productive; the Pydantic v2 integration; the dependency-injection chapter. |
| 8 | [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) | The handler contract, the `accept`/`send`/`receive` lifecycle, the broadcast pattern. |
| 9 | [Redis commands](https://redis.io/docs/latest/commands/) | The reference for every command; `SET`, `GET`, `INCR`, `EXPIRE`, `PUBSUB`, `EVAL`. |
| 10 | [PostgreSQL — Text Search](https://www.postgresql.org/docs/current/textsearch.html) | `tsvector`, `tsquery`, `to_tsvector`, `plainto_tsquery`, `phraseto_tsquery`, `websearch_to_tsquery`. |
| 11 | [PostgreSQL — Row Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | The full RLS chapter; `CREATE POLICY`, `FORCE ROW LEVEL SECURITY`, the `BYPASSRLS` role attribute. |
| 12 | [The Twelve-Factor App](https://12factor.net/) | The deployment-and-operations contract that every prior week composes toward. |

If you read no other documents this week, read those twelve. The C16 curriculum is, in one sense, a 240-hour walking tour of those twelve links.

## Free-tier deployment — pick one and own it

The lecture demonstrates Fly.io. The mini-project accepts any of the three. Pick one for the capstone; do not pick two until the stretch goal.

### Fly.io

- [Fly.io — Hands-on with Fly](https://fly.io/docs/hands-on/) — the official getting-started; covers `fly launch`, `fly deploy`, `fly logs`, `fly ssh console`.
- [Fly.io — Postgres](https://fly.io/docs/postgres/) — `fly postgres create`, connection-string discovery, backups, scaling.
- [Fly.io — Redis (Upstash)](https://fly.io/docs/reference/redis/) — `fly redis create`, the connection URL, the free-tier limits.
- [Fly.io — Pricing](https://fly.io/docs/about/pricing/) — what costs zero, what costs more than zero, what the free allowances actually are.
- [Fly.io — Secrets](https://fly.io/docs/reference/secrets/) — `fly secrets set`, `fly secrets list`, the rotation pattern.
- [Fly.io — Releases and rollbacks](https://fly.io/docs/reference/deploy/) — `fly releases`, `fly deploy --image`, the rollback procedure.
- [Fly.io — `fly.toml` reference](https://fly.io/docs/reference/configuration/) — the configuration file we will write.

### Render

- [Render — Quickstart](https://render.com/docs/your-first-deploy) — the dashboard-first path.
- [Render — Blueprints (Infrastructure-as-code)](https://render.com/docs/blueprint-spec) — `render.yaml`, the multi-service declaration.
- [Render — PostgreSQL](https://render.com/docs/databases) — managed Postgres; free-tier limits.
- [Render — Redis](https://render.com/docs/redis) — managed Redis; free-tier limits.
- [Render — Environment groups](https://render.com/docs/configure-environment-variables) — the secrets pattern.
- [Render — Health checks](https://render.com/docs/deploys#health-checks) — the readiness endpoint we will wire.

### Railway

- [Railway — Docs](https://docs.railway.app/) — the umbrella docs.
- [Railway — Reference](https://docs.railway.app/reference) — `railway.json`, plugins, environments.
- [Railway — Pricing](https://railway.app/pricing) — the trial credit and the free-tier limits.
- [Railway — PostgreSQL plugin](https://docs.railway.app/databases/postgresql) — the managed Postgres.
- [Railway — Redis plugin](https://docs.railway.app/databases/redis) — the managed Redis.

### Common to all three

- [Docker — Best practices for writing Dockerfiles](https://docs.docker.com/develop/dev-best-practices/) — the multi-stage build pattern.
- [Docker — Python images](https://hub.docker.com/_/python) — the `python:3.12-slim` base we will use.
- [Gunicorn](https://docs.gunicorn.org/en/stable/) — the WSGI server for Django.
- [Uvicorn](https://www.uvicorn.org/) — the ASGI server for FastAPI; also the worker class for Gunicorn when serving ASGI Django.

## Production readiness — the checklists

- [Django — Deployment checklist](https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/) — every settings flag you must flip for production. `DEBUG=False`, `ALLOWED_HOSTS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`. The single most useful Django page when you ship.
- [FastAPI — Deployment](https://fastapi.tiangolo.com/deployment/) — the deployment guide; covers HTTPS, the worker count, the health checks.
- [PostgreSQL — Server configuration](https://www.postgresql.org/docs/current/runtime-config.html) — the postgresql.conf parameters; `shared_buffers`, `work_mem`, `max_connections`.
- [Redis — Administration](https://redis.io/docs/latest/operate/oss_and_stack/management/) — `maxmemory`, `maxmemory-policy`, `appendonly`, the persistence trade-offs.
- [12-Factor App](https://12factor.net/) — the manifesto. Read it twice.
- [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) — the chapter on SLI/SLO/SLA; the basis for `docs/sla.md`.

## Observability — the W12 stretch territory

- [OpenTelemetry — Python](https://opentelemetry.io/docs/languages/python/) — the SDK and the auto-instrumentation packages.
- [opentelemetry-instrumentation-fastapi](https://opentelemetry.io/docs/languages/python/automatic/) — the auto-instrumentation for FastAPI; one decorator, full trace coverage.
- [opentelemetry-instrumentation-django](https://pypi.org/project/opentelemetry-instrumentation-django/) — the auto-instrumentation for Django.
- [Honeycomb — Free tier](https://www.honeycomb.io/pricing) — 20M events/month free; the easiest place to send OTel traces.
- [structlog](https://www.structlog.org/) — the structured logging library; the `logger.bind(tenant_id=...)` pattern.

## Testing — the W12 integration pyramid

- [pytest](https://docs.pytest.org/en/stable/) — the test runner; fixtures, parametrize, markers.
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/en/latest/) — the async support; the `@pytest.mark.asyncio` decorator.
- [httpx](https://www.python-httpx.org/) — the async HTTP client we use to drive FastAPI in tests.
- [pytest-django](https://pytest-django.readthedocs.io/en/latest/) — the pytest plugin for Django; `--reuse-db`, `--create-db`, the test-database lifecycle.
- [Testcontainers for Python](https://testcontainers-python.readthedocs.io/en/latest/) — the docker-based test fixtures; spin up a real Postgres and a real Redis per test session.
- [Locust](https://locust.io/) — the load-testing tool; the free, Python-native alternative to `k6`/`hey` for capstone load tests.

## Post-mortems and runbooks — the operational craft

- [Google SRE Book — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/) — the chapter on blameless post-mortems; the timeline format, the "what we changed" section.
- [Etsy — Debriefing facilitation guide](https://www.etsy.com/codeascraft/blameless-postmortems/) — Etsy engineering on blameless post-mortems; the cultural framing.
- [PagerDuty — Incident response](https://response.pagerduty.com/) — the open documentation of PagerDuty's own on-call practice; the runbook structure we borrow.
- [Atlassian — Incident management handbook](https://www.atlassian.com/incident-management/handbook) — the free PDF; the runbook patterns.

## Security checklists — before you ship

- [OWASP — Top 10 for Web Applications](https://owasp.org/www-project-top-ten/) — the list; map every item to your service before deploy.
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x00-header/) — the API-specific list; closer to what the W12 service does.
- [OWASP — Cheat Sheet Series](https://cheatsheetseries.owasp.org/) — the index; the [Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) and [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) cheat sheets are the immediate ones.
- [Mozilla — Web Security Cheat Sheet](https://infosec.mozilla.org/guidelines/web_security) — the HTTP security headers; `Strict-Transport-Security`, `Content-Security-Policy`, the bag.

## Reflection reading — the long-form

- [Designing Data-Intensive Applications — Chapter 1 (free preview)](https://dataintensive.net/) — Martin Kleppmann; the trade-off catalogue every backend engineer ends up internalising.
- [The Architecture of Open Source Applications — Volume 1](https://aosabook.org/en/v1/index.html) — free book; chapters on real systems including a small Python web framework.
- [Hillel Wayne — Why You Should Use a Formal Specification Language](https://www.hillelwayne.com/post/why-formal-specifications/) — short essay; the introduction to "what you cannot test, you can specify".

## Tools to install before Monday

```bash
# Fly.io CLI (the lecture path)
curl -L https://fly.io/install.sh | sh
fly version

# (Alternative) Render CLI
brew install render-oss/render/render        # macOS
render --version

# (Alternative) Railway CLI
npm install -g @railway/cli
railway --version

# Docker — for the local Dockerfile validation
docker --version

# hey — for the load test on the deployed service
brew install hey                              # macOS
hey -h
```

You need one deploy CLI; you need Docker; you need `hey`. Three tools, one shell session, ten minutes.

## What this list deliberately omits

- **Kubernetes** — not in scope. The capstone runs on a platform-as-a-service. The free-tier story we tell is "one container, one URL, one deploy command". Kubernetes is C17 stretch territory.
- **AWS / GCP / Azure** — not in scope. Each hyperscaler has a free tier and each free tier has expiry traps. Fly.io, Render, and Railway are PaaS-on-top-of-hyperscaler with the trap removed. Use them.
- **Elasticsearch / OpenSearch as a managed service** — not in scope. The capstone uses Postgres full-text search. The W10 stretch goal was Meilisearch on the same box; the capstone does not require it.
- **A web frontend** — not in scope. The capstone is a backend. The walkthrough recording can use `curl`, `httpie`, Postman, or a five-line HTML page; the frontend is a backend-engineer's afterthought for this purpose.
- **A CI/CD platform** — recommended but not required. GitHub Actions is the default; the `.github/workflows/test.yml` in the starter runs the tests on push. Mandatory CI is C17 territory.

Everything in the list above is free. Everything required for the capstone is in the list above.
