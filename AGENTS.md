# Agent guide

Boundaries for any coding agent working in this repository. They protect the trust model in [docs/DESIGN.md](docs/DESIGN.md). If a task conflicts with one of them, stop and ask.

## Boundaries

1. **Grants go only to the app's own service principal.** `app/grant.py` refuses any other principal and re-checks every rendered GRANT or REVOKE. Never add a code path, endpoint, or assistant tool that grants to a user, group, or another service principal. Promotion to real people stays a SQL snippet plus a Unity Catalog link.
2. **Securable names go through `app/securable.py`.** Every name that reaches SQL is parsed and backtick-quoted there. Never interpolate request, scenario, or assistant input into SQL directly.
3. **Nothing sent as the service principal may change data**, except the opt-in "really do" write probes in `app/probe.py`. The query runner accepts only what `app/sql_guard.py` allows (one SELECT, WITH, SHOW, DESCRIBE, or EXPLAIN). `app/sql_check.py` runs read-only statements as-is and sends every other statement only as `EXPLAIN`. Never weaken either.
4. **Every API route checks the caller.** All routes except `/health`, `/actions`, and `/me` call `require_tester`. New routes must too.
5. **A test never removes a grant the service principal already had.** Keep the `sp_holds_directly` check in front of every apply.
6. **The assistant's tools are a closed set** (`TOOL_NAMES` in `app/agent.py`), each going through the same guards as the HTTP endpoints.
7. **The app writes only to its own Lakebase schema** (`HARNESS_DB_SCHEMA`), which it creates on first start. It writes nowhere else.
8. **No credentials in code, config, or commits.** Credentials come from the Databricks Apps environment or the OAuth flow.

## Safety tests

Never delete or weaken these. Run them before every commit:

```bash
pytest tests/test_grant_guard.py tests/test_agent.py tests/test_authorization_coverage.py \
  tests/test_securable_parser.py tests/test_sql_guard.py tests/test_sql_guard_tokenizer.py \
  tests/test_sql_check.py tests/test_grant_preexisting.py
```

## Working in a customer workspace

- Ask before creating anything that costs money or deploys infrastructure: apps, Lakebase projects, model services, warehouses. Show the `preflight` output and wait for approval.
- Never run in auto-approve mode while the person you work for holds admin rights.
- Serverless compute only.
- Put scratch files in `.agent-scratch/` (gitignored), never in the repository.

## Before you commit

All of these must pass (see [CONTRIBUTING.md](CONTRIBUTING.md)): `pytest`, and in `client/`: `npx tsc -b`, `npm run lint` with zero warnings, and `npm run build`, with the rebuilt `client/dist` committed.
