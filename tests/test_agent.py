import pytest

import app.agent as agent


def test_registry_has_no_grant_to_real_principal_tool():
    names = set(agent.TOOL_NAMES)
    # These are the ONLY allowed tools. A grant-to-real-principal tool must NEVER exist.
    assert names == {
        "read_activity",
        "read_catalog",
        "check_effective_permissions",
        "run_single_test",
        "list_scenarios",
        "save_scenario",
        "run_scenario",
        "get_promotion_directions",
        "run_query_as_sp",
        "run_reach_sweep",
    }
    for n in names:
        # the only "promote"-ish tool is the non-mutating directions tool
        assert "promote" not in n or n == "get_promotion_directions"
        assert "grant_user" not in n and "grant_to" not in n and "grant_principal" not in n


def test_dispatch_rejects_unknown_tool():
    with pytest.raises(agent.UnknownToolError):
        agent.dispatch("delete_everything", {}, handlers={})


def test_dispatch_rejects_known_tool_with_no_handler():
    with pytest.raises(agent.UnknownToolError):
        agent.dispatch("read_catalog", {}, handlers={})


def test_dispatch_routes_to_handler():
    called = {}

    def h(args):
        called.update(args)
        return {"ok": True}

    out = agent.dispatch("read_catalog", {"x": 1}, handlers={"read_catalog": h})
    assert out == {"ok": True}
    assert called == {"x": 1}


def test_tool_schema_covers_all_tool_names():
    schema_names = {t["function"]["name"] for t in agent.tool_schema()}
    assert schema_names == set(agent.TOOL_NAMES)


def test_run_chat_executes_tool_then_returns_final():
    # Model asks for one tool call, then returns a final answer.
    script = [
        {"tool_calls": [{"id": "1", "name": "read_catalog", "arguments": {}}]},
        {"content": "Here are the actions."},
    ]
    steps = iter(script)

    def call_model(messages, tools):
        return next(steps)

    def dispatch_fn(name, args):
        assert name == "read_catalog"
        return {"actions": ["uc.table.select"]}

    final = agent.run_chat(
        messages=[{"role": "user", "content": "list actions"}],
        tools=agent.tool_schema(),
        call_model=call_model,
        dispatch=dispatch_fn,
    )
    assert final["content"] == "Here are the actions."


def test_run_chat_stops_at_iteration_cap():
    # Model never stops asking for tools -> loop must terminate.
    def call_model(messages, tools):
        return {"tool_calls": [{"id": "1", "name": "read_catalog", "arguments": {}}]}

    def dispatch_fn(name, args):
        return {"ok": True}

    final = agent.run_chat(
        messages=[{"role": "user", "content": "loop"}],
        tools=agent.tool_schema(),
        call_model=call_model,
        dispatch=dispatch_fn,
        max_iterations=3,
    )
    assert "limit" in final["content"].lower()
