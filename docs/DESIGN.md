# Design Document: Permission Test Harness

## Problem

Databricks permissions are hard to verify before deployment. The current flow is manual:

1. An admin applies a permission to a user or group.
2. The admin asks that user to try the operation.
3. If it fails, the admin tries to diagnose why from error logs (often incomplete).
4. The admin revokes the permission and tries again.

This round trip is slow, there is no record of what was tested, and there is no mechanism to test permissions **before** committing them to real users.

## Users

- **Admins in regulated environments** who need to test permissions before rolling them out (financial, healthcare, etc.).
- **Permission architects** designing role hierarchies who want to validate that a role grants exactly the intended capabilities.
- **Workspace support teams** who field permission requests and want to verify the grant works before telling the user to try it.

## Trust Model

The app enforces a strict separation between **identity** (who is making the decision) and **authority** (what they can do). This ensures the test is representative of what a real user with that grant will experience.

### Invariant 1: Grants are OBO-signed by the admin

Every `GRANT` or `REVOKE` runs under the logged-in admin's on-behalf-of (OBO) token, not the app's own credentials.

**Why:** If the app held its own grant authority, it could grant permissions the admin themselves does not have, making the test unrepresentative. By signing with the admin's token, the grant succeeds only if the admin has the authority to do it. This is both a safety guarantee (the app cannot escalate) and a realism guarantee (the test reflects what the admin can actually do).

**Enforcement:**
- `app/identity.py` mints two clients: one OBO-signed by the user's token (for `GRANT`/`REVOKE`) and one using the app SP's credentials (for probes).
- `app/grant.py` always runs SQL under the OBO client.
- The test suite (`tests/test_identity.py`) verifies the split.

**File references:**
- `app/identity.py`: `OBOClient` class, instantiation from `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` + user token.
- `app/grant.py`: `apply_to_sp()` and `revoke_from_sp()` accept an executor (the OBO client).

### Invariant 2: The tested principal is always the app SP

Every permission test runs as the app's own service principal. The SP is the single "actor" being tested.

**Why:** If the app could test on behalf of any principal (including real users), it would need to mint their credentials, which would require storing secrets or managing delegation. By testing only on its own SP, the app avoids the credential management problem and keeps the test actor fixed and observable.

**Enforcement:**
- `app/grant.py` includes a **principal guard** (`_guard()` function) that rejects any grant target other than the configured SP.
- The test suite (`tests/test_grant_guard.py`) includes explicit positive and negative tests:
  - `test_apply_to_sp_rejects_any_other_principal()`: proves that granting to a real user raises `ForbiddenPrincipalError`.
  - `test_revoke_from_sp_rejects_other_principal()`: proves revoke also rejects non-SP principals.
- The principal is compared by exact string match; there is no exception for group names, email addresses, or other principal forms.

**File references:**
- `app/grant.py` lines 31-37: the `_guard()` function.
- `tests/test_grant_guard.py`: the complete safety test.

### Invariant 3: Promotion to real users happens only in Unity Catalog

The app never performs a grant to a real user or group. Instead, it shows the validated SQL and a deep link into Unity Catalog's grant UI, and the human must copy-paste the SQL.

**Why:** This ensures the "real" grant is audited under the user's own identity (not the app's) and is subject to Unity Catalog's governance (approval workflows, RBAC, audit logging).

**Enforcement:**
- `app/promote.py` returns only SQL text and a deep link URL (no execution).
- The `/api/promote` endpoint renders the SQL and shows the link; it never runs any `GRANT`.
- The agent's tool registry (`app/agent.py`) includes `get_promotion_directions` (read-only) but NOT `grant_to_principal` or any tool that executes a grant to a real principal.
- Test verification: `tests/test_agent.py::test_registry_has_no_grant_to_real_principal_tool()` asserts that the tool registry never contains names like `grant_user`, `grant_principal`, or `promote_grant`.

**File references:**
- `app/promote.py`: returns SQL + URL only.
- `app/agent.py`: `TOOL_NAMES` registry, no grant-to-user tool.
- `tests/test_agent.py`: agent registry test.

### Invariant 4: The app SP never holds standing admin authority

