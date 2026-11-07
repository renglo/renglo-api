"""Cloud vs local detection for CORS and other host behavior."""

import pytest

from renglo_api.host_runtime import running_in_cloud


@pytest.fixture(autouse=True)
def _clear_host_env(monkeypatch):
    for name in (
        "AWS_LAMBDA_FUNCTION_NAME",
        "IDENTITY_ENDPOINT",
        "WEBSITE_INSTANCE_ID",
        "AZURE_FUNCTIONS_ENVIRONMENT",
        "FUNCTIONS_WORKER_RUNTIME",
    ):
        monkeypatch.delenv(name, raising=False)


def test_local_process_is_not_cloud():
    assert running_in_cloud() is False


def test_lambda_is_cloud(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "arbitium-backend")
    assert running_in_cloud() is True


def test_azure_flex_identity_endpoint_is_cloud(monkeypatch):
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://127.0.0.1:40342/msi/token")
    assert running_in_cloud() is True


def test_azure_instance_id_is_cloud(monkeypatch):
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "instance-1")
    assert running_in_cloud() is True


def test_local_func_start_is_not_cloud(monkeypatch):
    monkeypatch.setenv("AZURE_FUNCTIONS_ENVIRONMENT", "Development")
    monkeypatch.setenv("FUNCTIONS_WORKER_RUNTIME", "python")
    assert running_in_cloud() is False


def test_azure_production_environment_is_cloud(monkeypatch):
    monkeypatch.setenv("AZURE_FUNCTIONS_ENVIRONMENT", "Production")
    assert running_in_cloud() is True
