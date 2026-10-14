"""CORS allow-list from config, including a wildcard."""

import pytest

from renglo_api.cors_origins import build_cors_origins, parse_cors_allowed_origins


def test_json_list_is_appended_and_trailing_slash_stripped():
    origins = build_cors_origins(
        {
            "FE_BASE_URL": "https://staging.example.amplifyapp.com/",
            "CORS_ALLOWED_ORIGINS": '["https://lab.arbitium.com/"]',
        },
        include_dev=False,
    )
    assert origins == [
        "https://staging.example.amplifyapp.com",
        "https://lab.arbitium.com",
    ]


def test_star_opens_every_origin():
    assert parse_cors_allowed_origins('["https://lab.arbitium.com", "*"]') == ["*"]
    assert build_cors_origins(
        {"FE_BASE_URL": "https://console.example.com", "CORS_ALLOWED_ORIGINS": '["*"]'},
        include_dev=True,
    ) == "*"


def test_app_fe_and_dev_origins_stay_available():
    origins = build_cors_origins(
        {"APP_FE_BASE_URL": "https://lab.arbitium.com"},
        include_dev=True,
    )
    assert "https://lab.arbitium.com" in origins
    assert "http://127.0.0.1:5173" in origins


def test_invalid_json_list_raises():
    with pytest.raises(ValueError):
        parse_cors_allowed_origins('{"origins": "*"}')
