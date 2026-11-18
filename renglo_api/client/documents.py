"""/v1 document calls.

The route parses the client API request and calls AuthController,
BlueprintController, and DataController. This module is that translation.
It does not store anything itself.
"""

from __future__ import annotations

from renglo.blueprint.semver import structural_indexes
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


def index_list(blueprint):
    indexes = structural_indexes(blueprint)
    listed = []
    if indexes["path"]:
        listed.append({"id": "path", "kind": "path", "fields": indexes["path"]})
    if indexes["time"]:
        listed.append({"id": "time", "kind": "time", "fields": indexes["time"]})
    if indexes["geo"]:
        listed.append({"id": "geo", "kind": "geo", "fields": indexes["geo"]})
    return listed


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _require_ring(auth, portfolio, org, name):
    found = auth.get_entity(
        "ring",
        portfolio_id=portfolio,
        org_id=org,
        ring_id=name,
    )
    if not found or not found.get("success"):
        return None, fail("CollectionNotFound", "Collection not found", 404)
    return found.get("document") or {}, None


def _latest_blueprint(blueprints, portfolio, name, version=None):
    loaded = blueprints.get_blueprint(portfolio, name, version or "last")
    if not _saved(loaded):
        return None
    return loaded


def _data_type_name(config):
    named = (config or {}).get("dataType") or (config or {}).get("data_type")
    text = str(named or "").strip()
    return text or None


def _remember_data_type(auth, portfolio, org, name, data_type):
    setter = getattr(auth, "set_ring_data_type", None)
    if setter is None or not data_type:
        return
    setter(portfolio, org, name, data_type)
    rings = getattr(auth, "rings", None)
    if isinstance(rings, dict):
        document = rings.get((portfolio, org, name))
        if isinstance(document, dict):
            document["data_type"] = data_type


def _followed_data_type(ring, collection_name):
    named = ring.get("data_type") if isinstance(ring, dict) else None
    if isinstance(named, str) and named.strip():
        return named.strip()
    pointer = (ring or {}).get("blueprint") or {}
    pointer_name = pointer.get("name")
    if isinstance(pointer_name, str) and pointer_name.strip():
        return pointer_name.strip()
    return collection_name


def _remember_version(auth, portfolio, org, name, version):
    setter = getattr(auth, "set_ring_blueprint", None)
    if setter is None or not version:
        return
    setter(
        portfolio,
        org,
        name,
        {"handle": portfolio, "name": name, "version": version},
    )


def _branch_blueprint(blueprints, config, portfolio, name, uri):
    absolute = str(uri or "").strip()
    if absolute and not absolute.startswith("http://") and not absolute.startswith("https://"):
        base = str((config or {}).get("BASE_URL") or "").rstrip("/")
        if not absolute.startswith("/"):
            absolute = "/" + absolute
        absolute = base + absolute
    copied = blueprints.extract_blueprint_data(absolute)
    if not isinstance(copied, dict) or copied.get("error"):
        return {
            "success": False,
            "message": (copied or {}).get("message") if isinstance(copied, dict) else "Blueprint URI was not copied",
        }
    copied["name"] = name
    copied["label"] = copied.get("label") or name
    copied.pop("version", None)
    return blueprints.create_blueprint(copied, user_handle=portfolio)


