"""The ONLY writer in the app — applies/revokes candidate grants on the app SP.

HARD INVARIANT (non-negotiable, spec section 1):
    This module may write grants to EXACTLY ONE principal: the configured app
    service principal. Any attempt to grant/revoke against any other principal
    (a real user, a group, another SP) MUST raise ForbiddenPrincipalError and
    execute NOTHING.

This is the single code chokepoint that enforces "the harness may configure its
own test actor, nothing else." Never weaken the guard: if a refactor makes it
possible to write to a non-SP principal, that is a spec violation — stop.

In production the ``executor`` runs the rendered SQL under the OBO *admin*
client (so the grant succeeds because the admin has authority), while the
principal being granted is always the app SP.
"""

from __future__ import annotations

from typing import Any, Callable

from app.catalog import resolve

Executor = Callable[[str], Any]


class ForbiddenPrincipalError(Exception):
    """Raised when a write targets any principal other than the configured SP."""


def _guard(principal: str, configured_sp: str) -> None:
    if principal != configured_sp:
        raise ForbiddenPrincipalError(
            f"Refusing to write a grant to principal {principal!r}. "
            f"This app may only mutate its own service principal "
            f"({configured_sp!r}). Promote to real users/groups in Unity Catalog."
        )


def apply_to_sp(
    grant_sql_template: str,
    *,
    principal: str,
    configured_sp: str,
    executor: Executor,
    securable: str | None = None,
) -> Any:
    """Render and execute a GRANT — only if principal is the configured SP."""
    _guard(principal, configured_sp)
    sql = resolve(grant_sql_template, sp=principal, **({"securable": securable} if securable else {}))
    return executor(sql)


def revoke_from_sp(
    revoke_sql_template: str,
    *,
    principal: str,
    configured_sp: str,
    executor: Executor,
    securable: str | None = None,
) -> Any:
    """Render and execute a REVOKE — only if principal is the configured SP."""
    _guard(principal, configured_sp)
    sql = resolve(revoke_sql_template, sp=principal, **({"securable": securable} if securable else {}))
    return executor(sql)
