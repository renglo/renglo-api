"""Client /v1 document routes.

Each handler parses projectId into portfolio and org, then calls
AuthController, BlueprintController, DataController, or SchdController.
"""

from flask import Blueprint, jsonify, request

from renglo.auth.auth_controller import AuthController
from renglo.auth.request_identity import auth_required, current_claims
from renglo.blueprint.blueprint_controller import BlueprintController
from renglo.data.data_controller import DataController

from ..client.contracts import (
    clone_schema,
    commit_schema,
    deprecate_schema,
    get_schema,
    list_schemas,
    list_versions as list_schema_versions,
    new_schema,
    publish_schema,
    pull_schema,
)
from ..client.dictionaries import (
    clone_dictionary,
    commit_dictionary,
    deprecate_dictionary,
    get_dictionary,
    list_dictionaries,
    list_dictionary_versions,
    new_dictionary,
    publish_dictionary,
    pull_dictionary,
)
from ..client.ontologies import (
    clone_ontology,
    commit_ontology,
    deprecate_ontology,
    get_ontology,
    list_ontologies,
    list_ontology_versions,
    new_ontology,
    publish_ontology,
    pull_ontology,
)
from ..client.data_types import (
    create_data_type,
    get_data_type,
    update_data_type,
)
from ..client.documents import (
    create_collection as open_collection,
    create_document as insert_document,
    delete_document as remove_document,
    get_collection as read_collection,
    get_document as read_document,
    list_collections as read_collections,
    list_documents as read_documents,
    parse_project_id,
    query_documents as search_documents,
    update_document as patch_document,
)


app_client = Blueprint('app_client', __name__, url_prefix='/v1')

DAC = None
AUC = None
BPC = None


@app_client.record_once
def on_load(state):
    global DAC, AUC, BPC
    config = state.app.renglo_config
    DAC = DataController(config=config)
    AUC = AuthController(config=config)
    BPC = BlueprintController(config=config)


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
    """Unwrap `{data}` from an update. Any other body is the document."""
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


@app_client.route('/projects/<string:project_id>/contracts/schemas', methods=['POST'])
@auth_required
def new_schema_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    body = _json()
    return _respond(new_schema(BPC, portfolio, body.get('name'), body.get('schema') or {}))


@app_client.route('/projects/<string:project_id>/contracts/schemas', methods=['GET'])
@auth_required
def list_schemas_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(list_schemas(BPC, portfolio))


@app_client.route('/projects/<string:project_id>/contracts/schemas/clone', methods=['POST'])
@auth_required
def clone_schema_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(clone_schema(BPC, portfolio, _json().get('uri')))


@app_client.route('/projects/<string:project_id>/contracts/schemas/<string:name>', methods=['GET'])
@auth_required
def get_schema_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(get_schema(BPC, portfolio, name, version=request.args.get('version')))


@app_client.route('/projects/<string:project_id>/contracts/schemas/<string:name>/commit', methods=['POST'])
@auth_required
def commit_schema_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(commit_schema(BPC, portfolio, name, _json().get('schema') or {}))


@app_client.route('/projects/<string:project_id>/contracts/schemas/<string:name>/pull', methods=['POST'])
@auth_required
def pull_schema_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(pull_schema(BPC, portfolio, name))


@app_client.route('/projects/<string:project_id>/contracts/schemas/<string:name>/publish', methods=['POST'])
@auth_required
def publish_schema_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(publish_schema(BPC, portfolio, name))


@app_client.route('/projects/<string:project_id>/contracts/schemas/<string:name>/versions', methods=['GET'])
@auth_required
def list_schema_versions_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(list_schema_versions(BPC, portfolio, name))


@app_client.route(
    '/projects/<string:project_id>/contracts/schemas/<string:name>/versions/<string:version>/deprecate',
    methods=['POST'],
)
@auth_required
def deprecate_schema_route(project_id, name, version):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(deprecate_schema(BPC, portfolio, name, version))


@app_client.route('/projects/<string:project_id>/contracts/ontologies', methods=['POST'])
@auth_required
def new_ontology_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    body = _json()
    return _respond(new_ontology(BPC, portfolio, body.get('name'), body.get('ontology') or {}))


@app_client.route('/projects/<string:project_id>/contracts/ontologies', methods=['GET'])
@auth_required
def list_ontologies_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(list_ontologies(BPC, portfolio))


