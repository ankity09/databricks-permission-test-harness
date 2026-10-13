# Troubleshooting

## Common Issues and Fixes

| Symptom | Cause / Fix |
|---------|------------|
| `/api/me` returns 401 "user token passthrough not enabled" | User-authorization (OBO) preview is off. Enable it: Workspace admin → Workspace settings → enable "User authorization for Databricks Apps" (Public Preview). |
| `more than one authorization method configured: oauth and pat` | The OBO client must pin `auth_type="pat"` in `app/identity.py` so it ignores the ambient injected OAuth env. Already fixed in the code; check that you're running the latest version. |
| Grant fails with `PARSE_SYNTAX_ERROR at '.'` when using `USE CATALOG` | You passed a 3-level name (catalog.schema.table) to a catalog-level action. Use a bare catalog name. The app validates securable level before firing SQL and shows a distinct "check input" state. |
| `permission denied for schema perm_harness` (Lakebase) | The schema was created by a human, not the app SP. Deploy first so the SP owns the schema; or drop the schema + redeploy (ask before dropping if it holds data). |
| OBO scopes missing after a redeploy | Some deploys wipe scopes entirely (using `update_mask` that replaces wholesale). Re-run `databricks bundle deploy` with the same variables, or re-apply via `databricks apps create-update` and manually merge the scope fields. |
| App boots but chat dock errors | `UAIG_BASE_URL` or `UAIG_MODEL_SERVICE` is unset, or the model service has no route configured. Check `accelerator.yaml` for the values, verify the model service exists in Unity AI Gateway, and ensure a guardrail policy is attached. |
| UAIG model-service create API rejects the request body | The API is beta and field names may have shifted. Ensure: (a) `destination_type=DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL` (enum, exact string), (b) `model=models/system.ai.databricks-claude-...` (registered model path, not a serving endpoint name), (c) `model_service_id` and `parent` go as query params, not in the body. |
| Query runner rejects my read-only query | The tokenizer classified your first statement keyword as a mutation or unsupported type. Allowed: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`. Forbidden: `UPDATE`, `DELETE`, `INSERT`, `CREATE`, `ALTER`, `DROP`, `GRANT`, `REVOKE`. Rewrite using one of the allowed types. |
| Reach sweep runs but reports "no boundary violations" even though the SP shouldn't have access | Reach sweep checks only read permissions. It tests `SELECT` and `USE` on adjacent schemas/catalogs. It does not test write escalation or privilege escalation (those would require running `UPDATE`, `DELETE`, etc., which the app intentionally does not do). A green reach sweep means the SP cannot *read* adjacent objects; it says nothing about write or privilege boundaries. |
| Agent tool call fails with "UnknownToolError" | The tool name is not in the `TOOL_NAMES` registry in `app/agent.py`. Check the agent prompt; it should only invoke tools that are in the registry. If the model is trying to call a tool that doesn't exist, the agent has been given a bad prompt or the tool list is out of sync. Verify the schema passed to the model matches `agent.tool_schema()`. |
| Activity log grows very large | The `activity_log` table can grow quickly if tests are run frequently. To clean up: `TRUNCATE TABLE <catalog>.<schema>.perm_harness.activity_log`. This deletes the history but does not affect the app's operation. Consider setting up a retention policy if needed (e.g., delete rows older than 90 days). |
| Lakebase connection times out | Lakebase Autoscaling instances have an inactivity timeout (default ~5 min). If the app hasn't queried Lakebase for a while, the instance may pause. Reduce the timeout in the Lakebase project settings to save costs when idle, or query the instance again to wake it. |
| App deployment fails with "resource not found: warehouse" | The `warehouse_id` in `accelerator.yaml` is invalid or the warehouse has been deleted. Verify the ID is correct and the warehouse exists. If deleted, replace with a different warehouse ID and redeploy. |
| App starts but tabs are empty or grayed out | This usually means the app SP does not have permissions on the catalog or schema specified. Check: (1) Does the SP have `USE CATALOG` on the catalog? (2) Does it have `USE SCHEMA` on the schema? Mint a credential for the SP and verify with `SELECT COUNT(*) FROM <catalog>.<schema>.perm_harness.activity_log`. |
| Frontend shows "Cannot GET /api/..." | The backend is not running or not reachable. If running locally with `npm run dev`, ensure the Vite dev server is configured to proxy `/api` to `http://localhost:8000`. If deployed, ensure the app has started successfully (`databricks apps get permission-test-harness -o json` should show `app_status.state == RUNNING`). |
| Test applies the grant but probe hangs / never returns | The probe query (e.g., `SELECT COUNT(*) FROM <big-table> LIMIT 1`) may be slow on the configured warehouse, especially if the table is unpartitioned and the warehouse is small. Try: (1) pick a smaller table, (2) switch to a larger warehouse, or (3) kill the query in the Databricks UI and revoke the grant (clean up after failure). |

