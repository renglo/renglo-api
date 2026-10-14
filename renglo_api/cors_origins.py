"""Browser origins for Flask-CORS.

CORS_ALLOWED_ORIGINS is a JSON list written by the backend deploy from
the BOM file cors/allowed.yml. A "*" entry allows every origin.
"""

from __future__ import annotations

import json
from typing import Any

DEV_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)


def parse_cors_allowed_origins(raw: Any) -> list[str]:
    """Return concrete origins, or ['*'] when every origin is allowed."""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        if text == "*":
            return ["*"]
        if text[0] in "[{":
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("CORS_ALLOWED_ORIGINS must be a JSON list")
            items = parsed
        else:
            items = [part.strip() for part in text.split(",") if part.strip()]

    origins: list[str] = []
    for item in items:
        origin = str(item).strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            return ["*"]
        if origin not in origins:
            origins.append(origin)
    return origins


def build_cors_origins(config: dict, *, include_dev: bool) -> str | list[str]:
    """Origins for Flask-CORS. '*' allows every browser origin."""
    extras = parse_cors_allowed_origins(config.get("CORS_ALLOWED_ORIGINS"))
    if "*" in extras:
        return "*"

    origins: list[str] = []

    def add(value: Any) -> None:
        origin = str(value or "").strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)

    add(config.get("FE_BASE_URL"))
    add(config.get("APP_FE_BASE_URL"))
    for origin in extras:
        add(origin)
    if include_dev:
        for origin in DEV_ORIGINS:
            add(origin)
    return origins
