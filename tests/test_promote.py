from app.promote import build_promote_info


def test_promote_returns_grant_sql_and_uc_link():
    info = build_promote_info(
        action_id="uc.table.select",
        securable="main.sales.orders",
        principal="analyst@corp.com",
        host="https://x.databricks.com",
    )
    assert "GRANT SELECT ON TABLE main.sales.orders TO `analyst@corp.com`" in info.grant_sql
    assert info.uc_deep_link == "https://x.databricks.com/explore/data/main/sales/orders"


def test_promote_handles_trailing_slash_host():
    info = build_promote_info(
        action_id="uc.table.select",
        securable="main.sales.orders",
        principal="grp",
        host="https://x.databricks.com/",
    )
    assert info.uc_deep_link == "https://x.databricks.com/explore/data/main/sales/orders"


def test_promote_is_pure_no_execution():
    # build_promote_info must not require any client / executor — pure strings.
    info = build_promote_info(
        action_id="uc.schema.use",
        securable="main.sales",
        principal="analyst@corp.com",
        host="https://x.databricks.com",
    )
    assert "USE SCHEMA ON SCHEMA main.sales" in info.grant_sql
    assert info.uc_deep_link.endswith("/explore/data/main/sales")
