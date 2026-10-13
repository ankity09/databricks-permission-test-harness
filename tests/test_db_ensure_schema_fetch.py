"""ensure_schema against a cursor that behaves like a real one (fetchone consumes the row)."""

from app.db import ensure_schema


class RealisticCursor:
    """fetchone() returns the row once, then None, like psycopg."""

    def __init__(self, tables_exist: bool):
        self.executed = []
        self._tables_exist = tables_exist
        self._row = None

    def execute(self, sql, params=None):
        self.executed.append(sql)
        self._row = (self._tables_exist,) if "to_regclass" in sql else None

    def fetchone(self):
        row, self._row = self._row, None
        return row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RealisticConnection:
    def __init__(self, tables_exist: bool):
        self.cursor_obj = RealisticCursor(tables_exist)
        self.committed = False
        self.rolled_back = False

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_creates_everything_when_tables_are_missing():
    """Fetching the existence row once must not crash (it used to call fetchone twice)."""
    conn = RealisticConnection(tables_exist=False)
    ensure_schema(conn, "perm_harness")

    sql = " ".join(conn.cursor_obj.executed)
    assert 'CREATE SCHEMA IF NOT EXISTS "perm_harness"' in sql
    assert 'CREATE TABLE IF NOT EXISTS "perm_harness".activity_log' in sql
    assert 'CREATE TABLE IF NOT EXISTS "perm_harness".scenarios' in sql
    assert "`" not in sql  # Postgres identifiers use double quotes, never backticks
    assert conn.committed and not conn.rolled_back


def test_runs_no_ddl_when_both_tables_exist():
    """Existing tables may belong to another role, so no CREATE is attempted at all."""
    conn = RealisticConnection(tables_exist=True)
    ensure_schema(conn, "perm_harness")

    assert len(conn.cursor_obj.executed) == 1
    assert "to_regclass" in conn.cursor_obj.executed[0]
    assert not conn.rolled_back
