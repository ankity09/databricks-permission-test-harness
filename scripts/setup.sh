#!/usr/bin/env bash
#
# setup.sh — provision the non-DABs prerequisites for the Permission Test Harness.
#
# DABs can declare the App + warehouse/Lakebase bindings + OBO scopes, but it
# CANNOT create the Lakebase Autoscaling project, the Unity AI Gateway model
# service, or the Postgres schema + SP login role. This script creates those,
# then prints the 5 variables the bundle needs.
#
# It is idempotent: resources that already exist are reused.
#
# Usage:
#   ./scripts/setup.sh --profile <PROFILE> [options]
#
# Options:
#   --profile <name>         Databricks CLI profile (REQUIRED)
#   --warehouse-id <id>      Existing SQL warehouse id. If omitted, uses the default warehouse.
#   --lakebase-project <id>  Lakebase project id to create/reuse   (default: perm-harness-lakebase)
#   --model-catalog <cat>    UC catalog for the model service      (default: main)
#   --model-schema <sch>     UC schema for the model service       (default: perm_harness)
#   --model-service <name>   Model service leaf name               (default: harness_agent)
#   --base-model <name>      system.ai registered model to front   (default: databricks-claude-sonnet-4-5)
#   --app-name <name>        Deployed app name (to resolve the SP) (default: permission-test-harness)
#   --db-schema <name>       Postgres schema for the tables        (default: perm_harness)
#   --skip-schema            Skip the Lakebase schema/role init (run it after first deploy instead)
#   -h, --help               Show this help
#
# Requires: databricks CLI >= 0.294.0, python3, and psql (or `databricks psql`).

set -euo pipefail

# ---------- defaults ----------
PROFILE=""
WAREHOUSE_ID=""
LAKEBASE_PROJECT="perm-harness-lakebase"
MODEL_CATALOG="main"
MODEL_SCHEMA="perm_harness"
MODEL_SERVICE_LEAF="harness_agent"
BASE_MODEL="databricks-claude-sonnet-4-5"
APP_NAME="permission-test-harness"
DB_SCHEMA="perm_harness"
SKIP_SCHEMA="false"

err()  { echo "ERROR: $*" >&2; }
info() { echo "▶ $*" >&2; }
ok()   { echo "✓ $*" >&2; }

# ---------- arg parsing ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)          PROFILE="$2"; shift 2 ;;
    --warehouse-id)     WAREHOUSE_ID="$2"; shift 2 ;;
    --lakebase-project) LAKEBASE_PROJECT="$2"; shift 2 ;;
    --model-catalog)    MODEL_CATALOG="$2"; shift 2 ;;
    --model-schema)     MODEL_SCHEMA="$2"; shift 2 ;;
    --model-service)    MODEL_SERVICE_LEAF="$2"; shift 2 ;;
    --base-model)       BASE_MODEL="$2"; shift 2 ;;
    --app-name)         APP_NAME="$2"; shift 2 ;;
    --db-schema)        DB_SCHEMA="$2"; shift 2 ;;
    --skip-schema)      SKIP_SCHEMA="true"; shift ;;
    -h|--help)          sed -n '2,40p' "$0"; exit 0 ;;
    *) err "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  err "--profile is required. Run with -h for usage."
  exit 1
fi

DBX="databricks --profile $PROFILE"
UAIG_MODEL_SERVICE="${MODEL_CATALOG}.${MODEL_SCHEMA}.${MODEL_SERVICE_LEAF}"

# ---------- 0. sanity checks ----------
info "Checking CLI + auth (profile: $PROFILE)"
command -v databricks >/dev/null || { err "databricks CLI not found"; exit 1; }
command -v python3    >/dev/null || { err "python3 not found (needed to parse JSON)"; exit 1; }
$DBX current-user me >/dev/null 2>&1 || { err "Not authenticated on profile '$PROFILE'. Run: databricks auth login --profile $PROFILE"; exit 1; }
WS_HOST="$($DBX current-user me -o json | python3 -c 'import json,sys,os; print(os.environ.get("DATABRICKS_HOST",""))' 2>/dev/null || true)"
# Resolve host from the profile config (more reliable than env).
WS_HOST="$(databricks auth env --profile "$PROFILE" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("env",{}).get("DATABRICKS_HOST",""))' 2>/dev/null || true)"
if [[ -z "$WS_HOST" ]]; then
  WS_HOST="$(python3 - "$PROFILE" <<'PY'
