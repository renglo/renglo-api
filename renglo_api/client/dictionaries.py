"""Portfolio semantic dictionaries.

A dictionary is a versioned vocabulary of terms. Ontologies and schemas
cite a published dictionary by its id, ``name.version``. The first write is
a draft with the placeholder version ``x.y.z``. Publishing assigns a real
semantic version, marks that copy final, and opens a new draft for the next
edit. A cloned dictionary remembers its origin and is updated only by pulling.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from renglo.blueprint.dictionary_format import dictionary_errors, dictionary_skeleton
from renglo.blueprint.dictionary_version import classify_dictionary_change
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

_LOCKED = {"version", "status", "origin", "handle", "irn", "name", "id", "_id", "added", "modified"}


def fail(error_type, message, status):
    return {
        "success": False,
        "message": message,
        "error": {"type": error_type, "message": message},
    }, status


def _saved(document):
    return isinstance(document, dict) and document.get("success") is not False and (
        document.get("irn")
        or document.get("terms") is not None
        or document.get("version")
        or document.get("name")
    )


def public_dictionary(document):
    body = {
        key: value
        for key, value in (document or {}).items()
        if key not in _HIDDEN
    }
    body["name"] = (document or {}).get("name")
    body["version"] = (document or {}).get("version")
    body["status"] = (document or {}).get("status") or "draft"
    body["origin"] = (document or {}).get("origin") or ""
    body["id"] = (document or {}).get("id") or ""
    return body


def _origin(document):
    return str((document or {}).get("origin") or "").strip()


def _versions(blueprints, portfolio, name):
    listed = blueprints.list_dictionary_versions(portfolio, name)
    if not isinstance(listed, dict) or listed.get("success") is False:
        return None, fail(
            "RequestFailed",
            (listed or {}).get("message") if isinstance(listed, dict) else "Dictionaries could not be listed",
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


def _refresh(name, document):
    """Fill the envelope and term ids. A term id is ``name.key`` and the document id is ``name.version``."""
    body = dictionary_skeleton(name)
    body.update(document or {})
    body["name"] = name
    version = body.get("version") or DRAFT_VERSION
    if not isinstance(version, str) or not version.strip():
        version = DRAFT_VERSION
    body["version"] = version
    body["id"] = f"{name}.{version}"
    terms = body.get("terms")
    if isinstance(terms, dict):
        refreshed = {}
        for key, term in terms.items():
            if isinstance(term, dict):
                item = dict(term)
                item["id"] = f"{name}.{key}"
                if "external_mappings" not in item:
                    item["external_mappings"] = []
                if "status" not in item:
                    item["status"] = "active"
                refreshed[key] = item
            else:
                refreshed[key] = term
        body["terms"] = refreshed
    return body


def _template(name, dictionary=None):
    body = dictionary_skeleton(name)
    for key, value in (dictionary or {}).items():
        if key in _LOCKED:
            continue
        body[key] = value
    body["name"] = name
    body["version"] = DRAFT_VERSION
    body["status"] = "draft"
    body["origin"] = ""
    return _refresh(name, body)


def _store(blueprints, portfolio, name, document):
    document = _refresh(name, document)
    invalid = dictionary_errors(document)
    if invalid:
        return None, fail("InvalidDictionary", invalid, 400)
    saved = blueprints.put_dictionary_document(portfolio, name, document)
    if not isinstance(saved, dict) or saved.get("success") is False:
        return None, fail(
            "DictionaryRejected",
            (saved or {}).get("message") if isinstance(saved, dict) else "Dictionary was not saved",
            (saved or {}).get("status") if isinstance(saved, dict) else 400,
        )
    return saved.get("document") or document, None


def new_dictionary(blueprints, portfolio, name, dictionary=None):
    """Create the first draft. An existing name has to be committed or cloned."""
    dictionary_name = str(name or "").strip()
    if not dictionary_name:
        return fail("InvalidDictionary", "Dictionary name is required", 400)
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    if versions:
        return fail(
            "DictionaryExists",
            "Dictionary already exists. Change it with commitDictionary, or copy another dictionary with cloneDictionary.",
            409,
        )
    document, error = _store(blueprints, portfolio, dictionary_name, _template(dictionary_name, dictionary))
    if error:
        return error
    return public_dictionary(document), 201


def _latest_uri(uri):
    """Point a versioned dictionary URI at the current copy."""
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
    loaded = blueprints.fetch_dictionary(uri)
    if not _saved(loaded):
        message = (loaded or {}).get("message") if isinstance(loaded, dict) else "Dictionary URI could not be read"
        return None, fail("DictionaryUnreachable", message or "Dictionary URI could not be read", 400)
    return loaded, None


def clone_dictionary(blueprints, portfolio, uri):
    """Copy a dictionary from a URI and remember that URI as its origin."""
    source = str(uri or "").strip()
    if not source:
        return fail("InvalidDictionary", "Dictionary URI is required", 400)
    remote, error = _fetched(blueprints, source)
    if error:
        return error
    dictionary_name = str(remote.get("name") or "").strip()
    if not dictionary_name:
        return fail("InvalidDictionary", "Dictionary URI did not include a name", 400)
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    if versions:
        return fail(
            "DictionaryExists",
            "Dictionary already exists. Change it with commitDictionary, or copy another dictionary with cloneDictionary.",
            409,
        )
    copied = _refresh(dictionary_name, remote)
    copied["name"] = dictionary_name
    copied["origin"] = source
    copied["handle"] = portfolio
    copied.setdefault("status", remote.get("status") or "final")
    copied.setdefault("version", remote.get("version") or "1.0.0")
    copied["id"] = f"{dictionary_name}.{copied['version']}"
    document, error = _store(blueprints, portfolio, dictionary_name, copied)
    if error:
        return error
    return public_dictionary(document), 201


def pull_dictionary(blueprints, portfolio, name):
    """Replace the local copy with the latest dictionary at its origin."""
    dictionary_name = str(name or "").strip()
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    current = _current(versions)
    if current is None:
        return fail("DictionaryNotFound", "Dictionary was not found", 404)
    origin = _origin(current)
    if not origin:
        return fail("NotCloned", "pullDictionary only updates a dictionary that was cloned.", 400)
    remote, error = _fetched(blueprints, _latest_uri(origin))
    if error:
        return error
    copied = _refresh(dictionary_name, remote)
    copied["name"] = dictionary_name
    copied["origin"] = origin
    copied["handle"] = portfolio
    copied.setdefault("version", remote.get("version") or current.get("version") or "1.0.0")
    copied.setdefault("status", remote.get("status") or "final")
    copied["id"] = f"{dictionary_name}.{copied['version']}"
    document, error = _store(blueprints, portfolio, dictionary_name, copied)
    if error:
        return error
    previous = current.get("version")
    if previous and previous != document.get("version"):
        remover = getattr(blueprints, "delete_dictionary", None)
        if remover:
            remover(portfolio, dictionary_name, previous)
    return public_dictionary(document), 200


def get_dictionary(blueprints, portfolio, name, version=None):
    dictionary_name = str(name or "").strip()
    if not dictionary_name:
        return fail("InvalidDictionary", "Dictionary name is required", 400)
    if version:
        loaded = blueprints.get_dictionary(portfolio, dictionary_name, version)
        if not _saved(loaded):
            return fail("DictionaryNotFound", "Dictionary was not found", 404)
        return public_dictionary(loaded), 200
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    current = _current(versions)
    if current is None:
        return fail("DictionaryNotFound", "Dictionary was not found", 404)
    return public_dictionary(current), 200


def commit_dictionary(blueprints, portfolio, name, dictionary=None):
    """Apply an update to the draft. A cloned dictionary is refused."""
    dictionary_name = str(name or "").strip()
    if not dictionary_name:
        return fail("InvalidDictionary", "Dictionary name is required", 400)
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    if not versions:
        return fail("DictionaryNotFound", "Dictionary was not found", 404)
    if any(_origin(item) for item in versions):
        return fail(
            "ClonedDictionary",
            "This dictionary was cloned. Pull changes with pullDictionary.",
            400,
        )
    draft = _draft(versions)
    if draft is None:
        base = _published(versions) or {}
        draft = _template(dictionary_name)
        for key, value in base.items():
            if key in _LOCKED:
                continue
            draft[key] = value
        draft["name"] = dictionary_name
        draft["version"] = DRAFT_VERSION
        draft["status"] = "draft"
        draft["origin"] = ""
    merged = merge_blueprint(draft, dictionary or {})
    merged["name"] = dictionary_name
    merged["version"] = DRAFT_VERSION
    merged["status"] = "draft"
    merged["origin"] = ""
    document, error = _store(blueprints, portfolio, dictionary_name, merged)
    if error:
        return error
    return public_dictionary(document), 200


def _assigned_version(previous, draft):
    if previous is None:
        return "1.0.0"
    return next_version(previous.get("version"), classify_dictionary_change(previous, draft))


def publish_dictionary(blueprints, portfolio, name):
    """Freeze the draft as the next semantic version and open a new draft."""
    dictionary_name = str(name or "").strip()
    if not dictionary_name:
        return fail("InvalidDictionary", "Dictionary name is required", 400)
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    if not versions:
        return fail("DictionaryNotFound", "Dictionary was not found", 404)
    if any(_origin(item) for item in versions):
        return fail(
            "ClonedDictionary",
            "This dictionary was cloned. Pull changes with pullDictionary.",
            400,
        )
    draft = _draft(versions)
    if draft is None:
        return fail("DraftNotFound", "There is no draft to publish.", 404)
    version = _assigned_version(_published(versions), draft)
    final = dict(draft)
    final["name"] = dictionary_name
    final["version"] = version
    final["status"] = "final"
    final["origin"] = ""
    final.pop("_id", None)
    published, error = _store(blueprints, portfolio, dictionary_name, final)
    if error:
        return error
    nxt = dict(published)
    nxt["version"] = DRAFT_VERSION
    nxt["status"] = "draft"
    nxt["origin"] = ""
    nxt.pop("_id", None)
    opened, error = _store(blueprints, portfolio, dictionary_name, nxt)
    if error:
        return error
    return public_dictionary(published), 200


def list_dictionaries(blueprints, portfolio):
    listed = blueprints.list_dictionary_names(portfolio)
    if not isinstance(listed, dict) or listed.get("success") is False:
        return fail(
            "RequestFailed",
            (listed or {}).get("message") if isinstance(listed, dict) else "Dictionaries could not be listed",
            (listed or {}).get("status") if isinstance(listed, dict) else 400,
        )
    items = [{"name": name} for name in (listed.get("items") or []) if str(name or "").strip()]
    return {"items": items}, 200


def list_dictionary_versions(blueprints, portfolio, name):
    dictionary_name = str(name or "").strip()
    versions, error = _versions(blueprints, portfolio, dictionary_name)
    if error:
        return error
    if not versions:
        return fail("DictionaryNotFound", "Dictionary was not found", 404)
    items = [
        {"version": item.get("version"), "status": item.get("status") or "draft"}
        for item in versions
    ]
    items.sort(key=lambda item: (item["version"] == DRAFT_VERSION, str(item["version"])))
    return {"items": items}, 200


def deprecate_dictionary(blueprints, portfolio, name, version):
    dictionary_name = str(name or "").strip()
    dictionary_version = str(version or "").strip()
    if not dictionary_name or not dictionary_version:
        return fail("InvalidDictionary", "Dictionary name and version are required", 400)
    loaded = blueprints.get_dictionary(portfolio, dictionary_name, dictionary_version)
    if not _saved(loaded):
        return fail("DictionaryNotFound", "Dictionary was not found", 404)
    document = dict(loaded)
    document["status"] = "deprecated"
    stored, error = _store(blueprints, portfolio, dictionary_name, document)
    if error:
        return error
    return public_dictionary(stored), 200
