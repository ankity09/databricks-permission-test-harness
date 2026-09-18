"""Catalog Explorer backend: lazy tree browse + server-side search.

Everything here runs under the OBO admin's identity (the caller passes an
``exec(sql) -> list[dict]`` bound to the OBO client). So the tree and the search
results reflect exactly what the logged-in admin can see in Unity Catalog — the
right visibility for *choosing a test target*. This module never grants, writes,
or runs anything as the SP; it is pure read-only metadata.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

Exec = Callable[[str], List[Dict[str, Any]]]


class BrowseError(ValueError):
    """Bad browse request (unknown level, or missing parent for the level)."""


def _first(row: Dict[str, Any], *keys: str) -> Optional[str]:
    """Return the first present, non-empty value among the given column keys.

    SHOW commands differ in column naming across runtimes, so we probe several.
    """
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k])
    # last resort: single-column results land under 'col' or the sole value
    if len(row) == 1:
        return str(next(iter(row.values())))
    return None


def _esc(s: str) -> str:
    """Escape a SQL string literal (double single-quotes)."""
    return s.replace("'", "''")


def browse_node(
    exec_sql: Exec, *, level: str, parent: Optional[str]
) -> List[Dict[str, Any]]:
    """Return the children of a tree node, lazily, via SHOW commands.

    level='root'    -> catalogs               (parent ignored)
    level='catalog' -> schemas in <parent>    (parent = catalog)
    level='schema'  -> tables/views/volumes/functions in <parent> (parent=cat.sch)
    """
    if level == "root":
        rows = exec_sql("SHOW CATALOGS")
        names = sorted(
            {n for r in rows if (n := _first(r, "catalog", "catalogName", "catalog_name"))}
        )
        return [
            {"name": n, "type": "catalog", "path": n, "expandable": True} for n in names
        ]

    if level == "catalog":
        if not parent:
            raise BrowseError("catalog level requires a parent catalog name")
        cat = parent
        rows = exec_sql(f"SHOW SCHEMAS IN `{cat}`")
        names = sorted(
            {n for r in rows if (n := _first(r, "databaseName", "schemaName", "namespace", "schema_name"))}
        )
        return [
            {"name": n, "type": "schema", "path": f"{cat}.{n}", "expandable": True}
            for n in names
        ]

    if level == "schema":
        if not parent or parent.count(".") != 1:
            raise BrowseError("schema level requires parent 'catalog.schema'")
        out: List[Dict[str, Any]] = []
        out += _objects(exec_sql, parent, "table")
        out += _objects(exec_sql, parent, "view")
        out += _objects(exec_sql, parent, "volume")
        out += _objects(exec_sql, parent, "function")
        # stable, kind-grouped, then alphabetical within kind
        return out

    raise BrowseError(f"unknown browse level: {level}")


_KIND_SQL = {
    "table": ("SHOW TABLES IN `{cat}`.`{sch}`", ("tableName", "table_name")),
    "view": ("SHOW VIEWS IN `{cat}`.`{sch}`", ("viewName", "view_name")),
    "volume": ("SHOW VOLUMES IN `{cat}`.`{sch}`", ("volume_name", "volumeName")),
    "function": (
        "SHOW USER FUNCTIONS IN `{cat}`.`{sch}`",
        ("function", "functionName", "function_name"),
    ),
}


def _objects(exec_sql: Exec, parent: str, kind: str) -> List[Dict[str, Any]]:
    cat, sch = parent.split(".", 1)
    template, keys = _KIND_SQL[kind]
    try:
        rows = exec_sql(template.format(cat=cat, sch=sch))
    except Exception:  # noqa: BLE001 — a kind may be unsupported; skip it
        return []
    names = set()
    for r in rows:
        n = _first(r, *keys)
        if not n:
            continue
        # functions may come back fully-qualified; keep just the leaf name
        leaf = n.split(".")[-1]
        names.add(leaf)
    return [
        {"name": n, "type": kind, "path": f"{cat}.{sch}.{n}", "expandable": False}
        for n in sorted(names)
    ]


def search_objects(exec_sql: Exec, *, query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Search objects by name across all visible catalogs via information_schema.

    Uses system.information_schema (respects UC visibility for the OBO admin).
    Matches tables/views and volumes whose name contains ``query`` (case-insens).
    """
    q = query.strip()
    if not q:
        return []
    like = f"%{_esc(q.lower())}%"
    lim = max(1, min(int(limit), 100))
    results: List[Dict[str, Any]] = []

    # tables + views
    try:
        rows = exec_sql(
            "SELECT table_catalog, table_schema, table_name, table_type "
            "FROM system.information_schema.tables "
            f"WHERE lower(table_name) LIKE '{like}' "
            f"ORDER BY table_name LIMIT {lim}"
        )
        for r in rows:
            cat = _first(r, "table_catalog")
            sch = _first(r, "table_schema")
            name = _first(r, "table_name")
            ttype = (_first(r, "table_type") or "").upper()
            if not (cat and sch and name):
                continue
            results.append(
                {
                    "name": name,
                    "type": "view" if "VIEW" in ttype else "table",
                    "path": f"{cat}.{sch}.{name}",
                }
            )
    except Exception:  # noqa: BLE001
        pass

    # volumes
    try:
        rows = exec_sql(
            "SELECT volume_catalog, volume_schema, volume_name "
            "FROM system.information_schema.volumes "
            f"WHERE lower(volume_name) LIKE '{like}' "
            f"ORDER BY volume_name LIMIT {lim}"
        )
        for r in rows:
            cat = _first(r, "volume_catalog")
            sch = _first(r, "volume_schema")
            name = _first(r, "volume_name")
            if not (cat and sch and name):
                continue
            results.append(
                {"name": name, "type": "volume", "path": f"{cat}.{sch}.{name}"}
            )
    except Exception:  # noqa: BLE001
        pass

    return results[:lim]
