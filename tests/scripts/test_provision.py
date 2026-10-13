"""Unit tests for scripts/provision.py (no network: the workspace client is faked)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from databricks.sdk.errors import NotFound

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("provision", ROOT / "scripts" / "provision.py")
provision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(provision)


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "accelerator.yaml"
    path.write_text((ROOT / "accelerator.yaml").read_text())
    return provision.Config(path)


def _workspace(*, project_exists=True, service_exists=True, app_exists=True):
    w = MagicMock()
    w.config.host = "https://example.cloud.databricks.com/"
    w.current_user.me.return_value = SimpleNamespace(user_name="admin@example.com")
    if not project_exists:
        w.postgres.get_project.side_effect = NotFound("no project")
    w.postgres.list_endpoints.return_value = [
        SimpleNamespace(name="projects/perm-harness-lakebase/branches/production/endpoints/primary")
    ]
    w.postgres.list_databases.return_value = [
        SimpleNamespace(name="projects/perm-harness-lakebase/branches/production/databases/databricks-postgres",
                        status=SimpleNamespace(postgres_database="databricks_postgres"))
    ]
    w.registered_models.list.return_value = [
        SimpleNamespace(name="databricks-claude-opus-4-8"),
        SimpleNamespace(name="databricks-claude-sonnet-4-5"),
        SimpleNamespace(name="databricks-claude-sonnet-4-6"),
        SimpleNamespace(name="databricks-gpt-5-6"),
    ]

    def api(method, path, **kwargs):
        if method == "GET" and not service_exists:
            raise NotFound("no service")
        return {}

    w.api_client.do.side_effect = api
    if not app_exists:
        w.apps.get.side_effect = [NotFound("no app"), SimpleNamespace(compute_status=SimpleNamespace(
            state=SimpleNamespace(value="ACTIVE")), url="https://app.example")] + [
            SimpleNamespace(compute_status=SimpleNamespace(state=SimpleNamespace(value="ACTIVE")),
                            url="https://app.example")] * 3
    else:
        w.apps.get.return_value = SimpleNamespace(
            compute_status=SimpleNamespace(state=SimpleNamespace(value="ACTIVE")), url="https://app.example")
    return w


def test_yaml_set_scalar_keeps_comments_and_other_values():
    text = "a:\n  b: \"\"   # keep me\n  c: x\nd:\n  b: y\n"
    out = provision.yaml_set_scalar(text, "a.b", "primary")
    assert out == "a:\n  b: \"primary\"   # keep me\n  c: x\nd:\n  b: y\n"


def test_yaml_set_scalar_unknown_key_raises():
    with pytest.raises(KeyError):
        provision.yaml_set_scalar("a:\n  b: 1\n", "a.z", 2)


def test_provision_writes_back_without_losing_comments(cfg):
    cfg.set("harness.agent.model_catalog", "main")
    w = _workspace(project_exists=False, service_exists=False)
    provision.provision(w, cfg)

    w.postgres.create_project.assert_called_once()
    assert w.postgres.create_project.call_args.kwargs["project_id"] == "perm-harness-lakebase"
    saved = cfg.path.read_text()
    assert "# REQUIRED: serverless SQL warehouse" in saved  # comments survive
    reread = provision.Config(cfg.path)
    assert reread.get("harness.lakebase.endpoint") == "primary"
    assert reread.get("harness.agent.base_model") == "databricks-claude-sonnet-4-6"  # newest Sonnet
    assert reread.get("harness.agent.uaig_base_url") == "https://example.cloud.databricks.com/ai-gateway/mlflow/v1"


def test_provision_creates_model_service_with_leaf_id_and_registered_model_path(cfg):
    cfg.set("harness.agent.model_catalog", "main")
    cfg.set("harness.agent.base_model", "databricks-claude-sonnet-4-5")
    w = _workspace(service_exists=False)
    provision.provision(w, cfg)

    post = [c for c in w.api_client.do.call_args_list if c.args[0] == "POST"]
    assert len(post) == 1
    assert post[0].args[1] == "/api/2.1/unity-catalog/model-services"
    assert post[0].kwargs["query"] == {"parent": "schemas/main.perm_harness", "model_service_id": "harness_agent"}
    destination = post[0].kwargs["body"]["config"]["routing"]["destinations"][0]
    assert destination["destination_type"] == "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL"
    assert destination["pay_per_token_config"]["model"] == "models/system.ai.databricks-claude-sonnet-4-5"


def test_provision_reuses_existing_resources(cfg):
    cfg.set("harness.agent.model_catalog", "main")
    w = _workspace(project_exists=True, service_exists=True)
    provision.provision(w, cfg)
    w.postgres.create_project.assert_not_called()
    assert not [c for c in w.api_client.do.call_args_list if c.args[0] == "POST"]


def test_provision_requires_model_catalog_when_agent_enabled(cfg):
    with pytest.raises(SystemExit, match="model_catalog"):
        provision.provision(_workspace(), cfg)


def test_bundle_vars_requires_provision_first(cfg, capsys):
    with pytest.raises(SystemExit, match="run `provision` first"):
        provision.bundle_vars(cfg, None)


def test_bundle_vars_prints_all_six_vars(cfg, capsys):
    cfg.set("target.warehouse_id", "abc123")
    cfg.set("harness.lakebase.endpoint", "primary")
    cfg.set("harness.agent.model_catalog", "main")
    cfg.set("harness.agent.uaig_base_url", "https://h/ai-gateway/mlflow/v1")
    out = provision.bundle_vars(cfg, "my-profile")
    for flag in ('--var="warehouse_id=abc123"', '--var="lakebase_project=perm-harness-lakebase"',
                 '--var="lakebase_endpoint=primary"', '--var="uaig_base_url=https://h/ai-gateway/mlflow/v1"',
                 '--var="uaig_model_service=main.perm_harness.harness_agent"', '--var="allowed_group=none"'):
        assert flag in out
    assert "databricks bundle run permission-test-harness --target dev --profile my-profile" in out


def test_bundle_vars_blanks_agent_vars_when_disabled(cfg):
    cfg.set("target.warehouse_id", "abc123")
    cfg.set("harness.lakebase.endpoint", "primary")
    cfg.set("harness.agent.enabled", False)
    flags = provision.bundle_vars(cfg, None, flags_only=True)
    assert '--var="uaig_base_url=none"' in flags and '--var="uaig_model_service=none"' in flags


def test_deploy_app_sets_resources_scopes_and_env(cfg, tmp_path, monkeypatch):
    cfg.set("target.warehouse_id", "abc123")
    cfg.set("harness.lakebase.endpoint", "primary")
    cfg.set("harness.agent.enabled", False)
    cfg.set("harness.allowed_group", "perm-testers")
    w = _workspace(app_exists=True)
    monkeypatch.setattr(provision, "_upload_source", lambda w, staging: 3)

    url = provision.deploy_app(w, cfg, None)

    assert url == "https://app.example"
    app = w.apps.update.call_args.kwargs["app"]
    assert app.user_api_scopes == ["sql", "ai-gateway"]
    by_name = {r.name: r for r in app.resources}
    assert by_name["sql-warehouse"].sql_warehouse.id == "abc123"
    assert by_name["lakebase"].postgres.branch == "projects/perm-harness-lakebase/branches/production"
    assert by_name["lakebase"].postgres.database.endswith("/databases/databricks-postgres")
    deployment = w.apps.deploy_and_wait.call_args.kwargs["app_deployment"]
    assert deployment.source_code_path == "/Workspace/Users/admin@example.com/.apps/permission-test-harness"
    env = {e.name: e.value for e in deployment.env_vars}
    assert env["LAKEBASE_ENDPOINT"] == "projects/perm-harness-lakebase/branches/production/endpoints/primary"
    assert env["HARNESS_ALLOWED_GROUP"] == "perm-testers"
    assert env["UAIG_BASE_URL"] == "" and env["UAIG_MODEL_SERVICE"] == ""
    assert deployment.command[-1].startswith("exec uvicorn app.main:app")


def test_deploy_app_creates_missing_app(cfg, monkeypatch):
    cfg.set("target.warehouse_id", "abc123")
    cfg.set("harness.lakebase.endpoint", "primary")
    w = _workspace(app_exists=False)
    monkeypatch.setattr(provision, "_upload_source", lambda w, staging: 3)
    provision.deploy_app(w, cfg, "/Workspace/Shared/harness")
    w.apps.create_and_wait.assert_called_once()
    w.apps.update.assert_not_called()


def test_teardown_without_yes_deletes_nothing(cfg):
    w = _workspace()
    with pytest.raises(SystemExit, match="--yes"):
        provision.teardown(w, cfg, yes=False, delete_lakebase=True, staging=None)
    w.apps.delete.assert_not_called()
    w.postgres.delete_project.assert_not_called()


def test_teardown_keeps_lakebase_unless_asked(cfg):
    cfg.set("harness.agent.model_catalog", "main")
    w = _workspace()
    provision.teardown(w, cfg, yes=True, delete_lakebase=False, staging=None)
    w.apps.delete.assert_called_once_with(name="permission-test-harness")
    w.postgres.delete_project.assert_not_called()
    deletes = [c.args[1] for c in w.api_client.do.call_args_list if c.args[0] == "DELETE"]
    assert deletes == ["/api/2.1/unity-catalog/model-services/main.perm_harness.harness_agent"]


def test_preflight_reports_missing_warehouse_and_manual_obo(cfg):
    w = _workspace()
    w.warehouses.list.return_value = [SimpleNamespace(name="Starter", id="wh1", enable_serverless_compute=True)]
    rows = {feature: (status, detail) for feature, status, detail in provision.preflight(w, cfg)}
    assert rows["serverless_sql"][0] == "todo" and "wh1" in rows["serverless_sql"][1]
    assert rows["user_authorization"][0] == "manual"
    assert rows["unity_ai_gateway"][0] == "FAIL"  # agent enabled but no model_catalog yet


def test_chat_models_prefers_newest_sonnet():
    w = MagicMock()
    w.registered_models.list.return_value = [SimpleNamespace(name=n) for n in (
        "databricks-claude-sonnet-4", "databricks-claude-sonnet-5", "databricks-claude-opus-5-5",
        "databricks-claude-sonnet-5-5", "databricks-claude-sonnet-4-5")]
    assert provision._chat_models(w)[:3] == [
        "databricks-claude-sonnet-5-5", "databricks-claude-sonnet-5", "databricks-claude-sonnet-4-5"]
