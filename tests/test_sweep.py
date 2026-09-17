"""Tests for the adversarial read-only reach sweep (Feature 2).

The sweep asks: can the SP READ things it shouldn't? It auto-enumerates
same-schema siblings + one-level-up containers (under OBO), then the SP
attempts harmless SELECT/USE against each. DENIED = boundary holds (green),
unexpected SUCCESS = hole (red). Fully side-effect-free: no destructive verbs.
"""

from __future__ import annotations

from app.sweep import build_targets, run_sweep


def _obo_exec_factory(tables):
    """Return an obo_exec(sql) that answers SHOW TABLES with `tables`."""
    def _exec(sql):
        if sql.upper().startswith("SHOW TABLES"):
            return [{"database": "s", "tableName": t} for t in tables]
        return []
    return _exec


def test_build_targets_includes_siblings_and_parents():
    obo = _obo_exec_factory(["orders", "customers", "target"])
    targets = build_targets(obo, "c.s.target")
    objs = {t["object"] for t in targets}
    # one-level-up containers
    assert "c" in objs
    assert "c.s" in objs
    # sibling tables other than the target itself
    assert "c.s.orders" in objs
    assert "c.s.customers" in objs
    # the target table itself is not re-probed as a "sibling"
    assert "c.s.target" not in objs


def test_build_targets_actions_are_read_only():
    obo = _obo_exec_factory(["orders"])
    targets = build_targets(obo, "c.s.target")
    for t in targets:
        assert t["action"] in {"use_catalog", "use_schema", "select"}


class _FakeState:
    def __init__(self, v):
        self.value = v


class _FakeStatus:
    def __init__(self, v):
        self.state = _FakeState(v)
        self.error = None


class _FakeResp:
    def __init__(self, state="SUCCEEDED"):
        self.status = _FakeStatus(state)
        self.result = type("R", (), {"data_array": [["x"]]})()


class _FakeSP:
    """Denies SELECT on 'c.s.secret', allows everything else."""
    def __init__(self):
        self.statement_execution = self

    def execute_statement(self, *, statement, **kw):
        if "c.s.secret" in statement:
            raise RuntimeError("PERMISSION_DENIED: not authorized")
        return _FakeResp()


def test_run_sweep_denied_is_hold_success_is_hole():
    targets = [
        {"object": "c.s.secret", "action": "select"},   # denied -> hold (green)
        {"object": "c.s.public", "action": "select"},   # allowed -> hole (red)
    ]
    out = run_sweep(targets, sp_client=_FakeSP(), warehouse_id="w1")
    matrix = {row["object"]: row for row in out["matrix"]}
    assert matrix["c.s.secret"]["result"] == "hold"
    assert matrix["c.s.public"]["result"] == "hole"
    assert out["verdict"]["holes"] == 1
    assert out["verdict"]["status"] == "holes_found"


def test_run_sweep_all_denied_boundaries_hold():
    targets = [
        {"object": "c.s.secret", "action": "select"},
        {"object": "c.s.secret", "action": "select"},
    ]
    out = run_sweep(targets, sp_client=_FakeSP(), warehouse_id="w1")
    assert out["verdict"]["holes"] == 0
    assert out["verdict"]["status"] == "boundaries_hold"