import configparser, os, sys
p = configparser.ConfigParser()
p.read(os.path.expanduser("~/.databrickscfg"))
prof = sys.argv[1]
print(p.get(prof, "host", fallback="").rstrip("/"))
PY
)"
fi
[[ -n "$WS_HOST" ]] || { err "Could not resolve workspace host for profile '$PROFILE'"; exit 1; }
WS_HOST="${WS_HOST%/}"
ok "Workspace: $WS_HOST"

# ---------- 1. SQL warehouse ----------
if [[ -z "$WAREHOUSE_ID" ]]; then
  info "Resolving default SQL warehouse"
  WAREHOUSE_ID="$($DBX experimental aitools tools get-default-warehouse -o json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or d.get("warehouse_id") or "")' 2>/dev/null || true)"
fi
[[ -n "$WAREHOUSE_ID" ]] || { err "No warehouse id. Pass --warehouse-id <id> (list: databricks warehouses list --profile $PROFILE)"; exit 1; }
ok "SQL warehouse: $WAREHOUSE_ID"

# ---------- 2. Lakebase Autoscaling project ----------
info "Ensuring Lakebase project '$LAKEBASE_PROJECT'"
if $DBX postgres get-project "projects/$LAKEBASE_PROJECT" >/dev/null 2>&1; then
  ok "Lakebase project already exists (reusing)"
else
  info "Creating Lakebase project (this can take a couple of minutes)"
  $DBX postgres create-project "$LAKEBASE_PROJECT" \
    --json "{\"spec\": {\"display_name\": \"Permission Test Harness\"}}" >/dev/null
  ok "Lakebase project created"
fi

# production branch + primary endpoint are auto-provisioned
LB_BRANCH="projects/$LAKEBASE_PROJECT/branches/production"
LB_ENDPOINT_ID="$($DBX postgres list-endpoints "$LB_BRANCH" -o json 2>/dev/null | python3 -c 'import json,sys; e=json.load(sys.stdin); items=e if isinstance(e,list) else e.get("endpoints",[]); print(items[0]["name"].split("/")[-1] if items else "primary")' 2>/dev/null || echo "primary")"
LB_EP_PATH="$LB_BRANCH/endpoints/$LB_ENDPOINT_ID"
LB_DB_NAME="$($DBX postgres list-databases "$LB_BRANCH" -o json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); items=d if isinstance(d,list) else d.get("databases",[]); print(items[0].get("status",{}).get("postgres_database") or items[0]["name"].split("/")[-1] if items else "databricks_postgres")' 2>/dev/null || echo "databricks_postgres")"
LB_HOST="$($DBX postgres get-endpoint "$LB_EP_PATH" -o json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",{}).get("hosts",{}).get("host",""))' 2>/dev/null || true)"
ok "Lakebase endpoint: $LB_ENDPOINT_ID  (db: $LB_DB_NAME)"

# ---------- 3. Unity AI Gateway model service ----------
# NOTE: the model-services create API is beta. Two hard-won facts, encoded here:
#   * destination_type MUST be DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL
#   * the model MUST be the UC registered-model path "models/system.ai.<name>",
#     NOT a serving-endpoint name.
info "Ensuring UC schema $MODEL_CATALOG.$MODEL_SCHEMA for the model service"
$DBX experimental aitools tools query "CREATE SCHEMA IF NOT EXISTS \`$MODEL_CATALOG\`.\`$MODEL_SCHEMA\`" >/dev/null 2>&1 || \
  info "  (could not auto-create schema; ensure $MODEL_CATALOG.$MODEL_SCHEMA exists and you can create model services in it)"

info "Ensuring Unity AI Gateway model service '$UAIG_MODEL_SERVICE'"
TOKEN="$(databricks auth token --profile "$PROFILE" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' 2>/dev/null || true)"
[[ -n "$TOKEN" ]] || { err "Could not mint an access token for the profile (needed for the beta AI Gateway REST call)"; exit 1; }

MS_PARENT="catalogs/$MODEL_CATALOG/schemas/$MODEL_SCHEMA"
EXISTING_MS="$(curl -sS -H "Authorization: Bearer $TOKEN" "$WS_HOST/api/2.0/model-services/$UAIG_MODEL_SERVICE" 2>/dev/null | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d.get("name","") or d.get("id",""))
except Exception:
    print("")' 2>/dev/null || true)"

if [[ -n "$EXISTING_MS" ]]; then
  ok "Model service already exists (reusing)"
