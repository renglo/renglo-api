# search_routes.py - OpenSearch document search API

from flask import Blueprint, request, jsonify
from flask_cognito import cognito_auth_required

from renglo.search.search_controller import SearchController

app_search = Blueprint('app_search', __name__, url_prefix='/_search')

SHC = None


@app_search.record_once
def on_load(state):
    """Initialize SearchController when blueprint is registered."""
    global SHC
    config = state.app.renglo_config
    SHC = SearchController(config=config)


@app_search.route('/<string:portfolio>/<string:org>', methods=['POST'])
@cognito_auth_required
def route_search(portfolio, org):
    """
    Full-text search within org scope. Never returns cross-org results.
    """
    payload = request.get_json() or {}
    query = payload.get('query', '')
    datatypes = payload.get('datatypes')
    filters = payload.get('filters')
    limit = min(int(payload.get('limit', 20)), 100)
    offset = int(payload.get('offset', 0))
    search_fields = payload.get('search_fields')
    boost_fields = payload.get('boost_fields')

    result = SHC.search(
        portfolio=portfolio,
        org=org,
        query=query,
        datatypes=datatypes,
        filters=filters,
        limit=limit,
        offset=offset,
        search_fields=search_fields,
        boost_fields=boost_fields,
    )
    return jsonify(result), 200 if result.get('success') else 500
