from app.models import ProbeResult, ApplyRequest
from app.config import get_settings

def test_probe_result_pass():
    result = ProbeResult(status="pass")
    assert result.detail == ""
    assert result.rows is None


def test_probe_result_invalid_status():
    try:
        ProbeResult(status="bogus")
        assert False, "Should raise ValidationError"
    except:
        pass

def test_apply_request_defaults():
    req = ApplyRequest(action_id="x", securable="a.b.c")
    assert req.level is None

def test_get_settings_returns_object_with_attrs():
    settings = get_settings()
    assert hasattr(settings, "workspace_host")
    assert hasattr(settings, "sp_application_id")
    assert hasattr(settings, "warehouse_id")