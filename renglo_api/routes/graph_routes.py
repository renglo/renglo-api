# graph_routes.py - Read-only graph query API

from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_cognito import cognito_auth_required

from renglo.graph.graph_controller import (
    GraphController,
    GraphQueryCancelled,
    GraphQueryTimeout,
    GraphTraversalBudgetExceeded,
)

app_graph = Blueprint('app_graph', __name__, url_prefix='/_graph')

GRC = None


@app_graph.record_once
def on_load(state):
    """Initialize GraphController when blueprint is registered."""
    global GRC
    config = state.app.renglo_config
    GRC = GraphController(config=config)


def _to_node_id(payload):
    node_id = payload.get('node_id')
    if node_id:
        return node_id
    ring = payload.get('ring')
    idx = payload.get('id') or payload.get('_id')
    if ring and idx:
        return GraphController.make_node_id(str(ring), str(idx))
    return None


def _edge_to_dict(edge, perspective='outgoing'):
    raw_properties = _json_safe(edge.properties)
    edge_label = edge.edge_type
    properties = {}
    qualifiers = {}
    if isinstance(raw_properties, dict):
        if perspective == 'incoming':
            label_candidate = raw_properties.get('label_backward') or raw_properties.get('label_forward')
        else:
            label_candidate = raw_properties.get('label_forward') or raw_properties.get('label_backward')
        if isinstance(label_candidate, str) and label_candidate.strip():
            edge_label = label_candidate.strip()
        raw_qualifiers = raw_properties.get('qualifiers')
        if isinstance(raw_qualifiers, dict):
            qualifiers = raw_qualifiers

        # Keep "properties" for extensibility, but hide internal label/qualifier
        # transport fields from API clients.
        properties = {
            k: v for k, v in raw_properties.items()
            if k not in {'label_forward', 'label_backward', 'qualifiers'}
        }
    return {
        'portfolio': edge.portfolio,
        'org': edge.org,
        'edge_type': edge.edge_type,
        'from_node_id': edge.from_node_id,
        'to_node_id': edge.to_node_id,
        'properties': properties,
        'qualifiers': qualifiers,
        'edge_label': edge_label,
    }


def _edge_unique_key(edge):
    return f"{edge.edge_type}#{edge.from_node_id}#{edge.to_node_id}"


