# Lecture 3 — The twelve-week wrap-up: what every prior week contributed and where C17 picks up

> *Twelve weeks ago you wrote your first HTTP parser. Today you ship a multi-tenant content service to a free-tier cloud and a hiring manager can read it on their phone. The arc is the artefact. This lecture is the map of the arc.*

## 3.1 The map of the field

The arc had a shape. Each week was a layer; the layers stacked; the capstone proved they compose. Here is the map, in the order you climbed it:

```text
                                                  +---------------------------+
                                                  |       Week 12             |
                                                  |       Capstone             |
                                                  |    (this week's artefact)  |
                                                  +-------------+-------------+
                                                                |
                                +-------------------------------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 11           |
                  |     Multi-tenancy       |
                  |   shared schema + RLS    |
                  +-------------+-----------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 10           |
                  |       Search            |
                  |   tsvector + Meilisearch|
                  +-------------+-----------+
                                |
                                v
        +-----------------------+-----------------------+
        |       Week 9          |       Week 8          |
        |    Redis caching      | WebSockets + ARQ jobs |
        +-----------+-----------+-----------+-----------+
                    |                       |
                    +-----------+-----------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 7            |
                  |       FastAPI           |
                  +-------------+-----------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 6            |
                  | Migrations + Jobs + Cache|
                  +-------------+-----------+
                                |
        +-----------------------+-----------------------+
        |       Week 5          |       Week 4          |
        |   Django ORM deep     |    PostgreSQL         |
        +-----------+-----------+-----------+-----------+
                    |                       |
                    +-----------+-----------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 3            |
                  | Views, Forms, Auth      |
                  +-------------+-----------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 2            |
                  |   Django ORM + Admin    |
                  +-------------+-----------+
                                |
                                v
                  +-------------+-----------+
                  |       Week 1            |
                  | HTTP and modern Python  |
                  +-------------------------+
```

Read upward: every layer assumes the layers below.

## 3.2 Week-by-week, what it contributed

### Week 1 — HTTP and the modern Python web

The foundation. You wrote a request parser by hand, then a WSGI/ASGI shim, then a small framework that wrapped the shim. The lesson was that *every* Python web framework is a more-or-less elegant wrapper around the same two things: parsing an HTTP message and dispatching to a handler that returns an HTTP response.

You learned: HTTP/1.1 message structure (the request line, the headers, the body); status codes that mean what they mean (200, 201, 204, 301, 304, 400, 401, 403, 404, 422, 429, 500, 502, 503); the WSGI protocol (a callable that takes `(environ, start_response)`); the ASGI protocol (a coroutine that takes `(scope, receive, send)`); the request lifecycle through `uvicorn` and `gunicorn`.

What the capstone uses: every route in the capstone is HTTP/1.1 over TLS; the status codes are the ones the W1 lecture catalogued; the FastAPI process is ASGI under Uvicorn; the Django process is WSGI under Gunicorn-with-Uvicorn-workers (which serves ASGI Django too).

