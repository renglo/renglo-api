"""Universal EventBridge → Renglo API ingress dispatcher.

Authenticated by RENGLO_INGRESS_SECRET (header X-Renglo-Ingress-Secret).
Legacy per-channel secrets remain accepted during migration.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

# channel → extension/handler (server-side only; clients cannot pick arbitrary paths)
CHANNEL_HANDLERS: dict[str, str] = {
    "whatsapp": "whatsapp/inbound",
    "gmail-poll": "gmail/poll_inbox",
}

INGRESS_HEADER = "X-Renglo-Ingress-Secret"
LEGACY_HEADERS = (
    "X-Whatsapp-Ingress-Secret",
    "X-Gmail-Ingress-Secret",
)


def resolve_ingress_secret(app_cfg: dict | None = None, flask_config: dict | None = None) -> str:
    """Prefer RENGLO_INGRESS_SECRET; fall back to legacy per-channel secrets."""
    app_cfg = app_cfg or {}
    flask_config = flask_config or {}
    for key in (
        "RENGLO_INGRESS_SECRET",
        "WHATSAPP_INGRESS_SECRET",
        "GMAIL_INGRESS_SECRET",
    ):
        value = (
            app_cfg.get(key)
            or flask_config.get(key)
            or os.environ.get(key)
            or ""
        )
        if value:
            return str(value)
    return ""


def presented_ingress_secret(headers) -> str:
    """Read shared or legacy ingress secret from request headers."""
    for name in (INGRESS_HEADER, *LEGACY_HEADERS):
        presented = headers.get(name, "")
        if presented:
            return presented
    # Case-insensitive fallback (some gateways lowercase)
    lower_map = {str(k).lower(): v for k, v in headers.items()}
    for name in (INGRESS_HEADER, *LEGACY_HEADERS):
        presented = lower_map.get(name.lower(), "")
        if presented:
            return presented
    return ""


def check_ingress_secret(
    *,
    expected: str,
    presented: str,
) -> tuple[bool, dict | None, int | None]:
    """Return (ok, error_body, status). When expected is empty, auth is skipped."""
    if not expected:
        return True, None, None
    if presented != expected:
        return False, {"success": False, "message": "Unauthorized"}, 401
    return True, None, None


def normalize_detail(event_data: dict | None) -> dict | None:
    """Unwrap EventBridge envelope; parse stringified detail when needed."""
    if not event_data:
        return None
    detail = event_data.get("detail", event_data)
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except Exception:
            return None
    if not isinstance(detail, dict):
        return None
    return detail


def _headers_from_detail(detail: dict) -> dict[str, str]:
    raw = detail.get("headers") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in raw.items() if v is not None}


def webhook_payload_for_channel(channel: str, detail: dict) -> dict[str, Any]:
    """Build the extension handler payload from a uniform webhook envelope."""
    portfolio = detail.get("portfolio")
    org = detail.get("org") or "_all"
    raw_body = detail.get("raw_body")
    headers = _headers_from_detail(detail)

    if channel == "whatsapp":
        signature = (
            detail.get("signature_header")
            or headers.get("x-hub-signature-256")
            or headers.get("x-hub-signature")
            or ""
        )
        return {
            "portfolio": portfolio,
            "org": org,
            "raw_body": raw_body,
            "signature_header": signature,
        }

    if channel == "gmail-poll":
        return {"portfolio": portfolio, "org": org}

    # Generic pass-through for future channels registered in CHANNEL_HANDLERS
    return {
        "portfolio": portfolio,
        "org": org,
        "raw_body": raw_body,
        "headers": headers,
        "query": detail.get("query") or {},
    }


def dispatch_ingress(
    detail: dict,
    *,
    load_and_run: Callable[..., dict],
    create_job_run: Callable[..., tuple],
) -> tuple[dict, int]:
    """
    Dispatch a normalized ingress detail.

    Returns (response_dict, http_status).
    """
    event_type = detail.get("type")
    if not event_type:
        # Infer for legacy WhatsApp/Gmail process routes
        if detail.get("raw_body") is not None or detail.get("channel") == "whatsapp":
            event_type = "webhook"
            detail = {**detail, "channel": detail.get("channel") or "whatsapp"}
        elif detail.get("schd_jobs_id") or detail.get("trigger") == "cron":
            event_type = "schd_job"
        elif detail.get("portfolio") and not detail.get("raw_body"):
            # legacy process-gmail-poll shape
            event_type = "webhook"
            detail = {**detail, "channel": detail.get("channel") or "gmail-poll"}
        else:
            return {"success": False, "message": "type required"}, 400

    if event_type == "webhook":
        channel = str(detail.get("channel") or "").strip()
        if not channel:
            return {"success": False, "message": "channel required"}, 400
        handler = CHANNEL_HANDLERS.get(channel)
        if not handler:
            return {"success": False, "message": f"unknown channel: {channel}"}, 400

        portfolio = detail.get("portfolio")
        raw_body = detail.get("raw_body")
        # gmail-poll has no raw_body
        if not portfolio:
            return {"success": False, "message": "portfolio required"}, 400
        if channel != "gmail-poll" and raw_body is None:
            return {"success": False, "message": "portfolio and raw_body required"}, 400

        payload = webhook_payload_for_channel(channel, detail)
        response = load_and_run(handler, payload=payload)
        status = 200 if response.get("success") else 400
        return response, status

    if event_type == "schd_job":
        portfolio = detail.get("portfolio")
        org = detail.get("org")
        if not portfolio or not org:
            return {"success": False, "message": "portfolio and org required"}, 400
        if not detail.get("schd_jobs_id"):
            return {"success": False, "message": "schd_jobs_id required"}, 400
        response, status = create_job_run(portfolio, org, detail)
        return response, status

    return {"success": False, "message": f"unknown type: {event_type}"}, 400
