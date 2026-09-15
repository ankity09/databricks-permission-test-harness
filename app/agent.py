"""UAIG agent: tool registry + dispatch + tool-calling loop.

SECURITY (spec Feature 3): the agent's ENTIRE power surface is the tool registry
below. There is intentionally NO tool that grants to a real user/group -- that
path does not exist, so no model output or injected prompt can invoke one.
Authority is enforced in code (this registry + the SP-only guard in grant.py);
UAIG guardrails handle text-I/O safety. The system prompt is UX guidance only,
never a security control.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

# The complete, closed set of tool names. Adding a name here is a security
# decision -- a grant-to-real-principal tool must NEVER be added.
TOOL_NAMES = (
    "read_activity",
    "read_catalog",
    "check_effective_permissions",
    "run_single_test",
    "list_scenarios",
    "save_scenario",
    "run_scenario",
    "get_promotion_directions",
)


class UnknownToolError(Exception):
    pass


def tool_schema() -> list[dict]:
    """OpenAI-compatible tools schema advertised to the model."""

    def fn(name, desc, props=None, required=None):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props or {},
                    "required": required or [],
                },
            },
        }

    S = {"type": "string"}
    return [
        fn(
            "read_activity",
            "Read recent harness activity/history.",
            {"verdict": S, "securable": S, "limit": {"type": "integer"}},
        ),
        fn("read_catalog", "List the testable permission actions."),
        fn(
            "check_effective_permissions",
            "Read the SP's effective permission levels for a securable.",
            {"securable": S},
            ["securable"],
        ),
        fn(
            "run_single_test",
            "Apply a candidate grant to the app SP, probe it, then revoke.",
            {"action_id": S, "securable": S},
            ["action_id", "securable"],
        ),
        fn("list_scenarios", "List saved + seed role scenarios."),
        fn(
            "save_scenario",
            "Save a custom role scenario.",
            {"name": S, "description": S, "items": {"type": "array"}},
            ["name", "items"],
        ),
        fn(
            "run_scenario",
            "Batch-run a scenario (apply all, probe each, revoke all) and return a pass/fail matrix.",
            {"items": {"type": "array"}},
            ["items"],
        ),
        fn(
            "get_promotion_directions",
            "Get Unity Catalog steps + deep-link to promote a validated grant to a real user/group.",
            {"action_id": S, "securable": S},
            ["action_id", "securable"],
        ),
    ]


def dispatch(name: str, args: dict, *, handlers: Dict[str, Callable[[dict], Any]]) -> Any:
    if name not in TOOL_NAMES:
        raise UnknownToolError(f"unknown tool: {name}")
    handler = handlers.get(name)
    if handler is None:
        raise UnknownToolError(f"no handler bound for tool: {name}")
    return handler(args)


def run_chat(
    *,
    messages: list[dict],
    tools: list[dict],
    call_model: Callable[[list[dict], list[dict]], dict],
    dispatch: Callable[[str, dict], Any],
    max_iterations: int = 6,
) -> dict:
    """Tool-calling loop. Executes tool calls via `dispatch` until a final
    (content-only) message is returned or max_iterations is reached."""
    convo = list(messages)
    for _ in range(max_iterations):
        step = call_model(convo, tools)
        tool_calls = step.get("tool_calls")
        if not tool_calls:
            return {"content": step.get("content", "")}
        convo.append({"role": "assistant", "tool_calls": tool_calls})
        for tc in tool_calls:
            result = dispatch(tc["name"], tc.get("arguments", {}))
            convo.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": str(result)}
            )
    return {"content": "Reached tool-call limit without a final answer."}
