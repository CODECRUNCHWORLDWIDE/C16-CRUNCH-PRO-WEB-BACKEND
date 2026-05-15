# Lecture 2 — Deploy to a free tier: Fly.io, Render, Railway

> *The first deploy is the hardest deploy. Every subsequent deploy is `git push`. The hard part is not the build; the hard part is the dozen tiny decisions about secrets, networking, health checks, migration timing, and what to do when the database password is wrong. We make those decisions in this lecture, then we deploy.*

## 2.1 The three targets, ranked by lecture preference

We have three free-tier options. All three will host the capstone. The lecture demonstrates Fly.io because it is the most flexible, most "infrastructure-as-real-code", and most representative of how production teams operate. Render is the simpler dashboard-first path; Railway is the cleanest provisioning experience. Pick one. The mini-project accepts any of the three. Do not split your effort across two until the stretch goal.

| Platform | Strength | Weakness | Free-tier ceiling |
|----------|----------|----------|--------------------|
| Fly.io | Real machines, real Postgres, multi-region; the `fly` CLI is excellent | Steeper learning curve; the platform is opinionated | One shared-CPU machine, 3 GB Postgres, 256 MB Redis |
| Render | Dashboard-first; the docs are the friendliest of the three | Less control over machine sizing; cold starts on the free tier | 750 build minutes/month, 100 GB bandwidth, free Postgres expires after 90 days |
| Railway | Cleanest "click and provision" UX; trial credit | Trial credit (not strictly free); requires GitHub auth | $5 trial credit; ~500 hours of compute |

The lecture walks the Fly.io path. The corresponding Render and Railway recipes are in `infra/render.yaml` and `infra/railway.json` in the starter; the trade-off is documented in `docs/deployment-targets.md`.

## 2.2 The Fly.io path, step by step

The path is six commands, in order, run from the capstone repository root. Each command is reproducible; each is idempotent on the second run.

```bash
# 1. Install the Fly CLI and log in.
curl -L https://fly.io/install.sh | sh
fly auth signup    # or: fly auth login

# 2. Launch the app from the repo. Reads fly.toml if present.
fly launch --no-deploy --name multitenantcontenthub-<your-handle>
# Generates the fly.toml if missing; we ship a hand-written one in infra/.

# 3. Provision Postgres in the same region as the app.
fly postgres create --name mtch-pg --region iad --vm-size shared-cpu-1x --volume-size 3
fly postgres attach --app multitenantcontenthub-<your-handle> mtch-pg
# This sets DATABASE_URL in the app's secrets automatically.

# 4. Provision Redis (Upstash via Fly).
fly redis create --name mtch-redis --region iad --plan free
# Capture the REDIS_URL it prints, then:
fly secrets set REDIS_URL="redis://..." --app multitenantcontenthub-<your-handle>

# 5. Set the remaining secrets.
fly secrets set \
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')" \
  ALLOWED_HOSTS="multitenantcontenthub-<your-handle>.fly.dev" \
  DEBUG="False" \
  --app multitenantcontenthub-<your-handle>

# 6. Deploy.
fly deploy --app multitenantcontenthub-<your-handle>
```

The deploy builds the Dockerfile, pushes the image to Fly's registry, starts the three process groups (`web`, `api`, `worker`), and runs the `release_command` (which is `entrypoint.sh migrate`). Total wall-clock time, first deploy: about three minutes on a clean account.

The capstone's `fly.toml` (in `infra/fly.toml`):