def _json_safe(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return [_json_safe(v) for v in value]
    return value


@app_graph.route('/<string:portfolio>/<string:org>/node-edges', methods=['POST'])
@cognito_auth_required
def route_node_edges(portfolio, org):
    """
    Read incoming and outgoing edges for a node.

    Requires edge_types due graph index design (one edge type per query prefix).
    """
    payload = request.get_json() or {}
    node_id = _to_node_id(payload)
    edge_types = payload.get('edge_types') or []
    limit = min(int(payload.get('limit', 100)), 500)
    outgoing_cursor_by_type = payload.get('outgoing_cursor_by_type') or {}
    incoming_cursor_by_type = payload.get('incoming_cursor_by_type') or {}

    if not node_id:
        return jsonify({'success': False, 'message': "Missing node_id or ring+id"}), 400
    outgoing = []
    incoming = []
    incoming_seen = set()
    outgoing_next = {}
    incoming_next = {}
    include_incoming_discovery = bool(payload.get('include_incoming_discovery', True))

    def append_incoming_unique(items):
        for edge in items:
            key = _edge_unique_key(edge)
            if key in incoming_seen:
                continue
            incoming_seen.add(key)
            incoming.append(edge)

    edge_types_fallback = False
    if edge_types:
        for edge_type in edge_types:
            out_page = GRC.list_outgoing_edges(
                portfolio,
                org,
                edge_type,
                node_id,
                limit=limit,
                exclusive_start_key=outgoing_cursor_by_type.get(edge_type),
            )
            in_page = GRC.list_incoming_edges(
                portfolio,
                org,
                edge_type,
                node_id,
                limit=limit,
                exclusive_start_key=incoming_cursor_by_type.get(edge_type),
            )
            outgoing.extend(out_page.items)
            append_incoming_unique(in_page.items)
            if out_page.last_evaluated_key:
                outgoing_next[edge_type] = out_page.last_evaluated_key
            if in_page.last_evaluated_key:
                incoming_next[edge_type] = in_page.last_evaluated_key

        # Also query incoming discovery mode so nodes that have mixed incoming
        # edge types (not inferable from the local blueprint) still show all
        # inbound relationships.
        if include_incoming_discovery:
            discovery_page = GRC.list_incoming_edges_any_type(
                portfolio,
                org,
                node_id,
                limit=limit,
                exclusive_start_key=payload.get('incoming_discovery_cursor') or payload.get('incoming_cursor'),
            )
            append_incoming_unique(discovery_page.items)
            if discovery_page.last_evaluated_key:
                incoming_next["_discovery"] = discovery_page.last_evaluated_key
    else:
        # Fallback discovery mode: incoming edges only, without known edge types.
        edge_types_fallback = True
        in_page = GRC.list_incoming_edges_any_type(
            portfolio,
            org,
            node_id,
            limit=limit,
            exclusive_start_key=payload.get('incoming_cursor'),
        )
        append_incoming_unique(in_page.items)
        if in_page.last_evaluated_key:
            incoming_next["_discovery"] = in_page.last_evaluated_key

    result = {
        'success': True,
        'portfolio': portfolio,
        'org': org,
        'node_id': node_id,
        'edge_types': edge_types,
        'edge_types_fallback': edge_types_fallback,
        'outgoing_count': len(outgoing),
        'incoming_count': len(incoming),
        'outgoing': [_edge_to_dict(e, perspective='outgoing') for e in outgoing],
        'incoming': [_edge_to_dict(e, perspective='incoming') for e in incoming],
        'outgoing_cursor_by_type': outgoing_next,
        'incoming_cursor_by_type': incoming_next,
    }
    return jsonify(_json_safe(result)), 200


@app_graph.route('/<string:portfolio>/<string:org>/edges-by-type', methods=['POST'])
@cognito_auth_required
def route_edges_by_type(portfolio, org):
    """Read edges by edge type with pagination."""
    payload = request.get_json() or {}
    edge_type = payload.get('edge_type')
    limit = min(int(payload.get('limit', 100)), 500)
    exclusive_start_key = payload.get('exclusive_start_key')

    if not edge_type:
        return jsonify({'success': False, 'message': "edge_type is required"}), 400

    page = GRC.list_edges_by_type(
        portfolio,
        org,
        edge_type,
        limit=limit,
        exclusive_start_key=exclusive_start_key,
    )

    result = {
        'success': True,
        'portfolio': portfolio,
        'org': org,
        'edge_type': edge_type,
        'items': [_edge_to_dict(e, perspective='outgoing') for e in page.items],
        'last_evaluated_key': page.last_evaluated_key,
    }
    return jsonify(_json_safe(result)), 200


@app_graph.route('/<string:portfolio>/<string:org>/traverse', methods=['POST'])
@cognito_auth_required
def route_traverse(portfolio, org):
    """Run bounded graph traversal from a start node."""
    payload = request.get_json() or {}
    start_node_id = _to_node_id(payload)
    edge_types = payload.get('edge_types') or []
    dynamic_edge_types = bool(payload.get('dynamic_edge_types', False))

    if not start_node_id:
        return jsonify({'success': False, 'message': "Missing start node: node_id or ring+id"}), 400
    if not edge_types and not dynamic_edge_types:
        return jsonify({'success': False, 'message': "edge_types is required"}), 400

    try:
        direction = payload.get('direction', 'forward')
        if dynamic_edge_types and direction == 'forward':
            result = GRC.traverse_dynamic_forward(
                portfolio,
                org,
                start_node_id=start_node_id,
                max_depth=int(payload.get('max_depth', 3)),
                per_query_limit=int(payload.get('per_query_limit', 100)),
                max_nodes=int(payload.get('max_nodes', 1000)),
                max_edges=int(payload.get('max_edges', 5000)),
                max_neighbors_per_node=int(payload.get('max_neighbors_per_node', 100)),
                timeout_seconds=float(payload.get('timeout_seconds', 10.0)),
                include_duplicate_steps=bool(payload.get('include_duplicate_steps', True)),
                return_frontier_on_stop=bool(payload.get('return_frontier_on_stop', False)),
            )
        elif dynamic_edge_types and direction == 'backward':
            result = GRC.traverse_dynamic_backward(
                portfolio,
                org,
                start_node_id=start_node_id,
                max_depth=int(payload.get('max_depth', 3)),
                per_query_limit=int(payload.get('per_query_limit', 100)),
                max_nodes=int(payload.get('max_nodes', 1000)),
                max_edges=int(payload.get('max_edges', 5000)),
                max_neighbors_per_node=int(payload.get('max_neighbors_per_node', 100)),
                timeout_seconds=float(payload.get('timeout_seconds', 10.0)),
                include_duplicate_steps=bool(payload.get('include_duplicate_steps', True)),
                return_frontier_on_stop=bool(payload.get('return_frontier_on_stop', False)),
            )
        else:
            result = GRC.traverse(
                portfolio,
                org,
                start_node_id=start_node_id,
                edge_types=edge_types,
                direction=direction,
                max_depth=int(payload.get('max_depth', 3)),
                per_query_limit=int(payload.get('per_query_limit', 100)),
                max_nodes=int(payload.get('max_nodes', 1000)),
                max_edges=int(payload.get('max_edges', 5000)),
                max_neighbors_per_node=int(payload.get('max_neighbors_per_node', 100)),
                timeout_seconds=float(payload.get('timeout_seconds', 10.0)),
                min_score=payload.get('min_score'),
                include_duplicate_steps=bool(payload.get('include_duplicate_steps', True)),
                return_frontier_on_stop=bool(payload.get('return_frontier_on_stop', False)),
            )
    except GraphQueryTimeout as e:
        return jsonify({'success': False, 'message': str(e), 'error': 'timeout'}), 408
    except GraphQueryCancelled as e:
        return jsonify({'success': False, 'message': str(e), 'error': 'cancelled'}), 408
    except GraphTraversalBudgetExceeded as e:
        return jsonify({'success': False, 'message': str(e), 'error': 'budget_exceeded'}), 400
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    response = {
        'success': True,
        'start_node_id': result.start_node_id,
        'direction': result.direction,
        'dynamic_edge_types': dynamic_edge_types,
        'visited_nodes': sorted(result.visited_nodes),
        'visited_edges': sorted(result.visited_edges),
        'steps': [
            {
                'depth': step.depth,
                'edge': _edge_to_dict(
                    step.edge,
                    perspective='incoming' if result.direction == 'backward' else 'outgoing'
                ),
                'path': step.path,
                'duplicate_visit': step.duplicate_visit,
                'cycle_detected': step.cycle_detected,
            }
            for step in result.steps
        ],
        'cycles_detected': result.cycles_detected,
        'duplicate_visits': result.duplicate_visits,
        'stopped_reason': result.stopped_reason,
        'next_frontier': result.next_frontier,
    }
    return jsonify(_json_safe(response)), 200
