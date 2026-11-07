"""Config injected into controllers on Azure Functions."""

from renglo_api.config import load_env_config


def test_azure_settings_come_from_the_environment_when_no_file_is_present(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", "arbitiumpoc1")
    monkeypatch.setenv("AZURE_COSMOS_ACCOUNT_ENDPOINT", "https://arbitiumpoc1.documents.azure.com:443/")
    monkeypatch.setenv("AZURE_CLIENT_ID", "b67f7440-d957-4fb0-9e87-3ca29ca5db87")

    config = load_env_config(str(tmp_path / "missing.py"))

    assert config["AZURE_COSMOS_DATABASE_NAME"] == "arbitiumpoc1"
    assert config["AZURE_COSMOS_ACCOUNT_ENDPOINT"] == "https://arbitiumpoc1.documents.azure.com:443/"
    assert config["AZURE_CLIENT_ID"] == "b67f7440-d957-4fb0-9e87-3ca29ca5db87"


def test_environment_overrides_azure_settings_from_a_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "env_config.py"
    config_path.write_text(
        "AZURE_COSMOS_DATABASE_NAME = 'from-file'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", "from-env")

    config = load_env_config(str(config_path))

    assert config["AZURE_COSMOS_DATABASE_NAME"] == "from-env"
