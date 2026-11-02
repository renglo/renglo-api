"""Azure host entries for the Renglo API.

Sibling of lambda_handler.py. The AWS image command stays
``renglo_api.lambda_handler.lambda_handler``. An Azure Function app
points at the callables in this module. Nothing on the AWS path
imports this file.

``azure_handler`` will serve the Flask app (``renglo_api.application:app``).
``ingress_handler`` will call
``renglo.schd.ingress_worker.run_ingress_webhook_worker`` when a queue
message arrives after the HTTP request has already returned.
"""

from __future__ import annotations


def azure_handler(req):
    """HTTP entry. Serves the same Flask app the Lambda handler wraps."""
    raise NotImplementedError(
        "renglo_api.azure_handler is a positioning placeholder. "
        "The AWS entry remains renglo_api.lambda_handler.lambda_handler."
    )


def ingress_handler(message):
    """Queue entry for webhook work that finishes after the HTTP response."""
    raise NotImplementedError(
        "renglo_api.azure_handler.ingress_handler is a positioning placeholder. "
        "Delayed ingress on AWS stays inside lambda_handler via the "
        "renglo_ingress_worker flag."
    )
