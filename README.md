# Databricks Permission Test Harness

A Databricks App that lets an admin **test a Unity Catalog / workspace permission before granting it to a real person.**

The usual way to verify "will this grant let my teammate do X" is to change a permission and then ask the teammate to try it. That round trip is slow and there is no built-in Databricks feature for it. This app closes the loop: an admin applies a candidate permission **to the app's own service principal (SP)**, the SP attempts the action, and the app reports pass/fail with the *real* Databricks error. When the admin is satisfied, they promote the grant to the real user **in Unity Catalog** (the app never grants to real principals itself).

---

## Table of contents

- [What it does](#what-it-does)
- [The trust model (read this first)](#the-trust-model-read-this-first)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Deploy](#deploy)
  - [Option A — automated (`scripts/setup.sh`)](#option-a--automated-scriptssetupsh)
  - [Option B — Genie Code runbook](#option-b--genie-code-runbook)
  - [What DABs can and cannot create](#what-dabs-can-and-cannot-create)
- [Post-deploy verification](#post-deploy-verification)
- [Local development](#local-development)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Project layout](#project-layout)

---

## What it does

1. **Configure** — an admin (logged in via the app) picks a securable (e.g. `catalog.schema.table`) and an action to test (e.g. `SELECT`).
2. **Apply to SP** — the app runs `GRANT ... TO <app SP>`, **signed by the admin's own identity** (on-behalf-of / OBO). It succeeds only because the admin already has the authority.
3. **Attempt** — the app SP attempts the action as itself.
   - Unity Catalog data actions run a real, side-effect-free probe (`SELECT ... LIMIT 1`, `USE`, `LIST`, `EXECUTE`).
   - Workspace-object actions default to an effective-permission check, with an opt-in "really do it".
4. **Report** — green pass (rows / confirmed level) or red fail with the exact Databricks error. Revoking cleanly lets you test the negative ("confirm the SP genuinely *cannot* do X").
5. **Promote** — when satisfied, the app shows the validated `GRANT` SQL and a **deep-link into Unity Catalog** so the admin performs the real grant natively, where it is governed and audited.

---

## The trust model (read this first)

This app is a **test harness, not a grant-management tool.** Two invariants are enforced *in code*, not just by convention:

| Concern | Identity used | Why |
|---|---|---|
| Writing the candidate grant | **Logged-in admin, via OBO** (user-scoped token) | The grant succeeds because the admin has authority. The app carries **zero standing grant power**. |
| Attempting the action (the test) | **App's own SP** | The SP is the single "actor" being tested. |
| Reading effective permissions / history | Admin OBO | Reads only what the admin can already see. |

**Hard invariants:**

- The app writes grants to **exactly one principal: its own SP.** Never to any real user or group. (Enforced by a principal guard in `app/grant.py` with explicit positive + negative tests.)
- The SP **never** holds metastore/workspace admin or standing grant authority.
- **Promotion to real users happens only in Unity Catalog** (deep-link + copy-paste SQL). The app never performs it.
- The agent (see Features) has **no tool that can grant to a real principal** — it is structurally impossible, not merely discouraged (locked by test).

Because every write is a real OBO-signed `GRANT`/`REVOKE`, it lands in Databricks' own audit logs under the admin's name — there is no separate audit path to trust.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Databricks App                              │
│                                                                   │
│  React + Vite (client/)          FastAPI (app/)                   │
│  ┌────────────────────┐          ┌──────────────────────────┐    │
│  │ UC Data | Workspace │  /api   │ identity  (OBO ⟷ SP split)│    │
│  │ Scenarios | Activity│ ───────▶│ grant     (SP-only guard) │    │
│  │ resizable chat dock │          │ probe / catalog / promote │    │
│  └────────────────────┘          │ scenarios / activity / agent   │
│                                   └──────────┬───────────────┘    │
└──────────────────────────────────────────────┼──────────────────┘
                                                │
         ┌──────────────────────┬───────────────┼────────────────────┐
         ▼                      ▼               ▼                    ▼
   SQL Warehouse         Lakebase          Unity AI Gateway     Unity Catalog
   (GRANT/REVOKE,        (activity_log,    (governed LLM for    (real grants,
    probe queries)        scenarios)        the agent + guardrails)  deep-links)
```

- **Backend:** FastAPI (Python). Chosen over AppKit specifically because this app needs **per-call identity switching** — the `GRANT`/`REVOKE` must be signed by the admin's OBO token while the probe runs as the app SP. Owning the request path is what makes the SP-only invariant enforceable.
- **Frontend:** React 18 + TypeScript + Vite + Tailwind, DuBois design language, dark/light themes.
- **Persistence:** Lakebase (Autoscaling Postgres) for the durable activity log and saved scenarios.
- **Agent:** calls a governed model service through **Unity AI Gateway**; the tool-calling loop runs in FastAPI under the user's OBO, so the agent can only ever call the same guarded endpoints.

---

## Features

- **UC Data tab** — test `USE CATALOG/SCHEMA`, `SELECT`, `MODIFY` (write-guarded), `READ/WRITE VOLUME`, `EXECUTE`, model read.
- **Workspace Objects tab** — jobs, SQL warehouses, notebooks, pipelines, serving endpoints, secret scopes, clusters (effective-permission check by default, opt-in real execution).
- **Scenarios tab** — define a role as a set of (securable, action) pairs, run the whole set as a batch (apply-all → probe-each → revoke-all), see a pass/fail matrix. Ships with seed templates; custom scenarios persist to Lakebase.
- **Activity tab** — durable, filterable history of every apply/probe/revoke/promote, backed by Lakebase.
- **Agent chat dock** — a resizable, collapsible, cross-tab assistant (governed via Unity AI Gateway) that explains UC permissions, reads history, drives the test loop, authors + runs scenarios, and hands you UC promotion **directions** when a test passes. It cannot grant to real users.

---

## Prerequisites

Before deploying, confirm you have:

1. **Databricks CLI ≥ v0.294.0** and an authenticated profile: `databricks auth profiles`.
2. **Admin authority** in the target workspace (metastore admin or ownership of the securables you intend to test), because grants are signed by *your* identity via OBO.
3. **User authorization (OBO) enabled** on the workspace. This is a workspace-admin-toggled Public Preview. If it is off, `/api/me` returns 401 "user token passthrough not enabled" and the grant loop will not work.
4. **A SQL warehouse** the app can use (Serverless recommended).
5. **Access to a pay-per-token foundation model** (e.g. Claude) in `system.ai`, to front with the Unity AI Gateway model service.
6. **`psql`** (or `databricks psql`) available locally to initialize the Lakebase schema, and **`python3`** for the setup script's JSON parsing.

---

## Deploy

You need **5 workspace-specific values** to deploy. Three of them come from resources that **DABs cannot create** (see the table below), so you provision those first, then run the bundle. Both options below produce the same 5 values:

| Variable | Example | Source |
|---|---|---|
| `warehouse_id` | `0123456789abcdef` | existing SQL warehouse |
| `lakebase_project` | `perm-harness-lakebase` | created in setup |
| `lakebase_endpoint` | `primary` | created in setup (auto) |
| `uaig_base_url` | `https://<host>/ai-gateway/mlflow/v1` | your workspace host |
| `uaig_model_service` | `main.perm_harness.harness_agent` | created in setup |

### Option A — automated (`scripts/setup.sh`)

```bash
# 1. Provision the non-DABs prerequisites (Lakebase project, UAIG model service,
#    schema + SP login role). Prints the 5 variables at the end.
./scripts/setup.sh --profile <PROFILE>

# 2. Build the React frontend (FastAPI serves it as static files).
cd client && npm install && npm run build && cd ..

# 3. Deploy the app + all bindings via DABs, passing the 5 values.
databricks bundle deploy --target dev --profile <PROFILE> \
  --var="warehouse_id=<ID>" \
  --var="lakebase_project=<PROJECT>" \
  --var="lakebase_endpoint=primary" \
  --var="uaig_base_url=https://<HOST>/ai-gateway/mlflow/v1" \
  --var="uaig_model_service=<CATALOG.SCHEMA.SERVICE>"

# 4. Start the app.
databricks bundle run permission-test-harness --target dev --profile <PROFILE>
```

`scripts/setup.sh --help` documents every flag (catalog/schema for the model service, base foundation model, project name, etc.). The script is idempotent: re-running it reuses resources that already exist.

### Option B — Genie Code runbook

If your team prefers to "vibe" the setup, `GENIE_CODE_SETUP.md` is a copy-paste prompt for **Genie Code** (the Databricks AI Dev Kit coding agent). It encodes every gotcha (the beta UAIG create-API enum, the `system.ai` registered-model path, the OBO `auth_type=pat` fix, the scope-wipe behavior, and the schema-ownership ordering) and includes a verification checklist so the agent confirms each resource before proceeding. This path self-corrects if the beta APIs shift, where a static script would just fail.

After Genie Code prints the 5 values, run steps 2–4 above.

### What DABs can and cannot create

Being honest about the boundary so there are no surprises:

**DABs declares (in `databricks.yml`, done for you):**
- ✅ the App resource, its launch command and env
- ✅ the SQL-warehouse binding, the Lakebase (`postgres`) binding
- ✅ the OBO scopes (`user_api_scopes`: `sql`, `serving.serving-endpoints`)

**DABs cannot create (handled by `setup.sh` / Genie Code):**
- ❌ the Lakebase **Autoscaling project** (`databricks postgres create-project`) — DABs only *binds to* an existing one
- ❌ the **Unity AI Gateway model service** (AI Gateway REST API, beta)
- ❌ the Postgres **schema + tables** and the **SP login role** (`databricks_create_role` + `sql/schema.sql`)
- ❌ the **guardrail policy** (AI Gateway UI) and the **user-authorization preview** toggle (workspace-admin switch)

---

## Post-deploy verification

```bash
databricks apps get permission-test-harness --profile <PROFILE> -o json   # app_status.state == RUNNING; note the url
```

Then, logged into the app URL:

1. The identity banner is **green** (grantor = you via OBO, tester = app SP). If red with "user token passthrough not enabled", enable the user-authorization preview (prereq #3).
2. **UC Data**: pick a table you own, `SELECT`, Apply → Attempt → PASS with a row; Revoke → toggle Negative test → Attempt → green (confirmed denial).
3. **Scenarios**: load a seed template, fill in a catalog/schema/table, Run → pass/fail matrix.
4. **Activity**: the run shows up in the durable feed (Lakebase connected).
5. **Chat dock**: ask "what can I test?"; on a passing test it returns UC promotion directions, never a real grant.

---

## Local development

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                       # 71 unit tests; integration tests are gated/skipped by default

# Frontend
cd client && npm install && npm run dev      # Vite dev server (proxy /api to :8000)
npx tsc --noEmit                             # type check
npm run build                                # production build into client/dist
```

**Important:** always **deploy before running against Lakebase locally.** The app SP must create and own the `perm_harness` schema first; if your local identity creates it, the SP hits `permission denied`. See Troubleshooting.

---

## Configuration reference

All configuration is via environment variables injected by Databricks Apps (see `app.yaml`). **No secrets are hardcoded.**

| Env var | Meaning |
|---|---|
| `DATABRICKS_HOST` | workspace host (OBO client, deep-links) — auto-injected |
| `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` | app SP credential (probe identity) — auto-injected |
| `HARNESS_WAREHOUSE_ID` | SQL warehouse for probes + grant/revoke |
| `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` | Lakebase connection — auto-injected for the `postgres` resource |
| `LAKEBASE_ENDPOINT` | endpoint resource path used to mint the DB credential |
| `HARNESS_DB_SCHEMA` | Postgres schema for `activity_log` / `scenarios` (default `perm_harness`) |
| `UAIG_BASE_URL` | Unity AI Gateway base url (`.../ai-gateway/mlflow/v1`) |
| `UAIG_MODEL_SERVICE` | 3-part governed model-service name |

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/api/me` 401 "user token passthrough not enabled" | User-authorization preview is off. Enable it (workspace-admin, Public Preview). |
| `more than one authorization method configured: oauth and pat` | The OBO client must pin `auth_type="pat"` so it ignores the ambient injected OAuth env. (Already fixed in `app/identity.py`.) |
| Grant fails with `PARSE_SYNTAX_ERROR at '.'` on `USE CATALOG` | You passed a 3-level name to a catalog-level action. Use a bare catalog name. The app now validates securable level before firing SQL and shows a distinct "check input" state. |
| `permission denied for schema perm_harness` (Lakebase) | The schema was created by a human, not the SP. Deploy first so the SP owns it; or drop + redeploy (see the Lakebase skill — export first if it holds data). |
| OBO scopes missing after a deploy | Some deploys wipe scopes (`update_mask` replaces wholesale). Re-run `databricks bundle deploy`, or re-apply via `databricks apps create-update` merging resources. |
| App boots but chat dock errors | `UAIG_BASE_URL` / `UAIG_MODEL_SERVICE` unset or the model service has no route. Re-check setup output. |
| UAIG create-API rejects the body | It is beta. The destination must be `DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL` and the model must be the UC registered-model path `models/system.ai.databricks-claude-...`, not a serving-endpoint name. `setup.sh` handles this. |

---

## Security notes

- The app never holds standing privilege to grant anything; it borrows the admin's authority per-request via OBO and can only ever grant to its own SP.
- The one write the SP makes to its own Lakebase tables is **telemetry** (activity log, scenarios) — not a permission grant — so it does not violate the SP-only invariant.
- Every grant/revoke is audited by Databricks under the acting admin's identity.
- Review `app/grant.py` (the principal guard) and `app/agent.py` (the tool registry) — these are the two files that enforce the trust model.

---

## Project layout

```
databricks-permission-test-harness/
├── README.md                  # this file
├── GENIE_CODE_SETUP.md        # copy-paste runbook for Genie Code (Option B)
├── LICENSE
├── databricks.yml             # DABs bundle: app + warehouse/Lakebase bindings + OBO scopes
├── app.yaml                   # Databricks Apps runtime config (command + env)
├── requirements.txt
├── pytest.ini
├── scripts/
│   └── setup.sh               # provisions the non-DABs prerequisites (Option A)
├── sql/
│   └── schema.sql             # Lakebase schema + SP role init
├── app/                       # FastAPI backend
│   ├── identity.py            # OBO ⟷ SP identity split (the core)
│   ├── grant.py               # the ONLY writer; SP-only principal guard
│   ├── probe.py  catalog.py  promote.py
│   ├── scenarios.py  activity.py  db.py
│   ├── agent.py  uaig.py      # governed agent + tool registry
│   └── actions.yaml  seed_scenarios.yaml
├── client/                    # React + Vite frontend
│   └── src/ ...
└── tests/                     # 71 unit tests + gated integration suite
```

---

*Built by Databricks Field Engineering as a reusable accelerator. Contributions and issues welcome.*