@app_client.route('/projects/<string:project_id>/contracts/ontologies/clone', methods=['POST'])
@auth_required
def clone_ontology_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(clone_ontology(BPC, portfolio, _json().get('uri')))


@app_client.route('/projects/<string:project_id>/contracts/ontologies/<string:name>', methods=['GET'])
@auth_required
def get_ontology_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(get_ontology(BPC, portfolio, name, version=request.args.get('version')))


@app_client.route('/projects/<string:project_id>/contracts/ontologies/<string:name>/commit', methods=['POST'])
@auth_required
def commit_ontology_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(commit_ontology(BPC, portfolio, name, _json().get('ontology') or {}))


@app_client.route('/projects/<string:project_id>/contracts/ontologies/<string:name>/pull', methods=['POST'])
@auth_required
def pull_ontology_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(pull_ontology(BPC, portfolio, name))


@app_client.route('/projects/<string:project_id>/contracts/ontologies/<string:name>/publish', methods=['POST'])
@auth_required
def publish_ontology_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(publish_ontology(BPC, portfolio, name))


@app_client.route('/projects/<string:project_id>/contracts/ontologies/<string:name>/versions', methods=['GET'])
@auth_required
def list_ontology_versions_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(list_ontology_versions(BPC, portfolio, name))


@app_client.route(
    '/projects/<string:project_id>/contracts/ontologies/<string:name>/versions/<string:version>/deprecate',
    methods=['POST'],
)
@auth_required
def deprecate_ontology_route(project_id, name, version):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(deprecate_ontology(BPC, portfolio, name, version))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries', methods=['POST'])
@auth_required
def new_dictionary_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    body = _json()
    return _respond(new_dictionary(BPC, portfolio, body.get('name'), body.get('dictionary') or {}))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries', methods=['GET'])
@auth_required
def list_dictionaries_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(list_dictionaries(BPC, portfolio))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries/clone', methods=['POST'])
@auth_required
def clone_dictionary_route(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(clone_dictionary(BPC, portfolio, _json().get('uri')))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries/<string:name>', methods=['GET'])
@auth_required
def get_dictionary_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(get_dictionary(BPC, portfolio, name, version=request.args.get('version')))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries/<string:name>/commit', methods=['POST'])
@auth_required
def commit_dictionary_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(commit_dictionary(BPC, portfolio, name, _json().get('dictionary') or {}))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries/<string:name>/pull', methods=['POST'])
@auth_required
def pull_dictionary_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(pull_dictionary(BPC, portfolio, name))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries/<string:name>/publish', methods=['POST'])
@auth_required
def publish_dictionary_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(publish_dictionary(BPC, portfolio, name))


@app_client.route('/projects/<string:project_id>/contracts/dictionaries/<string:name>/versions', methods=['GET'])
@auth_required
def list_dictionary_versions_route(project_id, name):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(list_dictionary_versions(BPC, portfolio, name))


@app_client.route(
    '/projects/<string:project_id>/contracts/dictionaries/<string:name>/versions/<string:version>/deprecate',
    methods=['POST'],
)
@auth_required
def deprecate_dictionary_route(project_id, name, version):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, _org = scope
    return _respond(deprecate_dictionary(BPC, portfolio, name, version))


@app_client.route('/projects/<string:project_id>/documents/collections', methods=['POST'])
@auth_required
def create_collection(project_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    body = _json()
    schema_name = body.get('schema_name') or body.get('name')
    return _respond(open_collection(
        AUC,
        BPC,
        portfolio,
        org,
        schema_name,
        team_id=_team_id(),
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
    return _respond(read_collection(AUC, portfolio, org, name))


@app_client.route('/projects/<string:project_id>/documents/<string:collection>', methods=['POST'])
@auth_required
def create_document(project_id, collection):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(insert_document(
        DAC, AUC, BPC, portfolio, org, collection, _json(), team_id=_team_id(),
    ))


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


@app_client.route('/projects/<string:project_id>/documents/<string:collection>/<string:doc_id>', methods=['DELETE'])
@auth_required
def delete_document(project_id, collection, doc_id):
    scope, error = _scope(project_id)
    if error:
        return error
    portfolio, org = scope
    return _respond(remove_document(DAC, portfolio, org, collection, doc_id))
