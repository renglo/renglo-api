"""Universal EventBridge → Renglo API ingress dispatcher.

Authenticated by RENGLO_INGRESS_SECRET (header X-Renglo-Ingress-Secret).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

_logger = logging.getLogger(__name__)

# channel → extension/handler (server-side only; clients cannot pick arbitrary paths)
CHANNEL_HANDLERS: dict[str, str] = {
    "whatsapp": "whatsapp/inbound",
    "gmail-poll": "gmail/poll_inbox",
}

# Webhook channels that ACK ingress with 202 when async worker start succeeds.
WEBHOOK_ASYNC_CHANNELS: frozenset[str] = frozenset(CHANNEL_HANDLERS.keys())

INGRESS_HEADER = "X-Renglo-Ingress-Secret"


def resolve_ingress_secret(app_cfg: dict | None = None, flask_config: dict | None = None) -> str:
    app_cfg = app_cfg or {}
    flask_config = flask_config or {}
    value = (
        app_cfg.get("RENGLO_INGRESS_SECRET")
        or flask_config.get("RENGLO_INGRESS_SECRET")
        or os.environ.get("RENGLO_INGRESS_SECRET")
        or ""
    )
    return str(value) if value else ""


def presented_ingress_secret(headers) -> str:
    presented = headers.get(INGRESS_HEADER, "")
    if presented:
        return presented
    lower_map = {str(k).lower(): v for k, v in headers.items()}
    return lower_map.get(INGRESS_HEADER.lower(), "") or ""


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


def _header_lookup(headers: dict | None, *names: str) -> str:
    if not headers:
        return ""
    lower = {str(k).lower(): str(v) for k, v in headers.items() if v is not None}
    for name in names:
        value = lower.get(name.lower())
        if value:
            return value
    return ""


def attach_ingress_trace(
    detail: dict,
    event_data: dict | None = None,
    *,
    http_headers: dict | None = None,
) -> dict:
    """
    Preserve delivery identifiers for duplicate forensics (Meta vs EventBridge vs edge).

    EventBridge API destinations POST the full event JSON; ``id`` is stable across
    retries of the same bus event. A new Meta POST → new edge receipt → new bus ``id``.
    """
    trace = dict(detail.get("_ingress") or {})
    if isinstance(event_data, dict):
        bus_id = event_data.get("id")
        if bus_id:
            trace["eventbridge_event_id"] = str(bus_id)
        bus_time = event_data.get("time")
        if bus_time:
            trace["eventbridge_time"] = str(bus_time)
        bus_source = event_data.get("source")
        if bus_source:
            trace["eventbridge_source"] = str(bus_source)
    for key in ("eventbridge_event_id", "webhook_edge_receipt_id", "webhook_edge_enqueued_at"):
        embedded = detail.get(key)
        if embedded and key not in trace:
            trace[key] = str(embedded)
    req_id = _header_lookup(
        http_headers,
        "x-amzn-requestid",
        "x-amz-request-id",
        "x-amzn-request-id",
    )
    if req_id:
        trace["ingress_http_request_id"] = req_id
    trace_id = _header_lookup(http_headers, "x-amzn-trace-id")
    if trace_id:
        trace["ingress_http_trace_id"] = trace_id
    if trace:
        return {**detail, "_ingress": trace}
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
        payload = {
            "portfolio": portfolio,
            "org": org,
            "raw_body": raw_body,
            "signature_header": signature,
        }
        ingress = detail.get("_ingress")
        if isinstance(ingress, dict) and ingress:
            payload["ingress_trace"] = dict(ingress)
        return payload

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
    dispatch_heartbeat: Callable[..., tuple] | None = None,
    start_webhook_async: Callable[..., dict] | None = None,
) -> tuple[dict, int]:
    """
    Dispatch a normalized ingress detail.

    Returns (response_dict, http_status).
    """
    event_type = detail.get("type")
    if not event_type:
        if detail.get("raw_body") is not None or detail.get("channel") == "whatsapp":
            event_type = "webhook"
            detail = {**detail, "channel": detail.get("channel") or "whatsapp"}
        elif detail.get("schd_jobs_id") or detail.get("trigger") == "cron":
            event_type = "schd_job"
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
        if channel in WEBHOOK_ASYNC_CHANNELS and start_webhook_async is not None:
            async_resp = start_webhook_async(handler, payload)
            if async_resp.get("success"):
                body = {
                    "success": True,
                    "action": "accepted",
                    "handler": handler,
                    "channel": channel,
                    **{
                        k: async_resp[k]
                        for k in ("request_id", "task_id", "worker")
                        if k in async_resp
                    },
                }
                return body, 202
            _logger.warning(
                "Webhook async start failed channel=%s handler=%s error=%s; falling back to sync",
                channel,
                handler,
                async_resp.get("error"),
            )
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

    if event_type == "heartbeat":
        portfolio = detail.get("portfolio")
        org = detail.get("org")
        heartbeat_id = str(detail.get("heartbeat_id") or "").strip()
        if not portfolio or not org or not heartbeat_id:
            return {"success": False, "message": "portfolio, org, and heartbeat_id required"}, 400
        if dispatch_heartbeat is None:
            return {"success": False, "message": "heartbeat dispatcher not configured"}, 500
        response, status = dispatch_heartbeat(portfolio, org, heartbeat_id, detail)
        return response, status

    return {"success": False, "message": f"unknown type: {event_type}"}, 400
