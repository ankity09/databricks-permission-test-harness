"""Read-only SQL guard for the query runner's free-text box.

This is the single security chokepoint that keeps the harness read-only. It is
allowlist-based (reject-by-default): only statements whose first real keyword is
SELECT / WITH / SHOW / DESCRIBE / DESC / EXPLAIN are permitted, and only a
single statement at a time. Anything else raises ReadOnlyViolation.

Uses a tokenizer that properly handles:
  - Nested block comments /* ... */
  - Line comments -- to end of line
  - Single and double quoted strings with backslash escaping
  - Backtick-quoted identifiers with doubled-backtick escaping

Applied at the API layer BEFORE any client is built, so a blocked statement
never reaches the app service principal.
"""

from __future__ import annotations

_MESSAGE = (
    "Blocked: this is a read-only harness. "
    "Only SELECT / SHOW / DESCRIBE / EXPLAIN are allowed."
)

_ALLOWED_LEADING = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}

# Dangerous keywords that indicate write operations (outside strings/comments).
_DANGEROUS_KEYWORDS = {
    "INSERT", "DELETE", "UPDATE", "MERGE", "CREATE", "DROP", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "COPY", "OPTIMIZE", "VACUUM", "REFRESH",
    "CACHE", "UNCACHE", "MSCK", "REPAIR", "SET", "RESET", "USE", "CALL",
    "EXECUTE", "BEGIN", "DECLARE", "LOAD", "ANALYZE", "RESTORE", "CLONE",
    "UNDROP", "ADD", "LOCK", "UNLOCK"
}


class ReadOnlyViolation(ValueError):
    """Raised when a statement is not a safe, single, read-only statement."""


class _Token:
    """Represents a single SQL token with metadata."""

    def __init__(self, value: str, is_keyword: bool = True, is_quoted: bool = False):
        self.value = value
        self.is_keyword = is_keyword  # True if it's an unquoted keyword-like token
        self.is_quoted = is_quoted    # True if it was backtick-quoted or string


