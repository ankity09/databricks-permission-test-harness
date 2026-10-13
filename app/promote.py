"""Non-mutating promote handoff.

When a test passes and the admin wants to grant the SAME permission to a real
user/group, this module does TWO non-mutating things:
  1. Renders the exact, validated GRANT SQL for the chosen real principal.
  2. Builds a Unity Catalog Explorer deep-link so the admin finishes the grant
     natively, where it is governed and audited.

HARD INVARIANT: this module MUST NOT call any grant API. It is pure string
building. Real grants to real principals happen ONLY in Unity Catalog.

Principal validation: rejects principals containing backticks, quotes, semicolons,
comment markers, or newlines. All validated principals are backtick-quoted for safe
SQL rendering.
"""

from __future__ import annotations

from app.catalog import load_catalog, resolve
from app.models import PromoteInfo


class PrincipalValidationError(ValueError):
    """Raised when a principal name is invalid or contains injection attempts."""


def _validate_principal(principal: str) -> None:
    """Validate a principal name to prevent SQL injection in promote output.

    Rejects backticks, quotes, semicolons, comment markers, newlines.
    Raises PrincipalValidationError if invalid.
    """
    if not principal:
        raise PrincipalValidationError("Principal must be a non-empty string.")

    dangerous_chars = ["`", "'", '"', ";", "\n", "\r", "--", "/*", "*/"]
    for char_or_str in dangerous_chars:
        if char_or_str in principal:
            raise PrincipalValidationError(
                f"Principal {principal!r} contains invalid character {char_or_str!r}. "
                f"Principal must be an email or group name without special SQL characters."
            )


def _quote_principal(principal: str) -> str:
    """Backtick-quote a principal for safe embedding in SQL."""
    # Escape any backticks by doubling them.
    escaped = principal.replace("`", "``")
    return f"`{escaped}`"


def _uc_deep_link(host: str, action_id: str, securable: str) -> str:
    """Build the UC Explorer deep-link for the securable.

    UC Explorer paths are of the form:
        {host}/explore/data/<catalog>/<schema>/<table>
    We map the dotted securable onto that path. For catalog/schema-only
    securables the trailing segments are simply omitted.
    """
    host = host.rstrip("/")
    parts = [p for p in securable.split(".") if p]
    path = "/".join(parts)
    return f"{host}/explore/data/{path}"


def build_promote_info(
    *,
    action_id: str,
    securable: str,
    principal: str,
    host: str,
    catalog=None,
) -> PromoteInfo:
    """Return validated GRANT SQL + UC deep-link for promoting to a real principal.

    Validates the principal and securables before rendering. Does NOT execute anything.
    Raises PrincipalValidationError if the principal is invalid.
    """
    _validate_principal(principal)

    catalog = catalog if catalog is not None else load_catalog()
    descriptor = catalog[action_id]
    grant_sql = resolve(descriptor.grant_sql, securable=securable, sp=principal)
    return PromoteInfo(
        grant_sql=grant_sql,
        uc_deep_link=_uc_deep_link(host, action_id, securable),
    )
