"""
AWS Lambda entrypoint for Renglo API.
"""

from __future__ import annotations

import json
from typing import Any

from apig_wsgi import make_lambda_handler

from renglo_api.application import app
from renglo.schd.ingress_worker import INGRESS_WORKER_FLAG, run_ingress_webhook_worker

_apigw_handler = make_lambda_handler(app)


def _coerce_event(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if isinstance(event, (bytes, bytearray)):
        event = event.decode("utf-8", errors="replace")
    if isinstance(event, str):
        try:
            parsed = json.loads(event)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def lambda_handler(event, context):
    normalized = _coerce_event(event)
    if normalized.get(INGRESS_WORKER_FLAG):
        return run_ingress_webhook_worker(normalized, context)
    return _apigw_handler(event, context)
