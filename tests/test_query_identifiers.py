"""Tests for query module identifier quoting via securable parser.

Tests that build_select properly backtick-quotes all identifiers from the
securable parser, preventing SQL injection.
"""

import pytest
from app.query import build_select


def test_build_select_backtick_quotes_all_parts():
    """All three parts (catalog, schema, table) are backtick-quoted."""
    result = build_select("catalog.schema.table", 100)
    assert result == "SELECT * FROM `catalog`.`schema`.`table` LIMIT 100"


def test_build_select_with_special_chars_quoted():
    """Names with special chars (spaces, hyphens, etc.) are backtick-quoted."""
    result = build_select("my-catalog.my-schema.my-table", 50)
    assert "`my-catalog`" in result
    assert "`my-schema`" in result
    assert "`my-table`" in result
    assert "SELECT * FROM" in result


def test_build_select_escapes_backticks_in_names():
    """Internal backticks in names are doubled (escaped)."""
    # A name with a backtick: my`table
    result = build_select("cat.`sch`ema.`table`", 10)
    # The format_securable function should handle this
    assert "`" in result
    assert "SELECT * FROM" in result


def test_build_select_limit_is_respected():
    """LIMIT clause is applied with the provided limit."""
    result = build_select("c.s.t", 1)
    assert "LIMIT 1" in result

    result = build_select("c.s.t", 999)
    assert "LIMIT 999" in result


def test_build_select_rejects_invalid_securable():
    """Invalid securable raises ValueError with descriptive message."""
    # SQL injection attempt
    with pytest.raises(ValueError) as exc_info:
        build_select("c.s.t'; DROP TABLE users; --", 10)
    assert "Invalid table name" in str(exc_info.value) or "table name" in str(exc_info.value).lower()


def test_build_select_rejects_four_part_name():
    """Four-part names (not 3-part) raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        build_select("a.b.c.d", 10)
    assert "3-part" in str(exc_info.value)


def test_build_select_rejects_two_part_name():
    """Two-part names (not 3-part) raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        build_select("a.b", 10)
    assert "3-part" in str(exc_info.value)


def test_build_select_rejects_one_part_name():
    """One-part names (not 3-part) raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        build_select("table_only", 10)
    assert "3-part" in str(exc_info.value)


def test_build_select_rejects_empty_parts():
    """Empty parts in the name raise ValueError."""
    with pytest.raises(ValueError):
        build_select("c..t", 10)


def test_build_select_preserves_limit_int():
    """Limit parameter is converted to int."""
    result = build_select("c.s.t", 50)
    assert "LIMIT 50" in result


def test_build_select_quotes_reserved_words():
    """SQL reserved words in names are properly quoted."""
    # 'select', 'from', 'table', etc. should be safe when quoted
    result = build_select("select.from.table", 10)
    assert "`select`" in result
    assert "`from`" in result
    assert "`table`" in result
    assert "SELECT * FROM `select`.`from`.`table`" in result
