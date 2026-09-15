"""Resolves the two separate Databricks identities the app uses.

There are exactly two identities, and they must never be mixed:

1. OBO (on-behalf-of) client -- acts AS THE LOGGED-IN ADMIN, built from the
   ``x-forwarded-access-token`` request header. Used ONLY for grant/revoke and
   reads that require the admin's authority.

2. SP client -- acts AS THE APP'S SERVICE PRINCIPAL, built from the runtime-
   injected ``DATABRICKS_CLIENT_ID`` / ``DATABRICKS_CLIENT_SECRET`` env vars.
   Used ONLY to attempt the action being tested. NEVER use this client for
   grant/revoke.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from databricks.sdk import WorkspaceClient
from fastapi import HTTPException, Request

OBO_HEADER = "x-forwarded-access-token"


def get_obo_token(request: Request) -> str:
    """Return the on-behalf-of user token from the incoming request header.

    Raises HTTPException(401) if the header is missing or empty (which usually
    means user authorization is not enabled for this app).
    """
    token = request.headers.get(OBO_HEADER)
    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing OBO user token (x-forwarded-access-token). "
                "User authorization may not be enabled for this app."
            ),
        )
    return token


def get_obo_client(request: Request) -> WorkspaceClient:
    """Return a WorkspaceClient acting as the logged-in admin (OBO).

    Used ONLY for grant/revoke and admin-authority reads.
    """
    token = get_obo_token(request)
    host = os.environ.get("DATABRICKS_HOST")
    # auth_type="pat" is REQUIRED here: the Apps runtime injects
    # DATABRICKS_CLIENT_ID/SECRET (OAuth) into the env, so without pinning the
    # auth type the SDK sees both the ambient OAuth creds AND our forwarded
    # token and refuses with "more than one authorization method configured:
    # oauth and pat". Pinning to pat makes it use ONLY the forwarded token
    # (sent as a bearer header), which is the admin's OBO identity.
    return WorkspaceClient(host=host, token=token, auth_type="pat")


def get_sp_client() -> WorkspaceClient:
    """Return a WorkspaceClient acting as the app's service principal.

    Picks up DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET from the runtime.
    Used ONLY to attempt the action under test. NEVER use for grant/revoke.
    """
    return WorkspaceClient()


def get_obo_identity(request: Request) -> Dict[str, Any]:
    """Return the logged-in admin's identity (backs GET /api/me)."""
    me = get_obo_client(request).current_user.me()
    return {
        "user_name": me.user_name,
        "display_name": getattr(me, "display_name", None),
        "active": getattr(me, "active", None),
    }


def get_sp_identity() -> Dict[str, Any]:
    """Return the app SP's identity (which principal the probe runs as)."""
    me = get_sp_client().current_user.me()
    return {
        "user_name": me.user_name,
        "display_name": getattr(me, "display_name", None),
        "id": getattr(me, "id", None),
    }
