# Architecture Decisions

This document records the key choices made in designing the Permission Test Harness and the reasoning behind them.

## 1. FastAPI over AppKit for the Backend

**Decision:** Use FastAPI (not AppKit's Node.js runtime or Python async ASGI) as the backend framework.

**Context:**
- This app needs per-call identity switching: the `GRANT`/`REVOKE` must be signed by the admin's OBO token, while the probe runs as the app SP.
- AppKit's current Python support is sync-only, and its Node.js runtime does not have access to the Databricks Python SDK's OBO client.
- A single uniform identity (the app's SP) would make the app itself a standing permission holder, compromising the test's representativeness.

**Options considered:**
1. AppKit (Python): clean Databricks-native stack, but no support for per-call identity switching.
2. AppKit (Node.js) + custom OBO flow: would require implementing OBO token exchange in Node, error-prone.
3. Custom Flask/FastAPI with manual identity management: full control, but more code to maintain.
4. Genie Agents orchestrator: overkill for this use case; agent is optional, not required.

**Decision:** FastAPI with the Databricks Python SDK, manually managing the OBO vs SP split in `app/identity.py`.

**Rationale:**
- Gives full control over the identity split at each request.
- Databricks Python SDK has first-class OBO support.
- FastAPI is lightweight and pairs well with a React frontend.
- The identity split logic is explicitly visible, making it auditable.

**Trade-off:** Owning the request path means more code to maintain, but the safety gain (enforced per-call identity) is worth it.

---

## 2. OBO-Signed Grants to the SP vs Giving the SP Grant Authority

**Decision:** Every `GRANT`/`REVOKE` is signed by the admin's OBO token; the app SP never holds grant authority.

**Context:**
- Granting permissions to the app SP is the test action; someone with authority must perform it.
- Two approaches: (a) sign each grant under the admin's identity, or (b) give the app SP a standing grant authority role (e.g., catalog owner).

**Options considered:**
1. Admin OBO-signs each grant: grants succeed only if the admin has authority; test is representative; audit trail shows the admin, not the app.
2. App SP holds grant authority: simpler code (no identity split), but makes the test unrepresentative (the SP can grant things the admin cannot) and violates the "SP is unprivileged" invariant.

**Decision:** Admin OBO-signs every grant (option 1).

**Rationale:**
- Test representativeness: If the admin applies a grant under their own identity, the test result reflects what a real user with that admin's authority would see.
- Audit trail: Databricks logs the grant under the admin's identity, not the app's, making it clear who authorized the test.
- Safety: Avoids giving the app SP standing privilege, keeping it a pure test actor.
- Reversibility: If the test goes wrong, the admin can inspect Databricks' audit log and reverse the grant themselves; the app never holds privilege that could be exploited.

**Trade-off:** Requires more code for identity management (`app/identity.py`), but the safety and auditability gains are essential.

---

## 3. Read-Only Query Runner + Tokenizer Guard

**Decision:** The query runner is read-only, enforced via a token-based SQL classifier, not just a regex or whitelist.

**Context:**
- The "query as the SP" feature lets admins write ad-hoc SQL to see what the SP can actually select (useful for debugging column-mask and row-filter visibility).
- Must guarantee that mutations, DDL, and `GRANT`/`REVOKE` never execute under the SP's identity.

**Options considered:**
1. Regex blocklist (e.g., reject `.*UPDATE.*`, `.*DELETE.*`): simple, but easily bypassed (comments, multi-line, etc.).
2. SQL parser + statement type check: robust, but adds a dependency.
3. Token classifier (split by spaces/semicolons, classify first meaningful token): lightweight, catches 90% of cases.
4. Run the query in a sandbox with read-only credentials: most robust, but adds infrastructure.

**Decision:** Token classifier (`app/query.py`) classifying the first statement keyword.

**Rationale:**
- Catches common mutations: `UPDATE`, `DELETE`, `INSERT`, `ALTER`, `DROP`, `CREATE`, `REVOKE`, `GRANT`.
- Lightweight; no external parser dependency.
- Fast to execute (tokenize on first pass, check token).
- Allowed statement types: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`.
- Not foolproof (comments could mislead, multi-statement could be missed), but good enough for a prototype. A production system would add read-only credentials or a query sandbox.

**Trade-off:** Not as robust as a full SQL parser or a sandboxed execution, but acceptable for a prototype. Documented in `docs/DESIGN.md` under "Known Limitations."

---

## 4. Lakebase for the Activity Log

**Decision:** Use Lakebase (Postgres) for the durable activity log and saved scenarios.

**Context:**
- Activity needs to persist across app restarts.
- Multiple admins need to read history.
- Scenarios (user-defined roles) need to be shared and re-run.

**Options considered:**
1. Lakebase: OLTP database, low-latency reads/writes, integrates with Databricks' own Postgres connection pool.
2. Delta Lake table (in the customer's catalog): Lakehouse-native, but not optimized for transactional reads; harder to ensure schema ownership by the app SP.
3. In-memory cache (Memcached, Redis): fast, but loses data on restart; not suitable for durable audit.
4. S3/ADLS JSON files: fully decoupled, but complex schema evolution and concurrent write handling.

**Decision:** Lakebase.

**Rationale:**
- Transactional semantics (important for concurrent probes logging results).
- Low-latency queries (activity tab needs to render fast).
- SP ownership of the schema (ensures the app can manage the data independently of the admin).
- Integrated Postgres connection pooling (Databricks Apps provides `PGHOST`, `PGPORT`, etc. via bindings).

**Trade-off:** Adds a cost (Lakebase billing) and a setup step (provisioning the project, creating schema/role). Alternative (Delta) would be cheaper if read-only is acceptable, but we need transactional writes for concurrent safety.

---

## 5. Unity AI Gateway Model Service vs Calling system.ai Directly

**Decision:** Use a Unity AI Gateway model service (when available) as the agent's backend; fall back to direct `system.ai` calls if the service is unavailable.

**Context:**
- The agent needs to call a foundation model to answer questions about permissions.
- Two paths: (a) route through a governed Unity AI Gateway model service (with guardrails, audit, cost tracking), or (b) call `system.ai` directly via REST.

**Options considered:**
1. Unity AI Gateway model service: adds governance (guardrails, audit, rate limits), but requires regional availability and a setup step.
2. Direct `system.ai` calls: simpler provisioning, but loses governance and audit.
3. No agent at all: keeps the app simpler, but loses the "AI assistant" feature.

**Decision:** Prefer Unity AI Gateway when available; fall back to direct `system.ai` if not; agent is optional.

**Rationale:**
- Governance for regulated customers (the agent's chat is then subject to enterprise guardrails).
- Cost tracking (the model service reports usage separately).
- Audit trail (model service logs queries; direct calls do not).
- Graceful degradation: if Unity AI Gateway is not available in the region, the agent still works but without governance.

**Trade-off:** Complex provisioning (the setup script must create the model service, attach guardrails manually); if the feature is too hard to set up, customers may just skip it. Documented in DEPLOY.md as optional.

---

## 6. Committed client/dist/ for Deployment

**Decision:** The React build output (`client/dist/`) is committed to the repository, not generated at deploy time.

**Context:**
- Databricks Apps can mount a folder as a static file directory; the app serves React from `client/dist/`.
- Two approaches: (a) commit the build, or (b) generate it during the DABs deploy.

**Options considered:**
1. Commit `client/dist/`: larger repo, but deploy is simpler (no build step in CI/CD).
2. Generate at deploy time: smaller repo, but deploy pipeline must have Node.js and build tools.
3. Upload to cloud storage, reference from the app: decouples frontend from app repo, but adds infrastructure.

**Decision:** Commit `client/dist/`.

**Rationale:**
- Databricks Apps deploy from a Git folder; if the build is missing, the app fails to start with a cryptic "file not found" error.
- Committing the build makes the app deployable without Node.js in the deploy environment (useful for customers who want to deploy from a laptop or CI without Node setup).
- CI includes a freshness check (verifies `client/dist/` matches the source), catching out-of-sync builds.

**Trade-off:** The repo is larger (~500 KB for the built JavaScript), but the deployment simplicity and end-user deployability are worth it.

---

## 7. Python Provisioner vs Bash Script

**Decision:** `scripts/provision.py` is a Python script, not bash.

**Context:**
- Provisioning includes creating Lakebase projects, model services (REST API), and initializing Postgres schemas.
- Two approaches: (a) Python with the Databricks SDK, or (b) bash with `databricks` CLI + `curl`.

**Options considered:**
1. Python + Databricks SDK: structured, error handling, can parse responses; SDK is the canonical interface.
2. Bash + CLI + curl: simpler conceptually, but error handling is harder; JSON parsing with `jq` is fragile.
3. Genie Code skill: would defer provisioning to an agent; more flexible, but harder to version and test.

**Decision:** Python + Databricks SDK.

**Rationale:**
- Structured error handling (try/except, typed responses).
- JSON parsing is native (no `jq` fragility).
- Idempotency is easier (check if resource exists, skip if so).
- Can be tested in CI without a live workspace (mock the SDK).

**Trade-off:** Customers must have Python 3 installed; the bash + `jq` approach would work on any shell. Documented in prerequisites; acceptable for an enterprise tool.

---

## 8. Provisioner-Managed Lakebase Project

**Decision:** `scripts/provision.py provision` creates the Lakebase project if it does not already exist (idempotent).

**Context:**
- The Lakebase project is not a Databricks App resource that DABs can create (DABs only binds to existing Lakebase instances).
- Two approaches: (a) provisioner creates it, or (b) customer creates it manually.

**Options considered:**
1. Provisioner creates the project: easier for the customer; one-step deployment.
2. Customer creates manually: more control, but adds a pre-deploy step that many will forget.
3. Make Lakebase optional and degrade gracefully: possible, but activity log is core to the UX.

**Decision:** Provisioner creates it (idempotent).

**Rationale:**
- Reduces deployment friction (customer does not have to remember to create the project first).
- Idempotent: if the project exists, the provisioner reuses it (safe to re-run).
- Can document the created resource name, cost notes, and cleanup path clearly.

**Trade-off:** Provisioner has standing permission to create infrastructure (cost risk). Mitigated by preflight review gate (customer sees what will be created and approves before it happens).

---

## 9. HARNESS_ALLOWED_GROUP Gating

**Decision:** The app supports optional gating via `HARNESS_ALLOWED_GROUP` env var: if set, only users in that group can use the app (CAN_USE grant on the group).

**Context:**
- Permission testing is a sensitive operation (admins are testing what they can grant).
- Two approaches: (a) open the app to anyone with CAN_USE, or (b) restrict to a specific group.

**Options considered:**
1. No gating; open to all CAN_USE users: simple, but risky if the app is deployed in a shared workspace.
2. Optional gating via group: allows the customer to restrict to a specific team if desired.
3. Required gating (force group membership): safer, but less flexible for solo admins or small teams.

**Decision:** Optional gating via `HARNESS_ALLOWED_GROUP`.

**Rationale:**
- Gives the customer a choice: open for broad access or restricted to a team.
- If not set, behaves as "open to all CAN_USE users."
- Documented in DEPLOY.md; customers can tighten it if needed.

**Trade-off:** Adds a feature that many may not use; the code path is tested but not as commonly exercised. Acceptable for an optional security knob.

---

## 10. No Schema.yaml or Pydantic Models for Configuration

**Decision:** Configuration lives in `accelerator.yaml` (hand-editable YAML), not a schema definition or Pydantic models.

**Context:**
- Customers must review and understand the configuration before deploy (review gate).
- Two approaches: (a) Pydantic-modeled config with validation, or (b) hand-editable YAML with minimal tooling.

**Options considered:**
1. Pydantic models: type-safe, IDE autocomplete, clear validation errors.
2. Hand-editable YAML: easier for customers to read and modify without understanding Python.
3. JSON Schema: allows customers to validate with standard tools, but not human-readable.

**Decision:** Hand-editable YAML (`accelerator.yaml`).

**Rationale:**
- Customers will review the file and may hand-edit it (to correct warehouse IDs, change app names, etc.).
- YAML is more readable than JSON or Python code.
- Validation can happen at provisioning time (preflight step prints errors if values are invalid).

**Trade-off:** Less type safety; customers can make typos. Mitigated by the preflight step, which tests each value and reports errors clearly.

---

## 11. Checking Arbitrary SQL with EXPLAIN Plus Effective Permissions

**Context:** Testers wanted to run their own SQL as the SP, including writes, not only the predefined action tests. Running writes as the SP would change data in their workspace.

**Options considered:**

1. **Read-only statements only.** Safe, but does not answer the question for writes.
2. **Run writes for real behind a confirmation.** Definitive, but it changes data, and a mistake lands in a real table.
3. **EXPLAIN only.** Nothing runs. Verified live that it is not enough: EXPLAIN checks USE CATALOG, USE SCHEMA, SELECT on input tables, and READ VOLUME, but not MODIFY or CREATE privileges.
4. **EXPLAIN plus Unity Catalog effective permissions for the write target.** Nothing runs. EXPLAIN covers reachability and read access; the effective-permissions API covers the write privilege, including grants through groups and parent objects.

**Decision:** Option 4. Read-only statements run as the SP; every other statement is only sent as EXPLAIN, then the SP's effective permissions on the target are compared with `WRITE_PRIVILEGES`. The SP reads its own effective permissions, because reading them as the admin would require declaring the broad `unity-catalog` user scope.

**Verified on a live workspace:** for INSERT, UPDATE, DELETE, MERGE, TRUNCATE, CREATE TABLE, CREATE TABLE AS SELECT, CREATE VIEW, CREATE FUNCTION, and CREATE MATERIALIZED VIEW, the verdict was Denied without the privilege and Allowed with it, and the Delta history of the target tables showed that nothing ran.

**Limits:** Statement kinds that depend on ownership or MANAGE (DROP, ALTER, COMMENT, OPTIMIZE, VACUUM, ANALYZE, RESTORE) and targets that are not fully qualified are reported as not checkable. Row filters, column masks, and ABAC policies that apply at run time are not evaluated for writes.

