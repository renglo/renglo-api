# vector_routes.py - Platform S3 Vectors amenity API

from flask import Blueprint, jsonify, request
from flask_cognito import cognito_auth_required

from renglo.vector_controller import VectorController

app_vector = Blueprint("app_vector", __name__, url_prefix="/_vector")

VTC = None


@app_vector.record_once
def on_load(state):
    global VTC
    VTC = VectorController(config=state.app.renglo_config)


@app_vector.route("/status", methods=["GET", "POST"])
@cognito_auth_required
def route_status():
    payload = request.get_json(silent=True) or {}
    portfolio = str(payload.get("portfolio") or request.args.get("portfolio") or "")
    org = str(payload.get("org") or request.args.get("org") or "")
    result = VTC.status(portfolio=portfolio, org=org)
    return jsonify(result), 200


@app_vector.route("/query", methods=["POST"])
@cognito_auth_required
def route_query():
    payload = request.get_json() or {}
    result = VTC.query(
        portfolio=str(payload.get("portfolio") or ""),
        org=str(payload.get("org") or ""),
        extension=str(payload.get("extension") or ""),
        index_name=str(payload.get("index_name") or payload.get("index") or ""),
        vector=payload.get("vector"),
        text=payload.get("text") or payload.get("query"),
        top_k=int(payload.get("top_k") or 10),
        filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else None,
    )
    return jsonify(result), 200 if result.get("success") else 400


@app_vector.route("/put", methods=["POST"])
@cognito_auth_required
def route_put():
    payload = request.get_json() or {}
    result = VTC.put_vector(
        portfolio=str(payload.get("portfolio") or ""),
        org=str(payload.get("org") or ""),
        extension=str(payload.get("extension") or ""),
        index_name=str(payload.get("index_name") or payload.get("index") or ""),
        entity_id=str(payload.get("entity_id") or ""),
        vector=payload.get("vector"),
        text=payload.get("text"),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )
    return jsonify(result), 200 if result.get("success") else 400


@app_vector.route("/delete", methods=["POST"])
@cognito_auth_required
def route_delete():
    payload = request.get_json() or {}
    result = VTC.delete_vector(
        portfolio=str(payload.get("portfolio") or ""),
        org=str(payload.get("org") or ""),
        extension=str(payload.get("extension") or ""),
        index_name=str(payload.get("index_name") or payload.get("index") or ""),
        entity_id=str(payload.get("entity_id") or ""),
    )
    return jsonify(result), 200 if result.get("success") else 400


@app_vector.route("/ensure_index", methods=["POST"])
@cognito_auth_required
def route_ensure_index():
    payload = request.get_json() or {}
    result = VTC.ensure_index(
        portfolio=str(payload.get("portfolio") or ""),
        org=str(payload.get("org") or ""),
        index_name=str(payload.get("index_name") or payload.get("index") or ""),
        dimension=int(payload.get("dimension") or 1024),
    )
    return jsonify(result), 200 if result.get("success") else 400
