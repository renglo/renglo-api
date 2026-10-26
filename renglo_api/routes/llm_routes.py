# Narrow Console route for trying an LLM alias.
# Handlers keep calling LlmController.generate directly.

from flask import Blueprint, jsonify, request
from flask_cognito import cognito_auth_required

from renglo.llm import LlmController

app_llm = Blueprint("app_llm", __name__, url_prefix="/_llm")

LLC = None

_FORBIDDEN_TENANTS = frozenset({"", "_all", "*", "all"})
_TEXT_ROLES = ("system", "user", "assistant")
_REJECTED_FIELDS = (
    "provider_options",
    "tools",
    "stream",
    "output_schema",
    "fallback",
    "context",
    "timeout_seconds",
    "max_output_tokens",
)
_MAX_MESSAGES = 6
_MAX_PROMPT_CHARS = 8000
_MAX_OUTPUT_TOKENS = 256
_TIMEOUT_SECONDS = 30
_EXTENSION_ID = "data"


@app_llm.record_once
def on_load(state):
    global LLC
    LLC = LlmController(config=state.app.renglo_config)


def _reject_tenant(portfolio: str, org: str):
    portfolio_text = str(portfolio or "").strip()
    org_text = str(org or "").strip()
    if (
        not portfolio_text
        or not org_text
        or portfolio_text.lower() in _FORBIDDEN_TENANTS
        or org_text.lower() in _FORBIDDEN_TENANTS
        or "*" in portfolio_text
        or "*" in org_text
    ):
        return _fail("portfolio and org are required; _all and wildcards are not allowed", 400)
    return None


def _fail(error, status):
    return jsonify({"success": False, "action": "generate", "error": error, "status": status}), status


def _messages(payload):
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return None, "messages must be a non-empty list"
    if len(messages) > _MAX_MESSAGES:
        return None, f"messages are limited to {_MAX_MESSAGES}"
    cleaned = []
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            return None, "each message must be an object"
        role = message.get("role")
        content = message.get("content")
        if role not in _TEXT_ROLES:
            return None, "message role must be system, user, or assistant"
        if not isinstance(content, str) or not content.strip():
            return None, "message content must be a string"
        total += len(content)
        if total > _MAX_PROMPT_CHARS:
            return None, f"prompt is limited to {_MAX_PROMPT_CHARS} characters"
        cleaned.append({"role": role, "content": content})
    return cleaned, None


_ATTEMPT_FIELDS = (
    "attempt_id",
    "execution_id",
    "deployment_id",
    "provider_id",
    "model_id",
    "status",
    "error_type",
    "duration_ms",
    "usage",
    "cost",
)


def _source(provider, deployment_id=None):
    catalog = getattr(getattr(getattr(LLC, "LMM", None), "registry", None), "catalog", None) or []
    for entry in catalog:
        if entry.provider_id == provider and entry.source_label:
            return entry.source_label
    return str(provider or "") or None


def _public_attempts(attempts):
    shown = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict):
            continue
        item = {key: attempt.get(key) for key in _ATTEMPT_FIELDS}
        item["source"] = _source(attempt.get("provider_id"), attempt.get("deployment_id"))
        shown.append(item)
    return shown


def _call_attempt(attempts):
    for attempt in reversed(attempts):
        if attempt.get("status") == "completed":
            return attempt
    return attempts[-1] if attempts else None


def _stop_reason(provider_output):
    if not isinstance(provider_output, dict):
        return None
    for key in ("stopReason", "stop_reason", "finish_reason"):
        if provider_output.get(key):
            return provider_output.get(key)
    choices = provider_output.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0].get("finish_reason")
    return None


def _request_id(provider_output):
    if not isinstance(provider_output, dict):
        return None
    if provider_output.get("id"):
        return provider_output.get("id")
    metadata = provider_output.get("ResponseMetadata")
    if isinstance(metadata, dict):
        return metadata.get("RequestId")
    return None


