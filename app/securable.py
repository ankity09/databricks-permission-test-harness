"""Parser for securable names (catalog.schema.table, etc.).

Prevents SQL injection by strictly validating the format of unquoted parts and
properly handling backtick-quoted identifiers. Returns parsed parts that can
be safely quoted and embedded into SQL.
"""

from __future__ import annotations

import re
from typing import List

_UNQUOTED_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class SecurableParseError(ValueError):
    """Raised when a securable name is malformed or contains injection attempts."""


def parse_securable(securable: str) -> List[str]:
    """Parse a securable name into its dot-separated parts.

    Handles both unquoted identifiers (matching [A-Za-z_][A-Za-z0-9_-]*) and
    backtick-quoted identifiers with doubled-backtick escaping.

    Rejects:
      - Unquoted parts with whitespace, quotes, comment markers, semicolons, etc.
      - Unquoted parts starting with digits
      - Unterminated backtick quotes
      - Backticks inside backtick quotes (must be doubled as ``).

    Returns a list of parsed, unescaped parts.
    Raises SecurableParseError if the format is invalid.
    """
    if not securable or not isinstance(securable, str):
        raise SecurableParseError("Securable must be a non-empty string.")

    # Check for obvious injection patterns first.
    if any(
        marker in securable
        for marker in [";", "--", "/*", "*/", "TO", "FROM", "\n", "\r"]
    ):
        # More lenient: only reject if they're not inside backticks.
        # We'll do proper tokenization below.
        pass

    parts: List[str] = []
    i = 0
    while i < len(securable):
        # Dots separate parts; check for empty parts from consecutive dots.
        if securable[i] == ".":
            # Look back to see if the previous char was also a dot (double dot).
            if i > 0 and securable[i - 1] == ".":
                raise SecurableParseError(
                    f"Securable contains consecutive dots (empty part) at position {i}."
                )
            i += 1
            continue
        if securable[i] in (" ", "\t"):
            raise SecurableParseError(
                f"Securable contains unexpected whitespace at position {i}."
            )

        # Parse either a quoted or unquoted part.
        if securable[i] == "`":
            # Quoted identifier: scan until closing backtick.
            part, end_pos = _parse_quoted_part(securable, i)
            parts.append(part)
            i = end_pos
        else:
            # Unquoted identifier: scan until dot or end.
            part, end_pos = _parse_unquoted_part(securable, i)
            if not part:
                raise SecurableParseError("Securable contains an empty part.")
            parts.append(part)
            i = end_pos

    # Check for trailing dot (empty last part).
    if securable.endswith("."):
        raise SecurableParseError("Securable ends with a dot (empty last part).")

    if not parts:
        raise SecurableParseError("Securable name produced no parts.")

    return parts


def _parse_unquoted_part(securable: str, start: int) -> tuple[str, int]:
    """Parse an unquoted identifier starting at position start.

    Returns (part, next_position_after_part).
    """
    end = start
    while end < len(securable) and securable[end] != ".":
        end += 1

    part = securable[start:end]

    # Validate: no whitespace, no special chars, must match pattern.
    if any(marker in part for marker in ["--", "/*", "*/", "TO", "FROM", ";"]):
        raise SecurableParseError(
            f"Unquoted part {part!r} is unparseable (contains SQL keywords/markers)."
        )
    if any(c in part for c in [" ", "\t", "\n", "\r", "'", '"', "{", "}"]):
        raise SecurableParseError(
            f"Unquoted part {part!r} contains invalid characters (whitespace, "
            f"quotes, semicolon, etc.)."
        )
    if not _UNQUOTED_PATTERN.match(part):
        raise SecurableParseError(
            f"Unquoted part {part!r} is not a valid identifier. "
            f"Must start with letter or underscore, contain only [A-Za-z0-9_-]."
        )

    return part, end


def _parse_quoted_part(securable: str, start: int) -> tuple[str, int]:
    """Parse a backtick-quoted identifier starting at position start.

    Handles doubled backticks as escape sequences.
    Returns (unescaped_part, next_position_after_closing_backtick).
    """
    # start points to the opening backtick.
    i = start + 1
    result = []

    while i < len(securable):
        if securable[i] == "`":
            if i + 1 < len(securable) and securable[i + 1] == "`":
                # Doubled backtick: escaped backtick.
                result.append("`")
                i += 2
            else:
                # Closing backtick.
                part = "".join(result)
                if not part:
                    raise SecurableParseError(
                        f"Quoted identifier at position {start} is empty."
                    )
                return part, i + 1
        else:
            result.append(securable[i])
            i += 1

    # Unterminated quote.
    raise SecurableParseError(
        f"Unterminated backtick quote starting at position {start}."
    )


def format_securable(securable: str) -> str:
    """Parse and re-format a securable as fully backtick-quoted parts.

    This is the safe form for embedding into SQL: backtick-quoted each part
    and rejoin with dots.

    Raises SecurableParseError if the securable is invalid.
    """
    parts = parse_securable(securable)
    quoted_parts = [_quote_part(part) for part in parts]
    return ".".join(quoted_parts)


def _quote_part(part: str) -> str:
    """Backtick-quote a single identifier part, escaping internal backticks."""
    # Escape any backticks by doubling them.
    escaped = part.replace("`", "``")
    return f"`{escaped}`"