```toml
app = "multitenantcontenthub-<your-handle>"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[deploy]
  release_command = "./entrypoint.sh migrate"
  strategy = "rolling"

[env]
  PORT = "8000"
  LOG_LEVEL = "INFO"

[processes]
  web    = "./entrypoint.sh web"
  api    = "./entrypoint.sh api"
  worker = "./entrypoint.sh worker"

[[services]]
  processes = ["web"]
  internal_port = 8000
  protocol = "tcp"
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
  [[services.http_checks]]
    interval = "30s"
    timeout = "5s"
    method = "get"
    path = "/admin/healthz"

[[services]]
  processes = ["api"]
  internal_port = 8001
  protocol = "tcp"
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
  [[services.http_checks]]
    interval = "30s"
    timeout = "5s"
    method = "get"
    path = "/api/healthz"

[vm]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

Three processes; two services exposing port 443 with TLS handled by Fly; health checks on `/admin/healthz` and `/api/healthz`; one shared-CPU machine with 256 MB RAM. The free tier covers all of it.

Cite the [Fly.io `fly.toml` reference](https://fly.io/docs/reference/configuration/), the [Fly.io processes documentation](https://fly.io/docs/apps/processes/), and the [Fly.io health checks documentation](https://fly.io/docs/reference/configuration/#services-http_checks).

## 2.3 The health check endpoints

Every web process exposes a `/healthz` endpoint. The platform calls it; if it returns 200, the platform routes traffic; if it returns non-200 (or times out), the platform marks the process unhealthy and reroutes around it.

The Django side:

```python
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def healthz(request) -> JsonResponse:
    """Liveness probe. Always returns 200 if the process is up."""
    return JsonResponse({"status": "ok"})
