"""Check any single SQL statement as the app's service principal.

Read-only statements (anything the query runner accepts) run as the service
principal and return rows. Every other statement is never run: the harness
sends ``EXPLAIN <statement>`` instead. Unity Catalog checks privileges while it
plans a statement, so a missing privilege appears in the EXPLAIN output as
INSUFFICIENT_PERMISSIONS and nothing is executed.

EXPLAIN only covers part of it. Verified against a live workspace, planning
checks USE CATALOG, USE SCHEMA, SELECT on the tables a statement reads, and
READ VOLUME, but not the write privilege itself: an UPDATE by a principal with
SELECT only still plans cleanly. So for writes the harness also asks Unity
Catalog's effective permissions (which include group and inherited grants)
whether the service principal holds the privilege the statement needs on its
target (WRITE_PRIVILEGES); the service principal reads its own effective
permissions. Kinds without a known privilege, and targets that are not fully
qualified, are reported as not checkable instead of guessed.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.query import run_query_as_sp
from app.securable import SecurableParseError, parse_securable
from app.sql_guard import ReadOnlyViolation, SQLTokenizer, assert_read_only

# (securable_type, full_name) -> (the SP's effective privileges, the owner)
UcAccess = Callable[[str, str], Tuple[Set[str], Optional[str]]]


class SqlCheckRejected(ValueError):
    """The statement is not something this feature checks (HTTP 400)."""


# The privileges a write needs, by statement kind. "table" checks the
# statement's target; "schema" and "catalog" check the parent of the object a
# CREATE makes. USE CATALOG and USE SCHEMA on an existing target, and SELECT on
# tables the statement reads, are checked by EXPLAIN.
WRITE_PRIVILEGES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "INSERT": ("table", ("MODIFY",)),
    "UPDATE": ("table", ("MODIFY", "SELECT")),
    "DELETE": ("table", ("MODIFY", "SELECT")),
    "MERGE": ("table", ("MODIFY", "SELECT")),
    "TRUNCATE TABLE": ("table", ("MODIFY",)),
    "COPY INTO": ("table", ("MODIFY",)),
    "CREATE TABLE": ("schema", ("USE_SCHEMA", "CREATE_TABLE")),
    "CREATE TABLE AS SELECT": ("schema", ("USE_SCHEMA", "CREATE_TABLE")),
    "CREATE VIEW": ("schema", ("USE_SCHEMA", "CREATE_TABLE")),
    "CREATE MATERIALIZED VIEW": ("schema", ("USE_SCHEMA", "CREATE_MATERIALIZED_VIEW")),
    "CREATE FUNCTION": ("schema", ("USE_SCHEMA", "CREATE_FUNCTION")),
    "CREATE VOLUME": ("schema", ("USE_SCHEMA", "CREATE_VOLUME")),
    "CREATE SCHEMA": ("catalog", ("USE_CATALOG", "CREATE_SCHEMA")),
}

# A backtick identifier is masked as \ue000<n>\ue000 before matching (see _code_only).
_PART = r"(?:\ue000\d+\ue000|[A-Za-z0-9_]+)"
_NAME = rf"{_PART}(?:\s*\.\s*{_PART})*"
_TARGET = {
    "INSERT": rf"\bINSERT\s+(?:INTO|OVERWRITE)\s+(?:TABLE\s+)?({_NAME})",
    "UPDATE": rf"\bUPDATE\s+({_NAME})",
    "DELETE": rf"\bDELETE\s+FROM\s+({_NAME})",
    "MERGE": rf"\bMERGE\s+INTO\s+({_NAME})",
    "TRUNCATE TABLE": rf"\bTRUNCATE\s+TABLE\s+({_NAME})",
    "COPY INTO": rf"\bCOPY\s+INTO\s+({_NAME})",
    "CREATE": (rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:EXTERNAL\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW|"
               rf"FUNCTION|VOLUME|SCHEMA|DATABASE)\s+(?:IF\s+NOT\s+EXISTS\s+)?({_NAME})"),
}

_GRANTS_MESSAGE = (
    "Grants and ownership changes are tested with the app's grant tests and "
    "promoted in Unity Catalog."
)
_SESSION_MESSAGE = "Not a permission test: session and scripting commands are not checked."
_EXPLAIN_MESSAGE = (
    "Leave out EXPLAIN: the harness adds it for statements that change data or objects."
)
_MULTI_MESSAGE = "Check one statement at a time."
_PLANNED = "Unity Catalog found nothing missing while planning (access to the catalog, schema, and every table it reads)"
_NOT_CHECKABLE_MESSAGE = (
    _PLANNED + ", but checks the privilege for this kind of statement only when it runs, so the "
    "harness can't confirm it. Use the matching action test instead."
)

_GRANT_WORDS = {"GRANT", "REVOKE", "DENY"}
_SESSION_WORDS = {
    "SET", "RESET", "USE", "BEGIN", "DECLARE", "EXECUTE", "CALL", "FOR", "IF",
    "WHILE", "LOOP", "REPEAT", "CASE", "LEAVE", "ITERATE", "CLEAR", "ADD",
}
_WRITE_WORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "DROP", "ALTER", "TRUNCATE",
    "COPY", "OPTIMIZE", "VACUUM", "REFRESH", "ANALYZE", "RESTORE", "UNDROP",
    "COMMENT", "MSCK", "REPAIR", "CACHE", "UNCACHE", "LOAD",
}
_DML_WORDS = ("INSERT", "UPDATE", "DELETE", "MERGE")
_OBJECT_MODIFIERS = {"OR", "REPLACE", "TEMPORARY", "TEMP", "GLOBAL", "EXTERNAL", "IF", "NOT", "EXISTS"}

_PLANNING_ERROR = "Error occurred during query planning"
_DENIED_MARKERS = ("INSUFFICIENT_PERMISSIONS", "PERMISSION_DENIED", "SQLSTATE: 42501", "User does not have")


def _words(sql: str) -> List[str]:
    """Unquoted tokens, upper-cased, with a trailing ';' removed.

    Raises SqlCheckRejected for empty input, unterminated quotes or comments,
    and more than one statement.
    """
    try:
        tokens = SQLTokenizer(sql or "").tokens
    except ReadOnlyViolation as exc:
        raise SqlCheckRejected(str(exc)) from exc
    if tokens and tokens[-1].value == ";":
        tokens = tokens[:-1]
    if any(t.value == ";" for t in tokens):
        raise SqlCheckRejected(_MULTI_MESSAGE)
    words = [t.value.upper() for t in tokens if t.is_keyword]
    if not tokens or not words:
        raise SqlCheckRejected("Enter a SQL statement.")
    return words


def statement_kind(words: List[str]) -> str:
    """Name the statement kind from its leading keywords, e.g. "CREATE TABLE AS SELECT"."""
    first = words[0]
    if first == "WITH":
        return next((w for w in words if w in _DML_WORDS), "WITH")
    if first == "COPY":
        return "COPY INTO"
    if first in ("CREATE", "DROP", "ALTER", "TRUNCATE", "REFRESH", "ANALYZE",
                 "RESTORE", "UNDROP", "COMMENT", "CACHE"):
        rest = [w for w in words[1:] if w not in _OBJECT_MODIFIERS]
        obj = rest[0] if rest else ""
        if obj in ("MATERIALIZED", "STREAMING") and len(rest) > 1:
            obj = f"{obj} {rest[1]}"
        kind = f"{first} {obj}".strip()
        if kind == "CREATE TABLE" and "SELECT" in rest:
            return "CREATE TABLE AS SELECT"
        return kind
    return first


def classify(sql: str) -> Dict[str, str]:
    """Return {"kind": "read" | "check", "statement_kind": ...}.

    "read" statements pass the query runner's read-only guard and run as-is.
    "check" statements are only ever sent wrapped in EXPLAIN. Raises
    SqlCheckRejected for grants, ownership changes, session or scripting
    commands, multiple statements, and anything unrecognized.
    """
    words = _words(sql)
    first = words[0]
    if first in _GRANT_WORDS or (first == "ALTER" and "OWNER" in words):
        raise SqlCheckRejected(_GRANTS_MESSAGE)
    if first in _SESSION_WORDS:
        raise SqlCheckRejected(_SESSION_MESSAGE)

    try:
        assert_read_only(sql)
        return {"kind": "read", "statement_kind": statement_kind(words)}
    except ReadOnlyViolation as exc:
        guard_message = str(exc)

    if first == "EXPLAIN":
        raise SqlCheckRejected(_EXPLAIN_MESSAGE)
    kind = statement_kind(words)
    if first in _WRITE_WORDS or kind in _DML_WORDS:
        return {"kind": "check", "statement_kind": kind}
    raise SqlCheckRejected(guard_message)


def _code_only(sql: str) -> Tuple[str, List[str]]:
    """``sql`` with comments removed, string literals emptied, and each backtick
    identifier replaced by a placeholder, plus the identifiers in order.

    Masking identifiers keeps keywords inside them (for example a CTE named
    `INSERT INTO a.b.c`) from being matched as the statement's own keywords.
    """
    out, idents, i, n = [], [], 0, len(sql)
    while i < n:
        two = sql[i:i + 2]
        if two == "/*":
            depth, i = 1, i + 2
            while i < n and depth:
                if sql[i:i + 2] == "/*":
                    depth, i = depth + 1, i + 2
                elif sql[i:i + 2] == "*/":
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            out.append(" ")
        elif two == "--":
            while i < n and sql[i] != "\n":
                i += 1
        elif sql[i] in "'\"":
            quote, i = sql[i], i + 1
            while i < n and sql[i] != quote:
                i += 2 if sql[i] == "\\" else 1
            i += 1
            out.append("''")
        elif sql[i] == "`":
            j = i + 1
            while j < n and not (sql[j] == "`" and sql[j + 1:j + 2] != "`"):
                j += 2 if sql[j:j + 2] == "``" else 1
            out.append(f"\ue000{len(idents)}\ue000")
            idents.append(sql[i:j + 1])
            i = j + 1
        else:
            out.append(sql[i])
            i += 1
    return "".join(out), idents


def write_target(sql: str, statement_kind_: str) -> Tuple[str, List[Tuple[str, str, Tuple[str, ...]]]]:
    """The privilege checks a write needs, as (problem, [(type, full_name, privileges)]).

    problem is "" when the checks could be worked out, otherwise the reason
    they could not (unknown kind, temporary object, or a name that is not
    fully qualified).
    """
    if statement_kind_ not in WRITE_PRIVILEGES:
        return "unknown", []
    level, privileges = WRITE_PRIVILEGES[statement_kind_]
    code, idents = _code_only(sql)
    if re.search(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY|TEMP)\b", code, re.I):
        return "temporary", []
    key = "CREATE" if statement_kind_.startswith("CREATE") else statement_kind_
    match = re.search(_TARGET[key], code, re.I)
    try:
        name = re.sub(r"\s*\.\s*", ".", match.group(1)) if match else ""
        name = re.sub("\ue000(\\d+)\ue000", lambda m: idents[int(m.group(1))], name)
        parts = parse_securable(name) if name else []
    except (SecurableParseError, IndexError):
        parts = []
    want = 2 if level == "catalog" else 3
    if len(parts) != want:
        return "unqualified", []
    if level == "table":
        return "", [("table", ".".join(parts), privileges)]
    if level == "schema":
        return "", [("schema", ".".join(parts[:2]), privileges), ("catalog", parts[0], ("USE_CATALOG",))]
    return "", [("catalog", parts[0], privileges)]


def _privilege_verdict(checks, uc_access: UcAccess, sp: str) -> Tuple[str, str, List[dict]]:
    """Ask Unity Catalog whether the SP holds every privilege in ``checks``."""
    report, missing = [], []
    for securable_type, full_name, needed in checks:
        held, owner = uc_access(securable_type, full_name)
        is_owner = bool(owner) and owner == sp
        gaps = [] if is_owner or "ALL_PRIVILEGES" in held else [p for p in needed if p not in held]
        report.append({"securable_type": securable_type, "full_name": full_name,
                       "needed": list(needed), "missing": gaps, "owner": is_owner})
        missing += [f"{p.replace('_', ' ')} on {securable_type} {full_name}" for p in gaps]
    if missing:
        return "denied", (_PLANNED + ", but the app SP doesn't hold " + "; ".join(missing)
                          + " (Unity Catalog effective permissions, including group and inherited grants). "
                          "Nothing was run."), report
    held_text = "; ".join(f"{', '.join(p.replace('_', ' ') for p in r['needed'])} on {r['securable_type']} "
                          f"{r['full_name']}" + (" (owner)" if r["owner"] else "") for r in report)
    return "allowed", f"{_PLANNED}, and the app SP holds {held_text}. Nothing was run.", report


def _is_denied(text: str) -> bool:
    return any(marker in text for marker in _DENIED_MARKERS)


def _excerpt(text: str, limit: int = 2000) -> str:
    """The error part of an EXPLAIN result or error string, trimmed."""
    start = text.find(_PLANNING_ERROR)
    lines = [line.strip() for line in text[max(start, 0):].splitlines() if line.strip()]
    return "\n".join(lines)[:limit]


def _result(kind: str, statement_kind_: str, verdict: str, message: str, statement_run: str,
            *, executed: bool, plan: str | None = None, columns: list | None = None,
            rows: list | None = None, truncated: bool = False,
            privileges: list | None = None) -> Dict[str, Any]:
    return {
        "privileges": privileges or [],
        "kind": kind,
        "statement_kind": statement_kind_,
        "verdict": verdict,
        "message": message,
        "plan": plan,
        "columns": columns or [],
        "rows": rows or [],
        "truncated": truncated,
        "executed": executed,
        "statement_run": statement_run,
    }


def check_as_sp(sql: str, *, sp_client: Any, warehouse_id: str, row_limit: int = 100,
                uc_access: Optional[UcAccess] = None, sp: str = "") -> Dict[str, Any]:
    """Check ``sql`` as the app SP. Never runs a statement that changes anything.

    verdict is "allowed", "denied", "invalid" (the statement or its plan has an
    error unrelated to privileges), or "not_checkable". For writes, EXPLAIN runs
    as the SP and then ``uc_access`` (the SP's effective permissions) is asked
    whether ``sp`` holds the write privilege; without it, writes that plan
    cleanly are not checkable. Raises SqlCheckRejected (see
    classify) before contacting the warehouse; otherwise never raises.
    """
    info = classify(sql)
    kind, skind = info["kind"], info["statement_kind"]
    statement = sql.strip()

    if kind == "read":
        res = run_query_as_sp(statement, sp_client=sp_client, warehouse_id=warehouse_id, limit=row_limit)
        error = res.get("error")
        if error:
            verdict = "denied" if _is_denied(error) else "invalid"
            return _result(kind, skind, verdict, error, statement, executed=True)
        return _result(kind, skind, "allowed", "", statement, executed=True,
                       columns=res["columns"], rows=res["rows"], truncated=res["truncated"])

    explain = "EXPLAIN " + (statement[:-1].rstrip() if statement.endswith(";") else statement)
    res = run_query_as_sp(explain, sp_client=sp_client, warehouse_id=warehouse_id, limit=100_000)
    error = res.get("error")
    if error:
        verdict = "denied" if _is_denied(error) else "invalid"
        return _result(kind, skind, verdict, error, explain, executed=False)

    text = "\n".join(str(row[0]) for row in res["rows"] if row)
    if _PLANNING_ERROR in text:
        failure = _excerpt(text)
        verdict = "denied" if _is_denied(failure) else "invalid"
        return _result(kind, skind, verdict, failure, explain, executed=False)

    plan = text[:6000]
    problem, checks = write_target(statement, skind)
    if problem == "unqualified":
        return _result(kind, skind, "not_checkable", _PLANNED + ". Name the target as catalog.schema.table "
                       "(or catalog.schema for CREATE SCHEMA) so the harness can check the write privilege.",
                       explain, executed=False, plan=plan)
    if problem == "temporary":
        return _result(kind, skind, "not_checkable", _PLANNED + ". Temporary objects need no Unity "
                       "Catalog privilege, so there is nothing more to check.", explain, executed=False, plan=plan)
    if problem or uc_access is None:
        return _result(kind, skind, "not_checkable", _NOT_CHECKABLE_MESSAGE, explain, executed=False, plan=plan)
    try:
        verdict, message, report = _privilege_verdict(checks, uc_access, sp)
    except Exception as exc:  # noqa: BLE001 -- report it, never guess
        return _result(kind, skind, "not_checkable",
                       f"{_PLANNED}, but the app SP's effective permissions couldn't be read: {exc}",
                       explain, executed=False, plan=plan)
    return _result(kind, skind, verdict, message, explain, executed=False, plan=plan, privileges=report)
