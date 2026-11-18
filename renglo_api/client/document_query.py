"""Translate a /v1 document query into the operators DataController already accepts.

A filter is answered only when it is a prefix of a path, time, or geo index.
This module does not build DynamoDB expressions.
"""

from __future__ import annotations


class DocumentQueryError(Exception):
    def __init__(self, error_type, message):
        super().__init__(message)
        self.error_type = error_type


def _names(value):
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _indexes(blueprint):
    indexes = (blueprint or {}).get("indexes") or {}
    if not isinstance(indexes, dict):
        return [], [], []
    return (
        _names(indexes.get("path")),
        _names(indexes.get("time")),
        _names(indexes.get("geo")),
    )


def _is_prefix(keys, fields):
    if not keys or not fields or len(keys) > len(fields):
        return False
    return list(fields[: len(keys)]) == list(keys)


def sort_direction(sort):
    """Map the documented sort shapes onto the asc/desc string /_query stores."""
    if sort in ("asc", "desc"):
        return sort
    if isinstance(sort, dict):
        return "desc" if sort.get("direction") == "desc" else "asc"
    if isinstance(sort, list):
        for item in sort:
            if item == "desc":
                return "desc"
            if isinstance(item, dict) and item.get("direction") == "desc":
                return "desc"
        return "asc"
    return "asc"


def _joined(keys, filt):
    return ":".join("" if filt.get(key) is None else str(filt.get(key)) for key in keys)


def translate_document_query(blueprint, query):
    """Return the operator payload get_a_b_query already accepts.

    Raises DocumentQueryError(UnindexedFilter) when no index can answer it.
    """
    query = query or {}
    filt = query.get("filter") or {}
    if not isinstance(filt, dict):
        raise DocumentQueryError("UnindexedFilter", "filter must be an object")
    direction = sort_direction(query.get("sort"))
    keys = [str(key) for key in filt.keys()]
    path, time_fields, geo = _indexes(blueprint)

    if not keys:
        if path or geo:
            return {"operator": "begins_with", "value": "", "sort": direction}
        if time_fields:
            return {"operator": "chrono", "value": "", "sort": direction}
        raise DocumentQueryError(
            "UnindexedFilter",
            "The collection has no index that can answer this query",
        )

    if _is_prefix(keys, path):
        return {"operator": "begins_with", "value": _joined(keys, filt), "sort": direction}

    if _is_prefix(keys, time_fields):
        return {
            "operator": "chrono",
            "value": "",
            "filter": {
                "operator": "greater_than",
                "field": keys[-1],
                "value": "" if filt.get(keys[-1]) is None else str(filt.get(keys[-1])),
            },
            "sort": direction,
        }

    if _is_prefix(keys, geo):
        return {"operator": "begins_with", "value": _joined(keys, filt), "sort": direction}

    raise DocumentQueryError(
        "UnindexedFilter",
        "Filter is not a prefix of a path, time, or geo index",
    )
