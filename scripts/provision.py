#!/usr/bin/env python3
"""Provision and deploy the Permission Test Harness.

Runs from a laptop (``--profile <name>``) or inside a Databricks workspace
notebook or job (no profile: the runtime's own identity). Reads and updates
``accelerator.yaml``. Every command is safe to re-run.

  preflight     check the workspace can run the harness (changes nothing)
  provision     create or reuse the Lakebase project and, when the agent is
                enabled, the Unity AI Gateway model service
  bundle-vars   print the ``databricks bundle deploy`` commands (laptop/CI lane)
  deploy-app    deploy without the Databricks CLI (Genie Code / workspace lane)
  grant-access  give ``harness.allowed_group`` CAN_USE on the app
  teardown      delete what provision and deploy-app created (needs --yes)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "accelerator.yaml"
MODEL_SERVICES_API = "/api/2.1/unity-catalog/model-services"
# sql: grants, probes, catalog browsing. ai-gateway: the optional assistant.
USER_API_SCOPES = ["sql", "ai-gateway"]
APP_COMMAND = [
    "sh",
    "-c",
    "exec uvicorn app.main:app --host 0.0.0.0 --port ${DATABRICKS_APP_PORT:-8000}",
]
# What the running app needs. Tests, docs, and tooling stay behind.
DEPLOY_PATHS = ["app", "client/dist", "requirements.txt"]

OK, WARN, FAIL, TODO, MANUAL, SKIP = "ok", "warn", "FAIL", "todo", "manual", "skip"


def say(tag: str, msg: str) -> None:
    print(f"[{tag:>6}] {msg}")


# --------------------------------------------------------------------------
# accelerator.yaml
# --------------------------------------------------------------------------

_KEY_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_]+):(?P<rest>.*)$")
_TRAILING_COMMENT = re.compile(r"\s+#.*$")


def yaml_set_scalar(text: str, dotted: str, value: Any) -> str:
    """Replace one scalar in a block-style YAML document, keeping comments.

    accelerator.yaml is written for people to review, so a round trip through
    yaml.dump (which drops every comment) is not acceptable. Raises KeyError if
    the key path is not in the document.
    """
    want = dotted.split(".")
    stack: List[Tuple[int, str]] = []
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = _KEY_LINE.match(line)
        if not m:
            continue
        indent = len(m.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m.group("key")))
        if [key for _, key in stack] == want:
            comment = _TRAILING_COMMENT.search(m.group("rest").rstrip("\n"))
            tail = comment.group(0) if comment else ""
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = f"{m.group('indent')}{m.group('key')}: {json.dumps(value)}{tail}{newline}"
            return "".join(lines)
    raise KeyError(f"{dotted} is not in accelerator.yaml")


class Config:
    """accelerator.yaml: parsed for reading, edited as text for writing."""

    def __init__(self, path: Path):
        self.path = path
        if not path.exists():
            raise SystemExit(f"config not found: {path}")
        self.text = path.read_text()
        self.data = yaml.safe_load(self.text) or {}

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return default if node is None or node == "" else node

    def set(self, dotted: str, value: Any) -> None:
        self.text = yaml_set_scalar(self.text, dotted, value)
        node = self.data
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value

    def save(self) -> None:
        self.path.write_text(self.text)

    # Derived names used by several commands.
    @property
    def app_name(self) -> str:
        return self.get("target.app_name", "permission-test-harness")

    @property
    def agent_enabled(self) -> bool:
        return bool(self.get("harness.agent.enabled", False))

    @property
    def project(self) -> str:
        return self.get("harness.lakebase.project", "perm-harness-lakebase")

    @property
    def branch_path(self) -> str:
        return f"projects/{self.project}/branches/{self.get('harness.lakebase.branch', 'production')}"

    @property
    def model_service(self) -> Optional[str]:
        catalog = self.get("harness.agent.model_catalog")
        if not catalog:
            return None
        schema = self.get("harness.agent.model_schema", "perm_harness")
        return f"{catalog}.{schema}.{self.get('harness.agent.model_service', 'harness_agent')}"


def app_env(cfg: Config) -> Dict[str, str]:
    """The six environment variables the app reads, as plain values."""
    return {
        "HARNESS_WAREHOUSE_ID": cfg.get("target.warehouse_id", ""),
        "LAKEBASE_ENDPOINT": f"{cfg.branch_path}/endpoints/{cfg.get('harness.lakebase.endpoint', '')}",
        "HARNESS_DB_SCHEMA": cfg.get("harness.lakebase.schema", "perm_harness"),
        "UAIG_BASE_URL": cfg.get("harness.agent.uaig_base_url", "") if cfg.agent_enabled else "",
        "UAIG_MODEL_SERVICE": (cfg.model_service or "") if cfg.agent_enabled else "",
        "HARNESS_ALLOWED_GROUP": cfg.get("harness.allowed_group", ""),
    }


# --------------------------------------------------------------------------
# Workspace helpers
# --------------------------------------------------------------------------

def _client(profile: Optional[str]):
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()


def _not_found():
    from databricks.sdk.errors import NotFound

    return NotFound


def _chat_models(w) -> List[str]:
    """databricks-claude models visible in system.ai, Sonnet first, newest first."""
    try:
        names = [m.name for m in w.registered_models.list(catalog_name="system", schema_name="ai")]
    except Exception:  # noqa: BLE001 -- discovery is best-effort
        return []
    chat = [n for n in names if n and n.startswith("databricks-claude")]
    # Newest first: a trailing sentinel sorts "sonnet-5-5" (5.5) before "sonnet-5".
    return sorted(chat, key=lambda n: ("sonnet" not in n, [-int(x) for x in re.findall(r"\d+", n)] + [1]))


def _database(w, cfg: Config):
    """The Lakebase database resource matching harness.lakebase.database."""
    want = cfg.get("harness.lakebase.database", "databricks_postgres")
    databases = list(w.postgres.list_databases(parent=cfg.branch_path))
    for db in databases:
        status = getattr(db, "status", None)
        if getattr(status, "postgres_database", None) == want:
            return db
        if db.name.rsplit("/", 1)[-1] in (want, want.replace("_", "-")):
            return db
    raise SystemExit(f"database {want!r} not found under {cfg.branch_path}")


def _state(obj, attr: str) -> str:
    status = getattr(obj, attr, None)
    state = getattr(status, "state", None)
    return getattr(state, "value", str(state or "UNKNOWN"))


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def preflight(w, cfg: Config) -> List[Tuple[str, str, str]]:
    """Return (feature, status, detail) rows. Changes nothing."""
    from databricks.sdk.errors import DatabricksError

    NotFound = _not_found()
    rows: List[Tuple[str, str, str]] = []
    add = lambda feature, status, detail: rows.append((feature, status, detail))  # noqa: E731

    try:
        add("identity", OK, w.current_user.me().user_name)
    except DatabricksError as exc:
        add("identity", FAIL, f"cannot authenticate: {exc}")
        return rows

    try:
        add("unity_catalog", OK, f"metastore {w.metastores.current().metastore_id}")
    except DatabricksError as exc:
        add("unity_catalog", FAIL, f"no metastore assigned to this workspace: {exc}")

    warehouse_id = cfg.get("target.warehouse_id")
    if warehouse_id:
        try:
            wh = w.warehouses.get(warehouse_id)
            if wh.enable_serverless_compute:
                add("serverless_sql", OK, f"{wh.name} ({warehouse_id})")
            else:
                add("serverless_sql", WARN, f"{wh.name} is not serverless; it works but bills while idle")
        except DatabricksError as exc:
            add("serverless_sql", FAIL, f"warehouse {warehouse_id}: {exc}")
    else:
        serverless = [wh for wh in w.warehouses.list() if wh.enable_serverless_compute]
        listed = ", ".join(f"{wh.name} ({wh.id})" for wh in serverless[:5]) or "none found"
        add("serverless_sql", TODO if serverless else FAIL, f"set target.warehouse_id; serverless warehouses: {listed}")

    try:
        w.postgres.get_project(name=f"projects/{cfg.project}")
        add("lakebase_autoscaling", OK, f"project {cfg.project} exists and will be reused")
    except NotFound:
        add("lakebase_autoscaling", OK, f"available; project {cfg.project} will be created")
    except DatabricksError as exc:
        add("lakebase_autoscaling", FAIL, f"Lakebase Autoscaling is not available here: {exc}")

    add(
        "user_authorization",
        MANUAL,
        "not visible through the API. After deploy, the app header must show your identity; "
        "if it reports 'user token passthrough not enabled', a workspace admin turns on "
        "user authorization for Databricks Apps on the Previews page.",
    )

    if cfg.agent_enabled:
        full = cfg.model_service
        if not full:
            add("unity_ai_gateway", FAIL, "set harness.agent.model_catalog, or set harness.agent.enabled: false")
        else:
            try:
                w.api_client.do("GET", f"{MODEL_SERVICES_API}/{full}")
                add("unity_ai_gateway", OK, f"model service {full} exists and will be reused")
            except NotFound:
                add("unity_ai_gateway", OK, f"available; model service {full} will be created")
            except DatabricksError as exc:
                add("unity_ai_gateway", FAIL, f"model services are not available here: {exc}")
        models = _chat_models(w)
        base = cfg.get("harness.agent.base_model")
        if base:
            known = not models or base in models
            add("base_model", OK if known else WARN,
                base if known else f"{base} is not in system.ai; candidates: {', '.join(models[:5])}")
        else:
            add("base_model", TODO if models else FAIL,
                "provision will pick: " + (", ".join(models[:3]) or "no databricks-claude model in system.ai"))
    else:
        add("unity_ai_gateway", SKIP, "agent disabled (harness.agent.enabled: false); the rest of the app works")

    try:
        app = w.apps.get(name=cfg.app_name)
        add("app", OK, f"{cfg.app_name} exists ({_state(app, 'app_status')}); deploy updates it")
    except NotFound:
        add("app", OK, f"{cfg.app_name} will be created")

    group = cfg.get("harness.allowed_group")
    if group:
        found = list(w.groups.list(filter=f'displayName eq "{group}"'))
        add("allowed_group", OK if found else FAIL,
            group if found else f"group {group!r} not found; create it or clear harness.allowed_group")
    else:
        add("allowed_group", WARN, "empty: anyone you give CAN_USE on the app can use it")
    return rows


def print_matrix(rows: List[Tuple[str, str, str]]) -> None:
    width = max(len(feature) for feature, _, _ in rows)
    for feature, status, detail in rows:
        print(f"  {feature:<{width}}  {status:<6}  {detail}")


def provision(w, cfg: Config) -> None:
    from databricks.sdk.service.postgres import Project, ProjectSpec

    NotFound = _not_found()
    try:
        w.postgres.get_project(name=f"projects/{cfg.project}")
        say(OK, f"Lakebase project {cfg.project}: reusing")
    except NotFound:
        say("info", f"Lakebase project {cfg.project}: creating (a minute or two)")
        w.postgres.create_project(
            project=Project(spec=ProjectSpec(display_name="Permission Test Harness")),
            project_id=cfg.project,
        ).wait()
        say(OK, f"Lakebase project {cfg.project}: created")

    endpoints = list(w.postgres.list_endpoints(parent=cfg.branch_path))
    if not endpoints:
        raise SystemExit(f"no endpoints under {cfg.branch_path}; check the project in the Lakebase UI")
    endpoint = next((e for e in endpoints if e.name.endswith("/primary")), endpoints[0])
    cfg.set("harness.lakebase.endpoint", endpoint.name.rsplit("/", 1)[-1])
    say(OK, f"Lakebase endpoint: {endpoint.name}")
    say(OK, f"Lakebase database: {_database(w, cfg).name}")

    if cfg.agent_enabled:
        _provision_agent(w, cfg)
    else:
        say(SKIP, "agent disabled; no model service needed")

    cfg.save()
    say(OK, f"resolved values written to {cfg.path.name}")


def _provision_agent(w, cfg: Config) -> None:
    NotFound = _not_found()
    full = cfg.model_service
    if not full:
        raise SystemExit("set harness.agent.model_catalog, or set harness.agent.enabled: false")
    catalog, schema, service = full.split(".")

    base = cfg.get("harness.agent.base_model")
    if not base:
        candidates = _chat_models(w)
        if not candidates:
            raise SystemExit("no databricks-claude model is visible in system.ai; set harness.agent.base_model")
        base = candidates[0]
        cfg.set("harness.agent.base_model", base)
        say("info", f"base model: {base} (change harness.agent.base_model to use another)")

    try:
        w.schemas.get(full_name=f"{catalog}.{schema}")
    except NotFound:
        w.schemas.create(name=schema, catalog_name=catalog,
                         comment="Permission Test Harness: model service for the optional agent")
        say(OK, f"schema {catalog}.{schema}: created")

    try:
        w.api_client.do("GET", f"{MODEL_SERVICES_API}/{full}")
        say(OK, f"model service {full}: reusing")
    except NotFound:
        w.api_client.do(
            "POST",
            MODEL_SERVICES_API,
            query={"parent": f"schemas/{catalog}.{schema}", "model_service_id": service},
            body={"config": {"routing": {"destinations": [{
                "name": "primary",
                "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
                "pay_per_token_config": {"model": f"models/system.ai.{base}"},
            }]}}},
        )
        say(OK, f"model service {full}: created, routing to system.ai.{base}")

    cfg.set("harness.agent.uaig_base_url", f"{w.config.host.rstrip('/')}/ai-gateway/mlflow/v1")


def bundle_vars(cfg: Config, profile: Optional[str], flags_only: bool = False) -> str:
    env = app_env(cfg)
    missing = [key for key, value in (("target.warehouse_id", env["HARNESS_WAREHOUSE_ID"]),
                                      ("harness.lakebase.endpoint", cfg.get("harness.lakebase.endpoint")))
               if not value]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)}: fill in accelerator.yaml and run `provision` first")
    values = {
        "warehouse_id": env["HARNESS_WAREHOUSE_ID"],
        "lakebase_project": cfg.project,
        "lakebase_endpoint": cfg.get("harness.lakebase.endpoint"),
        "uaig_base_url": env["UAIG_BASE_URL"],
        "uaig_model_service": env["UAIG_MODEL_SERVICE"],
        "allowed_group": env["HARNESS_ALLOWED_GROUP"],
    }
    # A bundle deploy rejects empty environment values; the app reads "none" as unset.
    values = {key: value or "none" for key, value in values.items()}
    if flags_only:
        flags = " ".join(f'--var="{key}={value}"' for key, value in values.items())
        print(flags)
        return flags
    prof = f" --profile {profile}" if profile else ""
    lines = [f"databricks bundle deploy --target dev{prof} \\"]
    lines += [f'  --var="{key}={value}" \\' for key, value in values.items()]
    lines[-1] = lines[-1][: -len(" \\")]
    command = "\n".join(lines) + f"\ndatabricks bundle run permission-test-harness --target dev{prof}"
    print(command)
    return command


def _upload_source(w, staging: str) -> int:
    from databricks.sdk.service.workspace import ImportFormat

    if not (REPO_ROOT / "client" / "dist" / "index.html").exists():
        raise SystemExit("client/dist is missing; build it with `cd client && npm ci && npm run build`")
    files: List[Path] = []
    for rel in DEPLOY_PATHS:
        path = REPO_ROOT / rel
        if path.is_file():
            files.append(path)
        else:
            files += [f for f in sorted(path.rglob("*"))
                      if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"]
    try:
        w.workspace.delete(staging, recursive=True)  # no stale files from older deploys
    except _not_found():
        pass
    targets = [PurePosixPath(staging) / f.relative_to(REPO_ROOT).as_posix() for f in files]
    for folder in sorted({str(t.parent) for t in targets}):
        w.workspace.mkdirs(folder)
    for source, target in zip(files, targets):
        w.workspace.upload(str(target), source.read_bytes(), format=ImportFormat.RAW, overwrite=True)
    return len(files)


def deploy_app(w, cfg: Config, staging: Optional[str]) -> str:
    from databricks.sdk.service.apps import (
        App,
        AppDeployment,
        AppResource,
        AppResourcePostgres,
        AppResourcePostgresPostgresPermission,
        AppResourceSqlWarehouse,
        AppResourceSqlWarehouseSqlWarehousePermission,
        EnvVar,
    )

    NotFound = _not_found()
    env = app_env(cfg)
    if not env["HARNESS_WAREHOUSE_ID"] or not cfg.get("harness.lakebase.endpoint"):
        raise SystemExit("run `provision` first (needs target.warehouse_id and harness.lakebase.endpoint)")
    staging = staging or f"/Workspace/Users/{w.current_user.me().user_name}/.apps/{cfg.app_name}"

    count = _upload_source(w, staging)
    say(OK, f"uploaded {count} files to {staging}")

    app = App(
        name=cfg.app_name,
        description="Test a permission on the app's own service principal before granting it to a person.",
        resources=[
            AppResource(name="sql-warehouse", sql_warehouse=AppResourceSqlWarehouse(
                id=env["HARNESS_WAREHOUSE_ID"],
                permission=AppResourceSqlWarehouseSqlWarehousePermission.CAN_USE)),
            AppResource(name="lakebase", postgres=AppResourcePostgres(
                branch=cfg.branch_path,
                database=_database(w, cfg).name,
                permission=AppResourcePostgresPostgresPermission.CAN_CONNECT_AND_CREATE)),
        ],
        user_api_scopes=USER_API_SCOPES,
    )
    try:
        w.apps.get(name=cfg.app_name)
        w.apps.update(name=cfg.app_name, app=app)
        say(OK, f"app {cfg.app_name}: resources and scopes updated")
    except NotFound:
        say("info", f"app {cfg.app_name}: creating (compute takes a few minutes to start)")
        w.apps.create_and_wait(app=app)

    if _state(w.apps.get(name=cfg.app_name), "compute_status") != "ACTIVE":
        say("info", "starting app compute")
        w.apps.start(name=cfg.app_name).result()

    w.apps.deploy_and_wait(
        app_name=cfg.app_name,
        app_deployment=AppDeployment(
            source_code_path=staging,
            command=APP_COMMAND,
            env_vars=[EnvVar(name=name, value=value) for name, value in env.items()],
        ),
    )
    url = w.apps.get(name=cfg.app_name).url
    say(OK, f"deployed: {url}")
    return url


def grant_access(w, cfg: Config) -> None:
    from databricks.sdk.service.apps import AppAccessControlRequest, AppPermissionLevel

    group = cfg.get("harness.allowed_group")
    if not group:
        say("info", "harness.allowed_group is empty; give CAN_USE to individual admins in the app's Permissions dialog")
        return
    w.apps.update_permissions(
        app_name=cfg.app_name,
        access_control_list=[AppAccessControlRequest(group_name=group, permission_level=AppPermissionLevel.CAN_USE)],
    )
    say(OK, f"{group} can now use {cfg.app_name}")


def teardown(w, cfg: Config, yes: bool, delete_lakebase: bool, staging: Optional[str]) -> None:
    NotFound = _not_found()
    full = cfg.model_service if cfg.agent_enabled else None
    plan = [f"app {cfg.app_name} (its service principal is deleted with it)"]
    if full:
        plan.append(f"model service {full}")
    plan.append(f"Lakebase project {cfg.project} and ALL its data" if delete_lakebase
                else f"(kept) Lakebase project {cfg.project}; add --delete-lakebase to delete it and its data")
    for item in plan:
        say("plan", item)
    if not yes:
        raise SystemExit("nothing deleted; re-run with --yes to delete the items above")

    try:
        w.apps.delete(name=cfg.app_name)
        say(OK, f"app {cfg.app_name}: deleted")
    except NotFound:
        say(SKIP, f"app {cfg.app_name}: not found")
    staging = staging or f"/Workspace/Users/{w.current_user.me().user_name}/.apps/{cfg.app_name}"
    try:
        w.workspace.delete(staging, recursive=True)
        say(OK, f"staged source {staging}: deleted")
    except NotFound:
        pass
    if full:
        try:
            w.api_client.do("DELETE", f"{MODEL_SERVICES_API}/{full}")
            say(OK, f"model service {full}: deleted")
        except NotFound:
            say(SKIP, f"model service {full}: not found")
    if delete_lakebase:
        try:
            w.postgres.delete_project(name=f"projects/{cfg.project}").wait()
            say(OK, f"Lakebase project {cfg.project}: deleted")
        except NotFound:
            say(SKIP, f"Lakebase project {cfg.project}: not found")

    say("left", "not deleted: the model-service schema, the allowed group, and any bundle state "
                "(run `databricks bundle destroy` if you deployed with the bundle)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

COMMANDS = ("preflight", "provision", "bundle-vars", "deploy-app", "grant-access", "teardown")


def main(argv: Optional[List[str]] = None, client_factory=_client) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--profile", help="Databricks CLI profile (omit inside a workspace notebook or job)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to accelerator.yaml")
    parser.add_argument("--staging-path", help="workspace folder for the uploaded app source "
                                               "(default /Workspace/Users/<you>/.apps/<app_name>)")
    parser.add_argument("--flags-only", action="store_true", help="bundle-vars: print only the --var flags")
    parser.add_argument("--yes", action="store_true", help="teardown: actually delete")
    parser.add_argument("--delete-lakebase", action="store_true",
                        help="teardown: also delete the Lakebase project and its data")
    args = parser.parse_args(argv)

    cfg = Config(Path(args.config))
    if args.command == "bundle-vars":
        bundle_vars(cfg, args.profile, args.flags_only)
        return 0

    w = client_factory(args.profile)
    if args.command == "preflight":
        rows = preflight(w, cfg)
        print_matrix(rows)
        return 1 if any(status == FAIL for _, status, _ in rows) else 0
    if args.command == "provision":
        provision(w, cfg)
    elif args.command == "deploy-app":
        deploy_app(w, cfg, args.staging_path)
    elif args.command == "grant-access":
        grant_access(w, cfg)
    elif args.command == "teardown":
        teardown(w, cfg, args.yes, args.delete_lakebase, args.staging_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
