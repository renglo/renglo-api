# search_routes.py - OpenSearch document search API

from flask import Blueprint, request, jsonify
from flask_cognito import cognito_auth_required

from renglo.search.search_controller import SearchController

app_search = Blueprint('app_search', __name__, url_prefix='/_search')

SHC = None


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


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
    filters = payload.get('filters') or {}
    if not isinstance(filters, dict):
        filters = {}
    limit = min(int(payload.get('limit', 20)), 100)
    offset = int(payload.get('offset', 0))
    search_fields = filters.get('fields')
    boost_fields = filters.get('boost_fields')
    resolve_matches = _to_bool(filters.get('resolve'))

    result = SHC.search(
        portfolio=portfolio,
        org=org,
        query=query,
        datatypes=None,
        filters=filters,
        limit=limit,
        offset=offset,
        search_fields=search_fields,
        boost_fields=boost_fields,
        resolve_matches=resolve_matches,
    )
    return jsonify(result), 200 if result.get('success') else 500