def create_collection(auth, blueprints, portfolio, org, name, config=None, team_id=None, app_config=None):
    config = config or {}
    if not name:
        return fail("InvalidCollection", "Collection name is required", 400)
    data_type = _data_type_name(config)
    if data_type:
        existing = _latest_blueprint(blueprints, portfolio, data_type)
        if existing is None:
            return fail("DataTypeNotFound", "Data type was not found", 404)
        version = existing.get("version") or "1.0.0"
    elif config.get("blueprint_uri"):
        created = _branch_blueprint(blueprints, app_config, portfolio, name, config["blueprint_uri"])
        if not isinstance(created, dict) or created.get("success") is False:
            message = (created or {}).get("message") if isinstance(created, dict) else "Blueprint was not saved"
            return fail("BlueprintRejected", message or "Blueprint was not saved", 400)
        document = created.get("document") or created
        version = document.get("version") or "1.0.0"
        data_type = name
    else:
        body = dict(config.get("blueprint_object") or {})
        body.setdefault("name", name)
        body.setdefault("label", name)
        body.setdefault("fields", [])
        created = blueprints.create_blueprint(body, user_handle=portfolio)
        if not isinstance(created, dict) or created.get("success") is False:
            message = (created or {}).get("message") if isinstance(created, dict) else "Blueprint was not saved"
            return fail("BlueprintRejected", message or "Blueprint was not saved", 400)
        document = created.get("document") or created
        version = document.get("version") or "1.0.0"
        data_type = name
    ring = auth.create_entity(
        "ring",
        name=name,
        portfolio_id=portfolio,
        org_id=org,
        blueprint_handle=portfolio,
        blueprint_name=data_type,
        blueprint_version=version,
    )
    if not ring or not ring.get("success"):
        return fail(
            "CollectionRejected",
            (ring or {}).get("message") or "Collection was not created",
            (ring or {}).get("status") or 400,
        )
    if team_id:
        linked = auth.create_rel(
            "team:ring",
            team_id=team_id,
            org_id=org,
            ring_name=name,
        )
        if not linked or not linked.get("success"):
            return fail(
                "CollectionRejected",
                (linked or {}).get("message") or "Team access was not saved",
                (linked or {}).get("status") or 400,
            )
    _remember_data_type(auth, portfolio, org, name, data_type)
    return {
        "name": name,
        "dataType": data_type,
        "version": version,
        "document_count": 0,
    }, 201


def get_collection(auth, blueprints, portfolio, org, name, version=None):
    ring, missing = _require_ring(auth, portfolio, org, name)
    if missing:
        return missing
    data_type = _followed_data_type(ring, name)
    blueprint = _latest_blueprint(blueprints, portfolio, data_type, version)
    return {
        "name": name,
        "dataType": data_type,
        "version": (blueprint or {}).get("version"),
        "document_count": _as_int(ring.get("document_count")),
        "blueprint": blueprint,
    }, 200


