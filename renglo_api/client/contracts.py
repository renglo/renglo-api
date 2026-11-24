"""Portfolio schemas.

A schema and a blueprint are the same document. The first write is a draft
with the placeholder version ``x.y.z``. Publishing assigns a real semantic
version, marks that copy final, and opens a new draft for the next edit.
A cloned schema remembers its origin and is updated only by pulling.
``dictionaries`` names the semantic dictionaries this schema cites.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from renglo.blueprint.schema_format import schema_errors
from renglo.blueprint.semver import classify_change, merge_blueprint, next_version, parse_version


DRAFT_VERSION = "x.y.z"

_HIDDEN = {
    "irn",
    "_id",
    "handle",
    "added",
    "modified",
    "success",
    "message",
    "document",
}

_LOCKED = {"version", "status", "origin", "handle", "irn", "name", "_id", "added", "modified"}


def fail(error_type, message, status):
    return {
        "success": False,
        "message": message,
        "error": {"type": error_type, "message": message},
    }, status


def _saved(blueprint):
    return isinstance(blueprint, dict) and blueprint.get("success") is not False and (
        blueprint.get("irn") or blueprint.get("fields") is not None or blueprint.get("version") or blueprint.get("name")
    )


def public_schema(blueprint):
    body = {
        key: value
        for key, value in (blueprint or {}).items()
        if key not in _HIDDEN
    }
    body["name"] = (blueprint or {}).get("name")
    body["version"] = (blueprint or {}).get("version")
    body["status"] = (blueprint or {}).get("status") or "draft"
    body["origin"] = (blueprint or {}).get("origin") or ""
    return body


def _origin(document):
    return str((document or {}).get("origin") or "").strip()


def _versions(blueprints, portfolio, name):
    listed = blueprints.list_blueprint_versions(portfolio, name)
    if not isinstance(listed, dict) or listed.get("success") is False:
        return None, fail(
            "RequestFailed",
            (listed or {}).get("message") if isinstance(listed, dict) else "Schemas could not be listed",
            (listed or {}).get("status") if isinstance(listed, dict) else 400,
        )
    items = [item for item in (listed.get("items") or []) if isinstance(item, dict)]
    return items, None


def _draft(versions):
    for item in versions:
        if item.get("version") == DRAFT_VERSION and (item.get("status") or "draft") == "draft":
            return item
    return None


def _published(versions):
    ranked = []
    for item in versions:
        number = parse_version(item.get("version"))
        if number is None:
            continue
        ranked.append((number, item))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0])
    return ranked[-1][1]


def _current(versions):
    return _draft(versions) or _published(versions)


def _skeleton(name):
    """The blueprint envelope every schema starts from."""
    return {
        "name": name,
        "label": name,
        "description": "",
        "fields": [],
        "license": "CC BY",
        "dictionaries": [],
        "public": True,
        "singleton": False,
        "blueprint_origin": "",
        "uri": "",
        "version": DRAFT_VERSION,
        "status": "draft",
        "origin": "",
    }


def _ensure_skeleton(name, document):
    """Fill keys an empty body leaves out. Values already on the document stay."""
    body = _skeleton(name)
    body.update(document or {})
    body["name"] = name
    return body


def _template(name, schema=None):
    body = _skeleton(name)
    for key, value in (schema or {}).items():
        if key in _LOCKED:
            continue
        body[key] = value
    body["name"] = name
    body["version"] = DRAFT_VERSION
    body["status"] = "draft"
    body["origin"] = ""
    return body


def _store(blueprints, portfolio, name, document):
    document = _ensure_skeleton(name, document)
    invalid = schema_errors(document)
    if invalid:
        return None, fail("InvalidSchema", invalid, 400)
    saved = blueprints.put_blueprint_document(portfolio, name, document)
    if not isinstance(saved, dict) or saved.get("success") is False:
        return None, fail(
            "BlueprintRejected",
            (saved or {}).get("message") if isinstance(saved, dict) else "Schema was not saved",
            (saved or {}).get("status") if isinstance(saved, dict) else 400,
        )
    return saved.get("document") or document, None


def new_schema(blueprints, portfolio, name, schema=None):
    """Create the first draft. An existing name has to be committed or cloned."""
    schema_name = str(name or "").strip()
    if not schema_name:
        return fail("InvalidSchema", "Schema name is required", 400)
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    if versions:
        return fail(
            "SchemaExists",
            "Schema already exists. Change it with commitSchema, or copy another schema with cloneSchema.",
            409,
        )
    document, error = _store(blueprints, portfolio, schema_name, _template(schema_name, schema))
    if error:
        return error
    return public_schema(document), 201


def _latest_uri(uri):
    """Point a versioned schema URI at the current copy."""
    parts = urlparse(str(uri or "").strip())
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return str(uri or "").strip()
    tail = segments[-1]
    if tail == "last" or tail == DRAFT_VERSION or parse_version(tail):
        segments[-1] = "last"
        path = "/" + "/".join(segments)
        return urlunparse((parts.scheme, parts.netloc, path, "", "", ""))
    return str(uri).strip()


def _fetched(blueprints, uri):
    loaded = blueprints.fetch_blueprint(uri)
    if not _saved(loaded):
        message = (loaded or {}).get("message") if isinstance(loaded, dict) else "Schema URI could not be read"
        return None, fail("SchemaUnreachable", message or "Schema URI could not be read", 400)
    return loaded, None


def clone_schema(blueprints, portfolio, uri):
    """Copy a schema from a URI and remember that URI as its origin."""
    source = str(uri or "").strip()
    if not source:
        return fail("InvalidSchema", "Schema URI is required", 400)
    remote, error = _fetched(blueprints, source)
    if error:
        return error
    schema_name = str(remote.get("name") or "").strip()
    if not schema_name:
        return fail("InvalidSchema", "Schema URI did not include a name", 400)
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    if versions:
        return fail(
            "SchemaExists",
            "Schema already exists. Change it with commitSchema, or copy another schema with cloneSchema.",
            409,
        )
    copied = dict(remote)
    copied["name"] = schema_name
    copied["origin"] = source
    copied["handle"] = portfolio
    copied.setdefault("label", schema_name)
    copied.setdefault("fields", [])
    copied.setdefault("status", remote.get("status") or "final")
    copied.setdefault("version", remote.get("version") or "1.0.0")
    document, error = _store(blueprints, portfolio, schema_name, copied)
    if error:
        return error
    return public_schema(document), 201


def pull_schema(blueprints, portfolio, name):
    """Replace the local copy with the latest schema at its origin."""
    schema_name = str(name or "").strip()
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    current = _current(versions)
    if current is None:
        return fail("SchemaNotFound", "Schema was not found", 404)
    origin = _origin(current)
    if not origin:
        return fail("NotCloned", "pullSchema only updates a schema that was cloned.", 400)
    remote, error = _fetched(blueprints, _latest_uri(origin))
    if error:
        return error
    copied = dict(remote)
    copied["name"] = schema_name
    copied["origin"] = origin
    copied["handle"] = portfolio
    copied.setdefault("label", schema_name)
    copied.setdefault("fields", [])
    copied.setdefault("version", remote.get("version") or current.get("version") or "1.0.0")
    copied.setdefault("status", remote.get("status") or "final")
    document, error = _store(blueprints, portfolio, schema_name, copied)
    if error:
        return error
    previous = current.get("version")
    if previous and previous != document.get("version"):
        remover = getattr(blueprints, "delete_blueprint", None)
        if remover:
            remover(portfolio, schema_name, previous)
    return public_schema(document), 200


def get_schema(blueprints, portfolio, name, version=None):
    schema_name = str(name or "").strip()
    if not schema_name:
        return fail("InvalidSchema", "Schema name is required", 400)
    if version:
        loaded = blueprints.get_blueprint(portfolio, schema_name, version)
        if not _saved(loaded):
            return fail("SchemaNotFound", "Schema was not found", 404)
        return public_schema(loaded), 200
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    current = _current(versions)
    if current is None:
        return fail("SchemaNotFound", "Schema was not found", 404)
    return public_schema(current), 200


def commit_schema(blueprints, portfolio, name, schema=None):
    """Apply an update to the draft. A cloned schema is refused."""
    schema_name = str(name or "").strip()
    if not schema_name:
        return fail("InvalidSchema", "Schema name is required", 400)
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    if not versions:
        return fail("SchemaNotFound", "Schema was not found", 404)
    if any(_origin(item) for item in versions):
        return fail(
            "ClonedSchema",
            "This schema was cloned. Pull changes with pullSchema.",
            400,
        )
    draft = _draft(versions)
    if draft is None:
        base = _published(versions) or {}
        draft = _template(schema_name)
        for key, value in base.items():
            if key in _LOCKED:
                continue
            draft[key] = value
        draft["name"] = schema_name
        draft["version"] = DRAFT_VERSION
        draft["status"] = "draft"
        draft["origin"] = ""
    merged = merge_blueprint(draft, schema or {})
    merged["name"] = schema_name
    merged["version"] = DRAFT_VERSION
    merged["status"] = "draft"
    merged["origin"] = ""
    document, error = _store(blueprints, portfolio, schema_name, merged)
    if error:
        return error
    return public_schema(document), 200


def _assigned_version(previous, draft):
    if previous is None:
        return "1.0.0"
    return next_version(previous.get("version"), classify_change(previous, draft))


def publish_schema(blueprints, portfolio, name):
    """Freeze the draft as the next semantic version and open a new draft."""
    schema_name = str(name or "").strip()
    if not schema_name:
        return fail("InvalidSchema", "Schema name is required", 400)
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    if not versions:
        return fail("SchemaNotFound", "Schema was not found", 404)
    if any(_origin(item) for item in versions):
        return fail(
            "ClonedSchema",
            "This schema was cloned. Pull changes with pullSchema.",
            400,
        )
    draft = _draft(versions)
    if draft is None:
        return fail("DraftNotFound", "There is no draft to publish.", 404)
    version = _assigned_version(_published(versions), draft)
    final = dict(draft)
    final["name"] = schema_name
    final["version"] = version
    final["status"] = "final"
    final["origin"] = ""
    final.pop("_id", None)
    published, error = _store(blueprints, portfolio, schema_name, final)
    if error:
        return error
    nxt = dict(published)
    nxt["version"] = DRAFT_VERSION
    nxt["status"] = "draft"
    nxt["origin"] = ""
    nxt.pop("_id", None)
    opened, error = _store(blueprints, portfolio, schema_name, nxt)
    if error:
        return error
    return public_schema(published), 200


def list_schemas(blueprints, portfolio):
    listed = blueprints.list_blueprint_names(portfolio)
    if not isinstance(listed, dict) or listed.get("success") is False:
        return fail(
            "RequestFailed",
            (listed or {}).get("message") if isinstance(listed, dict) else "Schemas could not be listed",
            (listed or {}).get("status") if isinstance(listed, dict) else 400,
        )
    items = [{"name": name} for name in (listed.get("items") or []) if str(name or "").strip()]
    return {"items": items}, 200


def list_versions(blueprints, portfolio, name):
    schema_name = str(name or "").strip()
    versions, error = _versions(blueprints, portfolio, schema_name)
    if error:
        return error
    if not versions:
        return fail("SchemaNotFound", "Schema was not found", 404)
    items = [
        {"version": item.get("version"), "status": item.get("status") or "draft"}
        for item in versions
    ]
    items.sort(key=lambda item: (item["version"] == DRAFT_VERSION, str(item["version"])))
    return {"items": items}, 200


def deprecate_schema(blueprints, portfolio, name, version):
    schema_name = str(name or "").strip()
    schema_version = str(version or "").strip()
    if not schema_name or not schema_version:
        return fail("InvalidSchema", "Schema name and version are required", 400)
    loaded = blueprints.get_blueprint(portfolio, schema_name, schema_version)
    if not _saved(loaded):
        return fail("SchemaNotFound", "Schema was not found", 404)
    document = dict(loaded)
    document["status"] = "deprecated"
    stored, error = _store(blueprints, portfolio, schema_name, document)
    if error:
        return error
    return public_schema(stored), 200
