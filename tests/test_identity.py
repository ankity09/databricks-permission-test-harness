"""Unit tests for app.identity -- no real Databricks calls (all mocked)."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app import identity


def _fake_request(headers: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(headers=headers)


def test_get_obo_token_returns_token_when_present():
    req = _fake_request({"x-forwarded-access-token": "tok123"})
    assert identity.get_obo_token(req) == "tok123"


def test_get_obo_token_raises_401_when_missing():
    req = _fake_request({})
    with pytest.raises(HTTPException) as exc:
        identity.get_obo_token(req)
    assert exc.value.status_code == 401


def test_get_obo_token_raises_401_when_empty():
    req = _fake_request({"x-forwarded-access-token": ""})
    with pytest.raises(HTTPException) as exc:
        identity.get_obo_token(req)
    assert exc.value.status_code == 401


def test_get_obo_client_builds_client_with_token(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    req = _fake_request({"x-forwarded-access-token": "tok123"})
    with patch("app.identity.WorkspaceClient") as mock_wc:
        identity.get_obo_client(req)
    # auth_type="pat" is REQUIRED so the SDK ignores the ambient OAuth env
    # creds the Apps runtime injects (otherwise: "more than one authorization
    # method configured: oauth and pat"). Do not remove.
    mock_wc.assert_called_once_with(
        host="https://example.cloud.databricks.com", token="tok123", auth_type="pat"
    )


def test_get_sp_client_called_with_no_args():
    with patch("app.identity.WorkspaceClient") as mock_wc:
        identity.get_sp_client()
    mock_wc.assert_called_once_with()


def test_get_obo_identity_maps_fields():
    me = types.SimpleNamespace(
        user_name="admin@example.com", display_name="Admin", active=True
    )
    fake_client = MagicMock()
    fake_client.current_user.me.return_value = me
    req = _fake_request({"x-forwarded-access-token": "tok123"})
    with patch("app.identity.get_obo_client", return_value=fake_client):
        result = identity.get_obo_identity(req)
    assert result == {
        "user_name": "admin@example.com",
        "display_name": "Admin",
        "active": True,
    }


def test_get_sp_identity_maps_fields():
    me = types.SimpleNamespace(
        user_name="sp-app", display_name=None, id="sp-123"
    )
    fake_client = MagicMock()
    fake_client.current_user.me.return_value = me
    with patch("app.identity.get_sp_client", return_value=fake_client):
        result = identity.get_sp_identity()
    assert result == {"user_name": "sp-app", "display_name": None, "id": "sp-123"}
