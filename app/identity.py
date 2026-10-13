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

import hashlib
import os
import time
from typing import Any, Dict

from databricks.sdk import WorkspaceClient
from fastapi import Depends, HTTPException, Request

OBO_HEADER = "x-forwarded-access-token"

# Cache for caller identity + group membership checks (keyed by token hash).
# Entries: {token_hash: (identity_dict, groups, timestamp)}
_IDENTITY_CACHE: Dict[str, tuple[Dict, list, float]] = {}
_CACHE_TTL_SECONDS = 60


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


def _get_caller_groups(request: Request) -> list[str]:
    """Get the groups for the OBO caller (by display_name, case-insensitive).

    Returns an empty list if groups cannot be fetched.
    """
    try:
        client = get_obo_client(request)
        me = client.current_user.me()
        user_id = getattr(me, "id", None)
        if not user_id:
            return []

        user = client.users.get(user_id)
        groups_obj = getattr(user, "groups", None)
        if not groups_obj:
            return []

        group_names = []
        for group in groups_obj:
            display_name = getattr(group, "display", None)
            if display_name:
                group_names.append(display_name.lower())  # Normalize to lowercase for comparison
        return group_names
    except Exception:  # noqa: BLE001
        return []


def require_tester(request: Request) -> Dict[str, Any]:
    """FastAPI dependency: verify OBO token and (if configured) group membership.

    Returns the caller's identity dict.
    Raises HTTPException(401) if OBO token is missing.

    In test environments (no workspace configured), returns a minimal identity
    after verifying the token header exists.
    Raises HTTPException(403) if caller is not in the required group.
    """
    from app.config import get_settings

    # Verify token is present (raises 401 if missing).
    token = get_obo_token(request)

    # Try to get full identity from workspace; if workspace is not configured,
    # use a minimal test identity.
    settings = get_settings()
    if settings.workspace_host:
        # Real workspace: fetch full identity
        identity = get_obo_identity(request)
    else:
        # Test environment: accept the token and use minimal identity
        identity = {"user_name": "test-user", "display_name": "Test User"}

    if not settings.allowed_group:
        # No group restriction.
        return identity

    # Check group membership (with caching).
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()

    # Check cache.
    if token_hash in _IDENTITY_CACHE:
        cached_identity, cached_groups, cached_time = _IDENTITY_CACHE[token_hash]
        if now - cached_time < _CACHE_TTL_SECONDS:
            # Cache is fresh.
            group_lower = settings.allowed_group.lower()
            if group_lower not in cached_groups:
                raise HTTPException(
                    status_code=403,
                    detail=f"Not authorized: this harness is restricted to members of '{settings.allowed_group}'.",
                )
            return cached_identity

    # Fetch groups (cache miss or expired).
    groups = _get_caller_groups(request)
    _IDENTITY_CACHE[token_hash] = (identity, groups, now)

    group_lower = settings.allowed_group.lower()
    if group_lower not in groups:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized: this harness is restricted to members of '{settings.allowed_group}'.",
        )

    return identity
