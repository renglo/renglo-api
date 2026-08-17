# rag_routes.py - Platform Bedrock Knowledge Base amenity API

from flask import Blueprint, jsonify, request
from flask_cognito import cognito_auth_required

from renglo.rag import RagConfigError, RagController

app_rag = Blueprint("app_rag", __name__, url_prefix="/_rag")

RGC = None


@app_rag.record_once
def on_load(state):
    global RGC
    RGC = RagController(config=state.app.renglo_config)


@app_rag.route("/status", methods=["GET", "POST"])
@cognito_auth_required
def route_status():
    return jsonify(RGC.status()), 200


@app_rag.route("/retrieve", methods=["POST"])
@cognito_auth_required
def route_retrieve():
    payload = request.get_json() or {}
    query = str(payload.get("query") or payload.get("text") or "")
    try:
        result = RGC.rag_retrieve(
            query,
            number_of_results=int(payload.get("number_of_results") or payload.get("top_k") or 5),
            next_token=payload.get("next_token"),
            retrieval_configuration=payload.get("retrieval_configuration"),
        )
    except RagConfigError as exc:
        return jsonify({"success": False, "action": "rag_retrieve", "error": str(exc)}), 400
    return jsonify(result), 200 if result.get("success") else 400


@app_rag.route("/generate", methods=["POST"])
@cognito_auth_required
def route_generate():
    payload = request.get_json() or {}
    query = str(payload.get("query") or payload.get("text") or "")
    try:
        result = RGC.rag_generate(
            query,
            session_id=payload.get("session_id"),
            number_of_results=int(payload.get("number_of_results") or payload.get("top_k") or 5),
            retrieval_configuration=payload.get("retrieval_configuration"),
            generation_configuration=payload.get("generation_configuration"),
        )
    except RagConfigError as exc:
        return jsonify({"success": False, "action": "rag_generate", "error": str(exc)}), 400
    return jsonify(result), 200 if result.get("success") else 400


@app_rag.route("/upload", methods=["POST"])
@cognito_auth_required
def route_upload():
    payload = request.get_json() or {}
    result = RGC.upload_doc(
        filename=str(payload.get("filename") or ""),
        content_text=payload.get("content_text"),
        content_base64=payload.get("content_base64"),
        subpath=str(payload.get("subpath") or "runbooks"),
        bucket=payload.get("bucket"),
        prefix=payload.get("prefix"),
        content_type=payload.get("content_type"),
    )
    return jsonify(result), 200 if result.get("success") else 400


@app_rag.route("/start_sync", methods=["POST"])
@cognito_auth_required
def route_start_sync():
    payload = request.get_json() or {}
    try:
        result = RGC.start_ingestion_job(
            data_source_id=payload.get("data_source_id"),
            description=payload.get("description") or "console /_rag sync",
        )
    except RagConfigError as exc:
        return jsonify({"success": False, "action": "start_ingestion_job", "error": str(exc)}), 400
    return jsonify(result), 200 if result.get("success") else 400


@app_rag.route("/sync_status", methods=["POST"])
@cognito_auth_required
def route_sync_status():
    payload = request.get_json() or {}
    job_id = str(payload.get("ingestion_job_id") or "").strip()
    if not job_id:
        return jsonify(
            {"success": False, "action": "get_ingestion_job", "error": "ingestion_job_id is required"}
        ), 400
    try:
        result = RGC.get_ingestion_job(
            job_id, data_source_id=payload.get("data_source_id")
        )
    except RagConfigError as exc:
        return jsonify({"success": False, "action": "get_ingestion_job", "error": str(exc)}), 400
    return jsonify(result), 200 if result.get("success") else 400
