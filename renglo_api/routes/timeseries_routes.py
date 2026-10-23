# Platform TimeSeries API. Tenancy lives in the path.

from flask import Blueprint, jsonify, request
from flask_cognito import cognito_auth_required

from renglo.timeseries import TimeSeriesController

app_timeseries = Blueprint("app_timeseries", __name__, url_prefix="/_timeseries")

TSC = None

_FORBIDDEN_TENANTS = frozenset({"", "_all", "*", "all"})


@app_timeseries.record_once
def on_load(state):
    global TSC
    TSC = TimeSeriesController(config=state.app.renglo_config)


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
        return (
            jsonify(
                {
                    "success": False,
                    "error": "portfolio and org are required; _all and wildcards are not allowed",
                    "status": 400,
                }
            ),
            400,
        )
    return None


def _response(result):
    if not isinstance(result, dict):
        return jsonify(result), 200
    status = 200 if result.get("success") else int(result.get("status") or 400)
    if status not in (200, 400, 401, 403, 404, 409, 500):
        status = 400
    return jsonify(result), status


def _dimensions(name):
    values = request.args.getlist(name)
    if len(values) == 1 and "," in values[0]:
        return [part for part in values[0].split(",") if part != ""]
    return [value for value in values if value != ""]


@app_timeseries.route("/<string:portfolio>/<string:org>/<string:key>", methods=["POST"])
@cognito_auth_required
def route_put(portfolio, org, key):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), list) else []
    return _response(
        TSC.put(
            portfolio,
            org,
            key,
            payload.get("value"),
            dimensions=dimensions,
            timestamp=payload.get("timestamp"),
            resolution=payload.get("resolution") or "day",
            idempotency_key=payload.get("idempotency_key"),
        )
    )


@app_timeseries.route("/<string:portfolio>/<string:org>/<string:key>", methods=["GET"])
@cognito_auth_required
def route_get(portfolio, org, key):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    date = request.args.get("date")
    if date:
        return _response(
            TSC.get(
                portfolio,
                org,
                key,
                date,
                dimensions=_dimensions("dimensions"),
            )
        )
    return _response(
        TSC.query(
            portfolio,
            org,
            key,
            period=request.args.get("period"),
            dimensions_prefix=_dimensions("dimensions_prefix") or None,
            start=request.args.get("start"),
            end=request.args.get("end"),
            resolution=request.args.get("resolution"),
            dimensions=_dimensions("dimensions"),
        )
    )