```

The FastAPI side:

```python
@app.get("/api/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe. Returns 200 if the process can serve requests."""
    return {"status": "ok"}


@app.get("/api/readyz")
async def readyz(
    db: Annotated[asyncpg.Connection, Depends(get_db_no_tenant)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, str]:
    """Readiness probe. Verifies that the dependencies are reachable."""
    try:
        await db.fetchval("SELECT 1")
        await redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"not ready: {exc!s}")
    return {"status": "ready"}
```

The `/healthz` is the liveness probe — "is the process alive?". The `/readyz` is the readiness probe — "can the process serve requests?". Kubernetes makes the distinction sharp; Fly.io conflates them slightly but the convention is worth keeping. The W12 starter wires both. Cite the [Kubernetes liveness/readiness documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — the names are Kubernetes's contribution to the lexicon.

## 2.4 The release command and migration timing

Fly.io's `release_command` runs once per deploy, before the new image starts serving. We use it for migrations.

```toml
[deploy]
  release_command = "./entrypoint.sh migrate"
```

The order:

1. `fly deploy` builds the new image.
2. Fly.io starts a one-shot machine with the new image and runs `entrypoint.sh migrate`.
3. The migration runs to completion. If it fails, the deploy aborts and the previous image keeps serving.
4. If the migration succeeds, Fly.io starts the new `web`, `api`, and `worker` machines and drains the old ones.

The migration must be **forward-compatible with the old code**. The "add column nullable, deploy, backfill, deploy, set not-null, deploy" three-phase pattern is the W6 / W11 zero-downtime rule, applied at the platform level. The release-command pattern is documented at [Fly.io — Release command](https://fly.io/docs/reference/configuration/#the-deploy-section).

## 2.5 Secrets management

Secrets live in the platform's secret store. They are *not* in the repository. They are *not* in environment files committed to git. They are *not* in the Dockerfile.

The Fly.io commands:

```bash
# Set a secret.
fly secrets set KEY=value

# Set multiple secrets in one machine restart.
fly secrets set KEY1=value1 KEY2=value2

# List secret names (values are not shown).
fly secrets list

# Remove a secret (causes a machine restart).
fly secrets unset KEY

# Rotate the database password.
# 1. Generate a new password and update the Postgres role.
fly postgres connect -a mtch-pg
# postgres=# ALTER USER mtch_user WITH PASSWORD 'new-strong-password';
# 2. Update the secret.
fly secrets set DATABASE_URL="postgres://mtch_user:new-strong-password@..."
# 3. Fly.io restarts the app machines with the new secret.
```

The capstone has nine secrets. The complete list, with documentation, lives in `docs/secrets.md`. The list:

| Secret | Source | Rotation cadence |
|--------|--------|------------------|
| `DATABASE_URL` | `fly postgres attach` | When compromised; otherwise annually |
| `REDIS_URL` | `fly redis create` | When compromised; otherwise annually |
| `SECRET_KEY` | `secrets.token_urlsafe(64)` | Every six months |
| `JWT_SIGNING_KEY` | `secrets.token_urlsafe(64)` | Every six months (with overlap window) |
| `SENTRY_DSN` | Sentry dashboard | When the project is recreated |
| `EMAIL_HOST_PASSWORD` | SMTP provider | Quarterly |
| `S3_ACCESS_KEY` (if you add object storage) | Cloud provider | Quarterly |
| `S3_SECRET_KEY` (if you add object storage) | Cloud provider | Quarterly |
| `ADMIN_DEFAULT_PASSWORD` | `secrets.token_urlsafe(32)` (one-time use) | After first login |

Cite the [Fly.io secrets documentation](https://fly.io/docs/reference/secrets/).

## 2.6 Logs and metrics on the free tier

Fly.io ships every process's stdout/stderr to a built-in log aggregator. `fly logs --app multitenantcontenthub-<your-handle>` tails them. The output is line-oriented; the capstone emits structured JSON via `structlog`, so each line is parseable.

```bash
# Tail logs from all processes.
fly logs --app multitenantcontenthub-<your-handle>

# Filter to one process group.
fly logs --app multitenantcontenthub-<your-handle> --process-group api

# Search for a specific tenant.
fly logs --app multitenantcontenthub-<your-handle> | grep '"tenant_id":"<uuid>"'
```

Fly's built-in metrics show CPU, memory, and per-process restart counts. For per-tenant metrics — which the capstone exposes via the structured-log fields — the path is "ship the logs to a free-tier observability backend". Two free options:

1. **Logtail / BetterStack** at <https://betterstack.com/logtail> — 1 GB/month free; the Fly.io integration is a single `fly logs ship` command on their docs page.
2. **Axiom** at <https://axiom.co/> — 0.5 TB/month free; the Fly.io integration is well-documented.

The capstone does not require this; it is a stretch goal. The default log volume — about 50 MB/day for the capstone's test traffic — is easily inspected with `fly logs` alone.

## 2.7 The Render path

The Render path uses a `render.yaml` blueprint. The blueprint declares every service and every database in one file; Render's dashboard reads it and provisions everything.

```yaml
# render.yaml
services:
  - type: web
    name: mtch-django
    env: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: ./entrypoint.sh web
    plan: free
    healthCheckPath: /admin/healthz
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: mtch-pg
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: mtch-redis
          property: connectionString
      - key: SECRET_KEY
        generateValue: true
      - key: DEBUG
        value: "False"
  - type: web
    name: mtch-fastapi
    env: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: ./entrypoint.sh api
    plan: free
    healthCheckPath: /api/healthz
    envVars:
      - fromGroup: mtch-shared
  - type: worker
    name: mtch-worker
    env: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: ./entrypoint.sh worker
    plan: free
    envVars:
      - fromGroup: mtch-shared

databases:
  - name: mtch-pg
    plan: free
    postgresMajorVersion: 16

services:
  - type: redis
    name: mtch-redis
    plan: free
    ipAllowList: []
```

Push the repo to GitHub, point Render's dashboard at it, click "Apply Blueprint". The dashboard provisions Postgres, Redis, and all three services. The deploy hooks are git-push-driven: every push to `main` redeploys.

Cite the [Render Blueprint specification](https://render.com/docs/blueprint-spec).

## 2.8 The Railway path

The Railway path uses `railway.json` for declarative config plus the Railway CLI for the provisioning calls.

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "./entrypoint.sh api",
    "healthcheckPath": "/api/healthz",
    "healthcheckTimeout": 5,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

Plus the CLI:

```bash
railway login
railway init
railway add postgresql
railway add redis
railway up
railway domain   # prints the deployed URL
```

Cite the [Railway documentation](https://docs.railway.app/).

## 2.9 What we test before declaring "deployed"

The deploy is not done when `fly deploy` returns. The deploy is done when the smoke tests pass against the deployed URL.

```bash
# 1. Healthcheck passes.
curl -sf https://multitenantcontenthub-<handle>.fly.dev/api/healthz | tee
# {"status":"ok"}

# 2. Readiness passes (DB and Redis reachable).
curl -sf https://multitenantcontenthub-<handle>.fly.dev/api/readyz | tee
# {"status":"ready"}

# 3. Sign up the first tenant.
curl -sf -X POST https://multitenantcontenthub-<handle>.fly.dev/admin/signup \
  -H "Content-Type: application/json" \
  -d '{"slug":"acme","admin_email":"admin@acme.test","admin_password":"...","tenant_name":"Acme"}'
# {"tenant_id":"...","api_token":"..."}

# 4. Use the token to create an article.
TOKEN="..."
curl -sf -X POST https://multitenantcontenthub-<handle>.fly.dev/api/articles \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant: acme" \
  -H "Content-Type: application/json" \
  -d '{"title":"Hello world","body":"This is a test article."}'
# {"id":"...","title":"Hello world",...}

# 5. Search finds it (within 2 seconds; the indexer runs in the background).
sleep 3
curl -sf "https://multitenantcontenthub-<handle>.fly.dev/api/search?q=hello" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant: acme"
# [{"id":"...","title":"Hello world","rank":0.0607927,...}]

# 6. The WebSocket receives an event (use websocat or a small Python script).
websocat "wss://multitenantcontenthub-<handle>.fly.dev/ws?token=$TOKEN"
# Subscribe; then create another article from a different terminal; the event arrives.
```

These six checks are the "deployed" definition. They live in `tests/smoke/test_deployed.py` in the starter; they run against the deployed URL on a manual `pytest tests/smoke/ -v --base-url=...`.

## 2.10 The deployment runbook

The runbook is the cheat sheet for the four on-call procedures. The file is `docs/runbook.md`; the file is short on purpose.

### Procedure 1: Deploy a fix

1. Open the PR. CI must be green.
2. Merge to `main`.
3. `fly deploy` runs automatically (via the `.github/workflows/deploy.yml` workflow, if set up; otherwise manually).
4. Wait for the rolling restart to complete: `fly status --app multitenantcontenthub-<handle>`.
5. Run the six smoke-test commands from section 2.9.
6. If any fails, see Procedure 2.

### Procedure 2: Roll back

1. `fly releases --app multitenantcontenthub-<handle>` — find the last good release version.
2. `fly deploy --image registry.fly.io/multitenantcontenthub-<handle>:deployment-<previous-version>` — redeploy the previous image.
3. Wait for the rolling restart.
4. Run the smoke tests. If they pass, you have rolled back.
5. Write the post-mortem (Procedure 5).

### Procedure 3: Rotate the database password

1. `fly postgres connect -a mtch-pg`.
2. `ALTER USER mtch_user WITH PASSWORD 'new-password';`.
3. Update the secret: `fly secrets set DATABASE_URL="postgres://mtch_user:new-password@..."`.
4. Fly automatically restarts the app machines.
5. Verify with the smoke tests.

### Procedure 4: Evict a misbehaving tenant

1. Identify the tenant from the rate-limit 429 spike in the logs: `fly logs | grep '"status_code":429' | jq '.tenant_id' | sort | uniq -c | sort -nr | head`.
2. Connect to Postgres: `fly postgres connect -a mtch-pg`.
3. Set the tenant's rate-limit ceiling to zero: `UPDATE tenants SET rate_limit_override = 0 WHERE slug = '<slug>';`.
4. The next request from that tenant returns 429 immediately. The tenant is evicted in 60 seconds (the bucket TTL).
5. Notify the tenant via the admin email.

### Procedure 5: Write the post-mortem

The five-section template:

- **Timeline**: minute-by-minute, in UTC, from "first symptom observed" to "fully recovered".
- **Root cause**: one paragraph. The "five whys" should converge on the actual cause, not a proximate cause.
- **What went well**: the tools that worked, the alerts that fired, the runbook that was followed.
- **What did not**: the alerts that did not fire, the procedures that did not exist, the timing surprises.
- **What we changed**: the concrete commits, the new alerts, the new runbook sections.

The post-mortem template is in `docs/postmortem-template.md`. Cite the [Google SRE Book on post-mortems](https://sre.google/sre-book/postmortem-culture/).

## 2.11 The CI/CD wiring

The capstone's `.github/workflows/test.yml` runs on every push:

```yaml
name: tests
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: testpw
          POSTGRES_DB: mtch_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: python -m py_compile $(find . -name '*.py' -not -path './.venv/*')
      - run: python manage.py migrate
        env: { DATABASE_URL: "postgres://postgres:testpw@localhost:5432/mtch_test", REDIS_URL: "redis://localhost:6379/0" }
      - run: pytest -q
        env: { DATABASE_URL: "postgres://postgres:testpw@localhost:5432/mtch_test", REDIS_URL: "redis://localhost:6379/0" }
```

A `.github/workflows/deploy.yml` runs on every push to `main` *after* tests pass:

```yaml
name: deploy
on:
  push:
    branches: [main]
  workflow_run:
    workflows: ["tests"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    if: github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env: { FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }} }
