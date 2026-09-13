# vector_routes.py - Platform S3 Vectors amenity API
# Tenancy lives in the path. Index name is derived from portfolio/org only.

from flask import Blueprint, jsonify, request
from flask_cognito import cognito_auth_required

from renglo.vector import VectorController

app_vector = Blueprint("app_vector", __name__, url_prefix="/_vector")

VTC = None

_FORBIDDEN_TENANTS = frozenset({"", "_all", "*", "all"})


@app_vector.record_once
def on_load(state):
    global VTC
    VTC = VectorController(config=state.app.renglo_config)


def _reject_tenant(portfolio: str, org: str):
    p = str(portfolio or "").strip()
    o = str(org or "").strip()
    if (
        p.lower() in _FORBIDDEN_TENANTS
        or o.lower() in _FORBIDDEN_TENANTS
        or "*" in p
        or "*" in o
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


def _payload():
    return request.get_json(silent=True) or {}


def _vector_response(result):
    if not isinstance(result, dict):
        return jsonify(result), 200
    if result.get("success"):
        return jsonify(result), 200
    status = result.get("status")
    try:
        code = int(status) if status is not None else 400
    except (TypeError, ValueError):
        code = 400
    if code == 403 or str(result.get("message") or "").lower().find("not authorized") >= 0:
        code = 403
    if code not in (400, 401, 403, 404, 409, 500):
        code = 400
    return jsonify(result), code


@app_vector.route("/<string:portfolio>/<string:org>/status", methods=["GET", "POST"])
@cognito_auth_required
def route_status(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    return _vector_response(VTC.status(portfolio=portfolio, org=org))


@app_vector.route("/<string:portfolio>/<string:org>/query", methods=["POST"])
@cognito_auth_required
def route_query(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    payload = _payload()
    return _vector_response(
        VTC.query(
            portfolio=portfolio,
            org=org,
            entity_type=str(payload.get("entity_type") or "").strip() or None,
            vector=payload.get("vector"),
            text=payload.get("text") or payload.get("query"),
            top_k=int(payload.get("top_k") or 10),
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else None,
        )
    )


@app_vector.route("/<string:portfolio>/<string:org>/list", methods=["POST"])
@cognito_auth_required
def route_list(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    payload = _payload()
    return _vector_response(
        VTC.list_vectors(
            portfolio=portfolio,
            org=org,
            entity_type=str(payload.get("entity_type") or "").strip() or None,
            max_results=int(payload.get("max_results") or payload.get("limit") or 100),
            next_token=payload.get("next_token"),
        )
    )


@app_vector.route("/<string:portfolio>/<string:org>/ensure_index", methods=["POST"])
@cognito_auth_required
def route_ensure_index(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    payload = _payload()
    return _vector_response(
        VTC.ensure_index(
            portfolio=portfolio,
            org=org,
            dimension=int(payload.get("dimension") or 1024),
        )
    )


@app_vector.route("/<string:portfolio>/<string:org>/purge", methods=["POST"])
@cognito_auth_required
def route_purge(portfolio, org):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    payload = _payload()
    confirm = bool(payload.get("confirm") is True or str(payload.get("confirm") or "").lower() == "true")
    return _vector_response(VTC.purge_index(portfolio=portfolio, org=org, confirm=confirm))


@app_vector.route(
    "/<string:portfolio>/<string:org>/<string:entity_type>/<string:entity_id>",
    methods=["GET", "POST", "DELETE"],
)
@cognito_auth_required
def route_addressed(portfolio, org, entity_type, entity_id):
    denied = _reject_tenant(portfolio, org)
    if denied:
        return denied
    if request.method == "GET":
        return _vector_response(
            VTC.get_vector(
                portfolio=portfolio,
                org=org,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )
    if request.method == "DELETE":
        return _vector_response(
            VTC.delete_vector(
                portfolio=portfolio,
                org=org,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )
    payload = _payload()
    attrs = payload.get("attrs") if isinstance(payload.get("attrs"), dict) else None
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    return _vector_response(
        VTC.put_vector(
            portfolio=portfolio,
            org=org,
            entity_type=entity_type,
            entity_id=entity_id,
            vector=payload.get("vector"),
            text=payload.get("text"),
            attrs=attrs,
            metadata=metadata,
        )
    )
