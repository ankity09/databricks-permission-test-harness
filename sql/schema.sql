-- Permission Test Harness v2 -- Lakebase schema.
--
-- SETUP (run once, connected to the Lakebase database AS THE ADMIN):
--   1. Register the app service principal as a Postgres login role:
--        CREATE EXTENSION IF NOT EXISTS databricks_auth;
--        SELECT databricks_create_role('<app-sp-client-id>', 'service_principal');
--   2. Run this file (substitute <app-sp-client-id> below).
--   3. Optionally grant the OBO admin user SELECT on activity_log so the agent
--      can read history under the user's OBO identity.

CREATE SCHEMA IF NOT EXISTS perm_harness;

CREATE TABLE IF NOT EXISTS perm_harness.activity_log (
    id           TEXT PRIMARY KEY,
    session_id   TEXT,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    admin_email  TEXT,
    sp_id        TEXT,
    event_type   TEXT NOT NULL,
    action_id    TEXT,
    securable    TEXT,
    verdict      TEXT,
    raw_message  TEXT,
    scenario_id  TEXT
);
CREATE INDEX IF NOT EXISTS activity_log_ts_idx ON perm_harness.activity_log (ts DESC);

CREATE TABLE IF NOT EXISTS perm_harness.scenarios (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    items       JSONB NOT NULL,
    is_seed     BOOLEAN NOT NULL DEFAULT false
);

-- Grant the app SP access to its own tables (run after databricks_create_role).
-- Substitute the app SP client id:
GRANT USAGE ON SCHEMA perm_harness TO "<app-sp-client-id>";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA perm_harness TO "<app-sp-client-id>";
ALTER DEFAULT PRIVILEGES IN SCHEMA perm_harness
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<app-sp-client-id>";

-- Optional: let the OBO admin read history (agent reads under OBO):
-- GRANT USAGE ON SCHEMA perm_harness TO "<admin-user-email>";
-- GRANT SELECT ON perm_harness.activity_log TO "<admin-user-email>";
