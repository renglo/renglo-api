"""Portfolio ontologies.

An ontology is a versioned document of types, functional domains, and
relationships. The first write is a draft with the placeholder version
``x.y.z``. Publishing assigns a real semantic version, marks that copy
final, and opens a new draft for the next edit. A cloned ontology remembers
its origin and is updated only by pulling.

The document shape is domain agnostic. Cloud infrastructure is one example
of the same fields.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from renglo.blueprint.ontology_format import ontology_errors, ontology_skeleton
from renglo.blueprint.ontology_version import classify_ontology_change
from renglo.blueprint.semver import merge_blueprint, next_version, parse_version


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


def _saved(document):
    return isinstance(document, dict) and document.get("success") is not False and (
        document.get("irn")
        or document.get("node_types") is not None
        or document.get("version")
        or document.get("name")
    )


def public_ontology(document):
    body = {
        key: value
        for key, value in (document or {}).items()
        if key not in _HIDDEN
    }
    body["name"] = (document or {}).get("name")
    body["version"] = (document or {}).get("version")
    body["status"] = (document or {}).get("status") or "draft"
    body["origin"] = (document or {}).get("origin") or ""
    return body


def _origin(document):
    return str((document or {}).get("origin") or "").strip()


def _versions(blueprints, portfolio, name):
    listed = blueprints.list_ontology_versions(portfolio, name)
    if not isinstance(listed, dict) or listed.get("success") is False:
        return None, fail(
            "RequestFailed",
            (listed or {}).get("message") if isinstance(listed, dict) else "Ontologies could not be listed",
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


def _ensure_skeleton(name, document):
    """Fill keys an empty body leaves out. Values already on the document stay."""
    body = ontology_skeleton(name)
    body.update(document or {})
    body["name"] = name
    return body


def _template(name, ontology=None):
    body = ontology_skeleton(name)
    for key, value in (ontology or {}).items():
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
    invalid = ontology_errors(document)
    if invalid:
        return None, fail("InvalidOntology", invalid, 400)
    saved = blueprints.put_ontology_document(portfolio, name, document)
    if not isinstance(saved, dict) or saved.get("success") is False:
        return None, fail(
            "OntologyRejected",
            (saved or {}).get("message") if isinstance(saved, dict) else "Ontology was not saved",
            (saved or {}).get("status") if isinstance(saved, dict) else 400,
        )
    return saved.get("document") or document, None


def new_ontology(blueprints, portfolio, name, ontology=None):
    """Create the first draft. An existing name has to be committed or cloned."""
    ontology_name = str(name or "").strip()
    if not ontology_name:
        return fail("InvalidOntology", "Ontology name is required", 400)
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    if versions:
        return fail(
            "OntologyExists",
            "Ontology already exists. Change it with commitOntology, or copy another ontology with cloneOntology.",
            409,
        )
    document, error = _store(blueprints, portfolio, ontology_name, _template(ontology_name, ontology))
    if error:
        return error
    return public_ontology(document), 201


def _latest_uri(uri):
    """Point a versioned ontology URI at the current copy."""
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
    loaded = blueprints.fetch_ontology(uri)
    if not _saved(loaded):
        message = (loaded or {}).get("message") if isinstance(loaded, dict) else "Ontology URI could not be read"
        return None, fail("OntologyUnreachable", message or "Ontology URI could not be read", 400)
    return loaded, None


def clone_ontology(blueprints, portfolio, uri):
    """Copy an ontology from a URI and remember that URI as its origin."""
    source = str(uri or "").strip()
    if not source:
        return fail("InvalidOntology", "Ontology URI is required", 400)
    remote, error = _fetched(blueprints, source)
    if error:
        return error
    ontology_name = str(remote.get("name") or "").strip()
    if not ontology_name:
        return fail("InvalidOntology", "Ontology URI did not include a name", 400)
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    if versions:
        return fail(
            "OntologyExists",
            "Ontology already exists. Change it with commitOntology, or copy another ontology with cloneOntology.",
            409,
        )
    copied = _ensure_skeleton(ontology_name, remote)
    copied["name"] = ontology_name
    copied["origin"] = source
    copied["handle"] = portfolio
    copied.setdefault("status", remote.get("status") or "final")
    copied.setdefault("version", remote.get("version") or "1.0.0")
    document, error = _store(blueprints, portfolio, ontology_name, copied)
    if error:
        return error
    return public_ontology(document), 201


def pull_ontology(blueprints, portfolio, name):
    """Replace the local copy with the latest ontology at its origin."""
    ontology_name = str(name or "").strip()
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    current = _current(versions)
    if current is None:
        return fail("OntologyNotFound", "Ontology was not found", 404)
    origin = _origin(current)
    if not origin:
        return fail("NotCloned", "pullOntology only updates an ontology that was cloned.", 400)
    remote, error = _fetched(blueprints, _latest_uri(origin))
    if error:
        return error
    copied = _ensure_skeleton(ontology_name, remote)
    copied["name"] = ontology_name
    copied["origin"] = origin
    copied["handle"] = portfolio
    copied.setdefault("version", remote.get("version") or current.get("version") or "1.0.0")
    copied.setdefault("status", remote.get("status") or "final")
    document, error = _store(blueprints, portfolio, ontology_name, copied)
    if error:
        return error
    previous = current.get("version")
    if previous and previous != document.get("version"):
        remover = getattr(blueprints, "delete_ontology", None)
        if remover:
            remover(portfolio, ontology_name, previous)
    return public_ontology(document), 200


def get_ontology(blueprints, portfolio, name, version=None):
    ontology_name = str(name or "").strip()
    if not ontology_name:
        return fail("InvalidOntology", "Ontology name is required", 400)
    if version:
        loaded = blueprints.get_ontology(portfolio, ontology_name, version)
        if not _saved(loaded):
            return fail("OntologyNotFound", "Ontology was not found", 404)
        return public_ontology(loaded), 200
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    current = _current(versions)
    if current is None:
        return fail("OntologyNotFound", "Ontology was not found", 404)
    return public_ontology(current), 200


def commit_ontology(blueprints, portfolio, name, ontology=None):
    """Apply an update to the draft. A cloned ontology is refused."""
    ontology_name = str(name or "").strip()
    if not ontology_name:
        return fail("InvalidOntology", "Ontology name is required", 400)
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    if not versions:
        return fail("OntologyNotFound", "Ontology was not found", 404)
    if any(_origin(item) for item in versions):
        return fail(
            "ClonedOntology",
            "This ontology was cloned. Pull changes with pullOntology.",
            400,
        )
    draft = _draft(versions)
    if draft is None:
        base = _published(versions) or {}
        draft = _template(ontology_name)
        for key, value in base.items():
            if key in _LOCKED:
                continue
            draft[key] = value
        draft["name"] = ontology_name
        draft["version"] = DRAFT_VERSION
        draft["status"] = "draft"
        draft["origin"] = ""
    merged = merge_blueprint(draft, ontology or {})
    merged["name"] = ontology_name
    merged["version"] = DRAFT_VERSION
    merged["status"] = "draft"
    merged["origin"] = ""
    document, error = _store(blueprints, portfolio, ontology_name, merged)
    if error:
        return error
    return public_ontology(document), 200


def _assigned_version(previous, draft):
    if previous is None:
        return "1.0.0"
    return next_version(previous.get("version"), classify_ontology_change(previous, draft))


def publish_ontology(blueprints, portfolio, name):
    """Freeze the draft as the next semantic version and open a new draft."""
    ontology_name = str(name or "").strip()
    if not ontology_name:
        return fail("InvalidOntology", "Ontology name is required", 400)
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    if not versions:
        return fail("OntologyNotFound", "Ontology was not found", 404)
    if any(_origin(item) for item in versions):
        return fail(
            "ClonedOntology",
            "This ontology was cloned. Pull changes with pullOntology.",
            400,
        )
    draft = _draft(versions)
    if draft is None:
        return fail("DraftNotFound", "There is no draft to publish.", 404)
    version = _assigned_version(_published(versions), draft)
    final = dict(draft)
    final["name"] = ontology_name
    final["version"] = version
    final["status"] = "final"
    final["origin"] = ""
    final.pop("_id", None)
    published, error = _store(blueprints, portfolio, ontology_name, final)
    if error:
        return error
    nxt = dict(published)
    nxt["version"] = DRAFT_VERSION
    nxt["status"] = "draft"
    nxt["origin"] = ""
    nxt.pop("_id", None)
    opened, error = _store(blueprints, portfolio, ontology_name, nxt)
    if error:
        return error
    return public_ontology(published), 200


def list_ontologies(blueprints, portfolio):
    listed = blueprints.list_ontology_names(portfolio)
    if not isinstance(listed, dict) or listed.get("success") is False:
        return fail(
            "RequestFailed",
            (listed or {}).get("message") if isinstance(listed, dict) else "Ontologies could not be listed",
            (listed or {}).get("status") if isinstance(listed, dict) else 400,
        )
    items = [{"name": name} for name in (listed.get("items") or []) if str(name or "").strip()]
    return {"items": items}, 200


def list_ontology_versions(blueprints, portfolio, name):
    ontology_name = str(name or "").strip()
    versions, error = _versions(blueprints, portfolio, ontology_name)
    if error:
        return error
    if not versions:
        return fail("OntologyNotFound", "Ontology was not found", 404)
    items = [
        {"version": item.get("version"), "status": item.get("status") or "draft"}
        for item in versions
    ]
    items.sort(key=lambda item: (item["version"] == DRAFT_VERSION, str(item["version"])))
    return {"items": items}, 200


def deprecate_ontology(blueprints, portfolio, name, version):
    ontology_name = str(name or "").strip()
    ontology_version = str(version or "").strip()
    if not ontology_name or not ontology_version:
        return fail("InvalidOntology", "Ontology name and version are required", 400)
    loaded = blueprints.get_ontology(portfolio, ontology_name, ontology_version)
    if not _saved(loaded):
        return fail("OntologyNotFound", "Ontology was not found", 404)
    document = dict(loaded)
    document["status"] = "deprecated"
    stored, error = _store(blueprints, portfolio, ontology_name, document)
    if error:
        return error
    return public_ontology(stored), 200
