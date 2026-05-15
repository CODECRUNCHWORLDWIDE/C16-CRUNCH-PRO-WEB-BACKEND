# Challenge 1 — The RLS leak hunt

**Time**: ~2 hours.

**Goal**: A small multi-tenant FastAPI service is provided (or, equivalently, you build one from the Exercise 3 starter). It has three subtle tenant-isolation bugs. Find them, prove each one by reproducing the leak, and write the fix as a unit test that fails on the bug and passes on the fix.

The exercise is half forensic work and half engineering. You learn more from finding a leak in someone else's code than from being told one exists in yours.

## The deliverable

A file `LEAK-HUNT.md` with:

1. The three bugs, one per section, each titled with a short summary.
2. For each bug:
   - The exact location in the code (file + line).
   - The exploit — a `curl` command (or `httpx` snippet) that demonstrates the leak.
   - The expected behaviour (what should have happened).
   - The actual behaviour (what did happen).
   - The fix (the corrected code).
   - The unit test that, against the *unfixed* code, fails — and against the *fixed* code, passes.
3. A two-paragraph summary on which bug was hardest to find and why.

The deliverable is shareable. If you find this challenge productive, run it against your own multi-tenant service.

## The starter service

You can build the leak-prone service from scratch using the patterns from Exercise 3, or use the starter that ships at `mini-project/starter/`. The three bugs below are also present in the mini-project starter — but as future-self gifts, not as deliberate teaching tools.

The starter has these features:

- `GET /articles` — list the current tenant's articles.
- `GET /articles/{id}` — read one.
- `POST /articles` — create one.
- `GET /admin/stats` — return aggregate counts (article count, author count, total body bytes).
- `GET /search?q=...` — full-text search across the current tenant's articles.
- `GET /export` — return a `.json` dump of every article the current tenant owns.

Six endpoints. Three of them have isolation bugs. Find them.

## Bug 1: the `SET LOCAL` that is not local

**Hint**: read the `get_db` dependency. Look at the order in which `SET LOCAL` and `BEGIN` happen. There is a version of this code where `SET LOCAL` is called *outside* an explicit transaction.

**Reproducing the bug**: send a request as Tenant A; immediately send a request as Tenant B *to a different endpoint*; observe that Tenant B's response includes data from Tenant A's tenant context. (You may need to send requests rapidly, or have multiple worker processes, to manifest the bug — `SET LOCAL` outside a transaction is a `WARNING`, not an error, and one of two things happens: the parameter is not set at all, or it is set at session scope. Both are bugs; the second is the dangerous one.)

**The fix**: open `async with conn.transaction():` before the `SET LOCAL`. The `await conn.execute("SET LOCAL ...")` must be inside the transaction context manager. The exercise 3 solution shows the right shape.

**Test**: a `pytest` test that opens two connections from the same pool, sets tenant A on one, runs a query on the other (without setting context), and asserts the query fails (or returns zero rows, depending on the exact bug variant). The test should not pass against the buggy code.

## Bug 2: the admin endpoint that bypasses RLS

**Hint**: read the `/admin/stats` endpoint. It uses a different DB session pattern than the other endpoints. There may be a `SECURITY DEFINER` function, or a direct `BYPASSRLS`-role connection, or the endpoint may not call `get_db` at all.

**Reproducing the bug**: send a request to `/admin/stats` as Tenant A; compare the response to manually counting Tenant A's rows. If the counts include Tenant B's data, the endpoint is leaking.

The justification for an admin endpoint to bypass RLS is sometimes legitimate (aggregate stats *across* tenants), but the question is *who is allowed to call it*. An `/admin/stats` endpoint that any tenant can call is a global-stats leak. The right shape is either:
- The endpoint is restricted to an `admin` role (and the application authorises on the JWT or the IAM identity, not the tenant ID).
- The endpoint is tenant-scoped (it does respect RLS) and any "cross-tenant aggregation" lives in a separate internal service.

**The fix**: either restrict the endpoint to admins (and document the authorisation) or make it tenant-scoped (and rename it `/articles/stats`, since "admin" is misleading). The leak-hunt write-up explains the trade-off.

**Test**: a `pytest` test that calls `/admin/stats` as Tenant A and asserts the response only includes Tenant A's data. If the endpoint is intentionally cross-tenant, the test should call as a non-admin user and assert a 403.

## Bug 3: the cache that crosses tenants

**Hint**: read the `/search` endpoint. It caches the search results. Look at the cache key.

**Reproducing the bug**: as Tenant A, search for `"secret"` (or any term that matches Tenant A's articles). As Tenant B (immediately after), search for the same term. If Tenant B sees Tenant A's articles in the response, the cache key did not include the tenant ID.

**The fix**: change the cache key from `search:{query_hash}` to `tenant:{tenant_id}:search:{query_hash}`. Six bytes more of cache key; six orders of magnitude less risk.

**Test**: a `pytest` test that performs the sequence above and asserts Tenant B's results do not contain Tenant A's articles. The test must clear the cache between runs (or use a different query string each time) to be deterministic.

## How to find these bugs systematically

Three techniques that work in practice:

1. **Read the dependency tree.** For every endpoint, follow the `Depends(...)` chain. Note which endpoints use `get_db` versus a different DB accessor. Note which dependencies set `app.current_tenant` and which do not. Anywhere the dependency chain "forgets" the tenant context is a candidate bug.
2. **Read every cache key.** Search the codebase for `redis.set`, `redis.get`, `redis.delete`, and any wrapper functions. Inspect every key for the tenant prefix. The day-one rule is "every key has the tenant ID in it"; deviations are bugs.
3. **Read every direct SQL string.** Search the codebase for `fetch(`, `execute(`, `fetchrow(`, `fetchval(`. For every tenant-scoped table named in the SQL, the query should either (a) be on a connection with `app.current_tenant` set (and rely on RLS) or (b) have an explicit `WHERE tenant_id = ...` clause. Anything else is a candidate bug.

The pattern that works for the rest of your career is: **every tenant-scoped resource has the tenant ID in its access path**, and the access path is reviewable in five minutes. If you cannot identify the tenant ID in a query's path within five minutes of reading it, the query is suspicious.

## Stretch goal: write a fourth bug

Add your own tenant-isolation bug to the starter (in a branch you do not push). Submit it to a peer for hunting. The peer's job is to find it; your job is to make it subtle enough to be educational but not so subtle that it requires a debugger.

Some bug ideas:

- A migration script that runs as the `postgres` superuser and modifies rows without RLS — leaving the rows correct but the journal showing cross-tenant access.
- A background job that polls `articles` without setting `app.current_tenant` — the job runs as a service account; the service account might have `BYPASSRLS`; the job's `for tenant in get_all_tenants(): process(tenant)` loop might be missing the `SET LOCAL` between iterations.
- A foreign-key cascade that deletes rows in another tenant's table when a tenant is deleted (you wired the FK wrong; tenant_id should not be the source of a cascade to a *different* tenant's row).

The discipline of writing tenant-isolation bugs sharpens the eye for finding them. Apply once a quarter to your own service.

## Cited

- Postgres docs — Row Security Policies: <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- AWS SaaS Lens — Tenant isolation: <https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-isolation.html>
- Crunchy Data — Postgres RLS for SaaS: <https://www.crunchydata.com/blog/postgres-row-level-security-for-multi-tenant-saas>
