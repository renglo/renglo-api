"""Public authentication provider list from AUTH_PROVIDERS.

The value is the projection written to platform-vars. Secret fields are dropped
even if a deployment puts them in that JSON by mistake.
"""

from __future__ import annotations

import json
from typing import Any

_PUBLIC_FIELDS = (
    "id",
    "name",
    "type",
    "cognito_provider_name",
    "display_name",
    "icon",
    "display_order",
)


def public_auth_providers(raw: Any) -> list[dict[str, Any]]:
    """Return enabled providers with public fields only."""
    entries = _entries(raw)
    published: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue
        public = {key: item[key] for key in _PUBLIC_FIELDS if key in item}
        public["enabled"] = True
        if "id" not in public:
            continue
        published.append(public)
    published.sort(key=lambda item: (item.get("display_order") or 0, str(item.get("id"))))
    return published


def _entries(raw: Any) -> list:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        raw = raw.get("providers") or []
    if not isinstance(raw, list):
        return []
    return raw