def _public_result(result):
    output = result.get("output") if isinstance(result, dict) else {}
    output = output or {}
    execution = output.get("execution") or {}
    attempts = _public_attempts(output.get("attempts"))
    call = _call_attempt(attempts) or {}
    provider = output.get("provider") or call.get("provider_id")
    shown = {
        "text": output.get("text") or "",
        "status": execution.get("status") or call.get("status"),
        "source": _source(provider, call.get("deployment_id")),
        "provider": provider,
        "requested_model": output.get("requested_model"),
        "model": output.get("model") or call.get("model_id"),
        "deployment_id": call.get("deployment_id"),
        "execution_id": execution.get("execution_id") or call.get("execution_id"),
        "context": execution.get("context") or {},
        "response_time_ms": call.get("duration_ms"),
        "stop_reason": _stop_reason(output.get("provider_output")),
        "request_id": _request_id(output.get("provider_output")),
        "usage": execution.get("usage") or call.get("usage") or {},
        "cost": execution.get("cost") or call.get("cost") or {},
        "attempts": attempts,
        "limits": {
            "max_output_tokens": _MAX_OUTPUT_TOKENS,
            "timeout_seconds": _TIMEOUT_SECONDS,
            "max_messages": _MAX_MESSAGES,
            "max_prompt_chars": _MAX_PROMPT_CHARS,
        },
    }
    body = {
        "success": bool(result.get("success")),
        "action": "generate",
        "output": shown,
    }
    if not body["success"]:
        body["error"] = result.get("error") or "generate failed"
        body["error_type"] = result.get("error_type")
        shown["error"] = body["error"]
        shown["error_type"] = body["error_type"]
    return body


def _catalog():
    """Models the Console can offer. Each row is one provider's model."""
    items = []
    for entry in LLC.LMM.registry.catalog:
        items.append(
            {
                "provider": entry.provider_id,
                "model": entry.model_id,
                "enabled": bool(entry.available and entry.model_id),
                "source": entry.source_label,
                "reason": entry.reason,
            }
        )
    return items


def _selection_error(model, provider):
    if not hasattr(LLC, "LMM"):
        return None
    catalog = LLC.LMM.registry.catalog
    if provider is not None and not isinstance(provider, str):
        return "provider must be a string"
    provider = provider.strip() if isinstance(provider, str) else None
    provider = provider or None
    if model in (None, "", "default"):
        return "model is required"
    rows = [
        entry for entry in catalog
        if entry.model_id == model and (not provider or entry.provider_id == provider)
    ]
    if not rows:
        if provider and provider not in LLC.LMM.registry.modules:
            return "Unknown provider"
        if provider:
            return None
        return "Unknown model"
    if len(rows) > 1 and not provider:
        return "provider is required when more than one provider offers this model"
    if not rows[0].available:
        return rows[0].reason or "The model is not available"
    return None


def _http_status(result):
    if result.get("success"):
        return 200
    error_type = result.get("error_type")
    if error_type == "timeout":
        return 504
    if error_type in ("provider_error", "rate_limit"):
        return 502
    return 400


@app_llm.route("/<string:portfolio>/<string:org>/models", methods=["GET"])
@cognito_auth_required
def route_models(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    return jsonify({"success": True, "action": "models", "output": {"models": _catalog()}}), 200


@app_llm.route("/<string:portfolio>/<string:org>/generate", methods=["POST"])
@cognito_auth_required
def route_generate(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return _fail("JSON object is required", 400)
    rejected = [name for name in _REJECTED_FIELDS if name in payload]
    if rejected:
        return _fail(f"{rejected[0]} is not accepted", 400)
    messages, error = _messages(payload)
    if error:
        return _fail(error, 400)
    model = payload.get("model")
    provider = payload.get("provider")
    selection_error = _selection_error(model, provider)
    if selection_error:
        return _fail(selection_error, 400)
    try:
        result = LLC.generate(
            messages,
            model=model,
            provider=provider,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            timeout_seconds=_TIMEOUT_SECONDS,
            context={
                "portfolio_id": portfolio,
                "org_id": org,
                "extension_id": _EXTENSION_ID,
            },
        )
    except Exception:
        return _fail("generate failed", 500)
    status = _http_status(result)
    body = _public_result(result)
    body["status"] = status
    return jsonify(body), status
