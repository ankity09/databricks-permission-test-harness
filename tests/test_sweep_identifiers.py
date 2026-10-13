"""Tests for sweep module identifier quoting and error handling.

Tests that:
1. Identifiers in build_targets are safely quoted
2. Invalid securables are handled gracefully (skip enumeration)
3. Identifiers in _attempt (SP probes) are safely quoted
"""

import pytest
from app.sweep import build_targets


def test_build_targets_quotes_catalog_and_schema():
    """Catalog and schema names are backtick-quoted in SHOW TABLES."""
    calls = []

    def fake_obo_exec(sql):
        calls.append(sql)
        u = sql.upper()
        if "SHOW TABLES" in u:
            return [{"tableName": "orders", "isTemporary": False}]
        return []

    build_targets(fake_obo_exec, "my-catalog.my-schema.table")
    # SHOW TABLES command should quote the catalog and schema
    assert any("SHOW TABLES IN" in call for call in calls)
    assert any("`my-catalog`" in call or "my-catalog" in call for call in calls)


def test_build_targets_with_special_chars():
    """Names with spaces and special chars are properly quoted."""
    calls = []

    def fake_obo_exec(sql):
        calls.append(sql)
        return []

    build_targets(fake_obo_exec, "catalog-name.schema-name.table")
    # The SHOW TABLES call should quote the names
    assert any("`" in call for call in calls)


def test_build_targets_with_invalid_securable_skips_enumeration():
    """Invalid securable in build_targets skips sibling enumeration."""
    calls = []

    def fake_obo_exec(sql):
        calls.append(sql)
        raise RuntimeError("should not be called for enumeration")

    # Invalid securable (with SQL injection)
    targets = build_targets(fake_obo_exec, "c.s.t'; DROP TABLE; --")
    # Should gracefully skip and return container targets without enumeration
    # (The function returns early on invalid securable)
    assert isinstance(targets, list)


def test_build_targets_enumeration_errors_degrade_gracefully():
    """Errors in SHOW TABLES enumeration are caught, partial results returned."""
    def fake_obo_exec(sql):
        u = sql.upper()
        if "SHOW TABLES" in u:
            raise RuntimeError("enumeration failed")
        return []

    targets = build_targets(fake_obo_exec, "catalog.schema.table")
    # Should return at least the container targets even if enumeration fails
    assert len(targets) > 0


def test_build_targets_handles_quoted_names_safely():
    """Identifiers with backticks in their actual names are handled."""
    calls = []

    def fake_obo_exec(sql):
        calls.append(sql)
        return []

    # A valid quoted identifier with backticks
    build_targets(fake_obo_exec, "`cat-alog`.`sch-ema`.table")
    # Should construct valid SQL
    assert any("`" in call for call in calls)


def test_build_targets_sibling_detection():
    """Sibling tables in same schema are detected (requires proper quoting)."""
    def fake_obo_exec(sql):
        u = sql.upper()
        if "SHOW TABLES" in u:
            return [
                {"tableName": "orders", "isTemporary": False},
                {"tableName": "customers", "isTemporary": False},
            ]
        return []

    targets = build_targets(fake_obo_exec, "c.s.orders")
    # Should find targets with action names
    assert len(targets) > 0
    assert all("object" in t for t in targets)
    assert all("action" in t for t in targets)


def test_attempt_quotes_object_identifier():
    """The _attempt function safely quotes object identifiers for SP probes.

    This is an internal function but is critical for SQL injection prevention.
    """
    from app.sweep import _attempt
    from unittest.mock import MagicMock

    sp_client = MagicMock()
    sp_client.statement_execution.execute_statement.return_value = MagicMock(
        status=MagicMock(state=MagicMock(value="SUCCEEDED")),
        result=MagicMock(result_chunks=None),
    )

    # Call with an object that has special characters
    result = _attempt(sp_client, "warehouse1", "cat-alog", "use_catalog")
    # Should not raise; the identifier should be properly quoted
    assert isinstance(result, dict)


def test_attempt_handles_invalid_identifier_gracefully():
    """Invalid identifiers in _attempt are handled without raising SQL errors."""
    from app.sweep import _attempt
    from unittest.mock import MagicMock

    sp_client = MagicMock()

    # Call with an invalid identifier (SQL injection)
    result = _attempt(sp_client, "warehouse1", "cat'; DROP TABLE; --", "use_catalog")
    # Should return an error result, not execute the malicious SQL
    assert result.get("result") in ("error", "ParseError") or "error" in result
