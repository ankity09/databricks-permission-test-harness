"""Optional settings: "none" means unset (bundle deploys cannot pass empty values)."""

import importlib

import app.config as config


def test_none_and_empty_mean_unset(monkeypatch):
    monkeypatch.setenv("HARNESS_ALLOWED_GROUP", "none")
    monkeypatch.setenv("UAIG_BASE_URL", " None ")
    monkeypatch.delenv("UAIG_MODEL_SERVICE", raising=False)
    settings = importlib.reload(config)._load()
    assert settings.allowed_group == ""
    assert settings.uaig_base_url == ""
    assert settings.uaig_model_service == ""


def test_real_values_pass_through(monkeypatch):
    monkeypatch.setenv("HARNESS_ALLOWED_GROUP", "perm-testers")
    monkeypatch.setenv("UAIG_MODEL_SERVICE", "main.perm_harness.harness_agent")
    settings = importlib.reload(config)._load()
    assert settings.allowed_group == "perm-testers"
    assert settings.uaig_model_service == "main.perm_harness.harness_agent"
