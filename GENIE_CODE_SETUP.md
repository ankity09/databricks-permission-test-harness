# Genie Code setup runbook

This is a **copy-paste prompt for Genie Code** (the Databricks AI Dev Kit coding agent) to provision everything the Permission Test Harness needs that DABs cannot create, then deploy it. Genie Code has `databricks` CLI + SDK + REST access, so it can create the Lakebase project, the Unity AI Gateway model service, and initialize the Postgres schema — the exact steps a static script does, but able to self-correct if a beta API shifts.

## How to use

1. Open Genie Code in a checkout of this repo.
2. Paste the prompt below (fill in the four `<...>` values on the first line).
3. Let it work through the steps; it will confirm each resource before moving on and finish by deploying and printing the app URL.

---

## The prompt

```
You are setting up the "Databricks Permission Test Harness" app in a customer's
Databricks workspace. Use the Databricks CLI/SDK/REST for everything. Work step
by step, verify each resource before moving on, and STOP and report if a step
fails rather than guessing past it.

INPUTS (fill these in):
  PROFILE           = <your databricks CLI profile>
  MODEL_CATALOG     = <UC catalog you can create a model service in, e.g. main>
  MODEL_SCHEMA      = perm_harness
  APP_NAME          = permission-test-harness

CONSTANTS:
  LAKEBASE_PROJECT  = perm-harness-lakebase
  MODEL_SERVICE     = ${MODEL_CATALOG}.${MODEL_SCHEMA}.harness_agent
  BASE_MODEL        = system.ai.databricks-claude-sonnet-4-5   (a pay-per-token foundation model)
  DB_SCHEMA         = perm_harness

TRUST MODEL (do not violate): this app tests permissions by granting them to its
OWN service principal via the logged-in admin's OBO token, then attempting the
action as the SP. It never grants to real users. Nothing you set up should give
the app SP standing admin authority. You are only provisioning infrastructure.

STEP 0 — Preflight.
  - Confirm CLI auth: `databricks current-user me --profile PROFILE`.
  - Resolve and remember the workspace host (from ~/.databrickscfg or `databricks auth env`).
  - Confirm the user-authorization (OBO) Public Preview is enabled on the workspace.
    If you cannot confirm, warn that `/api/me` will 401 until a workspace admin enables it.

STEP 1 — SQL warehouse.
  - Use the workspace default warehouse (`databricks experimental aitools tools
    get-default-warehouse`) or ask which warehouse to use. Remember WAREHOUSE_ID.

STEP 2 — Lakebase Autoscaling project.
  - Check if `projects/LAKEBASE_PROJECT` exists (`databricks postgres get-project`).
    If not, create it: `databricks postgres create-project LAKEBASE_PROJECT
    --json '{"spec":{"display_name":"Permission Test Harness"}}'`.
  - It auto-provisions a `production` branch + `primary` read-write endpoint.
  - Record: endpoint id (LB_ENDPOINT_ID, usually "primary"), the endpoint host,
    and the postgres database name (usually databricks_postgres).

STEP 3 — Unity AI Gateway model service (BETA API — follow exactly).
  - Ensure the UC schema MODEL_CATALOG.MODEL_SCHEMA exists.
  - Create the model service via REST POST to
      {host}/api/2.0/model-services?model_service_id=MODEL_SERVICE&parent=catalogs/MODEL_CATALOG/schemas/MODEL_SCHEMA
    with body:
      {
        "config": { "routing": { "destinations": [ {
          "name": "primary",
          "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
          "pay_per_token_config": { "model": "models/BASE_MODEL" }
        } ] } }
      }
    CRITICAL, hard-won facts (do not deviate):
      * destination_type MUST be exactly DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL.
      * The model MUST be the UC registered-model path "models/system.ai.databricks-claude-...",
        NOT a serving-endpoint name.
      * model_service_id and parent go as QUERY PARAMS, not in the body.
    If the API rejects the body (it is beta and may have shifted): inspect the
    error, check the current SDK enum for ai_gateway/model-services, and adjust
    the field shape — do NOT fall back to a serving-endpoint reference.
  - The agent base url is {host}/ai-gateway/mlflow/v1. Verify the service responds:
    POST {base}/chat/completions with model=MODEL_SERVICE and a 1-token test message.

STEP 4 — Deploy the app (first pass, so the SP exists).
  - Build the frontend: `cd client && npm install && npm run build && cd ..`.
  - Deploy: `databricks bundle deploy --target dev --profile PROFILE` passing the
    5 variables: warehouse_id, lakebase_project=LAKEBASE_PROJECT,
    lakebase_endpoint=LB_ENDPOINT_ID, uaig_base_url={host}/ai-gateway/mlflow/v1,
    uaig_model_service=MODEL_SERVICE.
  - After deploy, get the app SP client id:
    `databricks apps get APP_NAME -o json` → service_principal_client_id (SP_ID).

STEP 5 — Lakebase schema + SP login role.
  - Mint a DB credential: `databricks postgres generate-database-credential
    projects/LAKEBASE_PROJECT/branches/production/endpoints/LB_ENDPOINT_ID`.
  - Connect (psql or `databricks psql --project LAKEBASE_PROJECT`) as yourself and run,
    in this ORDER (ownership matters — the SP must own the schema):
      CREATE EXTENSION IF NOT EXISTS databricks_auth;
      SELECT databricks_create_role('SP_ID', 'service_principal');
    then run sql/schema.sql from this repo with <app-sp-client-id> replaced by SP_ID
    (it creates the perm_harness schema + activity_log/scenarios tables and grants
    the SP access). Optionally grant the admin user SELECT on activity_log so the
    agent can read history under OBO.
  - IMPORTANT: deploy BEFORE creating the schema locally. If a human creates the
    schema first, the SP will hit "permission denied for schema" — then you must
    drop + recreate it so the SP owns it (ask before dropping if it holds data).

STEP 6 — Restart + verify.
  - `databricks bundle run permission-test-harness --target dev --profile PROFILE`
    (or `databricks apps deploy`) to pick up the schema.
  - Confirm app_status.state == RUNNING and print the app URL.
  - Note two manual follow-ups you cannot do headlessly:
      (a) attach a guardrail policy to MODEL_SERVICE in the AI Gateway UI (Policies tab);
      (b) enable the user-authorization preview if not already on.

VERIFICATION CHECKLIST (report pass/fail for each):
  [ ] `databricks current-user me` succeeds on PROFILE
  [ ] Lakebase project exists and endpoint host resolved
  [ ] Model service exists and responds to a test chat completion
  [ ] Bundle deployed; app_status.state == RUNNING
  [ ] App SP client id resolved
  [ ] perm_harness schema + activity_log + scenarios tables exist, SP has access
  [ ] Printed the app URL and the 5 bundle variables used

Then hand back: the app URL, the 5 variable values, the app SP client id, and the
two manual follow-ups.
```

---

## Notes

- **Why a runbook and not just `scripts/setup.sh`?** The bash script (Option A in the README) is deterministic and CI-friendly. This runbook is better when a beta API drifts: Genie Code reads the error and adapts, where the script just fails. Ship both; pick per team preference.
- **The gotchas are load-bearing.** The `DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL` enum, the `models/system.ai.*` registered-model path, and the deploy-before-schema ordering were all discovered the hard way during the reference deploy. Keep them in the prompt.
- **Guardrails vs. authority.** The AI Gateway guardrail policy governs the *content* of the agent conversation (scope, PII, safety). The *authority* guarantee (no grant-to-real-principal) is enforced in the app's code (`app/agent.py` tool registry + `app/grant.py` principal guard), independent of any prompt or guardrail.
