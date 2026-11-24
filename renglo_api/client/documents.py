"""/v1 document calls.

The route parses the client API request and calls AuthController,
BlueprintController, and DataController. This module is that translation.
It does not store anything itself.

A collection is the set of documents in one project that follow one schema.
The collection name is the schema name. Opening a collection writes an entity
document of type ``collection``. It does not write a schema. Saving the first
document opens that collection when it is not already there.
"""

from __future__ import annotations

from renglo.auth.entity_status import entity_is_deleted
from renglo_api.client.document_query import DocumentQueryError, translate_document_query


_HIDDEN = {
    "_id",
    "_modified",
    "_index",
    "portfolio",
    "org",
    "ring",
    "blueprint",
    "blueprint_version",
    "license",
    "public",
    "added",
    "path_index",
    "index",
    "irn",
    "attributes",
}


def parse_project_id(project_id):
    """Split `<portfolio>-<org>` on the first dash. Portfolio ids contain no dash."""
    text = str(project_id or "").strip()
    if "-" not in text:
        return None
    portfolio, org = text.split("-", 1)
    if not portfolio or not org:
        return None
    return portfolio, org


def fail(error_type, message, status):
    return {
        "success": False,
        "message": message,
        "error": {"type": error_type, "message": message},
    }, status


def public_document(item):
    """Return a document keyed by id, without portfolio, org, or ring."""
    if not isinstance(item, dict):
        return item
    if item.get("success") is False:
        return item
    attributes = item.get("attributes")
    if isinstance(attributes, dict):
        body = dict(attributes)
    else:
        body = {key: value for key, value in item.items() if key not in _HIDDEN}
    body["id"] = item.get("_id") or item.get("id")
    if item.get("_modified"):
        body["modified"] = item["_modified"]
    return body


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def public_collection(document):
    """The collection entity: its name is the schema, and it tracks the count."""
    if not isinstance(document, dict):
        return document
    name = document.get("name") or document.get("_id")
    return {
        "name": name,
        "count": _as_int(document.get("document_count")),
    }


def _controller_error(result, status):
    if not isinstance(result, dict) or result.get("success") is not False:
        return None
    code = status or result.get("status") or 400
    error = result.get("error")
    if isinstance(error, dict) and error.get("type"):
        return fail(error["type"], error.get("message") or result.get("message") or "Request failed", code)
    message = result.get("message") or (error if isinstance(error, str) else "") or "Request failed"
    error_type = "CollectionDeleted" if code == 409 else "RequestFailed"
    return fail(error_type, message, code)


def _saved(blueprint):
    return isinstance(blueprint, dict) and blueprint.get("success") is not False and (
        blueprint.get("irn") or blueprint.get("fields") is not None or blueprint.get("version")
    )


def _latest_blueprint(blueprints, portfolio, name):
    loaded = blueprints.get_blueprint(portfolio, name, "last")
    if not _saved(loaded):
        return None
    return loaded


def _read_collection(auth, portfolio, org, name, include_deleted=False):
    return auth.get_entity(
        "collection",
        portfolio_id=portfolio,
        org_id=org,
        collection_id=name,
        include_deleted=include_deleted,
    )


def _link_team(auth, team_id, org, name):
    if not team_id:
        return None
    linked = auth.create_rel(
        "team:collection",
        team_id=team_id,
        org_id=org,
        collection_name=name,
    )
    if not linked or not linked.get("success"):
        return fail(
            "CollectionRejected",
            (linked or {}).get("message") or "Team access was not saved",
            (linked or {}).get("status") or 400,
        )
    return None


def ensure_collection(auth, blueprints, portfolio, org, name, team_id=None):
    """Open the collection for this schema, or return the one already open.

    A missing schema is refused. This does not write a schema. A deleted
    collection entity is restored, because the next save regenerates it.
    """
    schema_name = str(name or "").strip()
    if not schema_name:
        return fail("InvalidCollection", "Schema name is required", 400)
    if _latest_blueprint(blueprints, portfolio, schema_name) is None:
        return fail("SchemaNotFound", "Schema was not found", 404)
    found = _read_collection(auth, portfolio, org, schema_name, include_deleted=True)
    document = (found or {}).get("document") if found and found.get("success") else None
    if isinstance(document, dict) and not entity_is_deleted(document):
        return public_collection(document), 200
    created = auth.create_entity(
        "collection",
        name=schema_name,
        portfolio_id=portfolio,
        org_id=org,
    )
    if not created or not created.get("success"):
        return fail(
            "CollectionRejected",
            (created or {}).get("message") or "Collection was not created",
            (created or {}).get("status") or 400,
        )
    refused = _link_team(auth, team_id, org, schema_name)
    if refused:
        return refused
    return public_collection(created.get("document") or {"name": schema_name}), 201


