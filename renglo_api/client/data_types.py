"""Portfolio data types.

A data type is the blueprint a collection follows. Versions stay on the
blueprint. A collection stores the name and reads the current version.
"""

from __future__ import annotations


_HIDDEN = {
    "irn",
    "_id",
    "handle",
    "added",
    "modified",
    "success",
    "status",
    "message",
    "document",
}


def fail(error_type, message, status):
    return {
        "success": False,
        "message": message,
        "error": {"type": error_type, "message": message},
    }, status


def _saved(blueprint):
    return isinstance(blueprint, dict) and blueprint.get("success") is not False and (
        blueprint.get("irn") or blueprint.get("fields") is not None or blueprint.get("version")
    )


def public_data_type(blueprint):
    body = {
        key: value
        for key, value in (blueprint or {}).items()
        if key not in _HIDDEN
    }
    body["name"] = blueprint.get("name")
    body["version"] = blueprint.get("version")
    return body


def get_data_type(blueprints, portfolio, name, version=None):
    if not name:
        return fail("InvalidDataType", "Data type name is required", 400)
    loaded = blueprints.get_blueprint(portfolio, name, version or "last")
    if not _saved(loaded):
        return fail("DataTypeNotFound", "Data type was not found", 404)
    return public_data_type(loaded), 200


def create_data_type(blueprints, portfolio, name, definition=None):
    if not name:
        return fail("InvalidDataType", "Data type name is required", 400)
    body = dict(definition or {})
    body["name"] = name
    body.setdefault("label", name)
    body.setdefault("fields", [])
    created = blueprints.create_blueprint(body, user_handle=portfolio)
    if not isinstance(created, dict) or created.get("success") is False:
        message = (created or {}).get("message") if isinstance(created, dict) else "Data type was not saved"
        return fail("BlueprintRejected", message or "Data type was not saved", 400)
    document = created.get("document") or created
    return public_data_type(document), 201


def update_data_type(blueprints, portfolio, name, definition):
    if not name:
        return fail("InvalidDataType", "Data type name is required", 400)
    current = blueprints.get_blueprint(portfolio, name, "last")
    if not _saved(current):
        return fail("DataTypeNotFound", "Data type was not found", 404)
    updated = blueprints.update_blueprint(portfolio, name, data=dict(definition or {}))
    if not isinstance(updated, dict) or updated.get("success") is False:
        message = (updated or {}).get("message") if isinstance(updated, dict) else "Data type was not saved"
        return fail("BlueprintRejected", message or "Data type was not saved", 400)
    document = updated.get("document") or updated
    return public_data_type(document), 200
