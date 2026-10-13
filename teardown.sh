#!/usr/bin/env bash
# Uninstall the Permission Test Harness: the bundle deployment (if any), the app,
# the model service, and optionally the Lakebase project. Uses accelerator.yaml.
set -euo pipefail

PROFILE="${1:-}"
if [ -z "$PROFILE" ]; then
  echo "Usage: ./teardown.sh <databricks-cli-profile>"
  exit 1
fi
cd "$(dirname "$0")"

python3 scripts/provision.py teardown --profile "$PROFILE"   # prints the plan, deletes nothing
read -r -p "Delete the items above? [y/N] " ans
case "$ans" in [yY]) ;; *) echo "Aborted."; exit 0 ;; esac
read -r -p "Also delete the Lakebase project and ALL its data (activity log, saved scenarios)? [y/N] " lb
LAKEBASE_FLAG=""
case "$lb" in [yY]) LAKEBASE_FLAG="--delete-lakebase" ;; esac

# Bundle deployments need the same variables to resolve the bundle.
if [ -d ".databricks/bundle" ] && FLAGS=$(python3 scripts/provision.py bundle-vars --flags-only 2>/dev/null); then
  echo "Destroying the bundle deployment..."
  eval databricks bundle destroy --target dev --profile "\"$PROFILE\"" --auto-approve "$FLAGS"
fi

python3 scripts/provision.py teardown --profile "$PROFILE" --yes $LAKEBASE_FLAG

echo ""
echo "Not deleted (remove by hand if you no longer need them):"
echo "  - the model-service schema (harness.agent.model_catalog / model_schema)"
echo "  - the allowed group and its members"
echo "  - user authorization for Databricks Apps, if you enabled it only for this app"
