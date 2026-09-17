"""FastAPI entry point for the Permission Test Harness.

Endpoints (all under /api):
  GET  /health         liveness
  GET  /actions        the action catalog, grouped by tab
  GET  /me             admin identity (from OBO token) + configured SP id.
                       Doubles as the OBO verification endpoint: if this
                       resolves the admin identity, OBO is wired correctly.
  POST /grant/apply    apply a candidate grant onto the app SP (OBO-signed)
  POST /grant/revoke   revoke it from the app SP (OBO-signed)
  POST /probe          SP attempts the action; returns pass/fail_denied/...
  POST /promote        non-mutating: validated GRANT SQL + UC deep-link
  POST /reset-sp       best-effort: revoke all app-applied test grants

Identity rules (spec section 1):
  * grant/revoke are executed under the OBO ADMIN client (admin authority).
  * probes execute under the app SP client.
  * the ONLY principal ever written to is the configured app SP.
"""

from __future__ import annotations

import contextlib
import os
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app import activity as activity_mod
from app import agent as agent_mod
from app import db as db_mod
from app import scenarios as scen_mod
from app import uaig as uaig_mod
from app.catalog import SecurableLevelError, load_catalog, validate_securable
from app.config import get_settings
from app.grant import ForbiddenPrincipalError, apply_to_sp, revoke_from_sp
from app.identity import (
    get_obo_client,
    get_obo_identity,
    get_obo_token,
    get_sp_client,
    get_sp_identity,
)
from app.promote import build_promote_info
from app.models import (
    AgentChatRequest,
    ApplyRequest,
    ProbeRequest,
    ProbeResult,
    PromoteInfo,
    QueryRequest,
    ScenarioRunRequest,
    ScenarioSaveRequest,
    SweepRequest,
)
from app.probe import run_probe
from app.query import build_select, run_query_as_sp
from app.masking import describe_governance
from app.sweep import build_targets, run_sweep
from app.sql_guard import assert_read_only, ReadOnlyViolation


@asynccontextmanager
async def _lifespan(_app):
    # Init the Lakebase pool without ever blocking boot (graceful lifespan).
    try:
        db_mod.init_pool(db_mod.get_state())
    except Exception:  # noqa: BLE001
        pass
    yield


app = FastAPI(title="Permission Test Harness", lifespan=_lifespan)
api = FastAPI()
app.mount("/api", api)


@contextlib.contextmanager
def _conn_factory():
    """Borrow a pooled Lakebase connection. Raises if the pool is unavailable."""
    pool = db_mod.get_pool()
    if pool is None:
        raise RuntimeError(db_mod.get_state().error or "no db pool")
    with pool.connection() as conn:
        yield conn


def _log_event(request, *, event_type, action_id, securable, verdict=None, raw_message=""):
    """Best-effort telemetry write. NEVER raises into the request path."""
    try:
        admin = get_obo_identity(request)
        admin_email = admin.get("user_name") or ""
    except Exception:  # noqa: BLE001
        admin_email = ""
    try:
        activity_mod.log_event(
            conn_factory=_conn_factory,
            schema=get_settings().db_schema,
            session_id=request.headers.get("x-session-id", "adhoc"),
            admin_email=admin_email,
            sp_id=get_settings().sp_application_id,
            event_type=event_type,
            action_id=action_id,
            securable=securable,
            verdict=verdict,
            raw_message=raw_message,
        )
    except Exception:  # noqa: BLE001 -- telemetry must not break the loop
        pass

# in-session record of what this app has applied to the SP (best-effort cleanup)
_APPLIED: list[dict] = []


def _configured_sp() -> str:
    sp = get_settings().sp_application_id
    if not sp:
        raise HTTPException(
            status_code=500,
            detail="App service principal id not configured (DATABRICKS_CLIENT_ID).",
        )
    return sp


def _obo_sql_executor(request: Request) -> Callable[[str], Any]:
    """Return an executor that runs SQL under the OBO ADMIN client.

    Grants only succeed because the admin has authority — the SP never does.
    """
    client = get_obo_client(request)
    warehouse_id = get_settings().warehouse_id

    def _exec(sql: str) -> Any:
        resp = client.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=warehouse_id,
            wait_timeout="30s",
        )
        status = getattr(resp, "status", None)
        state = getattr(status, "state", None)
        state_str = getattr(state, "value", str(state)) if state is not None else ""
        if state_str and state_str.upper() != "SUCCEEDED":
            err = getattr(status, "error", None)
            msg = getattr(err, "message", str(err)) if err else f"state={state_str}"
            raise RuntimeError(msg)
        return resp

    return _exec


