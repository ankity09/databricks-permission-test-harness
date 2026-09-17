"""Tests for the run-query-as-SP module (Feature 1).

The query runner executes a read-only statement AS THE APP SP and returns the
actual rows so the tester can see what the SP sees (column masks, row filters).
Denials/errors are captured as data, never raised.
"""

from __future__ import annotations

import pytest

from app.query import build_select, run_query_as_sp


class _FakeState:
    def __init__(self, value):
        self.value = value


class _FakeStatus:
    def __init__(self, state, error=None):
        self.state = _FakeState(state)
        self.error = error


class _FakeManifestCol:
    def __init__(self, name):
        self.name = name


class _FakeSchema:
    def __init__(self, names):
        self.columns = [_FakeManifestCol(n) for n in names]


class _FakeManifest:
    def __init__(self, names):
        self.schema = _FakeSchema(names)


class _FakeResult:
    def __init__(self, data_array):
        self.data_array = data_array


class _FakeResp:
    def __init__(self, *, state="SUCCEEDED", cols=None, data=None, error=None):
        self.status = _FakeStatus(state, error)
        self.manifest = _FakeManifest(cols or [])
        self.result = _FakeResult(data) if data is not None else None


class _FakeSPClient:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc
        self.statement_execution = self

    def execute_statement(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._resp


def test_build_select_produces_limited_select():
    assert build_select("c.s.t", 50) == "SELECT * FROM c.s.t LIMIT 50"


def test_build_select_rejects_non_three_part():
    with pytest.raises(ValueError):
        build_select("c.s", 50)


def test_run_query_returns_columns_and_rows():
    resp = _FakeResp(cols=["id", "email"], data=[["1", "a@x.com"], ["2", "***"]])
    out = run_query_as_sp(
        "SELECT * FROM c.s.t LIMIT 50",
        sp_client=_FakeSPClient(resp=resp),
        warehouse_id="w1",
        limit=50,
    )
    assert out["columns"] == ["id", "email"]
    assert out["rows"] == [["1", "a@x.com"], ["2", "***"]]
    assert out["truncated"] is False
    assert out.get("error") is None


def test_run_query_truncates_to_limit():
    data = [[str(i)] for i in range(10)]
    resp = _FakeResp(cols=["id"], data=data)
    out = run_query_as_sp(
        "SELECT * FROM c.s.t",
        sp_client=_FakeSPClient(resp=resp),
        warehouse_id="w1",
        limit=3,
    )
    assert len(out["rows"]) == 3
    assert out["truncated"] is True


def test_run_query_permission_denied_is_captured_not_raised():
    sp = _FakeSPClient(exc=RuntimeError("PERMISSION_DENIED: SP cannot SELECT"))
    out = run_query_as_sp(
        "SELECT * FROM c.s.t",
        sp_client=sp,
        warehouse_id="w1",
    )
    assert out["rows"] == []
    assert out["columns"] == []
    assert "PERMISSION_DENIED" in out["error"]


def test_run_query_failed_state_is_captured():
    resp = _FakeResp(state="FAILED", error=type("E", (), {"message": "boom"})())
    out = run_query_as_sp(
        "SELECT * FROM c.s.t",
        sp_client=_FakeSPClient(resp=resp),
        warehouse_id="w1",
    )
    assert "boom" in out["error"]
    assert out["rows"] == []
