"""Exercise 04 — The runbook drill: deploy, roll back, rotate, evict.

The four on-call procedures from Lecture 2 are scripted here so the
class can drill them in a dry-run mode and observe the state changes
without touching a real cloud account.

The procedures encoded:

  1. `deploy`   — build, push, release, smoke-test.
  2. `rollback` — switch the live image back to the previous version.
  3. `rotate`   — rotate the Postgres password without dropping traffic.
  4. `evict`    — set a misbehaving tenant's rate limit to zero.

Each procedure is a sequence of steps; each step has a precondition,
an action, and a post-condition. The script verifies the pre and the
post; the action is a stubbed mutation against an in-memory model of
the platform.

Run:

    python3 exercise-04-runbook-drill.py deploy
    python3 exercise-04-runbook-drill.py rollback
    python3 exercise-04-runbook-drill.py rotate
    python3 exercise-04-runbook-drill.py evict --tenant globex
    python3 exercise-04-runbook-drill.py all

References:

  - https://sre.google/sre-book/postmortem-culture/
  - https://response.pagerduty.com/
  - https://fly.io/docs/reference/deploy/

Compile:

    python3 -m py_compile exercise-04-runbook-drill.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field, SecretStr

logger = logging.getLogger("capstone.runbook")


# ----------------------------------------------------------------------
# The platform model — a stand-in for Fly.io / Render / Railway state.
# ----------------------------------------------------------------------


class Release(BaseModel):
    """One release of the application (one image version)."""

    version: int = Field(..., ge=1)
    image_tag: str
    created_at: float
    status: str = Field(default="pending", pattern=r"^(pending|live|rolled-back|failed)$")


class TenantState(BaseModel):
    slug: str
    rate_limit_override: int | None = Field(default=None, ge=0)
    last_429_count: int = Field(default=0, ge=0)


class PlatformState(BaseModel):
    """The portion of the platform we model."""

    app_name: str
    db_password: SecretStr
    redis_url: str
    releases: list[Release] = Field(default_factory=list)
    tenants: list[TenantState] = Field(default_factory=list)

    def current_live_release(self) -> Release | None:
        for r in reversed(self.releases):
            if r.status == "live":
                return r
        return None

    def find_tenant(self, slug: str) -> TenantState | None:
        for t in self.tenants:
            if t.slug == slug:
                return t
        return None


def initial_state() -> PlatformState:
    return PlatformState(
        app_name="multitenantcontenthub-demo",
        db_password=SecretStr("initial_pw_change_me"),
        redis_url="redis://demo:6379/0",
        releases=[
            Release(version=1, image_tag="img-v1", created_at=time.time() - 86_400, status="rolled-back"),
            Release(version=2, image_tag="img-v2", created_at=time.time() - 3_600, status="live"),
        ],
        tenants=[
            TenantState(slug="acme"),
            TenantState(slug="globex", last_429_count=12),
            TenantState(slug="initech"),
        ],
    )


# ----------------------------------------------------------------------
# The Step contract — pre, action, post.
# ----------------------------------------------------------------------


@dataclass
class Step:
    name: str
    pre: Callable[[PlatformState], bool]
    action: Callable[[PlatformState], None]
    post: Callable[[PlatformState], bool]
    explanation: str = ""


@dataclass
class StepOutcome:
    name: str
    passed: bool
    detail: str = ""


def run_steps(state: PlatformState, steps: Iterable[Step]) -> list[StepOutcome]:
    outcomes: list[StepOutcome] = []
    for step in steps:
        if not step.pre(state):
            outcomes.append(StepOutcome(name=step.name, passed=False,
                                        detail="precondition not met"))
            return outcomes
        try:
            step.action(state)
        except Exception as exc:  # pragma: no cover
            outcomes.append(StepOutcome(name=step.name, passed=False,
                                        detail=f"action raised {type(exc).__name__}: {exc}"))
            return outcomes
        if not step.post(state):
            outcomes.append(StepOutcome(name=step.name, passed=False,
                                        detail="postcondition violated"))
            return outcomes
        outcomes.append(StepOutcome(name=step.name, passed=True))
    return outcomes


# ----------------------------------------------------------------------
# Procedure 1: Deploy.
# ----------------------------------------------------------------------


def procedure_deploy() -> list[Step]:

    def pre_has_live(s: PlatformState) -> bool:
        return s.current_live_release() is not None

    def push_new_image(s: PlatformState) -> None:
        last = max(r.version for r in s.releases)
        s.releases.append(Release(
            version=last + 1,
            image_tag=f"img-v{last + 1}",
            created_at=time.time(),
            status="pending",
        ))

    def post_new_pending(s: PlatformState) -> bool:
        return any(r.status == "pending" for r in s.releases)

    def run_migration(_s: PlatformState) -> None:
        # Simulate a migration; real path runs `entrypoint.sh migrate`.
        time.sleep(0.001)

    def post_after_migration(s: PlatformState) -> bool:
        # The migration is idempotent; the post-cond is just "still has a pending".
        return any(r.status == "pending" for r in s.releases)

    def cut_over(s: PlatformState) -> None:
        for r in s.releases:
            if r.status == "live":
                r.status = "rolled-back"
        for r in s.releases:
            if r.status == "pending":
                r.status = "live"
                break

    def post_one_live(s: PlatformState) -> bool:
        live = [r for r in s.releases if r.status == "live"]
        return len(live) == 1

    def smoke_test(_s: PlatformState) -> None:
        # Real path: hit /api/healthz, /api/readyz, create-and-fetch an article.
        time.sleep(0.001)

    return [
        Step("push_new_image", pre_has_live, push_new_image, post_new_pending,
             "Build, push, and stage the new image."),
        Step("run_migration", post_new_pending, run_migration, post_after_migration,
             "Run release_command before the new image goes live."),
        Step("cut_over", post_new_pending, cut_over, post_one_live,
             "Rolling restart: old machines drain, new machines take traffic."),
        Step("smoke_test", post_one_live, smoke_test, post_one_live,
             "Run the six smoke-test curl commands against the live URL."),
    ]


# ----------------------------------------------------------------------
# Procedure 2: Rollback.
# ----------------------------------------------------------------------


def procedure_rollback() -> list[Step]:

    def has_previous(s: PlatformState) -> bool:
        rolled = [r for r in s.releases if r.status == "rolled-back"]
        return len(rolled) >= 1

    def pick_previous(s: PlatformState) -> None:
        # The previous release is the most recent rolled-back one.
        candidates = [r for r in s.releases if r.status == "rolled-back"]
        candidates.sort(key=lambda r: r.created_at, reverse=True)
        # Store a reference by mutating a known slot.
        target = candidates[0]
        # Mark the current live as rolled-back; mark the target as live.
        for r in s.releases:
            if r.status == "live":
                r.status = "rolled-back"
        target.status = "live"

    def one_live(s: PlatformState) -> bool:
        return len([r for r in s.releases if r.status == "live"]) == 1

    def smoke_test(_s: PlatformState) -> None:
        time.sleep(0.001)

    return [
        Step("pick_previous_release", has_previous, pick_previous, one_live,
             "Find the most recent good release and redeploy its image."),
        Step("smoke_test_post_rollback", one_live, smoke_test, one_live,
             "Confirm the rolled-back image is healthy."),
    ]


# ----------------------------------------------------------------------
# Procedure 3: Rotate the database password.
# ----------------------------------------------------------------------


def procedure_rotate() -> list[Step]:

    captured_pre: dict[str, str] = {}

    def pre_password_set(s: PlatformState) -> bool:
        captured_pre["pw"] = s.db_password.get_secret_value()
        return len(captured_pre["pw"]) >= 8

    def generate_new_password(s: PlatformState) -> None:
        import secrets as sec
        new_pw = sec.token_urlsafe(32)
        s.db_password = SecretStr(new_pw)

    def post_password_changed(s: PlatformState) -> bool:
        return s.db_password.get_secret_value() != captured_pre["pw"]

    def update_secret(s: PlatformState) -> None:
        # In real Fly.io: fly secrets set DATABASE_URL=...
        # Here we just record the rotation.
        time.sleep(0.001)

    def smoke_test_with_new_password(_s: PlatformState) -> None:
        time.sleep(0.001)

    return [
        Step("generate_new_password", pre_password_set, generate_new_password, post_password_changed,
             "Generate a 32-character URL-safe random password."),
        Step("update_platform_secret", post_password_changed, update_secret, post_password_changed,
             "`fly secrets set DATABASE_URL=...` causes a rolling restart."),
        Step("smoke_test_post_rotation", post_password_changed, smoke_test_with_new_password, post_password_changed,
             "Confirm the service reads the new password."),
    ]


# ----------------------------------------------------------------------
# Procedure 4: Evict a misbehaving tenant.
# ----------------------------------------------------------------------


def procedure_evict(slug: str) -> list[Step]:

    def pre_tenant_exists(s: PlatformState) -> bool:
        return s.find_tenant(slug) is not None

    def set_rate_limit_to_zero(s: PlatformState) -> None:
        t = s.find_tenant(slug)
        if t is None:
            raise RuntimeError(f"tenant {slug} not found")
        t.rate_limit_override = 0

    def post_tenant_rate_zero(s: PlatformState) -> bool:
        t = s.find_tenant(slug)
        return t is not None and t.rate_limit_override == 0

    def verify_429s_decline(_s: PlatformState) -> None:
        # Real path: tail the logs for 60 seconds; the bucket TTL is 60s.
        time.sleep(0.001)

    return [
        Step("identify_tenant", pre_tenant_exists, lambda _s: None, pre_tenant_exists,
             "Confirm the tenant exists in the platform state."),
        Step("set_rate_limit_zero", pre_tenant_exists, set_rate_limit_to_zero, post_tenant_rate_zero,
             "UPDATE tenants SET rate_limit_override = 0 WHERE slug = $1."),
        Step("verify_429s_decline_in_logs", post_tenant_rate_zero, verify_429s_decline, post_tenant_rate_zero,
             "Tail the logs; confirm 429s for this tenant taper to zero."),
    ]


# ----------------------------------------------------------------------
# CLI.
# ----------------------------------------------------------------------


def render_outcomes(name: str, outcomes: list[StepOutcome]) -> bool:
    print(f"\n=== {name.upper()} ===")
    ok = True
    for o in outcomes:
        marker = "[ok]  " if o.passed else "[FAIL]"
        detail = f" — {o.detail}" if o.detail else ""
        print(f"  {marker} {o.name}{detail}")
        if not o.passed:
            ok = False
    print(f"  Result: {'PASSED' if ok else 'FAILED'}")
    return ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Drill the W12 capstone runbook.")
    parser.add_argument("procedure",
                        choices=["deploy", "rollback", "rotate", "evict", "all"],
                        help="Which procedure to drill.")
    parser.add_argument("--tenant", default="globex",
                        help="Tenant slug for the `evict` procedure.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    state = initial_state()
    print(f"Initial state: {len(state.releases)} releases, {len(state.tenants)} tenants")
    print(f"Live release: v{state.current_live_release().version if state.current_live_release() else 'none'}")

    all_passed = True

    if args.procedure in ("deploy", "all"):
        outcomes = run_steps(state, procedure_deploy())
        all_passed &= render_outcomes("deploy", outcomes)

    if args.procedure in ("rollback", "all"):
        outcomes = run_steps(state, procedure_rollback())
        all_passed &= render_outcomes("rollback", outcomes)

    if args.procedure in ("rotate", "all"):
        outcomes = run_steps(state, procedure_rotate())
        all_passed &= render_outcomes("rotate", outcomes)

    if args.procedure in ("evict", "all"):
        outcomes = run_steps(state, procedure_evict(args.tenant))
        all_passed &= render_outcomes(f"evict ({args.tenant})", outcomes)

    print()
    print(f"Final state: {len(state.releases)} releases, "
          f"live release v{state.current_live_release().version if state.current_live_release() else 'none'}")
    target = state.find_tenant(args.tenant)
    if target is not None:
        print(f"Tenant '{args.tenant}': rate_limit_override = {target.rate_limit_override}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
