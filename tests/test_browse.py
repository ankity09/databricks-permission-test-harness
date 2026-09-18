"""Tests for the catalog browse + search module (Feature: Catalog Explorer).

The browser lists what the OBO admin can see. We inject a fake exec(sql) so
these are pure-logic tests with no Databricks dependency.
"""

import pytest

from app.browse import browse_node, search_objects, BrowseError


def test_browse_root_lists_catalogs():
    calls = []

    def fake_exec(sql):
        calls.append(sql)
        return [{"catalog": "main"}, {"catalog": "f5_demo"}]

    nodes = browse_node(fake_exec, level="root", parent=None)
    assert [n["name"] for n in nodes] == ["f5_demo", "main"]  # sorted
    assert all(n["type"] == "catalog" for n in nodes)
    assert all(n["expandable"] for n in nodes)
    assert "SHOW CATALOGS" in calls[0].upper()


def test_browse_catalog_lists_schemas():
    def fake_exec(sql):
        assert "SCHEMAS IN" in sql.upper()
        return [{"databaseName": "sales"}, {"databaseName": "default"}]

    nodes = browse_node(fake_exec, level="catalog", parent="main")
    assert [n["name"] for n in nodes] == ["default", "sales"]
    assert all(n["type"] == "schema" for n in nodes)
    # full path is carried so a click yields catalog.schema
    assert nodes[0]["path"] == "main.default"


def test_browse_schema_lists_objects_of_all_kinds():
    def fake_exec(sql):
        u = sql.upper()
        if "SHOW TABLES" in u:
            return [{"tableName": "orders", "isTemporary": False}]
        if "SHOW VIEWS" in u:
            return [{"viewName": "orders_v"}]
        if "SHOW VOLUMES" in u:
            return [{"volume_name": "raw"}]
        if "SHOW USER FUNCTIONS" in u or "SHOW FUNCTIONS" in u:
            return [{"function": "main.sales.mask_ssn"}]
        return []

    nodes = browse_node(fake_exec, level="schema", parent="main.sales")
    kinds = {n["type"] for n in nodes}
    # tables, views, volumes, functions all represented; leaves not expandable
    assert "table" in kinds and "view" in kinds and "volume" in kinds
    orders = next(n for n in nodes if n["name"] == "orders")
    assert orders["path"] == "main.sales.orders"
    assert orders["expandable"] is False


def test_browse_bad_level_raises():
    with pytest.raises(BrowseError):
        browse_node(lambda sql: [], level="bogus", parent=None)


def test_browse_catalog_level_requires_parent():
    with pytest.raises(BrowseError):
        browse_node(lambda sql: [], level="catalog", parent=None)


def test_search_uses_information_schema_and_returns_paths():
    seen = {}

    def fake_exec(sql):
        u = sql.upper()
        if "INFORMATION_SCHEMA.TABLES" in u:
            seen["tables"] = sql
            return [
                {
                    "table_catalog": "main",
                    "table_schema": "sales",
                    "table_name": "orders",
                    "table_type": "MANAGED",
                }
            ]
        if "INFORMATION_SCHEMA.VOLUMES" in u:
            return [
                {"volume_catalog": "main", "volume_schema": "sales", "volume_name": "raw"}
            ]
        return []

    results = search_objects(fake_exec, query="ord", limit=25)
    paths = [r["path"] for r in results]
    assert "main.sales.orders" in paths
    # the query term is passed to the WHERE (lowercased LIKE)
    assert "ord" in seen["tables"].lower()
    # a view/table result carries a type the UI can icon
    assert all("type" in r and "path" in r and "name" in r for r in results)


def test_search_escapes_single_quotes():
    captured = {}

    def fake_exec(sql):
        captured["sql"] = sql
        return []

    search_objects(fake_exec, query="o'brien", limit=10)
    # the raw quote must be escaped (doubled) so the LIKE literal is safe
    assert "o''brien" in captured["sql"]


def test_search_blank_query_returns_empty_without_calling():
    called = {"n": 0}

    def fake_exec(sql):
        called["n"] += 1
        return []

    assert search_objects(fake_exec, query="   ", limit=10) == []
    assert called["n"] == 0
