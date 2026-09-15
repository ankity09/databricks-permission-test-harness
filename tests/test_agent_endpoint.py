import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _configured_sp_env(monkeypatch):
    # The deployed app always has the SP client id injected; provide one so the
    # chat endpoint's _configured_sp() guard doesn't 500 in unit tests.
    monkeypatch.setattr(main, "_configured_sp", lambda: "test-sp-client-id")


def test_agent_chat_requires_obo():
    r = client.post(
        "/api/agent/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert r.status_code == 401


def test_agent_chat_runs_with_stubbed_model(monkeypatch):
    # Stub the model so no real UAIG call happens; assert the loop returns content.
    def fake_call_model(messages, tools, token=None):
        return {"content": "The catalog has actions."}

    monkeypatch.setattr(main, "_agent_call_model", fake_call_model)
    r = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "what can I test?"}]},
        headers={"x-forwarded-access-token": "fake"},
    )
    assert r.status_code == 200
    assert "catalog" in r.json()["content"].lower()


def test_agent_chat_tool_roundtrip_read_catalog(monkeypatch):
    # Model asks for read_catalog once, then answers. Assert the handler ran.
    script = [
        {"tool_calls": [{"id": "1", "name": "read_catalog", "arguments": {}}]},
        {"content": "done"},
    ]
    steps = iter(script)

    def fake_call_model(messages, tools, token=None):
        return next(steps)

    monkeypatch.setattr(main, "_agent_call_model", fake_call_model)
    r = client.post(
        "/api/agent/chat",
        json={"messages": [{"role": "user", "content": "list"}]},
        headers={"x-forwarded-access-token": "fake"},
    )
    assert r.status_code == 200
    assert r.json()["content"] == "done"
