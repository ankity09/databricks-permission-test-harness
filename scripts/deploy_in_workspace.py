# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy the Permission Test Harness from this workspace
# MAGIC
# MAGIC Run this notebook from the repository's Git folder on serverless compute. It uses
# MAGIC your own identity, needs no CLI or Node, and runs one step at a time:
# MAGIC
# MAGIC 1. Fill in `accelerator.yaml` at the repository root (see DEPLOY.md).
# MAGIC 2. Run **preflight**, read the capability matrix, and fix anything marked FAIL.
# MAGIC 3. Run **provision**, then **deploy-app**, then **grant-access**.
# MAGIC
# MAGIC Pick the step in the `step` widget at the top and run all cells. **teardown** deletes the
# MAGIC app and the model service; it also deletes the Lakebase project only when
# MAGIC `delete_lakebase` is `yes`.

# COMMAND ----------

# MAGIC %pip install --quiet databricks-sdk==0.138.0 pyyaml==6.0.3

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.dropdown("step", "preflight", ["preflight", "provision", "deploy-app", "grant-access", "teardown"])
dbutils.widgets.text("config", "../accelerator.yaml")
dbutils.widgets.dropdown("delete_lakebase", "no", ["no", "yes"])

# COMMAND ----------

import importlib.util

spec = importlib.util.spec_from_file_location("provision", "provision.py")
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)

step = dbutils.widgets.get("step")
args = [step, "--config", dbutils.widgets.get("config")]
if step == "teardown":
    args.append("--yes")
    if dbutils.widgets.get("delete_lakebase") == "yes":
        args.append("--delete-lakebase")

exit_code = provision.main(args)
assert exit_code == 0, f"{step} reported a failure; read the output above"