### The SQL check says "Not checkable"

The statement kind depends on ownership or MANAGE (DROP, ALTER, OPTIMIZE, and similar), the target is not fully qualified, or the app SP's effective permissions couldn't be read (the message includes the error). Name the target as `catalog.schema.table`, or use the matching action test.

## Debug Checklist

If something is not working, go through these steps:

1. **Check logs:**
   - Backend: `databricks apps logs permission-test-harness --profile <profile>` (shows FastAPI/Python errors).
   - Frontend: Open browser DevTools → Console (check for JavaScript errors).

2. **Verify deployment:**
   - `databricks apps get permission-test-harness --profile <profile> -o json` → is `app_status.state == RUNNING`?

3. **Test the app SP:**
   - Mint a credential for the app SP: `databricks sql get-database-credential --profile <profile>`.
   - Manually run a simple query as the SP to confirm it has access: `SELECT COUNT(*) FROM <catalog>.<schema>.<table> LIMIT 1`.

4. **Check OBO:**
   - Open the app → check the identity banner (top-left). Is it green (grantor + tester shown)? If red, OBO is not working; enable the user-authorization preview.

5. **Verify Lakebase:**
   - Connect to Lakebase using a Postgres client (e.g., via the Databricks SQL IDE or command line).
   - Check the schema: `SELECT table_name FROM information_schema.tables WHERE table_schema='perm_harness';` (should list `activity_log`, `scenarios`).
   - Check SP access: `SELECT COUNT(*) FROM perm_harness.activity_log;` (should return 0 or a count, not an error).

6. **Check UAIG (if agent enabled):**
   - Verify the model service exists: `databricks ml get-model-serving-endpoint <model_service> --profile <profile>`.
   - Test the endpoint: `curl -X POST https://<host>/ai-gateway/mlflow/v1/chat/completions -H "Authorization: Bearer <pat>" -H "Content-Type: application/json" -d '{"model":"<model_service>","messages":[{"role":"user","content":"hello"}]}'`.

7. **Inspect activity log:**
   - If tests have been run, check the activity log for errors: `SELECT * FROM <catalog>.<schema>.perm_harness.activity_log ORDER BY timestamp DESC LIMIT 10;`.

## Performance Tips

- **Query runner:** On very large tables, `SELECT ... LIMIT 1` can be slow even though it's read-only. If you want to test without scanning, use a smaller table or a Metastore-only permission (e.g., `USE CATALOG`, `USE SCHEMA`).
- **Reach sweep:** Enumerating all siblings can be slow in a large schema. If you have 1000+ objects in a schema, run the sweep on a specific sub-path if possible.
- **Activity log:** The app does not paginate the activity tab; showing 10,000 log entries may be slow. Truncate old entries if the log grows too large.
- **Lakebase cost:** The default inactivity timeout is long (5-10 min). Reduce it in the Lakebase project settings if you want to save on idle compute.

## Getting Help

- **Check the Activity tab** for recent test results and errors.
- **Read the chat dock** (if agent enabled) for explanations of permissions.
- **Review the logs** (see "Check logs" above).
- **Test manually**: use Databricks SQL to run the same probe query yourself and compare results.

If you believe there is a bug in the Permission Test Harness itself, please open an issue on GitHub or contact Databricks Field Engineering.