def list_collections(auth, portfolio, org, team_id=None):
    listed = auth.list_entity(
        "ring",
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
    for ring in ((listed.get("document") or {}).get("items") or []):
        collection_name = ring.get("name") or ring.get("_id")
        items.append({
            "name": collection_name,
            "dataType": _followed_data_type(ring, collection_name),
            "document_count": _as_int(ring.get("document_count")),
        })
    return {"items": items}, 200


def update_collection(auth, blueprints, portfolio, org, name, config):
    ring, missing = _require_ring(auth, portfolio, org, name)
    if missing:
        return missing
    config = dict(config or {})
    incoming = dict(config.get("blueprint_object") or {})
    for key, value in config.items():
        if key in ("blueprint_uri", "blueprint_object"):
            continue
        incoming[key] = value
    latest = _latest_blueprint(blueprints, portfolio, name)
    if (
        latest
        and "indexes" in incoming
        and structural_indexes(latest) != structural_indexes({"indexes": incoming.get("indexes")})
        and _as_int(ring.get("document_count")) > 0
    ):
        return fail(
            "ReindexRequired",
            "Index changes stay refused until a safe reindex exists",
            409,
        )
    updated = blueprints.update_blueprint(portfolio, name, data=incoming)
    if not isinstance(updated, dict) or updated.get("success") is False:
        return fail(
            "BlueprintRejected",
            (updated or {}).get("message") if isinstance(updated, dict) else "Blueprint was not saved",
            (updated or {}).get("status") or 400,
        )
    document = updated.get("document") or {}
    version = document.get("version")
    _remember_version(auth, portfolio, org, name, version)
    return {
        "name": name,
        "version": version,
        "document_count": _as_int(ring.get("document_count")),
    }, 200


def delete_collection(auth, portfolio, org, name):
    removed = auth.remove_ring_funnel(
        portfolio_id=portfolio,
        org_id=org,
        ring_id=name,
    )
    if not removed or not removed.get("success"):
        return fail(
            "CollectionNotFound" if (removed or {}).get("status") == 404 else "RequestFailed",
            (removed or {}).get("message") or "Collection was not deleted",
            (removed or {}).get("status") or 400,
        )
    return {"name": name, "deleted": True}, 200


def list_indexes(auth, blueprints, portfolio, org, name):
    _ring, missing = _require_ring(auth, portfolio, org, name)
    if missing:
        return missing
    blueprint = _latest_blueprint(blueprints, portfolio, name) or {}
    return {"items": index_list(blueprint)}, 200


def create_index(auth, blueprints, portfolio, org, name, index):
    ring, missing = _require_ring(auth, portfolio, org, name)
    if missing:
        return missing
    if _as_int(ring.get("document_count")) > 0:
        return fail(
            "ReindexRequired",
            "createIndex after documents exist stays refused until a safe reindex exists",
            409,
        )
    kind = str((index or {}).get("kind") or (index or {}).get("type") or "").strip()
    fields = (index or {}).get("fields")
    if kind == "path":
        names = fields
    elif kind in ("time", "geo"):
        field = (index or {}).get("field")
        if field:
            names = [field]
        elif isinstance(fields, list):
            names = fields
        else:
            names = []
    else:
        return fail("IndexKind", "Index kind must be path, time, or geo", 400)
    if not isinstance(names, list) or not names:
        return fail("IndexKind", "Index fields are required", 400)
    blueprint = _latest_blueprint(blueprints, portfolio, name) or {"fields": []}
    known = {
        str(field.get("name"))
        for field in (blueprint.get("fields") or [])
        if isinstance(field, dict) and field.get("name")
    }
    unknown = [str(field_name) for field_name in names if str(field_name) not in known]
    if unknown:
        return fail("UnknownField", "Index field is not on the blueprint: " + ", ".join(unknown), 400)
    indexes = dict(blueprint.get("indexes") or {})
    indexes[kind] = [str(field_name) for field_name in names]
    updated = blueprints.update_blueprint(portfolio, name, data={"indexes": indexes})
    if not isinstance(updated, dict) or updated.get("success") is False:
        return fail(
            "BlueprintRejected",
            (updated or {}).get("message") if isinstance(updated, dict) else "Index was not saved",
            400,
        )
    document = updated.get("document") or {}
    _remember_version(auth, portfolio, org, name, document.get("version"))
    return {"items": index_list(document)}, 201


def delete_index(auth, portfolio, org, name, index_id):
    _ring, missing = _require_ring(auth, portfolio, org, name)
    if missing:
        return missing
    return fail(
        "ReindexRequired",
        f"deleteIndex for {index_id} stays refused until a safe reindex exists",
        409,
    )


def _refuse_if_deleted(data, portfolio, org, collection):
    checker = getattr(data, "ring_is_deleted", None)
    if checker and checker(portfolio, org, collection):
        return fail("CollectionDeleted", "Collection is deleted", 409)
    return None


def create_document(data, auth, portfolio, org, collection, fields):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    _ring, missing = _require_ring(auth, portfolio, org, collection)
    if missing:
        return missing
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
        return fail("CollectionNotFound", "Collection blueprint was not found", 404)
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


def upsert_document(data, portfolio, org, collection, doc_id, fields):
    refused = _refuse_if_deleted(data, portfolio, org, collection)
    if refused:
        return refused
    existing = data.get_a_b_c(portfolio, org, collection, doc_id)
    missing = not isinstance(existing, dict) or existing.get("success") is False
    if missing:
        result, status = data.post_a_b(
            portfolio, org, collection, fields or {}, document_id=doc_id
        )
    else:
        result, status = data.put_a_b_c(portfolio, org, collection, doc_id, fields or {})
    failed = _controller_error(result, status)
    if failed:
        return failed
    if missing:
        return public_document((result or {}).get("item") or {"_id": doc_id}), status
    loaded = data.get_a_b_c(portfolio, org, collection, doc_id)
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


def count_documents(auth, portfolio, org, collection, query=None):
    if (query or {}).get("filter"):
        return fail(
            "FilteredCountUnavailable",
            "count reads document_count on the collection and does not apply a filter",
            400,
        )
    ring, missing = _require_ring(auth, portfolio, org, collection)
    if missing:
        return missing
    return {"count": _as_int(ring.get("document_count"))}, 200