@api.get("/health")
async def health():
    return {"status": "ok"}


@api.get("/actions")
async def actions():
    catalog = load_catalog()
    grouped: dict[str, list] = {"uc-data": [], "workspace": []}
    for d in catalog.values():
        grouped.setdefault(d.tab, []).append(d.model_dump())
    # flat list too (tests look for a flat list of {id,...})
    return [d.model_dump() for d in catalog.values()]



@api.get("/activity")
async def get_activity(
    admin_email: str | None = None,
    verdict: str | None = None,
    securable: str | None = None,
    scenario_id: str | None = None,
    limit: int = 100,
):
    try:
        events = activity_mod.read_events(
            conn_factory=_conn_factory,
            schema=get_settings().db_schema,
            admin_email=admin_email,
            verdict=verdict,
            securable=securable,
            scenario_id=scenario_id,
            limit=limit,
        )
    except Exception:  # noqa: BLE001
        events = []
    return {"events": events, "db": db_mod.healthcheck()}


@api.get("/me")
async def me(request: Request):
    """Admin identity from OBO + configured SP. OBO verification endpoint."""
    admin = get_obo_identity(request)  # raises 401 if OBO token missing
    try:
        sp = get_sp_identity()
    except Exception as exc:  # noqa: BLE001
        sp = {"error": str(exc)}
    return {
        "admin": admin,
        "app_sp": sp,
        "configured_sp_application_id": get_settings().sp_application_id,
        "obo": "ok",
    }


@api.post("/grant/apply")
async def grant_apply(request: Request, body: ApplyRequest):
    catalog = load_catalog()
    descriptor = catalog.get(body.action_id)
    if descriptor is None:
        raise HTTPException(404, f"Unknown action: {body.action_id}")
    if not descriptor.grant_sql:
        raise HTTPException(
            400,
            f"Action {body.action_id} has no grant SQL (workspace ACLs are set "
            "in the workspace UI, not via GRANT).",
        )
    try:
        validate_securable(descriptor, body.securable)
    except SecurableLevelError as exc:
        raise HTTPException(400, str(exc))
    executor = _obo_sql_executor(request)  # raises 401 if OBO token missing
    sp = _configured_sp()
    try:
        apply_to_sp(
            descriptor.grant_sql,
            principal=sp,
            configured_sp=sp,
            executor=executor,
            securable=body.securable,
        )
    except ForbiddenPrincipalError as exc:
        raise HTTPException(403, str(exc))
    except Exception as exc:  # noqa: BLE001 — surface grant-authority errors
        raise HTTPException(422, f"Grant failed: {exc}")
    _APPLIED.append({"action_id": body.action_id, "securable": body.securable})
    _log_event(request, event_type="apply", action_id=body.action_id, securable=body.securable)
    return {"status": "applied", "action_id": body.action_id, "securable": body.securable}


