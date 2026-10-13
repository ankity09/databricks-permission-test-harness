"""Real UAIG model call (governed).

Calls a 3-part model-service name through the /ai-gateway path so BOTH usage
tracking AND guardrails apply (calling a raw system.ai.<model> id would get
usage but NO custom guardrails). The token is the OBO admin token so usage
attributes to the logged-in admin. Injectable so the endpoint/tests can stub it.
"""

from __future__ import annotations

import json
from typing import Optional

from app.config import get_settings


def call_model(messages: list[dict], tools: list[dict], token: Optional[str] = None) -> dict:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(api_key=token or "", base_url=s.uaig_base_url)
    resp = client.chat.completions.create(
        model=s.uaig_model_service,  # 3-part model-service name (guardrails attached)
        messages=messages,
        tools=tools or None,
    )
    choice = resp.choices[0].message
    tool_calls = []
    for tc in getattr(choice, "tool_calls", None) or []:
        tool_calls.append(
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments or "{}"),
            }
        )
    return {"content": choice.content or "", "tool_calls": tool_calls or None}
