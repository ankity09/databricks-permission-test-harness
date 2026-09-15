"""The load-bearing safety test. NEVER weaken these assertions.

If any refactor makes it possible to write a grant to a non-SP principal,
that is a spec violation.
"""

import pytest

from app.grant import ForbiddenPrincipalError, apply_to_sp, revoke_from_sp

CONFIGURED_SP = "app-sp-1234"


class FakeExec:
    def __init__(self):
        self.ran = []

    def __call__(self, sql):
        self.ran.append(sql)
        return {"ok": True}


def test_apply_to_sp_allows_configured_sp():
    ex = FakeExec()
    apply_to_sp(
        "GRANT SELECT ON TABLE t TO `{sp}`",
        principal=CONFIGURED_SP,
        configured_sp=CONFIGURED_SP,
        executor=ex,
    )
    assert "app-sp-1234" in ex.ran[0]


def test_apply_to_sp_rejects_any_other_principal():
    ex = FakeExec()
    with pytest.raises(ForbiddenPrincipalError):
        apply_to_sp(
            "GRANT SELECT ON TABLE t TO `{sp}`",
            principal="real.user@corp.com",
            configured_sp=CONFIGURED_SP,
            executor=ex,
        )
    assert ex.ran == []  # nothing executed


def test_apply_to_sp_rejects_group_principal():
    ex = FakeExec()
    with pytest.raises(ForbiddenPrincipalError):
        apply_to_sp(
            "GRANT SELECT ON TABLE t TO `{sp}`",
            principal="group-admins",
            configured_sp=CONFIGURED_SP,
            executor=ex,
        )
    assert ex.ran == []


def test_revoke_from_sp_allows_configured_sp():
    ex = FakeExec()
    revoke_from_sp(
        "REVOKE SELECT ON TABLE t FROM `{sp}`",
        principal=CONFIGURED_SP,
        configured_sp=CONFIGURED_SP,
        executor=ex,
    )
    assert "app-sp-1234" in ex.ran[0]


def test_revoke_from_sp_rejects_other_principal():
    ex = FakeExec()
    with pytest.raises(ForbiddenPrincipalError):
        revoke_from_sp(
            "REVOKE SELECT ON TABLE t FROM `{sp}`",
            principal="group-admins",
            configured_sp=CONFIGURED_SP,
            executor=ex,
        )
    assert ex.ran == []
