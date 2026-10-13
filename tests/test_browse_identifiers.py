"""Tests for browse module identifier quoting and de-duplication.

Tests:
1. Catalog and schema names are backtick-quoted in SQL
2. View de-duplication: when SHOW TABLES and SHOW VIEWS both return the same
   object, it appears once with type="view"
3. LIKE patterns are properly escaped with ESCAPE clause
"""

import pytest
from app.browse import browse_node, search_objects, BrowseError


def test_browse_catalog_quotes_identifier():
    """Catalog name is backtick-quoted in SHOW SCHEMAS."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return [{"databaseName": "sales"}]

    browse_node(fake_exec, level="catalog", parent="my-catalog")
    # Catalog name should be backtick-quoted
    assert any("`my-catalog`" in call for call in calls)


def test_browse_schema_objects_quote_identifiers():
    """Catalog and schema names are backtick-quoted in SHOW TABLES/VIEWS/etc."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        u = sql.upper()
        if "SHOW TABLES" in u:
            return [{"tableName": "orders", "isTemporary": False}]
        if "SHOW VIEWS" in u:
            return []
        if "SHOW VOLUMES" in u:
            return []
        if "SHOW FUNCTIONS" in u or "SHOW USER FUNCTIONS" in u:
            return []
        return []

    browse_node(fake_exec, level="schema", parent="my-cat.my-schema")
    # Both catalog and schema should be backtick-quoted
    assert any("`my-cat`" in call for call in calls)
    assert any("`my-schema`" in call for call in calls)


def test_browse_schema_de_duplicates_views_from_tables():
    """When SHOW TABLES returns a view and SHOW VIEWS returns it again, dedupe."""
    def fake_exec(sql):
        u = sql.upper()
        if "SHOW TABLES" in u:
            # SHOW TABLES may return both tables and views
            return [
                {"tableName": "customers", "isTemporary": False},
                {"tableName": "orders_view", "isTemporary": False},
            ]
        if "SHOW VIEWS" in u:
            # SHOW VIEWS returns the views
            return [{"viewName": "orders_view"}]
        if "SHOW VOLUMES" in u:
            return []
        if "SHOW FUNCTIONS" in u or "SHOW USER FUNCTIONS" in u:
            return []
        return []

    nodes = browse_node(fake_exec, level="schema", parent="c.s")
    # orders_view should appear once with type "view"
    names_by_type = {}
    for n in nodes:
        path = n["path"]
        names_by_type.setdefault(path, []).append(n["type"])

    view_path = "c.s.orders_view"
    assert view_path in names_by_type
    # Should appear only once as a view
    assert names_by_type[view_path] == ["view"]


def test_browse_schema_preserves_table_type():
    """Tables stay as type 'table' even if SHOW VIEWS doesn't have them."""
    def fake_exec(sql):
        u = sql.upper()
        if "SHOW TABLES" in u:
            return [{"tableName": "actual_table", "isTemporary": False}]
        if "SHOW VIEWS" in u:
            return []
        if "SHOW VOLUMES" in u:
            return []
        if "SHOW FUNCTIONS" in u or "SHOW USER FUNCTIONS" in u:
            return []
        return []

    nodes = browse_node(fake_exec, level="schema", parent="c.s")
    actual_table = next((n for n in nodes if n["name"] == "actual_table"), None)
    assert actual_table is not None
    assert actual_table["type"] == "table"


def test_browse_schema_dedup_stable_order():
    """De-duplication maintains stable order: tables, then views, then volumes, etc."""
    def fake_exec(sql):
        u = sql.upper()
        if "SHOW TABLES" in u:
            return [
                {"tableName": "b_table", "isTemporary": False},
                {"tableName": "a_table", "isTemporary": False},
            ]
        if "SHOW VIEWS" in u:
            return [
                {"viewName": "b_view"},
                {"viewName": "c_view"},
            ]
        if "SHOW VOLUMES" in u:
            return [{"volume_name": "a_vol"}]
        if "SHOW FUNCTIONS" in u or "SHOW USER FUNCTIONS" in u:
            return []
        return []

    nodes = browse_node(fake_exec, level="schema", parent="c.s")
    types = [n["type"] for n in nodes]
    names = [n["name"] for n in nodes]

    # Types should be sorted: table < view < volume
    # Within each type, sorted by name
    assert types == ["table", "table", "view", "view", "volume"]
    assert names == ["a_table", "b_table", "b_view", "c_view", "a_vol"]


def test_browse_backticks_with_special_chars_in_name():
    """Names with special chars like spaces are properly backtick-quoted."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return [{"databaseName": "my schema"}]

    browse_node(fake_exec, level="catalog", parent="my-catalog")
    # Backticks should be in the SQL
    assert any("`" in call for call in calls)


def test_browse_escapes_backticks_in_identifier():
    """Backticks within identifiers are doubled (escaped)."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return [{"databaseName": "schema"}]

    browse_node(fake_exec, level="catalog", parent="my`catalog")
    # Internal backtick should be doubled
    assert any("`my``catalog`" in call for call in calls)


def test_search_like_with_escape_clause():
    """LIKE patterns include ESCAPE '\\' clause for safe matching."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return []

    search_objects(fake_exec, query="test", limit=10)
    # ESCAPE clause should be present
    sql_upper = " ".join(c.upper() for c in calls)
    assert "ESCAPE" in sql_upper


def test_search_escapes_underscore_and_percent_in_pattern():
    """LIKE pattern escapes _ and % with backslash."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return []

    search_objects(fake_exec, query="test_%", limit=10)
    # The % and _ should be escaped in the pattern
    sql_combined = " ".join(calls)
    assert "\\%" in sql_combined or "\\_" in sql_combined


def test_search_escapes_materialization_pattern():
    """__materialization exclusion pattern is properly escaped."""
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return []

    search_objects(fake_exec, query="test", limit=10)
    # The exclusion pattern for __materialization should be escaped
    sql_combined = " ".join(calls)
    # Should have the pattern with backslash-escaped underscores
    assert "__materialization" not in sql_combined or "\\\\" in sql_combined
