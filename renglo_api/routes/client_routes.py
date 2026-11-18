"""Client /v1 document routes.

Each handler parses projectId into portfolio and org, then calls
AuthController, BlueprintController, DataController, or SchdController.
"""

from flask import Blueprint, current_app, jsonify, request

from renglo.auth.auth_controller import AuthController
from renglo.auth.request_identity import auth_required, current_claims
from renglo.blueprint.blueprint_controller import BlueprintController
from renglo.data.data_controller import DataController
from renglo.schd.schd_controller import SchdController

from ..client.data_types import (
    create_data_type,
    get_data_type,
    update_data_type,
)
from ..client.documents import (
    count_documents as count_collection,
    create_collection as open_collection,
    create_document as insert_document,
    create_index as add_index,
    delete_collection as close_collection,
    delete_document as remove_document,
    delete_index as drop_index,
    get_collection as read_collection,
    get_document as read_document,
    list_collections as read_collections,
    list_documents as read_documents,
    list_indexes as read_indexes,
    parse_project_id,
    query_documents as search_documents,
    update_collection as patch_collection,
    update_document as patch_document,
    upsert_document as save_document,
)


app_client = Blueprint('app_client', __name__, url_prefix='/v1')

DAC = None
AUC = None
BPC = None
SHC = None


@app_client.record_once
def on_load(state):
    global DAC, AUC, BPC, SHC
    config = state.app.renglo_config
    DAC = DataController(config=config)
    AUC = AuthController(config=config)
    BPC = BlueprintController(config=config)
    SHC = SchdController(config=config)


def _scope(project_id):
    parsed = parse_project_id(project_id)
    if parsed is None:
        return None, (jsonify({
            'success': False,
            'message': 'projectId must be <portfolio>-<org>',
            'error': {
                'type': 'InvalidProject',
                'message': 'projectId must be <portfolio>-<org>',
            },
        }), 400)
    return parsed, None


def _team_id():
    claims = current_claims() or {}
    return claims.get('team_id') or claims.get('custom:team_id') or None


def _json():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _respond(result):
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], dict):
        body, status = result
        return jsonify(body), status
    return jsonify(result), 200


def _document_fields(body):
    """Unwrap `{data, upsert}` from replace and upsert. Any other body is the document."""
    if isinstance(body.get('data'), dict) and set(body) <= {'data', 'upsert', '_upsert'}:
        return body.get('data') or {}
    return {
        key: value
        for key, value in body.items()
        if key not in ('upsert', '_upsert')
    }


@app_client.route('/projects/<string:project_id>/data-types', methods=['POST'])
@auth_required
def create_data_type_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    body = _json()
    return _respond(create_data_type(BPC, portfolio, body.get('name'), body.get('definition') or {}))


@app_client.route('/projects/<string:project_id>/data-types/<string:name>', methods=['GET'])
@auth_required
def get_data_type_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(get_data_type(BPC, portfolio, name, version=request.args.get('version')))


@app_client.route('/projects/<string:project_id>/data-types/<string:name>', methods=['PATCH'])
@auth_required
def update_data_type_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(update_data_type(BPC, portfolio, name, _json()))


@app_client.route('/projects/<string:project_id>/documents/collections', methods=['POST'])
@auth_required
def create_collection(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    body = _json()
    name = body.get('name')
    return _respond(open_collection(
        AUC,
        BPC,
        portfolio,
        org,
        name,
        body.get('config') or {},
        team_id=_team_id(),
        app_config=current_app.renglo_config,
    ))


@app_client.route('/projects/<string:project_id>/documents/collections', methods=['GET'])
@auth_required
def list_collections(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(read_collections(AUC, portfolio, org, team_id=_team_id()))


@app_client.route('/projects/<string:project_id>/documents/collections/<string:name>', methods=['GET'])
@auth_required
def get_collection(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(read_collection(AUC, BPC, portfolio, org, name, version=request.args.get('version')))


@app_client.route('/projects/<string:project_id>/documents/collections/<string:name>', methods=['PATCH'])
@auth_required
def update_collection(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(patch_collection(AUC, BPC, portfolio, org, name, _json()))


@app_client.route('/projects/<string:project_id>/documents/collections/<string:name>', methods=['DELETE'])
@auth_required
def delete_collection(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(close_collection(AUC, portfolio, org, name))


@app_client.route('/projects/<string:project_id>/documents/collections/<string:name>/indexes', methods=['GET'])
@auth_required
def list_indexes(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(read_indexes(AUC, BPC, portfolio, org, name))


@app_client.route('/projects/<string:project_id>/documents/collections/<string:name>/indexes', methods=['POST'])
@auth_required
def create_index(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(add_index(AUC, BPC, portfolio, org, name, _json()))


@app_client.route(
    '/projects/<string:project_id>/documents/collections/<string:name>/indexes/<string:index_id>',
    methods=['DELETE'],
)
@auth_required
def delete_index(project_id, name, index_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(drop_index(AUC, portfolio, org, name, index_id))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>', methods=['POST'])
@auth_required
def create_document(project_id, collection):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(insert_document(DAC, AUC, portfolio, org, collection, _json()))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>', methods=['GET'])
@auth_required
def list_documents(project_id, collection):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    limit = request.args.get('limit', default=20, type=int)
    cursor = request.args.get('cursor') or request.args.get('lastkey')
    return _respond(read_documents(DAC, portfolio, org, collection, limit=limit, cursor=cursor))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/query', methods=['POST'])
@auth_required
def query_documents(project_id, collection):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(search_documents(DAC, BPC, portfolio, org, collection, _json()))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/count', methods=['POST'])
@auth_required
def count_documents(project_id, collection):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(count_collection(AUC, portfolio, org, collection, _json()))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/batch', methods=['POST'])
@auth_required
def batch_documents(project_id, collection):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    body = _json()
    response = SHC.handler_call_async_start(
        portfolio,
        org,
        'data',
        'batch_handler',
        {'collection': collection, 'operations': body.get('operations') or []},
    )
    status = 202 if response.get('success') else response.get('status', 400)
    return jsonify(response), status


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/<string:doc_id>', methods=['GET'])
@auth_required
def get_document(project_id, collection, doc_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(read_document(DAC, portfolio, org, collection, doc_id))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/<string:doc_id>', methods=['PATCH'])
@auth_required
def update_document(project_id, collection, doc_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(patch_document(DAC, portfolio, org, collection, doc_id, _document_fields(_json())))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/<string:doc_id>', methods=['PUT'])
@auth_required
def put_document(project_id, collection, doc_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    body = _json()
    fields = _document_fields(body)
    if body.get('upsert') or body.get('_upsert'):
        return _respond(save_document(DAC, portfolio, org, collection, doc_id, fields))
    return _respond(patch_document(DAC, portfolio, org, collection, doc_id, fields))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/<string:doc_id>', methods=['DELETE'])
@auth_required
def delete_document(project_id, collection, doc_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(remove_document(DAC, portfolio, org, collection, doc_id))
