# Contributing

This project is maintained by Databricks Field Engineering. Contributions and issues are welcome.

## Developer Setup

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd client
npm install
```

## Quality Checks

Run before committing:

```bash
# Backend tests
pytest

# Frontend type check
npx tsc -b

# Linting
npm run lint

# Production build (committed to client/dist/)
npm run build
```

All checks must pass with zero errors and zero warnings.

## Branch and Pull Request Rules

1. **Protected main branch**: cannot push directly to main.
2. **At least one approving review**: all PRs require review by someone other than the author.
3. **Author is not the reviewer**: self-reviews are not allowed.
4. **Small, focused PRs**: each PR should address one logical concern with a clear description.
5. **At least one Databricks reviewer**: while Databricks co-maintains this repo, every PR needs approval from a Databricks team member.

## Commit Messages

Use clear, concise commit messages:

```
Describe what changed and why

Include any relevant context or motivation.
```

## Testing Constraints

### Do not weaken safety tests

These tests enforce core invariants. Never modify `tests/test_grant_guard.py` or `tests/test_agent.py` in a way that reduces their coverage:

- `test_apply_to_sp_rejects_any_other_principal`: must reject non-SP principals
- `test_registry_has_no_grant_to_real_principal_tool`: agent tool registry must be closed-set

### Integration Tests

Integration tests are gated by default (require live Databricks workspace). Run locally with care:

```bash
HARNESS_WAREHOUSE_ID=... LAKEBASE_ENDPOINT=... pytest tests/test_integration.py -v
```

## GitLab Users

If mirroring this repo on GitLab, adapt the GitHub Actions steps in `.github/workflows/ci.yml` to `.gitlab-ci.yml`:

- Type check: `npm ci && npx tsc -b` (in `client/`)
- Lint: `npm run lint` (in `client/`)
- Test: `pytest` (backend)
- Build: `npm run build` (in `client/`)
- Dist freshness: verify `client/dist/` is committed and matches the source

## Architecture Decisions

Key architectural decisions are documented in `docs/DECISIONS.md`. Before proposing large changes, read that file to understand the "why" behind the current design.

## License

By contributing, you agree that your contributions are licensed under the Databricks License (see LICENSE).
