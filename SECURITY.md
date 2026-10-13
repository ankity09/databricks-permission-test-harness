# Security

## Reporting Vulnerabilities

If you discover a security vulnerability in this code, please report it to Databricks at bugbounty@databricks.com. Databricks acknowledges receipt and sends regular updates on the investigation.

Do not file a GitHub issue for security vulnerabilities.

## Prototype Status

This is a prototype provided as-is and not a supported Databricks product. The code demonstrates how to enforce permission testing in a Databricks workspace using the trust model described below. Before deploying in any environment with real permissions, thoroughly review the trust model and test the application in a non-production workspace.

## Trust Model

The Permission Test Harness enforces a strict separation of identity and authority:

1. **Writing grants**: Every `GRANT` or `REVOKE` is signed by the logged-in admin's on-behalf-of (OBO) token. The grant succeeds only because the admin has authority. The app itself carries zero standing grant power.

2. **Testing actions**: The app's own service principal (SP) attempts the action. The SP never holds admin privileges, so failures reflect what a real user with that grant level can actually do.

3. **Promotion to real users**: Happens only in Unity Catalog. The app shows validated SQL and a deep link, but never performs the grant itself. A human must copy-paste the SQL into Unity Catalog.

4. **Checking SQL as the SP**: Read-only statements run as the SP. Any other statement is only ever sent as `EXPLAIN`, which plans it without running it, and the SP's effective permissions decide whether it holds the write privilege.

For enforcement details and code references, see `docs/DESIGN.md`.

## Third-Party Notices

This project includes third-party packages under their own licenses. See `THIRD_PARTY_NOTICES.md`.
