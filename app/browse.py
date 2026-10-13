"""Catalog Explorer backend: lazy tree browse + server-side search.

Everything here runs under the OBO admin's identity (the caller passes an
``exec(sql) -> list[dict]`` bound to the OBO client). So the tree and the search
results reflect exactly what the logged-in admin can see in Unity Catalog: the
right visibility for *choosing a test target*. This module never grants, writes,
or runs anything as the SP; it is pure read-only metadata. Identifiers are
backtick-quoted via the securable parser; LIKE patterns are escaped with a
consistent ESCAPE clause.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.securable import parse_securable, SecurableParseError

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


def _quote_identifier(s: str) -> str:
    """Backtick-quote an identifier, escaping internal backticks."""
    escaped = s.replace("`", "``")
    return f"`{escaped}`"


def _esc(s: str) -> str:
    """Escape a SQL string literal (double single-quotes)."""
    return s.replace("'", "''")


def _esc_like(s: str, escape_char: str = "\\") -> str:
    """Escape LIKE pattern: handle %, _, and the escape character itself."""
    # First escape the escape character itself.
    s = s.replace(escape_char, escape_char + escape_char)
    # Then escape LIKE special characters.
    s = s.replace("%", escape_char + "%")
    s = s.replace("_", escape_char + "_")
    return s


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
        cat_quoted = _quote_identifier(cat)
        rows = exec_sql(f"SHOW SCHEMAS IN {cat_quoted}")
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
        # Collect objects and de-duplicate by path (SHOW TABLES already returns views).
        # Type is "view" for views, otherwise "table".
        by_path: Dict[str, Dict[str, Any]] = {}
        for kind in ("table", "view", "volume", "function"):
            for obj in _objects(exec_sql, parent, kind):
                path = obj["path"]
                if path not in by_path:
                    by_path[path] = obj
                elif kind == "view":
                    # If this is a view, update type to "view" (views should override table).
                    by_path[path]["type"] = "view"
        # Sort by type (table < view < volume < function), then by name.
        type_order = {"table": 0, "view": 1, "volume": 2, "function": 3}
        out = sorted(
            by_path.values(),
            key=lambda x: (type_order.get(x["type"], 999), x["name"]),
        )
        return out

    raise BrowseError(f"unknown browse level: {level}")


_KIND_SQL = {
    "table": ("SHOW TABLES IN {cat}.{sch}", ("tableName", "table_name")),
    "view": ("SHOW VIEWS IN {cat}.{sch}", ("viewName", "view_name")),
    "volume": ("SHOW VOLUMES IN {cat}.{sch}", ("volume_name", "volumeName")),
    "function": (
        "SHOW USER FUNCTIONS IN {cat}.{sch}",
        ("function", "functionName", "function_name"),
    ),
}


def _objects(exec_sql: Exec, parent: str, kind: str) -> List[Dict[str, Any]]:
    cat, sch = parent.split(".", 1)
    template, keys = _KIND_SQL[kind]
    try:
        # Quote identifiers for the SHOW command.
        cat_quoted = _quote_identifier(cat)
        sch_quoted = _quote_identifier(sch)
        rows = exec_sql(template.format(cat=cat_quoted, sch=sch_quoted))
    except Exception:  # noqa: BLE001 -- a kind may be unsupported; skip it
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
    LIKE patterns are escaped to prevent special character injection.
    """
    q = query.strip()
    if not q:
        return []
    # Escape LIKE metacharacters in the query term; use backslash as escape char.
    # Then escape single quotes for the SQL string literal.
    q_escaped = _esc_like(q.lower(), escape_char="\\")
    q_quoted = _esc(q_escaped)  # double single quotes for SQL string
    like = f"%{q_quoted}%"
    lim = max(1, min(int(limit), 100))
    results: List[Dict[str, Any]] = []

    # Internal pipeline/materialization tables are never a real grant target;
    # exclude them so the tester isn't drowned in __materialization_mat_* noise.
    # Escape the underscore and backslash in the exclusion pattern, then quotes.
    materialization_pattern = _esc_like("__materialization%", escape_char="\\")
    materialization_pattern_quoted = _esc(materialization_pattern)
    _noise = f"AND table_name NOT LIKE '{materialization_pattern_quoted}' ESCAPE '\\\\'"

    # tables + views
    try:
        rows = exec_sql(
            "SELECT table_catalog, table_schema, table_name, table_type "
            "FROM system.information_schema.tables "
            f"WHERE lower(table_name) LIKE '{like}' ESCAPE '\\\\' {_noise} "
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
            f"WHERE lower(volume_name) LIKE '{like}' ESCAPE '\\\\' "
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