else
  info "Creating model service (beta API; fronting system.ai.$BASE_MODEL)"
  CREATE_BODY=$(cat <<JSON
{
  "config": {
    "routing": {
      "destinations": [
        {
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": { "model": "models/system.ai.$BASE_MODEL" }
        }
      ]
    }
  }
}
JSON
)
  HTTP_CODE=$(curl -sS -o /tmp/uaig_create.json -w "%{http_code}" \
    -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "$WS_HOST/api/2.0/model-services?model_service_id=$UAIG_MODEL_SERVICE&parent=$MS_PARENT" \
    -d "$CREATE_BODY" || true)
  if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" ]]; then
    ok "Model service created"
  else
    err "Model service create returned HTTP $HTTP_CODE. Response:"
    cat /tmp/uaig_create.json >&2 || true
    err "This API is beta; if it has shifted, use the Genie Code runbook (GENIE_CODE_SETUP.md) which self-corrects, or create the model service in the AI Gateway UI."
    exit 1
  fi
fi
UAIG_BASE_URL="$WS_HOST/ai-gateway/mlflow/v1"
ok "UAIG base url: $UAIG_BASE_URL"

# ---------- 4. Lakebase schema + SP login role ----------
if [[ "$SKIP_SCHEMA" == "true" ]]; then
  info "Skipping schema init (--skip-schema). Run sql/schema.sql after first deploy."
else
  info "Resolving app service principal client id (app: $APP_NAME)"
  SP_ID="$($DBX apps get "$APP_NAME" -o json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("service_principal_client_id",""))' 2>/dev/null || true)"
  if [[ -z "$SP_ID" ]]; then
    info "App '$APP_NAME' not deployed yet — deferring schema init."
    info "After your FIRST 'databricks bundle deploy', re-run: ./scripts/setup.sh --profile $PROFILE --app-name $APP_NAME (or run sql/schema.sql manually)."
  else
    ok "App SP: $SP_ID"
    info "Initializing Lakebase schema + SP role via psql"
    PG_TOKEN="$($DBX postgres generate-database-credential "$LB_EP_PATH" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
    PG_USER="$($DBX current-user me -o json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("userName",""))')"
    SCHEMA_SQL="$(sed "s/<app-sp-client-id>/$SP_ID/g; s/perm_harness/$DB_SCHEMA/g" "$(dirname "$0")/../sql/schema.sql")"
    ROLE_SQL="CREATE EXTENSION IF NOT EXISTS databricks_auth; SELECT databricks_create_role('$SP_ID', 'service_principal');"
    if command -v psql >/dev/null; then
      PGPASSWORD="$PG_TOKEN" psql "host=$LB_HOST user=$PG_USER dbname=$LB_DB_NAME sslmode=require" -v ON_ERROR_STOP=1 -c "$ROLE_SQL" || info "  (role may already exist; continuing)"
      PGPASSWORD="$PG_TOKEN" psql "host=$LB_HOST user=$PG_USER dbname=$LB_DB_NAME sslmode=require" -v ON_ERROR_STOP=1 <<< "$SCHEMA_SQL"
      ok "Lakebase schema + role initialized"
    else
      info "  psql not found; run the schema init manually with 'databricks psql --project $LAKEBASE_PROJECT' and sql/schema.sql (substitute $SP_ID)."
    fi
  fi
fi

# ---------- 5. print the 5 bundle variables ----------
cat >&2 <<EOF

────────────────────────────────────────────────────────────────────
 Setup complete. Deploy with these 5 variables:
────────────────────────────────────────────────────────────────────
EOF
cat <<EOF
databricks bundle deploy --target dev --profile $PROFILE \\
  --var="warehouse_id=$WAREHOUSE_ID" \\
  --var="lakebase_project=$LAKEBASE_PROJECT" \\
  --var="lakebase_endpoint=$LB_ENDPOINT_ID" \\
  --var="uaig_base_url=$UAIG_BASE_URL" \\
  --var="uaig_model_service=$UAIG_MODEL_SERVICE"
EOF
cat >&2 <<EOF
────────────────────────────────────────────────────────────────────
 Reminders:
   • Build the frontend first:  cd client && npm install && npm run build && cd ..
   • Enable user-authorization (OBO) preview on the workspace (admin toggle).
   • After first deploy, attach a guardrail policy to $UAIG_MODEL_SERVICE in the AI Gateway UI.
   • If you deferred schema init, re-run this script after the first deploy.
────────────────────────────────────────────────────────────────────
EOF
