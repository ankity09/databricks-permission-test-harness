"""App settings resolved from the Databricks Apps runtime environment.

Env vars (injected by Databricks Apps at runtime):
  DATABRICKS_HOST       -> workspace_host    (used to build the OBO admin WorkspaceClient)
  DATABRICKS_CLIENT_ID  -> sp_application_id (the app service principal's application/client id)
  HARNESS_WAREHOUSE_ID  -> warehouse_id      (SQL warehouse used to run probe queries)

Lakebase (Autoscaling Postgres) env (v2):
  PGHOST/PGPORT/PGDATABASE/PGUSER -> auto-injected by the platform for the first
                                     postgres resource. PGUSER defaults to the SP
                                     client id when absent.
  LAKEBASE_ENDPOINT               -> resource path used to mint the short-lived DB credential.
  HARNESS_DB_SCHEMA               -> Postgres schema holding activity_log / scenarios.

Unity AI Gateway env (v2):
  UAIG_BASE_URL       -> /ai-gateway/mlflow/v1 base url for governed LLM calls.
  UAIG_MODEL_SERVICE  -> 3-part model-service name (guardrails attached).

No secrets are hardcoded. DATABRICKS_CLIENT_SECRET is read by the SDK directly
(WorkspaceClient()), not stored here.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    workspace_host: str
    sp_application_id: str
    warehouse_id: str
    # Lakebase (Autoscaling Postgres).
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    lakebase_endpoint: str
    db_schema: str
    # Unity AI Gateway model service (governed LLM calls).
    uaig_base_url: str
    uaig_model_service: str


def _load() -> Settings:
    return Settings(
        workspace_host=os.environ.get("DATABRICKS_HOST", ""),
        sp_application_id=os.environ.get("DATABRICKS_CLIENT_ID", ""),
        warehouse_id=os.environ.get("HARNESS_WAREHOUSE_ID", ""),
        pg_host=os.environ.get("PGHOST", ""),
        pg_port=int(os.environ.get("PGPORT", "5432") or "5432"),
        pg_database=os.environ.get("PGDATABASE", ""),
        pg_user=os.environ.get("PGUSER", "") or os.environ.get("DATABRICKS_CLIENT_ID", ""),
        lakebase_endpoint=os.environ.get("LAKEBASE_ENDPOINT", ""),
        db_schema=os.environ.get("HARNESS_DB_SCHEMA", "perm_harness"),
        uaig_base_url=os.environ.get("UAIG_BASE_URL", ""),
        uaig_model_service=os.environ.get("UAIG_MODEL_SERVICE", ""),
    )


settings = _load()


def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return settings