Reference: [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html), [WSGI PEP 3333](https://peps.python.org/pep-3333/), [ASGI specification](https://asgi.readthedocs.io/).

### Week 2 — Django models, ORM, admin

The first framework. You learned the Django ORM by building five models and watching the admin auto-generate the dashboard. The lesson was that an ORM is a domain-specific language for data, and Django's is one of the most coherent ones.

You learned: model fields and their database types; `ForeignKey`, `OneToOneField`, `ManyToManyField`; `Meta.constraints` and `Meta.indexes`; the QuerySet API; the admin's `ModelAdmin`; `makemigrations` and `migrate`.

What the capstone uses: the Django models for `Tenant`, `User`, `Article`, `Tag`, `Revision`, `Comment`, `Subscription`; the admin at `/admin/`; the migrations as the source of truth for the schema.

Reference: [Django models — the docs](https://docs.djangoproject.com/en/5.1/topics/db/models/).

### Week 3 — Django views, templates, forms, auth

The presentation layer. You built a CRUD with Django's class-based views, then with function-based views; you served HTML through templates; you protected the routes with `@login_required` and the permission framework. The lesson was that authentication is the hardest part of every web app, and Django shipped with most of the answers.

You learned: function-based views and class-based views; the `ModelForm` and the `Form`; the template language; `{% csrf_token %}` and the CSRF middleware; `AbstractUser` and `User.is_authenticated`; the permission framework.

What the capstone uses: the Django admin at `/admin/` (which is built on the W3 view/form/auth stack); the signup view that creates a `Tenant`-bound `User`; the password hashing (`pbkdf2_sha256` by default, configurable to `argon2`).

Reference: [Django authentication](https://docs.djangoproject.com/en/5.1/topics/auth/).

### Week 4 — PostgreSQL for app developers

The database for keeps. You went past "Django manages it for me" into the Postgres machinery: data types beyond `varchar`, indexes that match the access pattern, `EXPLAIN ANALYZE` as the diagnostic of last resort. The lesson was that the application's performance is the database's performance, and you cannot optimise what you cannot read.

You learned: Postgres data types (`text`, `varchar(n)`, `int`, `bigint`, `uuid`, `timestamptz`, `jsonb`, `tsvector`); B-tree, hash, GIN, GiST, BRIN indexes and when each fits; `EXPLAIN ANALYZE` and the cost model; the `random_page_cost` and `effective_cache_size` knobs; `VACUUM`, `ANALYZE`, autovacuum; transaction isolation levels.

What the capstone uses: a normalised schema; the right index on every foreign key; a composite primary key `(tenant_id, id)` on every tenant-scoped table; `EXPLAIN ANALYZE` in the test suite's slow-query guard.

Reference: [PostgreSQL — Performance Tips](https://www.postgresql.org/docs/current/performance-tips.html).

### Week 5 — Django ORM deep dive

The ORM, harder. The N+1 query problem and the `select_related` / `prefetch_related` fixes; `annotate`, `aggregate`, `Subquery`, `OuterRef`, `Window`; the `Manager` / `QuerySet` extension pattern. The lesson was that the gap between "the ORM made one query" and "the ORM made 1 + N queries" is the single biggest performance fork in a Django app.

You learned: how to read the SQL the ORM generates (`str(qs.query)`, `qs.explain()`); `select_related` for forward foreign keys; `prefetch_related` for reverse and many-to-many; `annotate` for per-row aggregates; `Subquery` and `OuterRef` for correlated subqueries; `Window` for ranking; custom `Manager` and `QuerySet` for reusable query patterns.

What the capstone uses: every admin list view is `.select_related('tenant').prefetch_related('tags')` (so the admin index doesn't N+1); the `Article.objects.with_view_count()` custom manager method.

Reference: [Django QuerySet API reference](https://docs.djangoproject.com/en/5.1/ref/models/querysets/).

### Week 6 — Migrations, scheduled jobs, caching

The operational layer of a Django service. Zero-downtime migrations (add column nullable; deploy; backfill; deploy; set not-null; deploy); the Django cache framework with Redis as the backend; the scheduled-job options (Celery, APScheduler, ARQ, plain cron). The lesson was that every migration has a deploy-time cost, and the cost is a function of which "phase" you skipped.

You learned: `RunPython` and `RunSQL` operations; the `--fake` flag (and when not to use it); `django-cache` with the Redis backend; the W6 ARQ introduction.

What the capstone uses: the three-phase zero-downtime migration pattern (validated in challenge 02 last week); the Django cache framework for session storage; the ARQ worker process for the search-index refresh job.

Reference: [Django migrations](https://docs.djangoproject.com/en/5.1/topics/migrations/), [Django cache framework](https://docs.djangoproject.com/en/5.1/topics/cache/).

### Week 7 — FastAPI fundamentals

The second framework. The async-first model; Pydantic v2 for the contracts; OpenAPI for the schema; the dependency-injection system. The lesson was that "framework" is a verb in 2026 — you can pick the framework whose primitives match the problem.

You learned: `async def` handlers; Pydantic v2 `BaseModel`, `Field`, `model_validate`, `model_dump`; `Depends` for shared logic; `Annotated[T, Depends(...)]` for the dependency-injection pattern; `asyncpg` for non-blocking Postgres; the OpenAPI auto-generation.

What the capstone uses: every public-API route; every Pydantic v2 schema; every `Depends` call; the OpenAPI at `/api/openapi.json` that documents the public surface.

Reference: [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/).

### Week 8 — WebSockets, SSE, and background jobs

The push-data story. WebSockets for bidirectional streams; Server-Sent Events for one-way push over plain HTTP; the ARQ worker for fan-out and offload. The lesson was that "the page polls every five seconds" is the dial-up version of the user experience; the modern version is "the server pushes when something happens".

You learned: the FastAPI WebSocket handler; the `accept`/`send`/`receive`/`close` lifecycle; the `WebSocketDisconnect` exception; Server-Sent Events with `EventSourceResponse` (from `sse-starlette`); ARQ task definitions, the worker process, retries.

What the capstone uses: the WebSocket endpoint at `/ws` that streams tenant-scoped events; the ARQ worker that handles the search-index refresh and the email-on-signup task.

Reference: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/), [ARQ docs](https://arq-docs.helpmanual.io/).

### Week 9 — Caching with Redis

Redis as a Swiss-army knife. The read-through cache, the rate limiter, the pub/sub backplane, the distributed lock. The lesson was that Redis is fast enough that you can call it on the hot path without thinking, and almost any read-heavy service benefits from a cache in front of the database.

You learned: `GET`/`SET`/`SETNX`/`SETEX`; `INCR`/`DECR`; `EXPIRE`/`TTL`; `PUBLISH`/`SUBSCRIBE`; the cache-stampede control via `SET NX EX`; the token-bucket rate limiter; the `Lua` script for atomic check-and-set.

What the capstone uses: the read-through cache on `GET /api/articles/{id}`; the per-tenant rate limiter on every public route; the pub/sub backplane for the WebSocket fan-out.

Reference: [Redis commands](https://redis.io/docs/latest/commands/).

### Week 10 — Search: FTS, OpenSearch, Meilisearch

The search story. Postgres full-text search with `tsvector` and `tsquery` and the `GIN` index; the optional bridge to Meilisearch for typo-tolerance; the trade-off between "one fewer service" and "better quality". The lesson was that Postgres FTS is good enough for most corpora, and the marginal quality of a dedicated search engine is paid for in operations.

You learned: `to_tsvector`, `plainto_tsquery`, `websearch_to_tsquery`, `phraseto_tsquery`; the `@@` operator; `ts_rank` for ordering; `ts_headline` for snippets; the `GIN` index; the trigger that keeps the vector in sync.

What the capstone uses: the `tsvector` column on `articles`; the `GIN` index; the trigger; the `/api/search` endpoint.

Reference: [PostgreSQL Text Search](https://www.postgresql.org/docs/current/textsearch.html).

### Week 11 — Multi-tenancy with RLS

The boundary. Shared schema with a `tenant_id` column; `FORCE ROW LEVEL SECURITY` policies on every tenant-scoped table; the `SET LOCAL app.current_tenant` per request; the per-tenant Redis namespace and rate limit. The lesson was that the database is a better isolation boundary than the application is, because the application has bugs and the database has policies.

You learned: `CREATE POLICY ... USING (...)` and `CREATE POLICY ... WITH CHECK (...)`; `FORCE ROW LEVEL SECURITY` (the gotcha); the superuser bypass; `BYPASSRLS`; the `SET LOCAL` versus `SET` distinction; the per-tenant cache prefix.

What the capstone uses: every tenant-scoped table has `FORCE ROW LEVEL SECURITY`; the `crunchreader_app` role is non-superuser; the `SET LOCAL app.current_tenant` runs in every transaction.

Reference: [PostgreSQL — Row Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

### Week 12 — Capstone

This week. The composition. The deploy. The post-mortem. The defence.

## 3.3 What you can build now that you could not in Week 1

A short list of the systems you can now build by yourself, or as the senior author on a small team. These are the artefacts a hiring manager will look for in a portfolio.

1. **A multi-tenant SaaS backend** — the capstone is the proof. The shape (Django admin + FastAPI public + Postgres + Redis) is the shape of 80% of the B2B SaaS services launched in 2026.
2. **A real-time dashboard backend** — WebSockets, Redis pub/sub, ARQ workers, the React/Vue/Svelte frontend that consumes the stream. The W8 and W9 work is the entire backend; the frontend is whatever framework you prefer.
3. **A search-backed content service** — the W10 work plus the W11 isolation plus the W7 API plus the W2 admin. Substack, Medium, and Ghost are this stack with different stylings.
4. **An internal tool with a Django admin** — the W2 / W3 / W5 / W6 stack alone is the entire "internal admin tool" a company of fifty people needs. Forty hours from idea to first deploy.
5. **A high-throughput public API** — the W7 / W9 / W11 stack. The FastAPI process under Gunicorn-with-Uvicorn-workers can serve 5 000 requests per second on a small machine.
6. **A migration runbook for a real project** — the W6 / W11 / W12 work. Every team needs someone who can answer "how do we add this column without dropping requests"; that someone is now you.

## 3.4 What you cannot do yet (and where C17 picks up)

C16 stopped here on purpose. The following are deliberately out of scope, because each is a course on its own; C17 (Crunch Pro Python Advanced) is the natural next step for several of them.

1. **Distributed systems**. Two nodes, one event log, the consistency model. CRDTs, Raft, Paxos. The capstone is one process per role; it does not have the failure modes of three replicas with a network partition between them. C17 has a unit on this.
2. **Event-driven architectures at scale**. Kafka, Pulsar, the "log is the source of truth" architecture. The capstone is request-response with a Redis pub/sub side channel; Kafka is the same shape times a thousand, with durability and consumer groups and back-pressure as first-class concerns.
3. **Observability beyond structured logs**. OpenTelemetry traces correlated with metrics correlated with logs; the SRE handbook on SLI/SLO/SLA; the alert design that does not page on every blip. The W12 stretch goal touches this; C17 spends a week on it.
4. **Container orchestration**. Kubernetes specifically. The capstone runs on platform-as-a-service that hides Kubernetes; the next layer up is Kubernetes itself, with the manifests, the operators, the autoscalers. Half-a-course on its own.
5. **Production database internals**. Beyond `EXPLAIN ANALYZE`. The Postgres MVCC model; the WAL; replication topologies; the `pg_stat_*` views in depth; the cost of every index page on writes. The W4 / W11 work touches the surface; a full course goes deeper.
6. **Security at the platform level**. AWS IAM, secrets rotation, the threat models, the supply-chain attacks. The W12 deploy section gives you the secrets-in-the-platform pattern; security as a discipline is bigger than the pattern.
7. **Machine learning in the request path**. Embedding models, vector search, retrieval-augmented generation. The W10 search work is keyword; the modern search has a vector component; the productionisation of that vector component is C17 / Crunch Wire territory.
8. **GraphQL**. The other API style. The capstone is REST; GraphQL is a worthwhile diversion for a different shape of client. Out of scope here; a chapter in C17.

C17 picks four of those eight (distributed systems, observability, K8s, ML in the request path) and goes deep on each. The C16 capstone is the prerequisite to enrol; the deployed URL plus the test suite is the entry ticket.

## 3.5 The skills the capstone proved

In hiring vocabulary, the capstone is evidence of the following:

- **Backend engineer (mid-level)**: can pick the right framework for the right problem; can model data in a relational store; can write queries that perform; can deploy and operate the service.
- **Site-reliability engineer (junior)**: can write a runbook; can perform a rollback; can rotate secrets without dropping traffic; can write a blameless post-mortem.
- **Full-stack engineer (back-leaning)**: can serve admin UI through Django templates and public API through FastAPI; can design the contracts that make a frontend team productive.
- **Data engineer (entry-level)**: can read `EXPLAIN ANALYZE`; can choose between index types; can move data with migrations that respect production constraints.
- **Security engineer (aware)**: can articulate why RLS matters; can articulate why the application role is not a superuser; can implement the OWASP API Top 10 controls.

The capstone is *not* evidence of senior-level work — it is one engineer's three-month project. It *is* evidence that you can be productive in the role from day one with light supervision, which is what mid-level hiring asks for.

## 3.6 The defence document

The capstone's `docs/defence.md` is the artefact you will reference in interviews. Ten questions, two paragraphs each. The questions are the ones that come up:

1. Why did you choose FastAPI for the public API and Django for the admin?
2. Why did you choose shared-schema multi-tenancy?
3. Why Postgres full-text search and not Elasticsearch?
4. Why Redis and not Memcached?
5. Why Fly.io (or Render, or Railway)?
6. How would you scale this to one million tenants?
7. How would you scale this to one hundred thousand requests per second?
8. What is the most likely production failure mode?
9. What did you cut from scope and why?
10. What would you change if you started over?

Write the document. Read it back. Practise the answers aloud. The interview that asks "tell me about your capstone" is the interview the document is for.

## 3.7 The walkthrough recording

Three minutes. No slides. Screen recording (QuickTime on Mac; OBS on Linux/Windows; both free). The script:

1. **0:00 — 0:30** — open the deployed URL. Log in as `acme` admin. Create an article. Show that the article appears.
2. **0:30 — 1:00** — open a second browser tab. Open a WebSocket connection (use a small `index.html` from the starter). Switch to the first tab. Create a second article. Show the second tab receiving the live event.
3. **1:00 — 1:30** — switch to the second tenant's admin (`globex`). Try to read the `acme` article by ID. Show the 404. Show the structured log line that proves the RLS policy filtered the query.
4. **1:30 — 2:30** — show the `/api/search?q=<term>` endpoint working. Switch to the third tenant (`initech`). Search for the same term. Show that the same query returns zero results because `initech` has no articles.
5. **2:30 — 3:00** — show the post-mortem document. Show the runbook. Show the GitHub repo's README.

Upload to YouTube unlisted; paste the link in the repo README; you are done.

## 3.8 What comes next (this Sunday and beyond)

- **Sunday morning**: the final exam (quiz.md). Forty-five minutes, twenty questions, no notes for the first ten and open-notes for the last ten.
- **Sunday afternoon**: the walkthrough recording, the LinkedIn post (if you choose), the celebration.
- **Monday morning**: open `docs/defence.md` and practise answering question 6 aloud. The first interview is whenever you choose; the practice is now.
- **The first week off-curriculum**: nothing. Take a week. Read a novel. The capstone is a marathon; rest is part of the training.
- **The first week back**: pick one of (a) the C17 advanced track if the prerequisites land for you; (b) a job application that links to the deployed URL; (c) your own side project that uses the capstone's shape.

## 3.9 The teaching team's note

This curriculum was built over twelve weeks of writing, in public, against a moving target of real-world Python web practice. Pydantic shipped v2 mid-arc; FastAPI's WebSocket auth pattern changed slightly between two minor versions; Postgres 16 became the supported floor halfway through. The W12 capstone is the version that matches the May 2026 reality of the field. By the time you read this in November 2026 or June 2027, two things will have changed (one library will have shipped a 2.0; one platform will have changed its free-tier ceiling) and ten things will not have changed (HTTP, SQL, the relational model, the cost of a wrong index, the value of a blameless post-mortem, the shape of a token bucket, the discipline of "every commit deploys", the comfort of a Django admin, the honesty of an `EXPLAIN ANALYZE`, the satisfaction of a green smoke test).

Carry the ten. Replace the two. Ship.

## 3.10 What W12 lecture 3 leaves you with

By the end of this lecture you should be able to describe each prior week's contribution to the capstone in one sentence, defend the architectural choices in writing, and identify the four C17 directions you are most curious about. The remaining work this week is the build itself; the lecture portion of C16 is complete.

## References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [WSGI — PEP 3333](https://peps.python.org/pep-3333/)
- [ASGI specification](https://asgi.readthedocs.io/)
- [Django — Documentation](https://docs.djangoproject.com/en/5.1/)
- [FastAPI — Documentation](https://fastapi.tiangolo.com/)
- [PostgreSQL — Documentation](https://www.postgresql.org/docs/16/)
- [Redis — Documentation](https://redis.io/docs/latest/)
- [Pydantic — Documentation](https://docs.pydantic.dev/latest/)
- [ARQ — Documentation](https://arq-docs.helpmanual.io/)
- [Twelve-Factor App](https://12factor.net/)
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [The OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x00-header/)
- [Designing Data-Intensive Applications](https://dataintensive.net/)
