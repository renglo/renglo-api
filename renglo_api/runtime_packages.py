"""Installed product package versions.

The Lambda image pip-installs the BOM pins. Their name and version live in
each distribution's metadata, which is what is actually running. Third-party
libraries such as Flask and boto3 are left out.

An extension is a distribution that ships ``blueprints/*.json``. The
white-label pack ships ``wl/locales/*.json``. ``renglo-api`` and ``renglo-lib``
are recognized by name.
"""

from __future__ import annotations

import importlib.metadata
import re
from typing import Any, Iterable

_BLUEPRINT = re.compile(r"(^|/)blueprints/[^/]+\.json$")
_WL_LOCALE = re.compile(r"(^|/)wl/locales/[^/]+\.json$")


def product_packages(distributions: Iterable[Any] | None = None) -> list[dict[str, str]]:
    """Return installed product packages sorted by name."""
    source = importlib.metadata.distributions() if distributions is None else distributions
    found: dict[str, dict[str, str]] = {}
    for dist in source:
        role = product_role(dist)
        if role is None:
            continue
        name = _dist_name(dist)
        version = _dist_version(dist)
        if not name or not version:
            continue
        found[name.lower()] = {"name": name, "version": version, "role": role}
    return [found[key] for key in sorted(found)]


def api_version(distributions: Iterable[Any] | None = None) -> str:
    """Version of the installed renglo-api distribution, when there is one."""
    for package in product_packages(distributions):
        if package["role"] == "api":
            return package["version"]
    if distributions is not None:
        return ""
    try:
        return importlib.metadata.version("renglo-api")
    except importlib.metadata.PackageNotFoundError:
        return ""


def product_role(dist: Any) -> str | None:
    name = _dist_name(dist).lower()
    files = _dist_files(dist)
    if name == "renglo-api":
        return "api"
    if name == "renglo-lib":
        return "lib"
    if any(_BLUEPRINT.search(path) for path in files):
        return "extension"
    if any(_WL_LOCALE.search(path) for path in files):
        return "wl"
    return None


def _dist_name(dist: Any) -> str:
    metadata = getattr(dist, "metadata", None)
    if metadata is None:
        return ""
    try:
        return str(metadata["Name"] or "").strip()
    except Exception:
        return ""


def _dist_version(dist: Any) -> str:
    try:
        return str(dist.version or "").strip()
    except Exception:
        return ""


def _dist_files(dist: Any) -> list[str]:
    try:
        files = dist.files
    except Exception:
        return []
    if not files:
        return []
    return [str(path).replace("\\", "/") for path in files]