@api.post("/grant/revoke")
async def grant_revoke(request: Request, body: ApplyRequest):
    catalog = load_catalog()
    descriptor = catalog.get(body.action_id)
    if descriptor is None:
        raise HTTPException(404, f"Unknown action: {body.action_id}")
    if not descriptor.revoke_sql:
        raise HTTPException(400, f"Action {body.action_id} has no revoke SQL.")
    try:
        validate_securable(descriptor, body.securable)
    except SecurableLevelError as exc:
        raise HTTPException(400, str(exc))
    executor = _obo_sql_executor(request)  # raises 401 if OBO token missing
    sp = _configured_sp()
    try:
        revoke_from_sp(
            descriptor.revoke_sql,
            principal=sp,
            configured_sp=sp,
            executor=executor,
            securable=body.securable,
        )
    except ForbiddenPrincipalError as exc:
        raise HTTPException(403, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Revoke failed: {exc}")
    _APPLIED[:] = [
        a for a in _APPLIED
        if not (a["action_id"] == body.action_id and a["securable"] == body.securable)
    ]
    _log_event(request, event_type="revoke", action_id=body.action_id, securable=body.securable)
    return {"status": "revoked", "action_id": body.action_id, "securable": body.securable}


@api.post("/probe", response_model=ProbeResult)
async def probe(request: Request, body: ProbeRequest):
    catalog = load_catalog()
    descriptor = catalog.get(body.action_id)
    if descriptor is None:
        raise HTTPException(404, f"Unknown action: {body.action_id}")
    sp_client = get_sp_client()
    outcome = run_probe(
        descriptor,
        securable=body.securable,
        sp_client=sp_client,
        warehouse_id=get_settings().warehouse_id,
        really_do=body.really_do,
        negative=body.negative_test,
    )
    _log_event(
        request,
        event_type="probe",
        action_id=body.action_id,
        securable=body.securable,
        verdict=outcome.status,
        raw_message=outcome.raw_error,
    )
    return ProbeResult(
        status=outcome.status,
        detail=outcome.detail,
        raw_error=outcome.raw_error,
        rows=outcome.rows,
    )


@api.post("/promote", response_model=PromoteInfo)
async def promote(request: Request, body: ApplyRequest, principal: str):
    from app.promote import build_promote_info

    catalog = load_catalog()
    if body.action_id not in catalog:
        raise HTTPException(404, f"Unknown action: {body.action_id}")
    info = build_promote_info(
        action_id=body.action_id,
        securable=body.securable,
        principal=principal,
        host=get_settings().workspace_host,
        catalog=catalog,
    )
    _log_event(request, event_type="promote_viewed", action_id=body.action_id, securable=body.securable)
    return info


@api.get("/scenarios")
async def list_scenarios_ep():
    seed = [
        {**s, "id": f"seed:{s['name']}", "is_seed": True}
        for s in scen_mod.load_seed_scenarios()
    ]
    custom = []
    try:
        custom = scen_mod.list_scenarios(
            conn_factory=_conn_factory, schema=get_settings().db_schema
        )
    except Exception:  # noqa: BLE001 -- degrade gracefully when DB is down
        pass
    return {"scenarios": seed + custom}


@api.post("/scenarios")
async def save_scenario_ep(request: Request, body: ScenarioSaveRequest):
    try:
        admin = get_obo_identity(request)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        raise HTTPException(401, "OBO required to save scenarios")
    sid = scen_mod.save_scenario(
        conn_factory=_conn_factory,
        schema=get_settings().db_schema,
        name=body.name,
        description=body.description,
        created_by=admin.get("user_name", ""),
        items=[i.model_dump() for i in body.items],
    )
    return {"id": sid}


@api.post("/scenarios/run")
async def run_scenario_ep(request: Request, body: ScenarioRunRequest):
    catalog = load_catalog()
    executor = _obo_sql_executor(request)  # raises 401 if no OBO token
    sp = _configured_sp()
    sp_client = get_sp_client()
    wid = get_settings().warehouse_id

    def apply_fn(action_id, securable):
        d = catalog[action_id]
        validate_securable(d, securable)
        apply_to_sp(
            d.grant_sql, principal=sp, configured_sp=sp,
            executor=executor, securable=securable,
        )
        _log_event(request, event_type="apply", action_id=action_id, securable=securable)

    def probe_fn(action_id, securable):
        d = catalog[action_id]
        outcome = run_probe(d, securable=securable, sp_client=sp_client, warehouse_id=wid)
        _log_event(
            request, event_type="probe", action_id=action_id, securable=securable,
            verdict=outcome.status, raw_message=outcome.raw_error,
        )
        return {"status": outcome.status, "detail": outcome.detail}

    def revoke_fn(action_id, securable):
        d = catalog[action_id]
        revoke_from_sp(
            d.revoke_sql, principal=sp, configured_sp=sp,
            executor=executor, securable=securable,
        )
        _log_event(request, event_type="revoke", action_id=action_id, securable=securable)

    return scen_mod.run_scenario(
        [i.model_dump() for i in body.items],
        apply_fn=apply_fn, probe_fn=probe_fn, revoke_fn=revoke_fn,
    )


# module-level indirection so tests can monkeypatch the model call
_agent_call_model = uaig_mod.call_model

_AGENT_SYSTEM_PROMPT = (
    "You are the Permission Test Harness assistant. Help the user understand "
    "Unity Catalog permissions and drive the harness. You can run tests on the "
    "app service principal and read history. You can NEVER grant access to a "
    "real user or group; when a test passes, use get_promotion_directions to "
    "give the user steps to promote it in Unity Catalog. Be concise."
)


@api.post("/agent/chat")
async def agent_chat(request: Request, body: AgentChatRequest):
    token = get_obo_token(request)  # 401 if missing
    catalog = load_catalog()
    sp = _configured_sp()
    wid = get_settings().warehouse_id
    # OBO executor and SP client are built lazily: constructing them needs live
    # host/SP creds, which are absent in unit tests where no grant/probe tool
    # actually fires (e.g. the model answers without a tool call).
    _boxes: dict = {}

    def executor(sql):
        if "exec" not in _boxes:
            _boxes["exec"] = _obo_sql_executor(request)
        return _boxes["exec"](sql)

    def sp_client():
        if "c" not in _boxes:
            _boxes["c"] = get_sp_client()
        return _boxes["c"]

    def _single_test(args):
        d = catalog[args["action_id"]]
        validate_securable(d, args["securable"])
        apply_to_sp(
            d.grant_sql, principal=sp, configured_sp=sp,
            executor=executor, securable=args["securable"],
        )
        _log_event(request, event_type="apply", action_id=args["action_id"], securable=args["securable"])
        try:
            outcome = run_probe(d, securable=args["securable"], sp_client=sp_client(), warehouse_id=wid)
            _log_event(
                request, event_type="probe", action_id=args["action_id"], securable=args["securable"],
                verdict=outcome.status, raw_message=outcome.raw_error,
            )
            return {"status": outcome.status, "detail": outcome.detail, "raw_error": outcome.raw_error}
        finally:
            revoke_from_sp(
                d.revoke_sql, principal=sp, configured_sp=sp,
                executor=executor, securable=args["securable"],
            )
            _log_event(request, event_type="revoke", action_id=args["action_id"], securable=args["securable"])

    def _run_scenario(args):
        return scen_mod.run_scenario(
            args["items"],
            apply_fn=lambda ai, se: apply_to_sp(
                catalog[ai].grant_sql, principal=sp, configured_sp=sp, executor=executor, securable=se),
            probe_fn=lambda ai, se: {
                "status": run_probe(catalog[ai], securable=se, sp_client=sp_client(), warehouse_id=wid).status},
            revoke_fn=lambda ai, se: revoke_from_sp(
                catalog[ai].revoke_sql, principal=sp, configured_sp=sp, executor=executor, securable=se),
        )

    handlers = {
        "read_activity": lambda a: {"events": _safe_read_activity(a)},
        "read_catalog": lambda a: {"actions": [d.model_dump() for d in catalog.values()]},
        "check_effective_permissions": lambda a: {
            "note": "Use run_single_test for a live pass/fail check of the SP's access."},
        "run_single_test": _single_test,
        "list_scenarios": lambda a: {"scenarios": scen_mod.load_seed_scenarios()},
        "save_scenario": lambda a: {
            "note": "Saving custom scenarios is done from the Scenarios tab in this build."},
        "run_scenario": _run_scenario,
        "get_promotion_directions": lambda a: build_promote_info(
            action_id=a["action_id"], securable=a["securable"],
            principal=a.get("principal", "<user-or-group>"),
            host=get_settings().workspace_host, catalog=catalog,
        ).model_dump(),
    }

    def _dispatch(name, args):
        return agent_mod.dispatch(name, args, handlers=handlers)

    # Resolve the model call at request time so tests can monkeypatch it.
    import sys

    def call_model(msgs, tools):
        fn = getattr(sys.modules[__name__], "_agent_call_model")
        return fn(msgs, tools, token=token)

    return agent_mod.run_chat(
        messages=[{"role": "system", "content": _AGENT_SYSTEM_PROMPT}] + body.messages,
        tools=agent_mod.tool_schema(),
        call_model=call_model,
        dispatch=_dispatch,
    )


def _safe_read_activity(a):
    try:
        return activity_mod.read_events(
            conn_factory=_conn_factory, schema=get_settings().db_schema,
            verdict=a.get("verdict"), securable=a.get("securable"),
            limit=int(a.get("limit", 20)),
        )
    except Exception:  # noqa: BLE001
        return []


def _obo_row_exec(request: Request):
    """Return an exec(sql)->list[dict] that runs under the OBO admin client.

    Used for read-only metadata lookups (masking annotations, sweep target
    enumeration) that the logged-in admin is entitled to perform.
    """
    client = get_obo_client(request)  # raises 401 if OBO token missing
    warehouse_id = get_settings().warehouse_id

    def _exec(sql: str):
        resp = client.statement_execution.execute_statement(
            statement=sql, warehouse_id=warehouse_id, wait_timeout="30s"
        )
        result = getattr(resp, "result", None)
        data = getattr(result, "data_array", None) if result else None
        manifest = getattr(resp, "manifest", None)
        schema = getattr(manifest, "schema", None)
        cols = [getattr(c, "name", "") for c in (getattr(schema, "columns", None) or [])]
        rows = []
        for row in data or []:
            rows.append(dict(zip(cols, row)) if cols else {"col": row})
        return rows

    return _exec


@api.post("/query")
async def query(request: Request, body: QueryRequest):
    """Run a read-only query AS THE APP SP and return rows + mask annotations.

    Free-text SQL is read-only enforced (400 on violation) BEFORE any client is
    built, so a blocked statement never reaches the SP. The guided path builds
    its own SELECT from a table name and never accepts user SQL.
    """
    if body.sql:
        try:
            assert_read_only(body.sql)
        except ReadOnlyViolation as exc:
            raise HTTPException(400, str(exc))
        sql = body.sql
        table = body.table
    elif body.table:
        try:
            sql = build_select(body.table, body.limit)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        table = body.table
    else:
        raise HTTPException(400, "Provide either 'sql' (read-only) or 'table'.")

    # OBO required (for identity/parity + the masking metadata read); check the
    # token BEFORE building any client so a missing token -> 401, not 500.
    get_obo_token(request)
    sp_client = get_sp_client()
    result = run_query_as_sp(
        sql, sp_client=sp_client, warehouse_id=get_settings().warehouse_id, limit=body.limit
    )

    # Mask annotations for single-table queries only (guided path, or a
    # free-text query the caller tagged with a table). Best-effort; never fatal.
    governance = {"masked_columns": [], "row_filter": False, "detail": ""}
    if table:
        try:
            governance = describe_governance(_obo_row_exec(request), table)
        except Exception:  # noqa: BLE001
            pass

    _log_event(
        request, event_type="query",
        action_id="uc.query.run", securable=table or "(free-text)",
        verdict="pass" if not result.get("error") else "fail_denied",
        raw_message=result.get("error") or "",
    )
    return {**result, "governance": governance}


@api.post("/sweep")
async def sweep(request: Request, body: SweepRequest):
    """Adversarial read-only reach sweep: enumerate adjacent objects (OBO),
    attempt harmless reads as the SP, return a boundary matrix."""
    obo_exec = _obo_row_exec(request)  # raises 401 if OBO token missing
    sp_client = get_sp_client()
    targets = build_targets(obo_exec, body.securable)
    result = run_sweep(
        targets, sp_client=sp_client, warehouse_id=get_settings().warehouse_id
    )
    _log_event(
        request, event_type="sweep",
        action_id="uc.sweep.reach", securable=body.securable,
        verdict="pass" if result["verdict"]["holes"] == 0 else "fail_denied",
        raw_message=result["verdict"]["status"],
    )
    return result


@api.post("/reset-sp")
async def reset_sp(request: Request):
    """Best-effort: revoke all grants this app applied to the SP this session."""
    catalog = load_catalog()
    executor = _obo_sql_executor(request)  # raises 401 if OBO token missing
    sp = _configured_sp()
    revoked, errors = [], []
    for applied in list(_APPLIED):
        d = catalog.get(applied["action_id"])
        if not d or not d.revoke_sql:
            continue
        try:
            revoke_from_sp(
                d.revoke_sql,
                principal=sp,
                configured_sp=sp,
                executor=executor,
                securable=applied["securable"],
            )
            revoked.append(applied)
        except Exception as exc:  # noqa: BLE001
            errors.append({"applied": applied, "error": str(exc)})
    _APPLIED[:] = [a for a in _APPLIED if a not in revoked]
    return {"revoked": revoked, "errors": errors}


# Serve the built React app at / (Vite outputs to client/dist).
# Mounted LAST so /api takes precedence. Guarded so the app still boots for
# backend tests before the client is built.
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
