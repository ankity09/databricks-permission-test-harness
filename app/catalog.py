"""Action-catalog loader + template resolver.

The catalog is DATA (``actions.yaml``), not code. This module parses and
validates it into ``ActionDescriptor`` objects and provides safe template
substitution for ``{securable}`` / ``{sp}`` (and derived) placeholders.
"""

from __future__ import annotations

import os
from typing import Dict

import yaml

from app.models import ActionDescriptor

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "actions.yaml")

# Fields every descriptor must have, and required sub-fields per probe kind.
_REQUIRED_TOP = {"id", "tab", "label", "grant_sql", "revoke_sql", "probe"}
_VALID_TABS = {"uc-data", "workspace"}
_VALID_PROBE_KINDS = {"sql", "permission-check"}


class DescriptorError(ValueError):
    """Raised when a catalog descriptor is missing/invalid fields."""


class SecurableLevelError(ValueError):
    """Raised when a securable name is at the wrong level for the action.

    e.g. USE CATALOG (a catalog-level grant) given ``catalog.schema.table``.
    This is an INPUT error, distinct from a grant-authority failure — catching
    it up front prevents firing malformed SQL that would surface a confusing
    PARSE_SYNTAX_ERROR mislabeled as "your account can't issue the grant".
    """


# Map the securable keyword in a grant template to the expected dotted-name
# part count. Catalog=1, schema=2, everything table-like=3.
_LEVEL_PARTS = {
    "CATALOG": (1, "catalog"),
    "SCHEMA": (2, "catalog.schema"),
    "TABLE": (3, "catalog.schema.table"),
    "VOLUME": (3, "catalog.schema.volume"),
    "FUNCTION": (3, "catalog.schema.function"),
    "MODEL": (3, "catalog.schema.model"),
}


def _expected_level(grant_sql: str) -> tuple[int, str] | None:
    """Infer the required (part_count, shape) from a grant template's ``ON <kind>``.

    Returns None when the template declares no securable kind (workspace-object
    actions have empty grant SQL, so their opaque ids/paths aren't validated).
    """
    tokens = grant_sql.upper().split()
    if "ON" not in tokens:
        return None
    kind = tokens[tokens.index("ON") + 1] if tokens.index("ON") + 1 < len(tokens) else ""
    return _LEVEL_PARTS.get(kind)


def validate_securable(descriptor: "ActionDescriptor", securable: str) -> None:
    """Validate that ``securable`` is named at the level the action requires.

    Raises SecurableLevelError with an actionable message on mismatch. No-ops
    for actions that declare no securable level (workspace-object ACLs).
    """
    expected = _expected_level(descriptor.grant_sql)
    if expected is None:
        return
    want_parts, shape = expected
    got_parts = len([p for p in securable.split(".") if p])
    if got_parts != want_parts:
        raise SecurableLevelError(
            f"'{descriptor.label}' expects a {shape} name "
            f"({want_parts}-part), but got '{securable}' ({got_parts}-part). "
            f"Provide a {shape}-level name for this action."
        )


def _validate(raw: dict) -> ActionDescriptor:
    missing = _REQUIRED_TOP - set(raw)
    if missing:
        raise DescriptorError(
            f"descriptor {raw.get('id', '<no-id>')} missing fields: {sorted(missing)}"
        )
    if raw["tab"] not in _VALID_TABS:
        raise DescriptorError(f"descriptor {raw['id']} has invalid tab: {raw['tab']!r}")

    probe = raw.get("probe")
    if not isinstance(probe, dict) or "kind" not in probe:
        raise DescriptorError(f"descriptor {raw['id']} has malformed probe")
    kind = probe["kind"]
    if kind not in _VALID_PROBE_KINDS:
        raise DescriptorError(f"descriptor {raw['id']} has invalid probe kind: {kind!r}")
    if kind == "sql" and not probe.get("statement"):
        raise DescriptorError(f"descriptor {raw['id']} sql probe missing statement")
    if kind == "permission-check" and not (probe.get("api") and probe.get("level")):
        raise DescriptorError(
            f"descriptor {raw['id']} permission-check probe missing api/level"
        )

    try:
        return ActionDescriptor(**raw)
    except Exception as exc:  # pydantic ValidationError, etc.
        raise DescriptorError(f"descriptor {raw.get('id')} invalid: {exc}") from exc


def load_catalog(path: str | None = None) -> Dict[str, ActionDescriptor]:
    """Load, validate, and index the action catalog by descriptor id.

    Raises DescriptorError on any malformed descriptor.
    """
    path = path or _DEFAULT_PATH
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    items = data.get("actions")
    if not isinstance(items, list) or not items:
        raise DescriptorError(f"catalog {path} has no 'actions' list")

    catalog: Dict[str, ActionDescriptor] = {}
    for raw in items:
        if not isinstance(raw, dict):
            raise DescriptorError(f"catalog {path} has a non-mapping action entry")
        descriptor = _validate(raw)
        if descriptor.id in catalog:
            raise DescriptorError(f"duplicate descriptor id: {descriptor.id}")
        catalog[descriptor.id] = descriptor
    return catalog


def resolve(template: str, **kwargs: str) -> str:
    """Safely substitute ``{securable}`` / ``{sp}`` (and derived) placeholders.

    A ``securable`` kwarg automatically derives ``securable_path`` (dots ->
    slashes) for volume-style probes. Missing placeholders raise KeyError so a
    bad template fails loudly rather than silently emitting ``{sp}``.
    """
    values = dict(kwargs)
    if "securable" in values and "securable_path" not in values:
        values["securable_path"] = values["securable"].replace(".", "/")
    return template.format(**values)
