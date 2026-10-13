import importlib


def test_settings_reads_lakebase_and_uaig_env(monkeypatch):
    monkeypatch.setenv("PGHOST", "pg.example")
    monkeypatch.setenv("PGDATABASE", "databricks_postgres")
    monkeypatch.setenv("PGUSER", "sp-client-id")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("LAKEBASE_ENDPOINT", "projects/p/branches/production/endpoints/e")
    monkeypatch.setenv("HARNESS_DB_SCHEMA", "perm_harness")
    monkeypatch.setenv("UAIG_BASE_URL", "https://ws/ai-gateway/mlflow/v1")
    monkeypatch.setenv("UAIG_MODEL_SERVICE", "cat.sch.svc")
    import app.config as cfg

    importlib.reload(cfg)
    s = cfg.get_settings()
    assert s.pg_host == "pg.example"
    assert s.pg_database == "databricks_postgres"
    assert s.pg_user == "sp-client-id"
    assert s.pg_port == 5432
    assert s.lakebase_endpoint.endswith("endpoints/e")
    assert s.db_schema == "perm_harness"
    assert s.uaig_base_url.endswith("/ai-gateway/mlflow/v1")
    assert s.uaig_model_service == "cat.sch.svc"
    importlib.reload(cfg)  # reset singleton for other tests
