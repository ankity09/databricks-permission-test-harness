"""Securable-level validation: a UC action must receive a name at the right level.

USE CATALOG needs a 1-part name (`catalog`), USE SCHEMA a 2-part name
(`catalog.schema`), SELECT/MODIFY/etc. a 3-part name. Passing the wrong level
used to fire malformed SQL (PARSE_SYNTAX_ERROR) that got mislabeled as a
grant-authority failure. We validate up front and raise a clear, distinct error.
"""

import pytest

from app.catalog import SecurableLevelError, load_catalog, validate_securable


def test_catalog_level_accepts_one_part():
    d = load_catalog()["uc.catalog.use"]
    # should not raise
    validate_securable(d, "f5_demo_workspace_catalog")


def test_schema_level_accepts_two_parts():
    d = load_catalog()["uc.schema.use"]
    validate_securable(d, "f5_demo_workspace_catalog.f5_watchdog")


def test_table_level_accepts_three_parts():
    d = load_catalog()["uc.table.select"]
    validate_securable(d, "f5_demo_workspace_catalog.f5_watchdog.findings")


def test_catalog_level_rejects_three_part_name():
    """The exact bug the user hit: USE CATALOG given catalog.schema.table."""
    d = load_catalog()["uc.catalog.use"]
    with pytest.raises(SecurableLevelError) as exc:
        validate_securable(d, "f5_demo_workspace_catalog.f5_watchdog.findings")
    msg = str(exc.value)
    # message must be actionable: name the expected level and the parts given
    assert "catalog" in msg.lower()
    assert "f5_demo_workspace_catalog.f5_watchdog.findings" in msg


def test_table_level_rejects_one_part_name():
    d = load_catalog()["uc.table.select"]
    with pytest.raises(SecurableLevelError):
        validate_securable(d, "just_a_catalog")


def test_workspace_action_without_level_is_not_validated():
    """Workspace-object actions declare no securable_level -> no part-count check."""
    d = load_catalog()["ws.job.can_run"]
    # a job id / path is opaque; must not raise regardless of dots
    validate_securable(d, "123456789")
    validate_securable(d, "/Repos/team/thing")
