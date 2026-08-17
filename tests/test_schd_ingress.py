"""Unit tests for universal EventBridge ingress dispatcher."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
_INGRESS = _API_ROOT / "renglo_api" / "routes" / "schd_ingress.py"

_spec = importlib.util.spec_from_file_location("schd_ingress", _INGRESS)
assert _spec and _spec.loader
schd_ingress = importlib.util.module_from_spec(_spec)
sys.modules["schd_ingress"] = schd_ingress
_spec.loader.exec_module(schd_ingress)

CHANNEL_HANDLERS = schd_ingress.CHANNEL_HANDLERS
check_ingress_secret = schd_ingress.check_ingress_secret
dispatch_ingress = schd_ingress.dispatch_ingress
normalize_detail = schd_ingress.normalize_detail
presented_ingress_secret = schd_ingress.presented_ingress_secret
webhook_payload_for_channel = schd_ingress.webhook_payload_for_channel


def test_normalize_detail_unwraps_envelope():
    detail = normalize_detail({"detail": {"type": "webhook", "channel": "whatsapp"}})
    assert detail == {"type": "webhook", "channel": "whatsapp"}


def test_normalize_detail_parses_string_detail():
    detail = normalize_detail({"detail": '{"portfolio":"p1"}'})
    assert detail == {"portfolio": "p1"}


def test_check_ingress_secret_skips_when_empty():
    ok, err, status = check_ingress_secret(expected="", presented="")
    assert ok and err is None and status is None


def test_check_ingress_secret_rejects_mismatch():
    ok, err, status = check_ingress_secret(expected="abc", presented="xyz")
    assert not ok and status == 401


def test_presented_reads_ingress_header():
    class H(dict):
        def get(self, k, default=""):
            return dict.get(self, k, default)

    assert presented_ingress_secret(H({"X-Renglo-Ingress-Secret": "s1"})) == "s1"
    assert presented_ingress_secret(H({"x-renglo-ingress-secret": "s2"})) == "s2"


def test_whatsapp_payload_maps_signature_header():
    payload = webhook_payload_for_channel(
        "whatsapp",
        {
            "portfolio": "p",
            "org": "o",
            "raw_body": "{}",
            "headers": {"x-hub-signature-256": "sha256=abc"},
        },
    )
    assert payload["signature_header"] == "sha256=abc"
    assert payload["raw_body"] == "{}"


def test_dispatch_webhook_whatsapp():
    calls = []

    def load_and_run(handler, payload=None):
        calls.append((handler, payload))
        return {"success": True}

    def create_job_run(*_a, **_k):
        raise AssertionError("should not run")

    resp, status = dispatch_ingress(
        {
            "type": "webhook",
            "channel": "whatsapp",
            "portfolio": "p1",
            "org": "o1",
            "raw_body": '{"entry":[]}',
            "signature_header": "sha256=x",
        },
        load_and_run=load_and_run,
        create_job_run=create_job_run,
    )
    assert status == 200 and resp["success"]
    assert calls[0][0] == CHANNEL_HANDLERS["whatsapp"]
    assert calls[0][1]["portfolio"] == "p1"


def test_dispatch_rejects_unknown_channel():
    resp, status = dispatch_ingress(
        {
            "type": "webhook",
            "channel": "nope",
            "portfolio": "p",
            "raw_body": "",
        },
        load_and_run=lambda *a, **k: {"success": True},
        create_job_run=lambda *a, **k: ({}, 200),
    )
    assert status == 400
    assert "unknown channel" in resp["message"]


def test_dispatch_heartbeat():
    seen = []

    def dispatch_heartbeat(portfolio, org, heartbeat_id, detail=None):
        seen.append((portfolio, org, heartbeat_id))
        return {"success": True, "dispatched": 1, "skipped": 0}, 200

    resp, status = dispatch_ingress(
        {
            "type": "heartbeat",
            "portfolio": "p",
            "org": "o",
            "heartbeat_id": "every_1_minute",
        },
        load_and_run=lambda *a, **k: {"success": False},
        create_job_run=lambda *a, **k: ({}, 200),
        dispatch_heartbeat=dispatch_heartbeat,
    )
    assert status == 200 and resp["success"]
    assert seen == [("p", "o", "every_1_minute")]


def test_dispatch_heartbeat_requires_id():
    resp, status = dispatch_ingress(
        {"type": "heartbeat", "portfolio": "p", "org": "o"},
        load_and_run=lambda *a, **k: {"success": True},
        create_job_run=lambda *a, **k: ({}, 200),
        dispatch_heartbeat=lambda *a, **k: ({"success": True}, 200),
    )
    assert status == 400


def test_dispatch_schd_job():
    def create_job_run(portfolio, org, payload):
        assert portfolio == "p"
        assert org == "o"
        assert payload["schd_jobs_id"] == "job1"
        return {"success": True, "action": "create_job_run"}, 200

    resp, status = dispatch_ingress(
        {
            "type": "schd_job",
            "portfolio": "p",
            "org": "o",
            "schd_jobs_id": "job1",
            "trigger": "cron",
        },
        load_and_run=lambda *a, **k: {"success": False},
        create_job_run=create_job_run,
    )
    assert status == 200 and resp["success"]


def test_legacy_whatsapp_shape_inferred():
    calls = []

    def load_and_run(handler, payload=None):
        calls.append(handler)
        return {"success": True}

    resp, status = dispatch_ingress(
        {"portfolio": "p", "org": "o", "raw_body": "{}"},
        load_and_run=load_and_run,
        create_job_run=lambda *a, **k: ({}, 200),
    )
    assert status == 200
    assert calls == ["whatsapp/inbound"]
