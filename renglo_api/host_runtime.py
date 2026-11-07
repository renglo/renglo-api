"""Whether this process is a hosted runtime or a local server."""

from __future__ import annotations

import os


def running_in_cloud() -> bool:
    """True on Lambda or Azure. False for a local process, including `func start`."""
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return True
    # Flex Consumption sets IDENTITY_ENDPOINT and does not set WEBSITE_INSTANCE_ID.
    # A local Functions host sets AZURE_FUNCTIONS_ENVIRONMENT=Development and neither.
    if os.getenv("IDENTITY_ENDPOINT") or os.getenv("WEBSITE_INSTANCE_ID"):
        return True
    azure_env = (os.getenv("AZURE_FUNCTIONS_ENVIRONMENT") or "").strip().lower()
    return bool(azure_env) and azure_env != "development"
