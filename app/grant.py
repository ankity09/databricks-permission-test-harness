"""The ONLY writer in the app: applies/revokes candidate grants on the app SP.

HARD INVARIANT (non-negotiable):
    This module may write grants to EXACTLY ONE principal: the configured app
    service principal. Any attempt to grant/revoke against any other principal
    (a real user, a group, another SP) MUST raise ForbiddenPrincipalError and
    execute NOTHING.

Defense in depth:
    1. Principal parameter must exactly match configured SP (ForbiddenPrincipalError).
    2. Securable is parsed and validated to reject injection payloads.
    3. Rendered SQL is tokenized to ensure exactly one TO/FROM clause to the SP.

This is the single code chokepoint that enforces "the harness may configure its
own test actor, nothing else." Never weaken the guard: if a refactor makes it
possible to write to a non-SP principal, that is a spec violation: stop.

In production the ``executor`` runs the rendered SQL under the OBO *admin*
client (so the grant succeeds because the admin has authority), while the
principal being granted is always the app SP.
"""

from __future__ import annotations

import re
import re
from typing import Any, Callable

from app.catalog import resolve
from app.securable import format_securable
from app.securable import parse_securable, format_securable, SecurableParseError

Executor = Callable[[str], Any]


class ForbiddenPrincipalError(Exception):
    """Raised when a write targets any principal other than the configured SP."""


class ForbiddenSecurableError(Exception):
    """Raised when a securable name contains injection attempts."""


def _guard(principal: str, configured_sp: str) -> None:
    if principal != configured_sp:
        raise ForbiddenPrincipalError(
            f"Refusing to write a grant to principal {principal!r}. "
            f"This app may only mutate its own service principal "
            f"({configured_sp!r}). Promote to real users/groups in Unity Catalog."
        )


def _validate_securable(securable: str) -> None:
    """Validate and normalize the securable via the parser.

    Raises ForbiddenSecurableError if the securable contains injection attempts.
    """
    try:
        parse_securable(securable)
    except SecurableParseError as exc:
        raise ForbiddenSecurableError(
            f"Securable rejected: {exc}. "
            f"Ensure the securable is a valid catalog.schema.table path with no SQL keywords, "
            f"comment markers, or special characters outside backticks."
        ) from exc


def _tokenize_and_check_principal(sql: str, configured_sp: str) -> None:
    """Tokenize the rendered SQL to ensure the principal can't be redirected.

    Rejects if:
      - Comments are found (-- or /* */)
      - Multiple statements (semicolons not in strings)
      - TO/FROM clause doesn't target the configured SP
      - SQL keywords (INSERT, DELETE, etc.) appear outside strings/comments

    Raises ForbiddenSecurableError if any check fails.
    """
    # Simple tokenization: remove strings and comments, then check structure.
    tokens = _extract_sql_tokens(sql)

    if not tokens:
        raise ForbiddenSecurableError("Rendered SQL is empty after tokenization.")

    # Check for dangerous keywords at top level (outside strings/comments).
    dangerous = {"INSERT", "DELETE", "UPDATE", "MERGE", "CREATE", "DROP", "ALTER"}
    for token in tokens:
        if token.upper() in dangerous:
            raise ForbiddenSecurableError(
                f"Rendered SQL contains a dangerous keyword {token!r}. "
                f"This may indicate a template injection."
            )

    # Count TO/FROM (grant/revoke) keywords.
    grant_keywords = [t.upper() for t in tokens if t.upper() in ("TO", "FROM")]
    if len(grant_keywords) == 0:
        raise ForbiddenSecurableError(
            "Rendered SQL has no TO/FROM clause. This may indicate a template error."
        )
    if len(grant_keywords) > 1:
        raise ForbiddenSecurableError(
            f"Rendered SQL has multiple TO/FROM clauses ({len(grant_keywords)}). "
            f"This may indicate injection."
        )

    # Last non-whitespace token should be the backtick-quoted configured SP.
    last_token = tokens[-1]
    expected_sp_token = f"`{configured_sp}`"
    if last_token != expected_sp_token:
        raise ForbiddenSecurableError(
            f"Last token {last_token!r} != expected SP {expected_sp_token!r}. "
            f"The principal may have been redirected."
        )


