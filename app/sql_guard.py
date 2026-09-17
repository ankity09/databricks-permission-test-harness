"""Read-only SQL guard for the query runner's free-text box (Feature 1).

This is the single security chokepoint that keeps the harness read-only. It is
allowlist-based (reject-by-default): only statements whose first real keyword is
SELECT / WITH / SHOW / DESCRIBE / DESC / EXPLAIN are permitted, and only a
single statement at a time. Anything else raises ReadOnlyViolation.

Applied at the API layer BEFORE any client is built, so a blocked statement
never reaches the app service principal.
"""

from __future__ import annotations

import re

_MESSAGE = (
    "Blocked: this is a read-only harness. "
    "Only SELECT / SHOW / DESCRIBE / EXPLAIN are allowed."
)

_ALLOWED_LEADING = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}

# Block comments /* ... */ (non-greedy, across newlines) and line comments --...
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")


class ReadOnlyViolation(ValueError):
    """Raised when a statement is not a safe, single, read-only statement."""


def _strip_comments(sql: str) -> str:
    prev = None
    cur = sql
    # Iterate so nested/sequential comments are fully removed.
    while cur != prev:
        prev = cur
        cur = _BLOCK_COMMENT.sub(" ", cur)
        cur = _LINE_COMMENT.sub(" ", cur)
    return cur


def assert_read_only(sql: str) -> None:
    """Raise ReadOnlyViolation unless ``sql`` is a single read-only statement."""
    cleaned = _strip_comments(sql or "").strip()

    # Reject multiple statements: drop one optional trailing ';', then any
    # remaining non-empty ';'-separated segment means more than one statement.
    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    segments = [seg for seg in body.split(";") if seg.strip()]
    if len(segments) > 1:
        raise ReadOnlyViolation(_MESSAGE)

    tokens = cleaned.split()
    if not tokens:
        raise ReadOnlyViolation(_MESSAGE)

    if tokens[0].upper() not in _ALLOWED_LEADING:
        raise ReadOnlyViolation(_MESSAGE)
