"""Exercise 03 — Deploy dry-run: the pre-deploy checklist as a runnable linter.

The pre-deploy checklist is the file you wish someone had handed you on
your second on-call shift. Instead of memorising twenty things to check
before `fly deploy`, you encode them as a runnable script and you run
the script as the first step of every deploy.

This file is the linter. It loads the project's `infra/fly.toml`,
`Dockerfile`, `entrypoint.sh`, `requirements.txt`, and the `.env.example`
(but not the real `.env`); it inspects each for the W12 deploy contract
and reports any violation as a non-zero exit code.

Each check is a function returning a `CheckResult`. The runner aggregates
and prints. The script is part of the capstone's CI pipeline
(`.github/workflows/test.yml`) and runs locally with:

    python3 exercise-03-deploy-dry-run.py --project-root .

References:

  - https://fly.io/docs/reference/configuration/
  - https://docs.docker.com/develop/dev-best-practices/
  - https://12factor.net/
  - https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

Compile:

    python3 -m py_compile exercise-03-deploy-dry-run.py
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# CheckResult — the unit of output.
# ----------------------------------------------------------------------


class CheckResult(BaseModel):
    """The result of one check."""

    name: str = Field(..., min_length=3)
    passed: bool
    message: str = Field(default="")
    severity: str = Field(default="error", pattern=r"^(error|warning|info)$")


# ----------------------------------------------------------------------
# Sample artefacts — these are written when the file is run standalone
# so the linter has something to inspect even in the exercise directory.
# ----------------------------------------------------------------------


SAMPLE_FLY_TOML = """\
app = "multitenantcontenthub-acme"
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
"""


SAMPLE_DOCKERFILE = """\
# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
RUN python -m py_compile $(find . -name '*.py' -not -path './.venv/*') || true
EXPOSE 8000 8001
CMD ["./entrypoint.sh", "web"]
"""


SAMPLE_ENTRYPOINT = """\
#!/bin/sh
set -e
case "$1" in
  web)    exec gunicorn -k uvicorn.workers.UvicornWorker mtch.django_app.asgi:application --bind 0.0.0.0:8000 --workers 2 ;;
  api)    exec uvicorn mtch.fastapi_app.main:app --host 0.0.0.0 --port 8001 --workers 2 ;;
  worker) exec arq mtch.worker.WorkerSettings ;;
  migrate) exec python manage.py migrate --noinput ;;
  *) echo "Usage: $0 {web|api|worker|migrate}" ; exit 1 ;;
