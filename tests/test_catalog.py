import os

import pytest

from app.catalog import DescriptorError, load_catalog, resolve

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_resolve_select_grant_sql():
    d = load_catalog()["uc.table.select"]
    sql = resolve(d.grant_sql, securable="main.sales.orders", sp="sp_app")
    assert sql == "GRANT SELECT ON TABLE main.sales.orders TO `sp_app`"


def test_resolve_derives_securable_path_for_volumes():
    out = resolve("LIST '/Volumes/{securable_path}'", securable="main.raw.files")
    assert out == "LIST '/Volumes/main/raw/files'"


def test_resolve_missing_placeholder_raises():
    with pytest.raises(KeyError):
        resolve("GRANT SELECT ON TABLE {securable} TO `{sp}`", securable="main.s.t")


def test_full_catalog_loads_and_indexes_by_id():
    catalog = load_catalog()
    assert "uc.table.select" in catalog
    assert "ws.job.can_run" in catalog
    # every descriptor keyed by its own id
    assert all(k == v.id for k, v in catalog.items())


def test_malformed_descriptor_rejected():
    with pytest.raises(DescriptorError):
        load_catalog(path=os.path.join(_FIXTURES, "bad_actions.yaml"))
