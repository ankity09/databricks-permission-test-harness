import app.scenarios as scen


def test_run_scenario_applies_all_then_probes_each_then_revokes_all():
    events = []
    items = [
        {"action_id": "uc.catalog.use", "securable": "main"},
        {"action_id": "uc.table.select", "securable": "main.sales.orders"},
    ]

    def apply_fn(action_id, securable):
        events.append(("apply", action_id))

    def probe_fn(action_id, securable):
        events.append(("probe", action_id))
        return {"status": "pass", "detail": "ok"}

    def revoke_fn(action_id, securable):
        events.append(("revoke", action_id))

    matrix = scen.run_scenario(
        items, apply_fn=apply_fn, probe_fn=probe_fn, revoke_fn=revoke_fn
    )
    kinds = [e[0] for e in events]
    # all applies precede all probes; all revokes happen at the end
    assert kinds == ["apply", "apply", "probe", "probe", "revoke", "revoke"]
    assert matrix["overall"] == "pass"
    assert len(matrix["results"]) == 2


def test_run_scenario_revokes_all_even_when_probe_raises():
    revoked = []
    items = [{"action_id": "a", "securable": "s"}]

    def apply_fn(a, s):
        pass

    def probe_fn(a, s):
        raise RuntimeError("boom")

    def revoke_fn(a, s):
        revoked.append(a)

    matrix = scen.run_scenario(
        items, apply_fn=apply_fn, probe_fn=probe_fn, revoke_fn=revoke_fn
    )
    assert revoked == ["a"]  # revoke-all still fired
    assert matrix["results"][0]["status"] == "error"
    assert matrix["overall"] == "fail"


def test_load_seed_scenarios_has_analyst():
    seeds = scen.load_seed_scenarios()
    names = [s["name"] for s in seeds]
    assert "Data Analyst" in names
    # every seed item references a real-looking action id
    for s in seeds:
        for it in s["items"]:
            assert it["action_id"].startswith("uc.")


def test_scenario_crud_save_and_list_with_fake_conn():
    import contextlib

    class FakeCursor:
        def __init__(self, rows=None):
            self.executed = []
            self._rows = rows or []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

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

    conn = FakeConn()

    @contextlib.contextmanager
    def factory():
        yield conn

    sid = scen.save_scenario(
        conn_factory=factory,
        schema="perm_harness",
        name="Custom",
        description="d",
        created_by="a@x.com",
        items=[{"action_id": "uc.table.select", "securable": "c.s.t"}],
    )
    assert sid
    sql, params = conn.cursor_obj.executed[0]
    assert "insert into perm_harness.scenarios" in sql.lower()
    assert conn.committed is True
