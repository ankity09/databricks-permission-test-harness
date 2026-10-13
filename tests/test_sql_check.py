"""SQL check: any statement checked as the app SP without changing anything."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sql_check import WRITE_PRIVILEGES, SqlCheckRejected, check_as_sp, classify, write_target

client = TestClient(app)
TOKEN = {"x-forwarded-access-token": "test-token"}

PLANNING_DENIED_ROWS = [
    ["Error occurred during query planning: "],
    ["[INSUFFICIENT_PERMISSIONS] Insufficient privileges:"],
    ["User does not have MODIFY on Table 'main.sandbox.orders'. SQLSTATE: 42501"],
]
PLANNING_INVALID_ROWS = [
    ["Error occurred during query planning: "],
    ["[TABLE_OR_VIEW_NOT_FOUND] The table or view `main`.`sandbox`.`nope` cannot be found. SQLSTATE: 42P01"],
]
CLEAN_PLAN_ROWS = [["== Physical Plan ==\nAppendDataExecV1 [num_affected_rows#1L], DeltaTableV2(...)"]]


class FakeSP:
    """Records every statement and answers like the Statement Execution API."""

    def __init__(self, rows=None, error=None, raises=None):
        self.sent = []
        self._rows, self._error, self._raises = rows, error, raises
        self.statement_execution = self

    def execute_statement(self, statement, warehouse_id, wait_timeout):
        self.sent.append(statement)
        if self._raises:
            raise self._raises
        if self._error:
            return SimpleNamespace(status=SimpleNamespace(
                state=SimpleNamespace(value="FAILED"), error=SimpleNamespace(message=self._error)))
        return SimpleNamespace(
            status=SimpleNamespace(state=SimpleNamespace(value="SUCCEEDED")),
            manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name="plan")])),
            result=SimpleNamespace(data_array=self._rows or []),
        )


SP_ID = "app-sp-id"


def uc(grants=None, owners=None):
    """Fake effective permissions: {(type, full_name): {privileges}}, {(type, name): owner}."""
    grants, owners = grants or {}, owners or {}
    calls = []

    def access(securable_type, full_name):
        calls.append((securable_type, full_name))
        return set(grants.get((securable_type, full_name), set())), owners.get((securable_type, full_name))

    access.calls = calls
    return access


def run(sql, uc_access=None, **fake):
    sp = FakeSP(**fake)
    return check_as_sp(sql, sp_client=sp, warehouse_id="wh", uc_access=uc_access, sp=SP_ID), sp


# --- classification -------------------------------------------------------

@pytest.mark.parametrize("sql,kind,skind", [
    ("SELECT * FROM t", "read", "SELECT"),
    ("WITH x AS (SELECT 1) SELECT * FROM x", "read", "WITH"),
    ("SHOW TABLES IN main.sandbox", "read", "SHOW"),
    ("DESCRIBE TABLE t", "read", "DESCRIBE"),
    ("EXPLAIN SELECT 1", "read", "EXPLAIN"),
    ("INSERT INTO t VALUES (1)", "check", "INSERT"),
    ("INSERT OVERWRITE t SELECT * FROM s", "check", "INSERT"),
    ("UPDATE t SET a = 1", "check", "UPDATE"),
    ("DELETE FROM t WHERE a = 1", "check", "DELETE"),
    ("MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN DELETE", "check", "MERGE"),
    ("WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", "check", "INSERT"),
    ("CREATE TABLE t AS SELECT 1", "check", "CREATE TABLE AS SELECT"),
    ("CREATE OR REPLACE TABLE t AS SELECT 1", "check", "CREATE TABLE AS SELECT"),
    ("CREATE TABLE IF NOT EXISTS t (a INT)", "check", "CREATE TABLE"),
    ("CREATE VIEW v AS SELECT 1", "check", "CREATE VIEW"),
    ("CREATE OR REPLACE VIEW v AS SELECT 1", "check", "CREATE VIEW"),
    ("CREATE MATERIALIZED VIEW mv AS SELECT 1", "check", "CREATE MATERIALIZED VIEW"),
    ("CREATE SCHEMA s", "check", "CREATE SCHEMA"),
    ("DROP TABLE IF EXISTS t", "check", "DROP TABLE"),
    ("ALTER TABLE t ADD COLUMN b INT", "check", "ALTER TABLE"),
    ("TRUNCATE TABLE t", "check", "TRUNCATE TABLE"),
    ("COPY INTO t FROM '/Volumes/a/b/c'", "check", "COPY INTO"),
    ("OPTIMIZE t", "check", "OPTIMIZE"),
    ("/* note */ DELETE FROM t -- trailing", "check", "DELETE"),
])
def test_classify(sql, kind, skind):
    assert classify(sql) == {"kind": kind, "statement_kind": skind}


@pytest.mark.parametrize("sql,message", [
    ("GRANT SELECT ON TABLE t TO `someone`", "Grants and ownership"),
    ("REVOKE SELECT ON TABLE t FROM `someone`", "Grants and ownership"),
    ("ALTER TABLE t OWNER TO `someone`", "Grants and ownership"),
    ("ALTER SCHEMA s SET OWNER TO `someone`", "Grants and ownership"),
    ("SET spark.sql.ansi.enabled = true", "Not a permission test"),
    ("USE CATALOG main", "Not a permission test"),
    ("BEGIN SELECT 1; END", "one statement"),
    ("EXPLAIN UPDATE t SET a = 1", "Leave out EXPLAIN"),
    ("SELECT 1; DELETE FROM t", "one statement"),
    ("SELECT 1; SELECT 2", "one statement"),
    ("", "Enter a SQL statement"),
    ("-- only a comment", "Enter a SQL statement"),
    ("SELECT 'unterminated", "Unterminated"),
    ("SELECT * FROM t WHERE drop = 1", "dangerous keyword"),
])
def test_classify_rejects(sql, message):
    with pytest.raises(SqlCheckRejected, match=f"(?i){message}"):
        classify(sql)


# --- the safety property: nothing that changes anything is ever run --------

@pytest.mark.parametrize("sql", [
    "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x",
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET a = 1",
    "DELETE FROM t",
    "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN DELETE",
    "CREATE TABLE t AS SELECT 1",
    "CREATE VIEW v AS SELECT 1",
])
def test_checkable_writes_are_only_sent_as_explain(sql):
    result, sp = run(sql, rows=CLEAN_PLAN_ROWS)
    assert sp.sent == ["EXPLAIN " + sql]
    assert result["executed"] is False and result["statement_run"] == "EXPLAIN " + sql


@pytest.mark.parametrize("sql", [
    "DROP TABLE main.s.t", "ALTER TABLE main.s.t ADD COLUMN b INT", "OPTIMIZE main.s.t",
    "VACUUM main.s.t", "COMMENT ON TABLE main.s.t IS 'x'",
])
def test_kinds_without_a_known_privilege_are_explained_but_not_checkable(sql):
    access = uc()
    result, sp = run(sql, uc_access=access, rows=CLEAN_PLAN_ROWS)
    assert sp.sent == ["EXPLAIN " + sql]  # EXPLAIN still catches missing USE or SELECT
    assert result["verdict"] == "not_checkable" and result["executed"] is False
    assert access.calls == []


def test_every_write_privilege_kind_is_classifiable():
    examples = {
        "INSERT": "INSERT INTO c.s.t VALUES (1)", "UPDATE": "UPDATE c.s.t SET a = 1",
        "DELETE": "DELETE FROM c.s.t", "MERGE": "MERGE INTO c.s.t USING c.s.u ON t.id = u.id WHEN MATCHED THEN DELETE",
        "TRUNCATE TABLE": "TRUNCATE TABLE c.s.t", "COPY INTO": "COPY INTO c.s.t FROM '/Volumes/c/s/v'",
        "CREATE TABLE": "CREATE TABLE c.s.t (a INT)", "CREATE TABLE AS SELECT": "CREATE TABLE c.s.t AS SELECT 1",
        "CREATE VIEW": "CREATE VIEW c.s.v AS SELECT 1", "CREATE MATERIALIZED VIEW": "CREATE MATERIALIZED VIEW c.s.m AS SELECT 1",
        "CREATE FUNCTION": "CREATE FUNCTION c.s.f() RETURNS INT RETURN 1", "CREATE VOLUME": "CREATE VOLUME c.s.v",
        "CREATE SCHEMA": "CREATE SCHEMA c.s",
    }
    assert set(examples) == set(WRITE_PRIVILEGES)
    for kind, sql in examples.items():
        assert classify(sql)["statement_kind"] == kind
        problem, checks = write_target(sql, kind)
        assert problem == "" and checks, kind


@pytest.mark.parametrize("sql,kind,expected", [
    ("UPDATE main.sandbox.orders SET a = 1", "UPDATE", ("", [("table", "main.sandbox.orders", ("MODIFY", "SELECT"))])),
    ("WITH x AS (SELECT 1) INSERT INTO main.s.t SELECT * FROM x", "INSERT", ("", [("table", "main.s.t", ("MODIFY",))])),
    ("INSERT INTO `my cat`.s.`t-1` VALUES (1)", "INSERT", ("", [("table", "my cat.s.t-1", ("MODIFY",))])),
    ("/* UPDATE a.b.c */ DELETE FROM main.s.t -- x", "DELETE", ("", [("table", "main.s.t", ("MODIFY", "SELECT"))])),
    ("UPDATE main.s.t SET v = 'UPDATE a.b.c'", "UPDATE", ("", [("table", "main.s.t", ("MODIFY", "SELECT"))])),
    ("CREATE OR REPLACE TABLE main.s.t AS SELECT 1", "CREATE TABLE AS SELECT",
     ("", [("schema", "main.s", ("USE_SCHEMA", "CREATE_TABLE")), ("catalog", "main", ("USE_CATALOG",))])),
    ("CREATE SCHEMA main.new_schema", "CREATE SCHEMA", ("", [("catalog", "main", ("USE_CATALOG", "CREATE_SCHEMA"))])),
    # Keywords inside a backtick identifier are not the statement's own keywords.
    ("WITH `INSERT INTO main.s.allowed_t` AS (SELECT 1 AS c) INSERT INTO main.s.target_t "
     "SELECT c FROM `INSERT INTO main.s.allowed_t`", "INSERT",
     ("", [("table", "main.s.target_t", ("MODIFY",))])),
    ("UPDATE `main`.`odd ``name`` here`.t SET a = 1", "UPDATE",
     ("", [("table", "main.odd `name` here.t", ("MODIFY", "SELECT"))])),
    ("UPDATE orders SET a = 1", "UPDATE", ("unqualified", [])),
    ("CREATE TEMPORARY VIEW v AS SELECT 1", "CREATE VIEW", ("temporary", [])),
    ("DROP TABLE main.s.t", "DROP TABLE", ("unknown", [])),
])
def test_write_target(sql, kind, expected):
    assert write_target(sql, kind) == expected


def test_trailing_semicolon_is_dropped_before_explain():
    _, sp = run("UPDATE t SET a = 1;", rows=CLEAN_PLAN_ROWS)
    assert sp.sent == ["EXPLAIN UPDATE t SET a = 1"]


# --- verdicts -------------------------------------------------------------

def test_permission_error_inside_a_successful_explain_is_denied():
    # Live behavior: EXPLAIN succeeds and the denial is in the plan rows.
    result, _ = run("UPDATE main.sandbox.orders SET a = 1", rows=PLANNING_DENIED_ROWS)
    assert result["verdict"] == "denied"
    assert "User does not have MODIFY" in result["message"]


def test_planning_error_without_permission_problem_is_invalid():
    result, _ = run("DELETE FROM main.sandbox.nope", rows=PLANNING_INVALID_ROWS)
    assert result["verdict"] == "invalid"
    assert "TABLE_OR_VIEW_NOT_FOUND" in result["message"]


def test_clean_plan_and_held_privileges_is_allowed():
    access = uc({("table", "main.s.t"): {"MODIFY", "SELECT", "READ_METADATA"}})
    result, _ = run("UPDATE main.s.t SET a = 1", uc_access=access, rows=CLEAN_PLAN_ROWS)
    assert result["verdict"] == "allowed"
    assert "AppendDataExecV1" in result["plan"]
    assert result["privileges"][0]["missing"] == []


def test_clean_plan_but_missing_modify_is_denied():
    # Live behavior: an SP with SELECT only still gets a clean EXPLAIN for UPDATE.
    access = uc({("table", "main.s.t"): {"SELECT", "READ_METADATA"}})
    result, _ = run("UPDATE main.s.t SET a = 1", uc_access=access, rows=CLEAN_PLAN_ROWS)
    assert result["verdict"] == "denied"
    assert "MODIFY on table main.s.t" in result["message"]
    assert result["privileges"][0]["missing"] == ["MODIFY"]


def test_all_privileges_or_ownership_satisfies_the_check():
    by_grant = uc({("table", "main.s.t"): {"ALL_PRIVILEGES"}})
    by_owner = uc(owners={("table", "main.s.t"): SP_ID})
    assert run("DELETE FROM main.s.t", uc_access=by_grant, rows=CLEAN_PLAN_ROWS)[0]["verdict"] == "allowed"
    assert run("DELETE FROM main.s.t", uc_access=by_owner, rows=CLEAN_PLAN_ROWS)[0]["verdict"] == "allowed"


def test_create_checks_the_parent_schema_and_catalog():
    access = uc({("schema", "main.s"): {"USE_SCHEMA"}, ("catalog", "main"): {"USE_CATALOG"}})
    result, _ = run("CREATE TABLE main.s.t AS SELECT 1", uc_access=access, rows=CLEAN_PLAN_ROWS)
    assert result["verdict"] == "denied"
    assert "CREATE TABLE on schema main.s" in result["message"]
    assert access.calls == [("schema", "main.s"), ("catalog", "main")]


def test_unqualified_target_is_not_checkable():
    result, _ = run("UPDATE orders SET a = 1", uc_access=uc(), rows=CLEAN_PLAN_ROWS)
    assert result["verdict"] == "not_checkable" and "catalog.schema.table" in result["message"]


def test_without_effective_permissions_a_clean_write_is_not_checkable():
    result, _ = run("UPDATE main.s.t SET a = 1", rows=CLEAN_PLAN_ROWS)
    assert result["verdict"] == "not_checkable"


def test_effective_permission_errors_are_reported_not_guessed():
    def broken(securable_type, full_name):
        raise RuntimeError("PERMISSION_DENIED: cannot read grants")
    result, _ = run("UPDATE main.s.t SET a = 1", uc_access=broken, rows=CLEAN_PLAN_ROWS)
    assert result["verdict"] == "not_checkable" and "cannot read grants" in result["message"]


def test_planning_denial_wins_before_effective_permissions_are_asked():
    access = uc({("table", "main.s.t"): {"MODIFY", "SELECT"}})
    result, _ = run("UPDATE main.s.t SET a = 1", uc_access=access, rows=PLANNING_DENIED_ROWS)
    assert result["verdict"] == "denied" and access.calls == []


def test_literal_text_in_a_clean_plan_is_not_mistaken_for_a_denial():
    rows = [["== Physical Plan ==\nLocalTableScan ['User does not have MODIFY']"]]
    access = uc({("table", "main.s.t"): {"MODIFY"}})
    result, _ = run("INSERT INTO main.s.t VALUES ('User does not have MODIFY')", uc_access=access, rows=rows)
    assert result["verdict"] == "allowed"


def test_explain_request_failure_maps_to_denied_or_invalid():
    denied, _ = run("UPDATE t SET a = 1", error="[INSUFFICIENT_PERMISSIONS] User does not have USE CATALOG")
    invalid, _ = run("UPDATE t SET a = 1", error="[PARSE_SYNTAX_ERROR] Syntax error at or near 'SET'")
    assert (denied["verdict"], invalid["verdict"]) == ("denied", "invalid")


def test_exception_is_captured_not_raised():
    result, _ = run("UPDATE t SET a = 1", raises=RuntimeError("warehouse unreachable"))
    assert result["verdict"] == "invalid" and "warehouse unreachable" in result["message"]


def test_read_runs_as_is_and_returns_rows():
    result, sp = run("SELECT id FROM t", rows=[["1"], ["2"]])
    assert sp.sent == ["SELECT id FROM t"]
    assert (result["verdict"], result["rows"], result["executed"]) == ("allowed", [["1"], ["2"]], True)


def test_read_denied():
    result, _ = run("SELECT * FROM t", error="[INSUFFICIENT_PERMISSIONS] User does not have SELECT on Table 't'.")
    assert result["verdict"] == "denied"


def test_rejected_statement_never_reaches_the_warehouse():
    sp = FakeSP(rows=CLEAN_PLAN_ROWS)
    with pytest.raises(SqlCheckRejected):
        check_as_sp("GRANT SELECT ON TABLE t TO `someone`", sp_client=sp, warehouse_id="wh")
    assert sp.sent == []


# --- endpoint -------------------------------------------------------------

def test_endpoint_requires_a_signed_in_user():
    assert client.post("/api/sql/check", json={"sql": "SELECT 1"}).status_code == 401


def test_endpoint_rejects_grants_with_400():
    r = client.post("/api/sql/check", json={"sql": "GRANT SELECT ON TABLE t TO `x`"}, headers=TOKEN)
    assert r.status_code == 400 and "Grants" in r.json()["detail"]


def test_endpoint_checks_a_write_and_logs_it():
    sp = FakeSP(rows=PLANNING_DENIED_ROWS)
    with patch("app.main.get_sp_client", return_value=sp), patch("app.main._log_event") as log, \
         patch("app.main._uc_access", return_value=uc()), patch("app.main._configured_sp", return_value=SP_ID):
        r = client.post("/api/sql/check",
                        json={"sql": "UPDATE main.sandbox.orders SET a = 1", "table": "main.sandbox.orders"},
                        headers=TOKEN)
    assert r.status_code == 200
    body = r.json()
    assert (body["verdict"], body["kind"], body["executed"]) == ("denied", "check", False)
    assert sp.sent == ["EXPLAIN UPDATE main.sandbox.orders SET a = 1"]
    assert log.call_args.kwargs["event_type"] == "sql_check"
    assert log.call_args.kwargs["verdict"] == "fail_denied"
    assert log.call_args.kwargs["securable"] == "main.sandbox.orders"


def test_endpoint_ignores_an_invalid_table_tag():
    sp = FakeSP(rows=[["1"]])
    with patch("app.main.get_sp_client", return_value=sp), patch("app.main._log_event") as log, \
         patch("app.main._uc_access", return_value=uc()), patch("app.main._configured_sp", return_value=SP_ID):
        r = client.post("/api/sql/check", json={"sql": "SELECT 1", "table": "t; DROP TABLE x"}, headers=TOKEN)
    assert r.status_code == 200
    assert log.call_args.kwargs["securable"] == "(free-text)"
