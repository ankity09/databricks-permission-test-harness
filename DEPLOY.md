# Deploy the Permission Test Harness

There are two ways to deploy. Both read the same file, [accelerator.yaml](accelerator.yaml), and both take about 20 minutes once the prerequisites are in place.

- **Lane A, Genie Code in your workspace.** Add this repository as a Git folder and let Genie Code run the steps below. Nothing is installed on a laptop and no Node or CLI is needed.
- **Lane B, a laptop, CI, or Genie Code CLI.** Run the same steps with the Databricks CLI and the bundle in `databricks.yml`.

Pick one lane per app. Lane A deploys through the Apps API, Lane B through the bundle, and mixing them on the same app name makes the bundle's view of the app go stale.

## Prerequisites and who does them

| # | Prerequisite | Who | How you know it is done |
|---|---|---|---|
| 1 | A Unity Catalog workspace to deploy into: a dev or test workspace, not production | Workspace admin | `preflight` shows `unity_catalog ok` |
| 2 | **User authorization for Databricks Apps** turned on (Public Preview, on the workspace Previews page) | Workspace admin | After deploy, the app header shows your identity. "user token passthrough not enabled" means it is still off |
| 3 | Lakebase Autoscaling available in your region | Workspace admin | `preflight` shows `lakebase_autoscaling ok` |
| 4 | A serverless SQL warehouse | Workspace admin | `preflight` shows `serverless_sql ok` |
| 5 | The deployer can create apps and Lakebase projects and has CAN_USE on the warehouse | Workspace admin | `provision` and `deploy-app` succeed |
| 6 | For the optional assistant: Unity AI Gateway, a catalog where the deployer can create a schema and a model service, and EXECUTE on a `system.ai` Claude model | Workspace admin | `preflight` shows `unity_ai_gateway ok` and a `base_model` |
| 7 | The app can install its Python packages: outbound access to PyPI from Databricks Apps, or your private package index | Network or workspace admin | The deployment log shows `Successfully installed` |
| 8 | A workspace group for the people who will test grants (recommended) | Workspace admin | `preflight` shows `allowed_group ok` |
| 9 | Testers hold grant authority (owner or `MANAGE`) on the objects they test | Data owners | A test grant succeeds |
| 10 | Lane A: a Git folder linked with **your own** Git credential. Lane B: Databricks CLI 1.0 or later and Python 3.10 or later | Deployer | `git pull` works in the folder, or `databricks --version` |

## What is automated and what is manual

| Step | Lane A | Lane B |
|---|---|---|
| Check the workspace (`preflight`) | Notebook | `provision.py` |
| Create the Lakebase project and the model service (`provision`) | Notebook | `provision.py` |
| Create and deploy the app | Notebook (`deploy-app`) | `databricks bundle deploy` and `bundle run` |
| Give the tester group access (`grant-access`) | Notebook | `provision.py` |
| Tear everything down | Notebook (`teardown`) | `./teardown.sh` |
| Turn on user authorization for Databricks Apps | Manual, a workspace admin, once | Same |
| Create the tester group and add its members | Manual, a workspace admin | Same |
| Attach a guardrail policy to the model service (optional) | Manual, in the AI Gateway UI | Same |
| Approve the plan before anything is created | You, by design | You |
| Check the app in a browser | You, about 5 minutes | You |

Genie Code usage and the assistant's model calls are billed to your account.

## The playbook

Genie Code follows these steps in order. A person can follow them too. Ask before creating anything, and do not run an agent in auto-approve mode while the person holds admin rights.

### 0. Context

Read [README.md](README.md), this file, [accelerator.yaml](accelerator.yaml), and [AGENTS.md](AGENTS.md).

### 1. Interview

Ask one question at a time and record the answers:

1. Which serverless SQL warehouse should the app use? (`preflight` lists them.)
2. App name? (default `permission-test-harness`)
3. Which workspace group may use the app? (recommended: the admins who test grants)
4. Lakebase project name? (default `perm-harness-lakebase`)
5. Enable the assistant? If yes: which catalog should hold its model service, and which `system.ai` model should it use? (`provision` picks the newest Claude Sonnet if left empty.)

### 2. Preflight

- Lane A: open `scripts/deploy_in_workspace` in the Git folder, attach serverless compute, set `step` to `preflight`, and run all cells.
- Lane B: `python scripts/provision.py preflight --profile <profile>`

Show the capability matrix. Every `FAIL` row must be fixed before continuing. `user_authorization` is always `manual` because no API reports it.

### 3. Write the config

Put the interview answers into `accelerator.yaml`. Leave the values marked "resolved by provision" empty.

### 4. Stop: review

Show the person the completed `accelerator.yaml`, the capability matrix, and this list of what will be created, then wait for an explicit yes:

- a Lakebase project (it stores the activity log and saved scenarios),
- if the assistant is on, a schema and a Unity AI Gateway model service in the chosen catalog,
- the app and the service principal Databricks creates for it,
- Lane A only: the app's files, copied to `/Workspace/Users/<you>/.apps/<app_name>`.

Costs to mention: the app's compute bills while it runs, Lakebase compute bills until its inactivity timeout, and the assistant bills per token.

### 5. Deploy

**Lane A, in the workspace.** In `scripts/deploy_in_workspace`, run all cells with `step` set to each of these in turn:

1. `provision`. Creates or reuses the Lakebase project and the model service, and writes the resolved values (endpoint, model, gateway URL) back into `accelerator.yaml` in the Git folder. These values are specific to your workspace, so do not push them to a shared branch.
2. `deploy-app`. Copies the app's files, creates or updates the app with its warehouse and Lakebase resources and OAuth scopes (`sql`, `ai-gateway`), deploys it, and prints the URL.
3. `grant-access`. Gives the allowed group CAN_USE on the app.

**Lane B, a laptop, CI, or Genie Code CLI.**

```bash
git clone <this repository> && cd databricks-permission-test-harness
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
databricks auth login --host https://<your-workspace-host> --profile <profile>

python scripts/provision.py provision --profile <profile>
python scripts/provision.py bundle-vars --profile <profile>   # prints the next two commands, filled in
databricks bundle deploy --target dev --profile <profile> --var="warehouse_id=..." ...
databricks bundle run permission-test-harness --target dev --profile <profile>
python scripts/provision.py grant-access --profile <profile>
```

The built frontend is committed in `client/dist`, so neither lane needs Node. If you change the frontend, rebuild it as described in [CONTRIBUTING.md](CONTRIBUTING.md). With Genie Code CLI, run `genie` in the repository directory and ask it to follow this playbook with Lane B.

### 6. Verify

In a browser, as one of the testers:

1. Open the app URL and accept the authorization prompt if one appears.
2. The header shows your identity. If it reports "user token passthrough not enabled", prerequisite 2 is not done yet.
3. Run a scenario on a sandbox table you own: USE CATALOG, USE SCHEMA, and SELECT. All three should pass, and the grants are revoked when the run ends. Then run a single SELECT test with *Negative test* on: it should be denied.
4. Open the Activity tab: the run is listed, which means Lakebase is connected.
5. In the SQL section, check an UPDATE on a table the SP can only read: it should be Denied and nothing runs.
6. If the assistant is on, ask it "What can I test?".
7. In the app's Permissions dialog, confirm that only the testers have CAN_USE.

### 7. Teardown

- Lane A: run the notebook with `step` set to `teardown`. Set `delete_lakebase` to `yes` only if you also want the activity log and saved scenarios gone.
- Lane B: `./teardown.sh <profile>`. It asks before deleting, and asks separately about the Lakebase project.

Teardown leaves the model service's schema, the tester group, and the user-authorization setting in place.

## Configuration reference

| accelerator.yaml | App environment variable | Notes |
|---|---|---|
| `target.warehouse_id` | `HARNESS_WAREHOUSE_ID` | Also bound to the app as the `sql-warehouse` resource |
| `harness.lakebase.project`, `branch`, `endpoint` | `LAKEBASE_ENDPOINT` | `projects/<project>/branches/<branch>/endpoints/<endpoint>` |
| `harness.lakebase.schema` | `HARNESS_DB_SCHEMA` | The Postgres schema the app creates on first start |
| `harness.agent.uaig_base_url` | `UAIG_BASE_URL` | Empty disables the assistant |
| `harness.agent.model_catalog`, `model_schema`, `model_service` | `UAIG_MODEL_SERVICE` | `catalog.schema.service` |
| `harness.allowed_group` | `HARNESS_ALLOWED_GROUP` | Empty means anyone with CAN_USE on the app can use it |

A bundle deploy cannot pass an empty environment value, so `bundle-vars` passes `none` for anything empty, and the app reads `none` as unset.

## Costs

- **App:** compute bills while the app is running. Stop it when nobody is testing (`databricks apps stop <app_name>` or the Stop button on the app page).
- **Lakebase:** compute bills until the project's inactivity timeout. Shorten the timeout in the project's settings.
- **Warehouse:** set auto-stop to a few minutes.
- **Assistant:** pay-per-token model usage, attributed to the signed-in admin.

## When something goes wrong

- **"user token passthrough not enabled"**: turn on user authorization for Databricks Apps (prerequisite 2).
- **The assistant says the token "does not have required scopes: ai-gateway"**: redeploy so the app declares the `ai-gateway` scope, then reopen the app and accept the new authorization prompt.
- **The Activity tab stays empty**: check the app logs for `ensure_schema` warnings and that the app's Lakebase resource points at the right project.

More in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