```

The `FLY_API_TOKEN` is created with `fly auth token` and stored as a GitHub Actions secret. After this is wired, every green push to `main` is a production deploy.

Cite the [GitHub Actions documentation](https://docs.github.com/en/actions) and the [Fly.io GitHub Actions guide](https://fly.io/docs/app-guides/continuous-deployment-with-github-actions/).

## 2.12 The cost dashboard

We never want a surprise bill. The free tier is bounded, but a misconfiguration (the wrong VM size, the wrong region count, an accidental scale-up) can move the bill above zero. We pre-empt this with a one-page `docs/cost.md`:

```markdown
# Cost dashboard

| Item              | Free-tier ceiling                    | Current usage             | Alert threshold |
|-------------------|---------------------------------------|---------------------------|-----------------|
| Fly machine       | 3 shared-cpu-1x machines, 256 MB each | 3 / 3                     | n/a (at cap)    |
| Fly Postgres      | 3 GB storage                          | <100 MB (capstone seed)   | 2 GB            |
| Fly Redis         | 256 MB                                | <5 MB                     | 200 MB          |
| Egress            | 3 GB/month                            | ~100 MB/month             | 2 GB            |
| Build minutes     | unlimited on Fly                      | n/a                       | n/a             |

If any current value crosses the alert threshold, write the move-off-free-tier plan into `docs/scaling.md` before the next deploy.
```

Fly.io's billing dashboard at <https://fly.io/dashboard/personal/billing> shows the current usage. Check it weekly during the capstone.

## 2.13 What W12 lecture 2 leaves you with

By the end of this lecture you should be able to deploy the capstone end-to-end to Fly.io in six commands, have the smoke-test commands memorised, and have walked through the runbook once on the deployed service. Tomorrow's lecture closes the loop: a tour back through every prior week, ending with where C17 picks up.

## References

- [Fly.io — Hands-on with Fly](https://fly.io/docs/hands-on/)
- [Fly.io — Apps and machines](https://fly.io/docs/apps/)
- [Fly.io — `fly.toml` reference](https://fly.io/docs/reference/configuration/)
- [Fly.io — Processes](https://fly.io/docs/apps/processes/)
- [Fly.io — Postgres](https://fly.io/docs/postgres/)
- [Fly.io — Redis (Upstash)](https://fly.io/docs/reference/redis/)
- [Fly.io — Secrets](https://fly.io/docs/reference/secrets/)
- [Fly.io — Continuous deployment with GitHub Actions](https://fly.io/docs/app-guides/continuous-deployment-with-github-actions/)
- [Render — Blueprint spec](https://render.com/docs/blueprint-spec)
- [Render — Health checks](https://render.com/docs/deploys#health-checks)
- [Railway — Documentation](https://docs.railway.app/)
- [Kubernetes — Liveness, readiness, startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [GitHub Actions — Documentation](https://docs.github.com/en/actions)
- [Google SRE Book — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