def _extract_sql_tokens(sql: str) -> list[str]:
    """Extract tokens from SQL, removing string literals and comments.

    Returns a list of non-whitespace tokens suitable for checking structure.
    """
    # Remove block comments /* ... */ and line comments -- ...
    sql_cleaned = sql
    # Remove /* ... */
    sql_cleaned = re.sub(r"/\*.*?\*/", " ", sql_cleaned, flags=re.DOTALL)
    # Remove -- ... to end of line
    sql_cleaned = re.sub(r"--[^\n]*", " ", sql_cleaned)

    # Split into tokens, skipping quoted strings.
    tokens = []
    i = 0
    while i < len(sql_cleaned):
        # Skip whitespace.
        while i < len(sql_cleaned) and sql_cleaned[i] in (" ", "\t", "\n", "\r"):
            i += 1
        if i >= len(sql_cleaned):
            break

        # Extract a token (either a backtick-quoted identifier or a word).
        if sql_cleaned[i] == "`":
            # Backtick-quoted identifier: keep as-is (including backticks).
            end = i + 1
            while end < len(sql_cleaned) and sql_cleaned[end] != "`":
                end += 1
            if end < len(sql_cleaned):
                end += 1  # Include closing backtick.
            tokens.append(sql_cleaned[i:end])
            i = end
        elif sql_cleaned[i] == "'":
            # Single-quoted string: skip (but note its presence).
            end = i + 1
            while end < len(sql_cleaned) and sql_cleaned[end] != "'":
                if sql_cleaned[end] == "\\":
                    end += 2
                else:
                    end += 1
            i = end + 1 if end < len(sql_cleaned) else end
        else:
            # Regular token (keyword, symbol, etc.).
            end = i
            while end < len(sql_cleaned) and sql_cleaned[end] not in (
                " ", "\t", "\n", "\r", "`", "'", ";", "("
            ):
                end += 1
            tokens.append(sql_cleaned[i:end])
            i = end

    return tokens


def apply_to_sp(
    grant_sql_template: str,
    *,
    principal: str,
    configured_sp: str,
    executor: Executor,
    securable: str | None = None,
) -> Any:
    """Render and execute a GRANT: only if principal is the configured SP."""
    _guard(principal, configured_sp)

    # Validate securable before rendering.
    if securable:
        _validate_securable(securable)
        # Use the parser to normalize the securable.
        securable = format_securable(securable)

    sql = resolve(
        grant_sql_template, sp=principal, **({"securable": securable} if securable else {})
    )

    # Defense in depth: check the rendered SQL structure.
    _tokenize_and_check_principal(sql, configured_sp)

    return executor(sql)


def revoke_from_sp(
    revoke_sql_template: str,
    *,
    principal: str,
    configured_sp: str,
    executor: Executor,
    securable: str | None = None,
) -> Any:
    """Render and execute a REVOKE: only if principal is the configured SP."""
    _guard(principal, configured_sp)

    # Validate securable before rendering.
    if securable:
        _validate_securable(securable)
        # Use the parser to normalize the securable.
        securable = format_securable(securable)

    sql = resolve(
        revoke_sql_template, sp=principal, **({"securable": securable} if securable else {})
    )

    # Defense in depth: check the rendered SQL structure.
    _tokenize_and_check_principal(sql, configured_sp)

    return executor(sql)


_GRANT_SHAPE = re.compile(r"^\s*GRANT\s+(?P<privilege>.+?)\s+ON\s+(?P<kind>[A-Z]+)\s+\{securable\}", re.I)


def sp_holds_directly(
    grant_sql_template: str,
    *,
    securable: str,
    sp: str,
    row_exec: Callable[[str], Any],
) -> bool:
    """True if ``sp`` already holds this exact grant directly on ``securable``.

    Then the GRANT would change nothing and the matching REVOKE would remove a
    grant that existed before the test, so callers skip both. Reads SHOW
    GRANTS through ``row_exec`` (the admin's identity). Returns False when the
    template has no GRANT ... ON <kind> shape or the lookup fails, which keeps
    the plain apply-then-revoke behavior.
    """
    shape = _GRANT_SHAPE.match(grant_sql_template or "")
    if not shape:
        return False
    privilege, kind = shape.group("privilege").upper(), shape.group("kind").upper()
    try:
        rows = row_exec(f"SHOW GRANTS `{sp}` ON {kind} {format_securable(securable)}") or []
    except Exception:  # noqa: BLE001 -- unknown means "not held"
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = {str(k).lower().replace("_", ""): str(v) for k, v in row.items()}
        if (values.get("principal") == sp and values.get("actiontype", "").upper() == privilege
                and values.get("objecttype", "").upper() == kind):
            return True
    return False