class SQLTokenizer:
    """Tokenizes SQL while properly handling comments, strings, and identifiers."""

    def __init__(self, sql: str):
        self.sql = sql
        self.pos = 0
        self.tokens = []
        self._tokenize()

    def _peek(self, offset: int = 0) -> str | None:
        """Peek at character at current position + offset."""
        p = self.pos + offset
        return self.sql[p] if p < len(self.sql) else None

    def _advance(self, count: int = 1) -> None:
        """Advance position by count characters."""
        self.pos += count

    def _read_block_comment(self) -> None:
        """Scan and skip a block comment /* ... */.

        Properly handles nested comments by tracking depth.
        """
        # start at '/*'
        self._advance(2)
        depth = 1

        while self.pos < len(self.sql) and depth > 0:
            if self.sql[self.pos : self.pos + 2] == "/*":
                depth += 1
                self._advance(2)
            elif self.sql[self.pos : self.pos + 2] == "*/":
                depth -= 1
                self._advance(2)
            else:
                self._advance(1)

    def _read_line_comment(self) -> None:
        """Scan and skip a line comment -- to end of line."""
        self._advance(2)
        while self.pos < len(self.sql) and self.sql[self.pos] != "\n":
            self._advance(1)
        if self.pos < len(self.sql):
            self._advance(1)  # skip the newline

    def _read_string_single_quote(self) -> str:
        """Read a single-quoted string, handling backslash escapes."""
        self._advance(1)  # skip opening quote
        result = []

        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch == "\\":
                # Backslash escape: skip next character.
                self._advance(1)
                if self.pos < len(self.sql):
                    result.append(self.sql[self.pos])
                    self._advance(1)
            elif ch == "'":
                # Closing quote.
                self._advance(1)
                return "".join(result)
            else:
                result.append(ch)
                self._advance(1)

        # Unterminated string.
        raise ReadOnlyViolation("Unterminated string in SQL.")

    def _read_string_double_quote(self) -> str:
        """Read a double-quoted string, handling backslash escapes."""
        self._advance(1)  # skip opening quote
        result = []

        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch == "\\":
                # Backslash escape: skip next character.
                self._advance(1)
                if self.pos < len(self.sql):
                    result.append(self.sql[self.pos])
                    self._advance(1)
            elif ch == '"':
                # Closing quote.
                self._advance(1)
                return "".join(result)
            else:
                result.append(ch)
                self._advance(1)

        # Unterminated string.
        raise ReadOnlyViolation("Unterminated string in SQL.")

    def _read_backtick_identifier(self) -> _Token:
        """Read a backtick-quoted identifier, handling doubled backticks."""
        self._advance(1)  # skip opening backtick
        result = []

        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch == "`":
                if self._peek(1) == "`":
                    # Doubled backtick: escaped backtick.
                    result.append("`")
                    self._advance(2)
                else:
                    # Closing backtick.
                    self._advance(1)
                    return _Token("".join(result), is_keyword=False, is_quoted=True)
            else:
                result.append(ch)
                self._advance(1)

        # Unterminated identifier.
        raise ReadOnlyViolation("Unterminated backtick-quoted identifier in SQL.")

    def _read_keyword_or_symbol(self) -> str:
        """Read an unquoted keyword or symbol."""
        result = []
        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch in (" ", "\t", "\n", "\r", ";", "(", ")", ","):
                break
            result.append(ch)
            self._advance(1)
        return "".join(result)

    def _tokenize(self) -> None:
        """Tokenize the SQL statement."""
        while self.pos < len(self.sql):
            ch = self._peek()

            # Skip whitespace.
            if ch in (" ", "\t", "\n", "\r"):
                self._advance(1)
                continue

            # Skip comments.
            if ch == "/" and self._peek(1) == "*":
                self._read_block_comment()
                continue

            if ch == "-" and self._peek(1) == "-":
                self._read_line_comment()
                continue

            # Read quoted strings and identifiers.
            if ch == "'":
                self._read_string_single_quote()
                continue

            if ch == '"':
                self._read_string_double_quote()
                continue

            if ch == "`":
                token = self._read_backtick_identifier()
                self.tokens.append(token)
                continue

            # Semicolon ends a statement (allow at most one).
            if ch == ";":
                self.tokens.append(_Token(";", is_keyword=False, is_quoted=False))
                self._advance(1)
                continue

            # Read keywords/symbols.
            if ch in ("(", ")", ","):
                self._advance(1)
                continue

            token_str = self._read_keyword_or_symbol()
            if token_str:
                # Unquoted tokens are considered keywords.
                self.tokens.append(_Token(token_str, is_keyword=True, is_quoted=False))


def assert_read_only(sql: str) -> None:
    """Raise ReadOnlyViolation unless ``sql`` is a single read-only statement."""
    if not sql or not sql.strip():
        raise ReadOnlyViolation(_MESSAGE)

    try:
        tokenizer = SQLTokenizer(sql)
    except ReadOnlyViolation:
        raise
    except Exception as exc:
        raise ReadOnlyViolation(f"Failed to tokenize SQL: {exc}") from exc

    tokens = tokenizer.tokens

    if not tokens:
        raise ReadOnlyViolation(_MESSAGE)

    # Check for multiple statements (semicolons).
    semicolon_count = sum(1 for t in tokens if t.value == ";")
    if semicolon_count > 1:
        raise ReadOnlyViolation(_MESSAGE)

    # Remove trailing semicolon if present.
    if tokens and tokens[-1].value == ";":
        tokens = tokens[:-1]

    if not tokens:
        raise ReadOnlyViolation(_MESSAGE)

    # A ';' that is not the last token starts a second statement.
    if any(t.value == ";" for t in tokens):
        raise ReadOnlyViolation(_MESSAGE)

    # First token must be in the allowed set.
    first_token = tokens[0].value.upper()
    if first_token not in _ALLOWED_LEADING:
        raise ReadOnlyViolation(_MESSAGE)

    # Check for dangerous keywords anywhere in the statement.
    # Only check unquoted tokens (is_keyword=True).
    for token in tokens:
        if token.is_keyword:
            upper_value = token.value.upper()
            if upper_value in _DANGEROUS_KEYWORDS:
                raise ReadOnlyViolation(
                    f"Blocked: dangerous keyword '{token.value}' found in SQL. "
                    f"If '{token.value}' is a column name, quote it with backticks like `{token.value}`."
                )