def create_collection(auth, blueprints, portfolio, org, schema_name, team_id=None):
    """Declare an empty collection. The schema must already exist."""
    opened, status = ensure_collection(
        auth, blueprints, portfolio, org, schema_name, team_id=team_id
    )
    if status == 200:
        return fail("CollectionExists", "Collection already exists", 409)
    return opened, status


def get_collection(auth, portfolio, org, name):
    found = _read_collection(auth, portfolio, org, name)
    if not found or not found.get("success"):
        return fail("CollectionNotFound", "Collection not found", 404)
    return public_collection(found.get("document") or {}), 200


def list_collections(auth, portfolio, org, team_id=None):
    listed = auth.list_entity(
        "collection",
        portfolio_id=portfolio,
        org_id=org,
        team_id=team_id,
    )
    if not listed or listed.get("success") is False:
        return fail(
            "RequestFailed",
            (listed or {}).get("message") or "Collections could not be listed",
            (listed or {}).get("status") or 400,
        )
    items = []
    for document in ((listed.get("document") or {}).get("items") or []):
        if not isinstance(document, dict):
            continue
        items.append(public_collection(document))
    return {"items": items}, 200


def _refuse_if_deleted(data, portfolio, org, collection):
    checker = getattr(data, "ring_is_deleted", None)
    if checker and checker(portfolio, org, collection):
        return fail("CollectionDeleted", "Collection is deleted", 409)
    return None


def create_document(data, auth, blueprints, portfolio, org, collection, fields, team_id=None):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    opened, status = ensure_collection(
        auth, blueprints, portfolio, org, collection, team_id=team_id
    )
    if status >= 400:
        return opened, status
    result, status = data.post_a_b(portfolio, org, collection, fields or {})
    failed = _controller_error(result, status)
    if failed:
        return failed
    return public_document((result or {}).get("item") or {}), status


def get_document(data, portfolio, org, collection, doc_id):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    result = data.get_a_b_c(portfolio, org, collection, doc_id)
    failed = _controller_error(result, None)
    if failed:
        body, code = failed
        return body, 404 if "could not be retrieved" in (body.get("message") or "").lower() else code
    return public_document(result), 200


def list_documents(data, portfolio, org, collection, limit=20, cursor=None):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    result = data.get_a_b(portfolio, org, collection, limit=limit, lastkey=cursor)
    failed = _controller_error(result, None)
    if failed:
        return failed
    items = [public_document(item) for item in (result or {}).get("items") or []]
    return {"items": items, "cursor": (result or {}).get("last_id")}, 200


def query_documents(data, blueprints, portfolio, org, collection, query):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    blueprint = _latest_blueprint(blueprints, portfolio, collection)
    if blueprint is None:
        return fail("SchemaNotFound", "Schema was not found", 404)
    try:
        translated = translate_document_query(blueprint, query or {})
    except DocumentQueryError as exc:
        return fail(exc.error_type, str(exc), 400)
    limit = (query or {}).get("limit") or 20
    cursor = (query or {}).get("cursor") or (query or {}).get("lastkey")
    result = data.get_a_b_query({
        "portfolio": portfolio,
        "org": org,
        "ring": collection,
        "operator": translated["operator"],
        "value": translated.get("value"),
        "filter": translated.get("filter") or {},
        "limit": int(limit),
        "lastkey": cursor,
        "sort": translated.get("sort"),
    })
    failed = _controller_error(result, None)
    if failed:
        return failed
    items = [public_document(item) for item in (result or {}).get("items") or []]
    return {"items": items, "cursor": (result or {}).get("last_id")}, 200


def update_document(data, portfolio, org, collection, doc_id, fields):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    result, status = data.put_a_b_c(portfolio, org, collection, doc_id, fields or {})
    failed = _controller_error(result, status)
    if failed:
        return failed
    loaded = data.get_a_b_c(portfolio, org, collection, doc_id)
    if isinstance(loaded, dict) and loaded.get("success") is False:
        return {"id": doc_id}, status
    return public_document(loaded), status


def delete_document(data, portfolio, org, collection, doc_id):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    result, status = data.delete_a_b_c(portfolio, org, collection, doc_id)
    failed = _controller_error(result, status)
    if failed:
        return failed
    return {"id": doc_id, "deleted": True}, status
