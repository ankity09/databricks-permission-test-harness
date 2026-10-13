"""Tests that expose the double-quoting bug in browse.py schema level.

The bug: templates already have backticks ("SHOW TABLES IN `{cat}`.`{sch}`")
and the code quotes them again, producing "SHOW TABLES IN ``cat``.``sch``"
which is invalid SQL. The broad except hides the error, returning [] silently.
"""

import pytest
from app.browse import browse_node


def test_browse_schema_does_not_double_quote():
    """Test that browse_node doesn't double-quote identifiers.

    The bug: if templates use backticks AND _objects quotes again,
    you get ``cat`` instead of `cat`, causing SHOW TABLES to fail silently.
    """
    calls = []
    successful_calls = []

    def fake_exec(sql):
        calls.append(sql)
        u = sql.upper()

        # Log any calls that succeeded
        successful_calls.append(sql)

        # If SQL has double backticks, that's the bug
        if "``" in sql:
            raise RuntimeError(f"Double backticks (invalid SQL): {sql}")

        # Normal success path
        if "SHOW TABLES" in u:
            return [{"tableName": "orders", "isTemporary": False}]
        if "SHOW VIEWS" in u:
            return []
        if "SHOW VOLUMES" in u:
            return []
        if "SHOW FUNCTIONS" in u or "SHOW USER FUNCTIONS" in u:
            return []
        return []

    nodes = browse_node(fake_exec, level="schema", parent="my-catalog.my-schema")

    # If the bug exists, no objects will be returned (broad except caught the error).
    # Without the bug, we should get the tables.
    assert len(nodes) > 0, "Schema should have returned tables, but double-quoting bug hid the error"

    # Verify the SQL doesn't have double backticks
    assert all("``" not in call for call in calls), "Found double backticks in SQL"


def test_browse_schema_sql_is_valid():
    """Test that SHOW TABLES SQL is syntactically valid (no double quotes)."""
    captured_sql = []

    def fake_exec(sql):
        captured_sql.append(sql)
        u = sql.upper()
        if "SHOW TABLES" in u:
            # Only return data if SQL looks valid
            if "``" in sql:
                raise SyntaxError(f"Invalid SQL (double backticks): {sql}")
            return [{"tableName": "orders", "isTemporary": False}]
        if "SHOW VIEWS" in u:
            return []
        if "SHOW VOLUMES" in u:
            return []
        if "SHOW FUNCTIONS" in u or "SHOW USER FUNCTIONS" in u:
            return []
        return []

    nodes = browse_node(fake_exec, level="schema", parent="catalog.schema")

    # Should have gotten tables without syntax error
    assert len(nodes) > 0


def test_browse_show_tables_uses_single_quotes_per_identifier():
    """Test that each identifier part is quoted exactly once."""
    captured = []

    def fake_exec(sql):
        captured.append(sql)
        u = sql.upper()
        if "SHOW TABLES" in u:
            # Pattern should be: SHOW TABLES IN `catalog`.`schema`
            # NOT: SHOW TABLES IN ``catalog``.``schema``
            assert "`catalog`" in sql or "`" in sql, "Should have backticks"
            # But NOT double backticks
            if "``" in sql:
                raise AssertionError(f"Double backticks found: {sql}")
            return [{"tableName": "table1", "isTemporary": False}]
        return []

    nodes = browse_node(fake_exec, level="schema", parent="catalog.schema")
    assert len(nodes) > 0
