from app.probe import map_result


def test_permission_denied_maps_to_fail_denied():
    r = map_result(exc_type="PERMISSION_DENIED", raw="User does not have SELECT", negative=False)
    assert r.status == "fail_denied"
    assert r.raw_error == "User does not have SELECT"


def test_permission_denied_under_negative_test_is_pass():
    r = map_result(exc_type="PERMISSION_DENIED", raw="denied", negative=True)
    assert r.status == "pass"


def test_grant_authority_failure_is_distinct_state():
    r = map_result(exc_type="GRANT_AUTHORITY", raw="you can't grant", negative=False)
    assert r.status == "grant_failed"


def test_rows_returned_is_pass():
    r = map_result(exc_type=None, raw=None, negative=False, rows=[{"x": 1}])
    assert r.status == "pass"


def test_permission_check_allowed_is_pass():
    r = map_result(exc_type=None, raw="levels: [CAN_USE]", negative=False, allowed=True)
    assert r.status == "pass"


def test_permission_check_not_allowed_is_fail_denied():
    r = map_result(exc_type=None, raw="levels: none", negative=False, allowed=False)
    assert r.status == "fail_denied"


def test_negative_test_but_action_succeeds_is_fail():
    # Expected a denial, but rows came back -> negative test did NOT pass.
    r = map_result(exc_type=None, raw=None, negative=True, rows=[{"x": 1}])
    assert r.status == "fail_denied"


def test_unknown_outcome_is_error():
    r = map_result(exc_type="WeirdError", raw="something odd", negative=False)
    assert r.status == "error"
