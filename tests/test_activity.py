import contextlib

import app.activity as activity


class FakeCursor:
    def __init__(self, rows=None):
        self.executed = []
        self._rows = rows or []
        self.description = [("id",), ("event_type",)]

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows)
        self.committed = False

    def cursor(self, *a, **k):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def _factory(conn):
    @contextlib.contextmanager
    def factory():
        yield conn

    return factory


def test_log_event_inserts_row_and_commits():
    conn = FakeConn()
    activity.log_event(
        conn_factory=_factory(conn),
        schema="perm_harness",
        session_id="s1",
        admin_email="a@x.com",
        sp_id="sp1",
        event_type="apply",
        action_id="uc.table.select",
        securable="c.s.t",
        verdict=None,
        raw_message="",
        scenario_id=None,
    )
    sql, params = conn.cursor_obj.executed[0]
    assert "insert into perm_harness.activity_log" in sql.lower()
    assert "apply" in params
    assert conn.committed is True


def test_log_event_rejects_bad_event_type():
    conn = FakeConn()
    try:
        activity.log_event(
            conn_factory=_factory(conn),
            schema="perm_harness",
            session_id="s1",
            admin_email="a@x.com",
            sp_id="sp1",
            event_type="nonsense",
            action_id="a",
            securable="s",
            verdict=None,
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_read_events_filters_by_verdict():
    conn = FakeConn(rows=[{"id": 1, "event_type": "probe"}])
    rows = activity.read_events(
        conn_factory=_factory(conn), schema="perm_harness", verdict="pass", limit=10
    )
    sql, params = conn.cursor_obj.executed[0]
    assert "where" in sql.lower() and "verdict" in sql.lower()
    assert "pass" in params
    assert rows == [{"id": 1, "event_type": "probe"}]
