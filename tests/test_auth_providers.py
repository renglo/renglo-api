"""Public provider list drops secrets and disabled entries."""

from renglo_api.auth_providers import public_auth_providers


def test_enabled_providers_keep_only_public_fields():
    raw = {
        "providers": [
            {
                "id": "microsoft",
                "name": "Microsoft",
                "type": "oidc",
                "cognito_provider_name": "MicrosoftEntra",
                "enabled": False,
                "display_name": "Continue with Microsoft",
                "secret": "example/renglo/auth/microsoft",
                "display_order": 30,
            },
            {
                "id": "okta",
                "name": "Okta",
                "type": "oidc",
                "cognito_provider_name": "Okta",
                "enabled": True,
                "display_name": "Continue with Okta",
                "icon": "okta",
                "display_order": 20,
                "client_secret": "do-not-return",
            },
            {
                "id": "google",
                "name": "Google",
                "type": "social",
                "cognito_provider_name": "Google",
                "enabled": True,
                "display_name": "Continue with Google",
                "icon": "google",
                "display_order": 10,
            },
        ]
    }
    published = public_auth_providers(raw)
    assert [item["id"] for item in published] == ["google", "okta"]
    assert published[0]["type"] == "social"
    assert published[1]["type"] == "oidc"
    assert all("secret" not in item and "client_secret" not in item for item in published)


def test_empty_and_invalid_payloads():
    assert public_auth_providers(None) == []
    assert public_auth_providers("") == []
    assert public_auth_providers("not-json") == []
    assert public_auth_providers("[]") == []
