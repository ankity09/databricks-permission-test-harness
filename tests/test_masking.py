"""Tests for the UC governance-metadata module (Feature 1, masking-aware grid).

describe_governance reads UC metadata (under the OBO identity) to detect which
columns carry a column mask and whether the table has a row filter, so the
results grid can annotate them. It must NEVER raise into the grid: any error
degrades to empty (no annotations).
"""

from __future__ import annotations

from app.masking import describe_governance


def test_detects_masked_columns_and_row_filter():
    def obo_exec(sql):
        u = sql.upper()
        if "COLUMN_MASKS" in u:
            return [{"column_name": "ssn"}, {"column_name": "email"}]
        if "ROW_FILTERS" in u:
            return [{"table_name": "customers"}]
        return []

    out = describe_governance(obo_exec, "c.s.customers")
    assert set(out["masked_columns"]) == {"ssn", "email"}
    assert out["row_filter"] is True


def test_no_governance_returns_empty_flags():
    def obo_exec(sql):
        return []

    out = describe_governance(obo_exec, "c.s.plain")
    assert out["masked_columns"] == []
    assert out["row_filter"] is False


def test_errors_degrade_to_empty_never_raise():
    def obo_exec(sql):
        raise RuntimeError("information_schema not accessible")

    out = describe_governance(obo_exec, "c.s.t")
    assert out["masked_columns"] == []
    assert out["row_filter"] is False


def test_handles_list_row_shape():
    # Some executors return positional rows instead of dicts.
    def obo_exec(sql):
        if "COLUMN_MASKS" in sql.upper():
            return [["ssn"], ["dob"]]
        return []

    out = describe_governance(obo_exec, "c.s.t")
    assert set(out["masked_columns"]) == {"ssn", "dob"}