The app's service principal does not hold metastore admin, workspace admin, or any catalog/schema/table ownership. It only holds the specific permissions being tested (for the duration of the test).

**Why:** This ensures that test results are bounded in scope. If the SP held standing admin authority, every permission test would succeed (because admins bypass permission checks). By keeping the SP unprivileged, test failures are real.

**Enforcement:**
- The provisioning script (`scripts/provision.py`) never grants admin roles to the SP.
- The `sql/schema.sql` initialization script grants only specific permissions to the SP (usage on schema, select on tables, etc.).
- The test-revoke flow ensures permissions are temporary (they're revoked after the test).

**File references:**
- `scripts/provision.py`: never adds admin roles.
- `sql/schema.sql`: minimal permissions.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Databricks App                                  │
│                                                                   │
│  React + Vite (client/)          FastAPI (app/)                   │
│  ┌────────────────────┐          ┌──────────────────────────┐    │
│  │ Home, Test, ...    │  /api   │ identity  (OBO ⟷ SP split)│    │
│  │ Scenarios, Activity │ ───────▶│ grant     (SP-only guard) │    │
│  │ Assistant (dock)    │          │ probe / catalog / promote │    │
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

### Backend (FastAPI)

- **Identity split** (`app/identity.py`): Maintains two SQL clients, one OBO-signed (for grants) and one SP-signed (for probes).
- **Grant module** (`app/grant.py`): The only code that writes grants; enforces the principal guard and delegates to OBO client.
- **Probe module** (`app/probe.py`): Tests actions as the SP; includes side-effect-free probes (e.g., `SELECT ... LIMIT 1`).
- **Catalog module** (`app/catalog.py`): Parses and validates securable names; renders them as backtick-quoted SQL identifiers.
- **Query module** (`app/query.py`): Enforces read-only on user queries via token classification.
- **Agent module** (`app/agent.py`): Tool registry and dispatch loop; closed-set of tools, no grant-to-principal tools.
- **Scenarios** (`app/scenarios.py`): Batch test execution; applies all grants, probes each, revokes all.
- **Activity** (`app/activity.py`): Logs every apply/probe/revoke/promote to Lakebase.

### Frontend (React)

- **Test**: UC data and workspace objects modes. Lists testable actions (USE, SELECT, MODIFY, etc.); allows single-test flow and reach-sweep scans.
- **Scenarios**: Batch execution; templates + custom scenarios.
- **Activity**: Filterable history (Lakebase-backed).
- **Assistant**: Optional resizable dock (Unity AI Gateway agent); read-only query and reach-sweep runners.

### Persistence (Lakebase)

The app creates a schema with two tables:

- `activity_log`: Every apply, probe, revoke, promote, and promotion-action (copy-paste confirmation).
- `scenarios`: User-defined and seed role scenarios.

The SP owns the schema; reads happen via OBO (admins can only see what they queried).

### Agent (Unity AI Gateway)

The optional agent is a tool-calling loop:

1. Model receives a system prompt and tool registry.
2. User asks a question (e.g., "what permissions can I test on this table?").
3. Model calls tools (read_activity, read_catalog, run_single_test, get_promotion_directions, etc.).
4. App executes the tool under the user's OBO identity (for reads) or SP identity (for tests).
5. Model synthesizes results and returns an answer.

The guardrail policy attached to the model service (Unity AI Gateway UI) governs the conversation safety.

## Checking Any SQL Statement

The SQL section (and the assistant's `check_sql_as_sp` tool) answers "could the app SP run this statement?" without changing anything (`app/sql_check.py`).

1. **Classify.** The statement goes through the same tokenizer as the query runner. Grants, revokes, ownership changes, session or scripting commands, and multiple statements are rejected with HTTP 400.
2. **Read-only statements run.** Anything `assert_read_only` accepts runs as the SP and returns rows, with mask badges when a table is named.
3. **Everything else is never run.** The harness sends only `EXPLAIN <statement>` as the SP. Unity Catalog plans the statement, so missing USE CATALOG, USE SCHEMA, SELECT on tables the statement reads, or READ VOLUME show up as `INSUFFICIENT_PERMISSIONS` in the EXPLAIN output.
4. **The write privilege is read from Unity Catalog.** EXPLAIN does not check MODIFY or CREATE privileges (verified: an SP with SELECT only gets a clean plan for UPDATE). So the harness takes the statement's target (for example the table after `UPDATE` or `INSERT INTO`, or the schema for `CREATE TABLE`) and asks Unity Catalog for the SP's effective permissions on it, which include group and inherited grants. `WRITE_PRIVILEGES` maps each statement kind to what it needs: MODIFY for INSERT and TRUNCATE; MODIFY and SELECT for UPDATE, DELETE, and MERGE; USE SCHEMA plus CREATE TABLE, CREATE FUNCTION, CREATE MATERIALIZED VIEW, or CREATE VOLUME on the parent schema; USE CATALOG plus CREATE SCHEMA on the catalog. Ownership or ALL PRIVILEGES satisfies any check. The SP reads its own effective permissions with its own credentials, so the app needs no extra user scope.
5. **Verdicts.** Allowed, Denied, Invalid (a planning or syntax error unrelated to privileges), or Not checkable. Not checkable is used when the statement kind has no known privilege (DROP, ALTER, COMMENT, OPTIMIZE, VACUUM, ANALYZE, RESTORE, which depend on ownership or MANAGE), when the target is not fully qualified, for temporary objects, and when effective permissions can't be read. The harness never guesses.

Limits: the check covers Unity Catalog privileges only. Row filters, column masks, and ABAC policies that act when a statement runs are not evaluated for writes, and ownership through a group the SP belongs to is not detected.

## Data Model

### activity_log (Lakebase)

```
timestamp: timestamp
admin_identity: string (email)
action: string (apply | probe | revoke | promote | promotion_confirmed)
securable: string (catalog.schema.table, etc.)
action_id: string (SELECT, USE_SCHEMA, etc.)
principal: string (the app SP name)
grant_verdict: string (PASS | FAIL | ERROR)
error_message: string (if verdict != PASS)
query_limit: integer (for probe queries, rows returned)
```

### scenarios (Lakebase)

```
scenario_id: string (UUID)
created_by: string (admin email)
created_at: timestamp
name: string
description: string
items: JSON array [{securable, action_id}, ...]
```

## Agent Design

The agent is optional and read-only:

- **TOOL_NAMES** (closed set): read_activity, read_catalog, check_effective_permissions, run_single_test, list_scenarios, save_scenario, run_scenario, get_promotion_directions, run_query_as_sp, run_reach_sweep.
- **No grant-to-principal tool**: the registry is deliberately missing any tool that performs a grant to a real user.
- **Tool-calling loop** (`app/agent.py::run_chat`): Executes tool calls until the model returns a final answer (or max iterations reached).
- **Tool handlers**: Each tool handler is a FastAPI endpoint wrapped as a tool. Runs under the user's OBO identity (for reads) or SP identity (for tests).

## Known Limitations

1. **No workspace-object write tests**: The reach sweep and effective-permission checks on workspace objects are read-only or hypothetical. There is no "actually try to delete this notebook" probe.

2. **No multi-workspace testing**: All tests are within a single workspace. Cross-workspace permissions (Databricks to Databricks, account-level SCIM) are not supported.

3. **No tester audit trail**: Activity logs record what the app attempted, not which user used the UI to trigger the test. For audit, audit logs are in Databricks' own system-tables.

4. **No integration with external IdP**: Auth is workspace identity only. External identity systems (Okta, Azure AD) are not integrated.

5. **No approval workflow**: Tests execute immediately. A production system would add an approval step between the admin's request and the probe execution.

6. **Agent is not multi-turn with memory**: Each chat message starts fresh; there is no session memory. A message like "revoke that grant" would require repeating the full context.

## Security Considerations

- **Credentials:** The app SP credentials are auto-injected by Databricks Apps and never appear in code or logs.
- **Audit:** Every grant/revoke is audited by Databricks under the admin's own identity (via OBO).
- **Secret scanning:** CI includes a secret scan step; no credentials should be committed.
- **Read-only guarantee:** The query runner enforces read-only via token classification, not just SQL validation.
- **Rate limiting:** Not implemented; a production system would add rate limiting to prevent brute-force on sensitive tables.
