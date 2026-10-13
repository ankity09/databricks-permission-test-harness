"""Tests for scenario pre-flight validation (new feature).

Validates that all items in a scenario pass checks (action_id exists and known,
securable is non-empty and parses correctly, securable is at correct level for
the action) BEFORE any apply/probe/revoke operations execute.
"""

import pytest

import app.scenarios as scen
from app.catalog import load_catalog, SecurableLevelError
from app.securable import SecurableParseError


def test_validate_scenario_items_empty_list_passes():
    """Empty item list is valid."""
    catalog = load_catalog()
    scen.validate_scenario_items([], catalog)  # Should not raise


def test_validate_scenario_items_valid_items_pass():
    """Valid items with known actions and proper securables pass."""
    catalog = load_catalog()
    items = [
        {"action_id": "uc.catalog.use", "securable": "main"},
        {"action_id": "uc.table.select", "securable": "main.sales.orders"},
    ]
    scen.validate_scenario_items(items, catalog)  # Should not raise


def test_validate_scenario_items_missing_action_id_raises():
    """Missing action_id raises ValidationError with row index."""
    catalog = load_catalog()
    items = [
        {"action_id": "uc.catalog.use", "securable": "main"},
        {"securable": "main.sales.orders"},  # Missing action_id
    ]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 1
    assert "action_id" in exc_info.value.message.lower()
    assert exc_info.value.action_id == ""


def test_validate_scenario_items_empty_action_id_raises():
    """Empty action_id string raises ValidationError."""
    catalog = load_catalog()
    items = [{"action_id": "", "securable": "main"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert "action_id" in exc_info.value.message.lower()


def test_validate_scenario_items_whitespace_only_action_id_raises():
    """Whitespace-only action_id is treated as empty."""
    catalog = load_catalog()
    items = [{"action_id": "   ", "securable": "main"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0


def test_validate_scenario_items_missing_securable_raises():
    """Missing securable raises ValidationError."""
    catalog = load_catalog()
    items = [{"action_id": "uc.catalog.use"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert "securable" in exc_info.value.message.lower()
    assert exc_info.value.securable == ""


def test_validate_scenario_items_empty_securable_raises():
    """Empty securable string raises ValidationError."""
    catalog = load_catalog()
    items = [{"action_id": "uc.catalog.use", "securable": ""}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert "securable" in exc_info.value.message.lower()


def test_validate_scenario_items_whitespace_only_securable_raises():
    """Whitespace-only securable is treated as empty."""
    catalog = load_catalog()
    items = [{"action_id": "uc.catalog.use", "securable": "   "}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0


def test_validate_scenario_items_unfilled_placeholder_raises():
    """Securable with unfilled placeholders (e.g. {catalog}) raises."""
    catalog = load_catalog()
    items = [{"action_id": "uc.catalog.use", "securable": "{catalog}"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert "placeholder" in exc_info.value.message.lower()


def test_validate_scenario_items_multiple_placeholders_raises():
    """Securable with multiple placeholders raises."""
    catalog = load_catalog()
    items = [{"action_id": "uc.table.select", "securable": "{catalog}.{schema}.{table}"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert "placeholder" in exc_info.value.message.lower()


def test_validate_scenario_items_unknown_action_id_raises():
    """Unknown action_id raises ValidationError."""
    catalog = load_catalog()
    items = [{"action_id": "bogus.fake.action", "securable": "main"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert "not found" in exc_info.value.message.lower() or "action_id" in exc_info.value.message.lower()
    assert exc_info.value.action_id == "bogus.fake.action"


def test_validate_scenario_items_unparseable_securable_raises():
    """Securable that fails parsing raises ValidationError."""
    catalog = load_catalog()
    items = [{"action_id": "uc.catalog.use", "securable": "main'; DROP TABLE users; --"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0
    assert exc_info.value.action_id == "uc.catalog.use"


def test_validate_scenario_items_wrong_level_raises():
    """Securable at wrong level for action raises ValidationError."""
    catalog = load_catalog()
    # uc.catalog.use expects a 1-part catalog name, not 3-part table name
    items = [{"action_id": "uc.catalog.use", "securable": "main.sales.orders"}]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 0


def test_validate_scenario_items_stops_at_first_error():
    """Validation stops at the first error (doesn't validate all items)."""
    catalog = load_catalog()
    items = [
        {"action_id": "uc.catalog.use", "securable": "main"},  # valid
        {"action_id": "uc.table.select", "securable": "main"},  # invalid level
        {"action_id": "", "securable": "main"},  # would error too but not checked
    ]
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    assert exc_info.value.row == 1  # Second item (index 1)


def test_validate_scenario_items_carries_full_detail():
    """ValidationError carries all fields (message, row, action_id, securable)."""
    catalog = load_catalog()
    items = [{"action_id": "uc.table.select", "securable": "main"}]  # wrong level
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.validate_scenario_items(items, catalog)
    err = exc_info.value
    assert err.row == 0
    assert err.action_id == "uc.table.select"
    assert err.securable == "main"
    assert len(err.message) > 0


def test_run_scenario_with_catalog_validates_before_execute():
    """run_scenario accepts optional catalog; if provided, validates before execution."""
    catalog = load_catalog()
    events = []

    def apply_fn(action_id, securable):
        events.append(("apply", action_id))

    def probe_fn(action_id, securable):
        return {"status": "pass"}

    def revoke_fn(action_id, securable):
        events.append(("revoke", action_id))

    items = [{"action_id": "invalid.action", "securable": "main"}]

    # Without catalog, no validation occurs (backward compatible).
    # With catalog, validation runs before apply.
    with pytest.raises(scen.ValidationError) as exc_info:
        scen.run_scenario(
            items, apply_fn=apply_fn, probe_fn=probe_fn, revoke_fn=revoke_fn, catalog=catalog
        )
    assert exc_info.value.row == 0
    # No applies/revokes happened
    assert events == []