esac
"""


SAMPLE_REQUIREMENTS = """\
Django==5.1.3
fastapi==0.115.5
uvicorn[standard]==0.32.1
gunicorn==23.0.0
asyncpg==0.30.0
psycopg[binary]==3.2.3
pydantic==2.10.3
pydantic-settings==2.7.0
redis==5.2.1
arq==0.26.3
PyJWT==2.10.1
python-multipart==0.0.20
sse-starlette==2.1.3
structlog==24.4.0
"""


SAMPLE_ENV_EXAMPLE = """\
# Copy to .env for local development. NEVER commit .env to git.
DATABASE_URL=postgres://crunchreader_app:devpw@localhost:5432/mtch_dev
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=replace-me-with-secrets.token_urlsafe-64
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
"""


# ----------------------------------------------------------------------
# The project loader.
# ----------------------------------------------------------------------


@dataclass
class ProjectArtefacts:
    """Files the linter inspects. Missing files yield a failed check."""

    project_root: Path
    fly_toml: str | None = None
    dockerfile: str | None = None
    entrypoint: str | None = None
    requirements: str | None = None
    env_example: str | None = None
    missing: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> "ProjectArtefacts":
        artefacts = cls(project_root=root)
        for attr, candidates in {
            "fly_toml": ["infra/fly.toml", "fly.toml"],
            "dockerfile": ["Dockerfile"],
            "entrypoint": ["entrypoint.sh"],
            "requirements": ["requirements.txt"],
            "env_example": [".env.example", ".env.sample"],
        }.items():
            for cand in candidates:
                p = root / cand
                if p.exists() and p.is_file():
                    setattr(artefacts, attr, p.read_text(encoding="utf-8"))
                    break
            else:
                artefacts.missing.append(attr)
        return artefacts


# ----------------------------------------------------------------------
# The checks.
# ----------------------------------------------------------------------


def check_fly_toml_present(art: ProjectArtefacts) -> CheckResult:
    if art.fly_toml is None:
        return CheckResult(
            name="fly_toml_present",
            passed=False,
            message="No fly.toml found in infra/ or root.",
        )
    return CheckResult(name="fly_toml_present", passed=True)


def check_fly_toml_declares_three_processes(art: ProjectArtefacts) -> CheckResult:
    if art.fly_toml is None:
        return CheckResult(name="fly_toml_three_processes", passed=False, message="no fly.toml")
    required = ["web", "api", "worker"]
    missing = [p for p in required if f"{p}    =" not in art.fly_toml and f"{p} =" not in art.fly_toml]
    if missing:
        return CheckResult(
            name="fly_toml_three_processes",
            passed=False,
            message=f"missing process groups in [processes]: {', '.join(missing)}",
        )
    return CheckResult(name="fly_toml_three_processes", passed=True)


def check_fly_toml_has_release_command(art: ProjectArtefacts) -> CheckResult:
    if art.fly_toml is None:
        return CheckResult(name="fly_toml_release_command", passed=False, message="no fly.toml")
    if "release_command" not in art.fly_toml:
        return CheckResult(
            name="fly_toml_release_command",
            passed=False,
            message="missing release_command — migrations will not run on deploy",
        )
    return CheckResult(name="fly_toml_release_command", passed=True)


def check_fly_toml_has_health_checks(art: ProjectArtefacts) -> CheckResult:
    if art.fly_toml is None:
        return CheckResult(name="fly_toml_health_checks", passed=False, message="no fly.toml")
    if "http_checks" not in art.fly_toml:
        return CheckResult(
            name="fly_toml_health_checks",
            passed=False,
            message="no http_checks declared — platform cannot detect unhealthy machines",
        )
    return CheckResult(name="fly_toml_health_checks", passed=True)


def check_dockerfile_present(art: ProjectArtefacts) -> CheckResult:
    if art.dockerfile is None:
        return CheckResult(name="dockerfile_present", passed=False, message="no Dockerfile")
    return CheckResult(name="dockerfile_present", passed=True)


def check_dockerfile_pinned_python_minor(art: ProjectArtefacts) -> CheckResult:
    if art.dockerfile is None:
        return CheckResult(name="dockerfile_pinned_python", passed=False, message="no Dockerfile")
    match = re.search(r"FROM\s+python:(\d+\.\d+)", art.dockerfile)
    if match is None:
        return CheckResult(
            name="dockerfile_pinned_python",
            passed=False,
            message="Dockerfile does not pin a Python minor version (use python:3.12-slim, not python:slim)",
        )
    if match.group(1) < "3.12":
        return CheckResult(
            name="dockerfile_pinned_python",
            passed=False,
            severity="warning",
            message=f"Dockerfile uses Python {match.group(1)}; capstone targets 3.12+",
        )
    return CheckResult(name="dockerfile_pinned_python", passed=True)


def check_dockerfile_compiles_python(art: ProjectArtefacts) -> CheckResult:
    if art.dockerfile is None:
        return CheckResult(name="dockerfile_compiles_python", passed=False, message="no Dockerfile")
    if "py_compile" not in art.dockerfile:
        return CheckResult(
            name="dockerfile_compiles_python",
            passed=False,
            severity="warning",
            message="Dockerfile does not run `python -m py_compile` — syntax errors slip past the build",
        )
    return CheckResult(name="dockerfile_compiles_python", passed=True)


def check_entrypoint_handles_four_modes(art: ProjectArtefacts) -> CheckResult:
    if art.entrypoint is None:
        return CheckResult(name="entrypoint_four_modes", passed=False, message="no entrypoint.sh")
    required = ["web)", "api)", "worker)", "migrate)"]
    missing = [m for m in required if m not in art.entrypoint]
    if missing:
        return CheckResult(
            name="entrypoint_four_modes",
            passed=False,
            message=f"entrypoint.sh missing case branches: {', '.join(missing)}",
        )
    return CheckResult(name="entrypoint_four_modes", passed=True)


def check_requirements_pin_versions(art: ProjectArtefacts) -> CheckResult:
    if art.requirements is None:
        return CheckResult(name="requirements_pinned", passed=False, message="no requirements.txt")
    unpinned: list[str] = []
    for line in art.requirements.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Allow exact-version pins ("==") and constraint pins (">=", "~=")
        if "==" not in line and "~=" not in line and ">=" not in line:
            unpinned.append(line)
    if unpinned:
        return CheckResult(
            name="requirements_pinned",
            passed=False,
            message=f"requirements.txt has unpinned packages: {', '.join(unpinned[:3])}",
        )
    return CheckResult(name="requirements_pinned", passed=True)


def check_requirements_include_capstone_deps(art: ProjectArtefacts) -> CheckResult:
    if art.requirements is None:
        return CheckResult(name="requirements_capstone_deps", passed=False, message="no requirements.txt")
    required = {
        "django": "Django (W2 admin)",
        "fastapi": "FastAPI (W7 public API)",
        "asyncpg": "asyncpg (W7 async DB driver)",
        "redis": "redis-py (W9 cache)",
        "arq": "arq (W6/W8 background worker)",
        "pydantic": "pydantic (W7 schemas)",
    }
    body = art.requirements.lower()
    missing = [v for k, v in required.items() if k not in body]
    if missing:
        return CheckResult(
            name="requirements_capstone_deps",
            passed=False,
            message=f"missing capstone deps: {', '.join(missing)}",
        )
    return CheckResult(name="requirements_capstone_deps", passed=True)


def check_env_example_present(art: ProjectArtefacts) -> CheckResult:
    if art.env_example is None:
        return CheckResult(
            name="env_example_present",
            passed=False,
            message="no .env.example — onboarding new developers fails the 'one command to run' contract",
        )
    return CheckResult(name="env_example_present", passed=True)


def check_env_example_no_real_secrets(art: ProjectArtefacts) -> CheckResult:
    if art.env_example is None:
        return CheckResult(name="env_example_no_secrets", passed=False, message="no .env.example")
    # Heuristic: if SECRET_KEY contains > 16 base64-looking characters,
    # the file may be a real .env mistakenly named .env.example.
    if re.search(r"SECRET_KEY=[A-Za-z0-9_\-]{32,}", art.env_example):
        return CheckResult(
            name="env_example_no_secrets",
            passed=False,
            severity="error",
            message=".env.example appears to contain a real-looking SECRET_KEY. Replace with placeholder.",
        )
    if re.search(r"DATABASE_URL=postgres://[^:]+:[^@]{12,}@[^/]+/", art.env_example):
        return CheckResult(
            name="env_example_no_secrets",
            passed=False,
            severity="error",
            message=".env.example may contain a real DATABASE_URL with a real password. Replace with placeholder.",
        )
    return CheckResult(name="env_example_no_secrets", passed=True)


def check_django_debug_off_in_env_example(art: ProjectArtefacts) -> CheckResult:
    if art.env_example is None:
        return CheckResult(name="django_debug_off", passed=False, message="no .env.example")
    if "DEBUG=True" in art.env_example or "DEBUG=true" in art.env_example:
        return CheckResult(
            name="django_debug_off",
            passed=False,
            severity="warning",
            message=".env.example sets DEBUG=True; the default should be False (developers can override locally)",
        )
    return CheckResult(name="django_debug_off", passed=True)


# ----------------------------------------------------------------------
# The runner.
# ----------------------------------------------------------------------


ALL_CHECKS: list[Callable[[ProjectArtefacts], CheckResult]] = [
    check_fly_toml_present,
    check_fly_toml_declares_three_processes,
    check_fly_toml_has_release_command,
    check_fly_toml_has_health_checks,
    check_dockerfile_present,
    check_dockerfile_pinned_python_minor,
    check_dockerfile_compiles_python,
    check_entrypoint_handles_four_modes,
    check_requirements_pin_versions,
    check_requirements_include_capstone_deps,
    check_env_example_present,
    check_env_example_no_real_secrets,
    check_django_debug_off_in_env_example,
]


def write_sample_artefacts(root: Path) -> None:
    """Write the sample artefacts into a temp directory so the demo can run."""
    (root / "infra").mkdir(parents=True, exist_ok=True)
    (root / "infra" / "fly.toml").write_text(SAMPLE_FLY_TOML, encoding="utf-8")
    (root / "Dockerfile").write_text(SAMPLE_DOCKERFILE, encoding="utf-8")
    (root / "entrypoint.sh").write_text(SAMPLE_ENTRYPOINT, encoding="utf-8")
    (root / "requirements.txt").write_text(SAMPLE_REQUIREMENTS, encoding="utf-8")
    (root / ".env.example").write_text(SAMPLE_ENV_EXAMPLE, encoding="utf-8")


def render_result(r: CheckResult) -> str:
    icon = {"error": "FAIL", "warning": "WARN", "info": "INFO"}.get(r.severity, "----")
    status = "OK  " if r.passed else icon
    msg = f"  ({r.message})" if r.message else ""
    return f"  [{status}] {r.name}{msg}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Deploy dry-run linter for the W12 capstone.")
    parser.add_argument("--project-root", default=".", help="Path to the capstone project root.")
    parser.add_argument(
        "--use-samples",
        action="store_true",
        help="Write sample artefacts and lint them (for the demo).",
    )
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    if args.use_samples or not (root / "Dockerfile").exists():
        # Demo mode: write samples into a tmp dir.
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="mtch-deploy-lint-"))
        write_sample_artefacts(tmp)
        root = tmp
        print(f"Demo mode: linting sample artefacts in {root}")

    art = ProjectArtefacts.load(root)
    print(f"\nLinting project root: {art.project_root}")
    if art.missing:
        print(f"Missing files: {', '.join(art.missing)}\n")

    results = [chk(art) for chk in ALL_CHECKS]
    failed = [r for r in results if not r.passed and r.severity == "error"]
    warned = [r for r in results if not r.passed and r.severity == "warning"]

    for r in results:
        print(render_result(r))

    print()
    print(f"Summary: {len(results) - len(failed) - len(warned)} ok, {len(warned)} warning(s), {len(failed)} error(s)")

    if failed:
        print("\nDeploy NOT recommended. Fix the errors above and re-run.")
        return 1
    if warned:
        print("\nDeploy OK with warnings. Address before next deploy.")
    else:
        print("\nDeploy green-light.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
