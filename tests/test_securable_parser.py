"""Tests for securable name parser (A1: injection prevention)."""

import pytest
from app.securable import parse_securable, SecurableParseError


def test_parse_valid_simple_names():
    """Valid single-level catalogs."""
    parts = parse_securable("main")
    assert parts == ["main"]


def test_parse_valid_two_part_schema():
    """Valid two-level schema names."""
    parts = parse_securable("main.default")
    assert parts == ["main", "default"]


def test_parse_valid_three_part_table():
    """Valid three-level table names."""
    parts = parse_securable("main.sales.orders")
    assert parts == ["main", "sales", "orders"]


def test_parse_unquoted_names_alphanumeric_underscore_hyphen():
    """Unquoted parts allow alphanumeric, underscore, and hyphen."""
    parts = parse_securable("main_db.my-schema.table_123")
    assert parts == ["main_db", "my-schema", "table_123"]


def test_parse_quoted_names_preserve_case_and_special_chars():
    """Backtick-quoted parts preserve case and spaces."""
    parts = parse_securable("`Main`.`Sales Data`.`Order Details`")
    assert parts == ["Main", "Sales Data", "Order Details"]


def test_parse_mixed_quoted_unquoted():
    """Mix of quoted and unquoted parts."""
    parts = parse_securable("main.`Sales Data`.orders")
    assert parts == ["main", "Sales Data", "orders"]


def test_parse_reject_unquoted_starting_with_digit():
    """Unquoted parts must start with letter or underscore."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.123invalid.table")
    assert "valid identifier" in str(exc_info.value)


def test_parse_reject_unquoted_containing_whitespace():
    """Unquoted parts cannot have spaces."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.bad schema.table")
    assert "whitespace" in str(exc_info.value)


def test_parse_reject_injection_to_clause():
    """Reject SQL injection attempts with TO clause."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.sales.orders TO `users`")
    assert "unparseable" in str(exc_info.value).lower()


def test_parse_reject_injection_comment_marker():
    """Reject comment markers outside quotes."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.sales --comment")
    assert "unparseable" in str(exc_info.value).lower()


def test_parse_reject_injection_line_comment_in_middle():
    """Reject line comments embedded in identifier."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.--comment\norders")
    assert "unparseable" in str(exc_info.value).lower()


def test_parse_reject_injection_block_comment():
    """Reject block comments outside quotes."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main./* comment */orders")
    assert "unparseable" in str(exc_info.value).lower()


def test_parse_reject_semicolon():
    """Reject semicolons."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.sales; DROP TABLE")
    assert "unparseable" in str(exc_info.value).lower()


def test_parse_reject_empty_unquoted_part():
    """Reject empty parts created by double dots."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main..table")
    assert "empty" in str(exc_info.value).lower()


def test_parse_reject_empty_quoted_part():
    """Reject empty backtick-quoted parts."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.``.table")
    assert "empty" in str(exc_info.value).lower()


def test_parse_reject_unclosed_backtick():
    """Reject unterminated backtick quotes."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.`unclosed")
    assert "unterminated" in str(exc_info.value).lower()


def test_parse_reject_backtick_in_quoted_part():
    """Reject backticks inside backtick-quoted parts (must be doubled)."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.`bad`quote`.table")
    # The error occurs when parsing "quote`" as an unquoted part (invalid identifier).
    assert "backtick" in str(exc_info.value).lower() or "valid identifier" in str(exc_info.value).lower()


def test_parse_allow_doubled_backticks_escape():
    """Allow doubled backticks as escape sequence in quoted parts."""
    parts = parse_securable("main.`that``s`.table")
    assert parts == ["main", "that`s", "table"]


def test_parse_reject_unquoted_single_quote():
    """Reject single quotes in unquoted parts."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.schema'injection.table")
    assert "invalid" in str(exc_info.value).lower()


def test_parse_reject_unquoted_double_quote():
    """Reject double quotes in unquoted parts."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable('main.schema"injection.table')
    assert "invalid" in str(exc_info.value).lower()


def test_parse_reject_unquoted_curly_braces():
    """Reject curly braces (template placeholders)."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.{schema}.table")
    assert "invalid" in str(exc_info.value).lower()


def test_parse_reject_newlines():
    """Reject newlines in unquoted parts."""
    with pytest.raises(SecurableParseError) as exc_info:
        parse_securable("main.schema\ntable.table")
    assert "invalid" in str(exc_info.value).lower()


def test_format_quoted_simple():
    """Format valid 3-part securable with full quotes."""
    from app.securable import format_securable
    result = format_securable("main.sales.orders")
    assert result == "`main`.`sales`.`orders`"


def test_format_quoted_with_spaces():
    """Format quoted names preserve structure."""
    from app.securable import format_securable
    result = format_securable("`Main`.`Sales Data`.`Order Details`")
    assert result == "`Main`.`Sales Data`.`Order Details`"


def test_format_quoted_preserves_escaped_backticks():
    """Format preserves doubled backticks after parsing."""
    from app.securable import format_securable
    result = format_securable("main.`that``s`.table")
    assert result == "`main`.`that``s`.`table`"
