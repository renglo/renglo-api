"""Unit tests for SchdController schedule utility (heartbeats, jobs, activity)."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

_LIB_ROOT = Path(__file__).resolve().parents[2] / "renglo-lib"
if str(_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT))

from renglo.logger import get_logger  # noqa: E402
from renglo.schd.schd_activity_log import SchdActivityLog  # noqa: E402
from renglo.schd.schd_controller import SchdController  # noqa: E402
from renglo.schd.schd_model import SchdModel  # noqa: E402
from renglo.schd.schd_schedule import DUE_CHECK_HANDLE, SchdScheduleMixin  # noqa: E402


class MemoryStore:
    def __init__(self):
        self.docs = {}

    def _key(self, portfolio, org, ring, idx):
        return (portfolio, org, ring, idx)

    def post_a_b(self, portfolio, org, ring, item):
        idx = item["_id"]
        self.docs[self._key(portfolio, org, ring, idx)] = item
        return {"message": "ok"}

    def get_a_b_c(self, portfolio, org, ring, idx):
        item = self.docs.get(self._key(portfolio, org, ring, idx))
        return item or {"error": "Document not found"}

    def get_a_b(self, portfolio, org, ring, limit=10000, lastkey=None):
        items = [
            value
            for (p, o, r, _i), value in self.docs.items()
            if p == portfolio and o == org and r == ring
        ]
        return {"items": items, "last_id": None}

    def put_a_b_c(self, portfolio, org, ring, idx, item):
        key = self._key(portfolio, org, ring, idx)
        if key not in self.docs:
            return {"error": "Item not found"}
        current = self.docs[key]
        attrs = dict(current.get("attributes") or {})
        attrs.update(item.get("attributes") or {})
        current["attributes"] = attrs
        self.docs[key] = current
        return {"message": "Item updated", "response": "{}"}

    def delete_a_b_c(self, portfolio, org, ring, idx):
        self.docs.pop(self._key(portfolio, org, ring, idx), None)
        return {"message": "deleted"}


class FakeDAC:
    def __init__(self, store: MemoryStore):
        self.DAM = store

    def construct_post_item(self, portfolio, org, ring, payload):
        return {
            "_id": str(uuid.uuid4()),
            "attributes": dict(payload),
            "portfolio": portfolio,
            "org": org,
            "ring": ring,
        }

    def construct_put_item(self, portfolio, org, ring, idx, payload):
        existing = self.DAM.get_a_b_c(portfolio, org, ring, idx)
        attrs = dict(existing.get("attributes") or {})
        attrs.update(payload)
        return {"_id": idx, "attributes": attrs}


class BlueprintGatedDAC(FakeDAC):
    """Mirrors live Dynamo: only blueprint-known fields are copied into attributes."""

    KNOWN = {
        "name",
        "status",
        "version",
        "handler",
        "description",
        "type",
        "schedule_kind",
        "heartbeat_id",
        "schedule_expression",
        "run_at",
        "handler_payload",
        "enabled",
        "last_run_at",
        "last_run_status",
        "last_run_error",
        "run_lease_until",
    }

    def construct_post_item(self, portfolio, org, ring, payload):
        item = super().construct_post_item(portfolio, org, ring, payload)
        item["attributes"] = {k: v for k, v in (payload or {}).items() if k in self.KNOWN}
        return item

    def construct_put_item(self, portfolio, org, ring, idx, payload):
        existing = self.DAM.get_a_b_c(portfolio, org, ring, idx)
        attrs = dict(existing.get("attributes") or {})
        attrs.update({k: v for k, v in (payload or {}).items() if k in self.KNOWN})
        return {"_id": idx, "attributes": attrs}


class FakeSHM:
    def __init__(self):
        self.rules = {}
        self.events = []
        self.put_calls = []
        self.local_activity = []

    def create_https_target_event(self, rule_name, schedule_expression, payload, backend="cloud"):
        self.rules[rule_name] = {
            "expression": schedule_expression,
            "payload": payload,
            "state": "ENABLED",
            "backend": backend,
        }
        return {"success": True, "output": {"RuleArn": f"arn:{rule_name}"}}

    def delete_https_target_event(self, rule_name, backend="cloud"):
        self.rules.pop(rule_name, None)
        return {"success": True}

    def create_event_pattern_target(self, rule_name, event_source, payload_defaults=None, backend="cloud"):
        self.rules[rule_name] = {"pattern": event_source, "state": "ENABLED", "backend": backend}
        return {"success": True, "output": {"RuleArn": f"arn:{rule_name}"}}

    def put_schd_events(self, entries, backend="cloud"):
        batch = list(entries)
        self.put_calls.append(batch)
        self.events.extend(batch)
        return {"success": True, "output": {"FailedEntryCount": 0, "backend": backend}}

    def find_rule(self, name):
        rule = self.rules.get(name)
        return {"success": bool(rule), "output": rule or False}

    def append_local_activity(self, entry):
        stored = dict(entry or {})
        self.local_activity.append(stored)
        return {"success": True, "entry": stored}

    def list_local_activity(self, **filters):
        items = []
        for entry in reversed(self.local_activity):
            if filters.get("event_type") and str(entry.get("event_type") or "") != filters["event_type"]:
                continue
            if filters.get("schd_jobs_id") and str(entry.get("schd_jobs_id") or "") != filters["schd_jobs_id"]:
                continue
            if filters.get("portfolio") and str(entry.get("portfolio") or "") != filters["portfolio"]:
                continue
            if filters.get("org") and str(entry.get("org") or "") != filters["org"]:
                continue
            if filters.get("schd_machine_id") and str(entry.get("schd_machine_id") or "") != filters["schd_machine_id"]:
                continue
            row = dict(entry)
            if "detail" in row:
                row.pop("detail")
                row["has_detail"] = True
            items.append(row)
        limit = int(filters.get("limit") or 100)
        return {"success": True, "items": items[:limit]}

    def get_local_activity(self, event_id):
        for entry in reversed(self.local_activity):
            if str(entry.get("event_id") or "") == str(event_id):
                return {"success": True, "entry": dict(entry)}
        return {"success": False, "output": "not found"}


class FakeSHL:
    def __init__(self):
        self.calls = []
        self.response = {"success": True, "output": {"ok": True}}

    def load_and_run(self, handler, payload=None, check=False):
        self.calls.append({"handler": handler, "payload": payload})
        return dict(self.response)


class FakeAUC:
    def authorize(self, *args, **kwargs):
        return {"success": True, "roles": []}


class FakeFiles:
    def __init__(self):
        self.blobs = {}

    def a_b_post(self, portfolio, org, ring, body, type, name):
        path = f"_files/{portfolio}/{org}/{ring}/{name}.json"
        self.blobs[path] = body
        return {"success": True, "path": path}

    def a_b_c_get(self, portfolio, org, ring, filename):
        path = f"_files/{portfolio}/{org}/{ring}/{filename}"
        if path not in self.blobs:
            return {"success": False}
        return {"success": True, "content": self.blobs[path]}


class TestSchd(SchdScheduleMixin):
    """In-memory controller: no Dynamo, EventBridge, or Cognito."""

    def __init__(self, config=None):
        self.config = config or {}
        self.logger = get_logger()
        self.DAC = FakeDAC(MemoryStore())
        self.SHM = FakeSHM()
        self.SHL = FakeSHL()
        self.AUC = FakeAUC()


def _controller(aws=False, inline=True):
    config = {"SCHD_INLINE_EXECUTE": True} if inline else {}
    if aws:
        config["ROLE_ARN"] = "arn:aws:iam::1:role/r"
        config["RENGLO_INGRESS_DESTINATION"] = "env-renglo-process"
    return TestSchd(config=config)


def test_ensure_and_subscribe_lazy_rule():
    ctrl = _controller(aws=True, inline=False)
    seeded = ctrl.ensure_heartbeats("p", "o")
    assert seeded["success"]
    assert any(h["handle"] == DUE_CHECK_HANDLE for h in seeded["heartbeats"])
    due_rule = ctrl._rule_name("p", "o", DUE_CHECK_HANDLE)
    assert due_rule in ctrl.SHM.rules

    five_rule = ctrl._rule_name("p", "o", "every_5_minutes")
    assert five_rule not in ctrl.SHM.rules

    sub = ctrl.subscribe("p", "o", {"handler": "pes/wakeup", "heartbeat_id": "every_5_minutes", "name": "Wake"})
    assert sub["success"]
    assert five_rule in ctrl.SHM.rules
    job_id = sub["schd_jobs_id"]

    unsub = ctrl.unsubscribe("p", "o", job_id)
    assert unsub["success"]
    assert five_rule not in ctrl.SHM.rules
    assert due_rule in ctrl.SHM.rules


def test_once_job_fires_on_one_minute_tick():
    ctrl = _controller(aws=False, inline=True)
    ctrl.ensure_heartbeats("p", "o")
    created = ctrl.schedule_once(
        "p",
        "o",
        {"handler": "pes/wakeup", "name": "Later", "run_at": str(int(time.time()) - 10)},
    )
    assert created["success"]
    job_id = created["schd_jobs_id"]

    result, status = ctrl.dispatch_heartbeat("p", "o", DUE_CHECK_HANDLE)
    assert status == 200
    assert result["dispatched"] == 1
    assert ctrl.SHL.calls[0]["handler"] == "pes/wakeup"
    payload = ctrl.SHL.calls[0]["payload"]
    assert payload["schd_jobs_id"] == job_id
    assert payload["trigger"] == "once"
    assert payload["portfolio"] == "p"

    job = ctrl._get_doc("p", "o", "schd_jobs", job_id)
    assert job["enabled"] == "false"
    assert job["schedule_kind"] == "none"

    result2, _ = ctrl.dispatch_heartbeat("p", "o", DUE_CHECK_HANDLE)
    assert result2["dispatched"] == 0


def test_overlap_skip_and_activity_index():
    ctrl = _controller(aws=False, inline=True)
    ctrl.ensure_heartbeats("p", "o")
    sub = ctrl.subscribe(
        "p",
        "o",
        {"handler": "triage/wakeup", "heartbeat_id": "every_1_minute", "name": "Tick"},
    )
    job_id = sub["schd_jobs_id"]
    ctrl._patch_doc("p", "o", "schd_jobs", job_id, {"run_lease_until": str(int(time.time()) + 60)})

    result, status = ctrl.dispatch_heartbeat("p", "o", DUE_CHECK_HANDLE)
    assert status == 200
    assert result["skipped"] == 1
    assert result["dispatched"] == 0
    assert ctrl.SHL.calls == []

    files = FakeFiles()
    log = SchdActivityLog(ctrl.DAC, "p", "o", config={})
    log._files = files
    entry = log.append(
        event_type="executed",
        summary="triage/wakeup executed",
        trigger="heartbeat",
        schd_jobs_id=job_id,
        heartbeat_id="every_1_minute",
        detail={
            "success": True,
            "action": "execute_job",
            "input": {"handler": "triage/wakeup"},
            "output": {"success": True, "output": {"ok": True}},
            "job": {"schd_jobs_id": job_id, "trigger": "heartbeat", "handler": "triage/wakeup"},
        },
    )
    assert entry["event_id"]
    assert entry["detail_s3_path"]
    recent = log.list_recent(days=7, schd_jobs_id=job_id)
    assert len(recent) >= 1
    day_docs = [
        row
        for (p, o, r, _i), row in ctrl.DAC.DAM.docs.items()
        if r == "schd_activity"
    ]
    assert len(day_docs) == 1
    detail = log.load_detail(entry["detail_s3_path"])
    assert detail["success"] is True
    assert detail["job"]["schd_jobs_id"] == job_id
    assert detail["output"]["output"]["ok"] is True


def test_execute_job_passes_run_context():
    ctrl = _controller(aws=False, inline=True)
    ctrl.ensure_heartbeats("p", "o")
    sub = ctrl.subscribe(
        "p",
        "o",
        {
            "handler": "pes/wakeup",
            "heartbeat_id": "every_1_minute",
            "handler_payload": {"cycle": "ops"},
        },
    )
    fake_files = FakeFiles()
    with patch("renglo.schd.schd_activity_log.FilesModel", return_value=fake_files):
        result, status = ctrl.execute_job(
            "p",
            "o",
            {"schd_jobs_id": sub["schd_jobs_id"], "trigger": "heartbeat", "heartbeat_id": "every_1_minute"},
        )
    assert status == 200
    payload = ctrl.SHL.calls[0]["payload"]
    assert payload["handler"] == "pes/wakeup"
    assert payload["schd_jobs_id"] == sub["schd_jobs_id"]
    assert payload["trigger"] == "heartbeat"
    assert payload["heartbeat_id"] == "every_1_minute"
    assert payload["event_id"]
    assert payload["cycle"] == "ops"
    assert result["success"]
    day_docs = [
        row
        for (_p, _o, r, _i), row in ctrl.DAC.DAM.docs.items()
        if r == "schd_activity"
    ]
    assert len(day_docs) == 1
    entries = day_docs[0]["attributes"]["entries"]
    assert entries[0]["event_type"] == "executed"
    assert entries[0]["schd_jobs_id"] == sub["schd_jobs_id"]
    log = SchdActivityLog(ctrl.DAC, "p", "o", config={})
    log._files = fake_files
    detail = log.load_detail(entries[0]["detail_s3_path"])
    assert detail["success"] is True
    assert detail["action"] == "execute_job"
    assert "schd_jobs_id" not in detail
    assert "handler" not in detail
    assert detail["input"]["handler"] == "pes/wakeup"
    assert detail["input"]["cycle"] == "ops"
    assert detail["job"]["handler"] == "pes/wakeup"
    assert detail["job"]["schd_jobs_id"] == sub["schd_jobs_id"]
    assert detail["job"]["trigger"] == "heartbeat"
    assert detail["job"]["heartbeat_id"] == "every_1_minute"
    assert detail["job"]["handler_payload"] == {"cycle": "ops"}
    assert detail["output"]["success"] is True


def test_local_execute_writes_ebe_not_s3():
    ctrl = _controller(aws=False, inline=True)
    ctrl.ensure_heartbeats("p", "o")
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-a"):
        sub = ctrl.subscribe(
            "p",
            "o",
            {
                "handler": "pes/wakeup",
                "heartbeat_id": "every_1_minute",
                "name": "Local",
                "schedule_origin": "local",
            },
        )
        result, status = ctrl.execute_job(
            "p",
            "o",
            {
                "schd_jobs_id": sub["schd_jobs_id"],
                "trigger": "heartbeat",
                "heartbeat_id": "every_1_minute",
                "schedule_origin": "local",
                "schd_machine_id": "machine-a",
            },
        )
        listed = ctrl.list_activity("p", "o", origin="local")
        cloud = ctrl.list_activity("p", "o", origin="cloud")
    assert status == 200 and result["success"]
    day_docs = [
        row
        for (_p, _o, r, _i), row in ctrl.DAC.DAM.docs.items()
        if r == "schd_activity"
    ]
    assert day_docs == []
    assert len(ctrl.SHM.local_activity) == 1
    assert ctrl.SHM.local_activity[0]["schedule_origin"] == "local"
    assert "detail" in ctrl.SHM.local_activity[0]
    local_detail = ctrl.SHM.local_activity[0]["detail"]
    assert local_detail["input"]["handler"] == "pes/wakeup"
    assert local_detail["job"]["schedule_origin"] == "local"
    assert local_detail["job"]["schd_machine_id"] == "machine-a"
    assert listed["items"][0]["schd_jobs_id"] == sub["schd_jobs_id"]
    assert "detail" not in listed["items"][0]
    assert listed["items"][0]["has_detail"] is True
    assert cloud["items"] == []


def test_verify_rule_uses_cron_prefix():
    ctrl = _controller(aws=True, inline=False)
    ctrl.SHM.rules["cron_p_o_timer"] = {"state": "ENABLED"}
    found = SchdController.verify_rule(ctrl, "p", "o", "timer")
    assert found["success"]
    assert found["output"]["state"] == "ENABLED"


def test_ingress_target_uses_api_destination():
    dest = "arn:aws:events:us-east-1:1:api-destination/env-renglo-process/abc"
    model = SchdModel(
        config={"ROLE_ARN": "arn:aws:iam::1:role/r", "RENGLO_INGRESS_DESTINATION": "env-renglo-process"}
    )
    captured = {}

    class Client:
        def describe_api_destination(self, Name):
            return {"ApiDestinationArn": dest}

        def put_targets(self, Rule, Targets):
            captured["arn"] = Targets[0]["Arn"]
            captured["headers"] = Targets[0]["HttpParameters"]["HeaderParameters"]
            return {"FailedEntryCount": 0}

    model.client = Client()
    result = model._put_ingress_target("cron_p_o_every_1_minute", {"type": "heartbeat"})
    assert result["success"]
    assert captured["arn"] == dest
    assert "X-Renglo-Ingress-Secret" not in captured["headers"]


def test_ingress_target_rejects_execute_api_arn():
    model = SchdModel(config={"RENGLO_INGRESS_DESTINATION": "env-renglo-process"})

    class Client:
        def describe_api_destination(self, Name):
            return {"ApiDestinationArn": "arn:aws:execute-api:us-east-1:1:abc/*"}

    model.client = Client()
    result = model._put_ingress_target("cron_p_o_every_1_minute", {"type": "heartbeat"})
    assert result["success"] is False
    assert "API Destination" in str(result["output"])


def test_destination_name_from_wl_name():
    model = SchdModel(config={"WL_NAME": "arbitium0813"})
    assert model.ingress_destination_name() == "arbitium0813-renglo-process"


def test_cloud_list_hides_local_jobs():
    ctrl = _controller(aws=True, inline=False)
    ctrl.ensure_heartbeats("p", "o")
    cloud = ctrl.subscribe("p", "o", {"handler": "pes/wakeup", "heartbeat_id": "every_5_minutes", "name": "Cloud"})
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-a"):
        local = ctrl.subscribe(
            "p",
            "o",
            {
                "handler": "pes/wakeup",
                "heartbeat_id": "every_5_minutes",
                "name": "Local",
                "schedule_origin": "local",
            },
        )
        listed_cloud = ctrl.list_jobs("p", "o", origin="cloud")
        listed_local = ctrl.list_jobs("p", "o", origin="local")
    ids_cloud = {j["_id"] for j in listed_cloud["items"]}
    ids_local = {j["_id"] for j in listed_local["items"]}
    assert cloud["schd_jobs_id"] in ids_cloud
    assert local["schd_jobs_id"] not in ids_cloud
    assert local["schd_jobs_id"] in ids_local
    assert cloud["schd_jobs_id"] not in ids_local


def test_local_origin_survives_stale_blueprint():
    ctrl = _controller(aws=True, inline=False)
    ctrl.DAC = BlueprintGatedDAC(ctrl.DAC.DAM)
    ctrl.ensure_heartbeats("p", "o")
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-a"):
        created = ctrl.subscribe(
            "p",
            "o",
            {
                "handler": "schd/check_weather",
                "heartbeat_id": "every_1_hour",
                "name": "Weather",
                "schedule_origin": "local",
            },
        )
        job = created["job"]
        listed_local = ctrl.list_jobs("p", "o", origin="local")
        listed_cloud = ctrl.list_jobs("p", "o", origin="cloud")
    assert job["schedule_origin"] == "local"
    assert job["schd_machine_id"] == "machine-a"
    assert created["schd_jobs_id"] in {j["_id"] for j in listed_local["items"]}
    assert created["schd_jobs_id"] not in {j["_id"] for j in listed_cloud["items"]}


def test_cloud_dispatch_skips_local_jobs():
    ctrl = _controller(aws=False, inline=True)
    ctrl.ensure_heartbeats("p", "o")
    ctrl.subscribe("p", "o", {"handler": "pes/wakeup", "heartbeat_id": "every_1_minute", "name": "Cloud"})
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-a"):
        ctrl.subscribe(
            "p",
            "o",
            {
                "handler": "pes/wakeup",
                "heartbeat_id": "every_1_minute",
                "name": "Local",
                "schedule_origin": "local",
            },
        )
        cloud_tick, status = ctrl.dispatch_heartbeat("p", "o", DUE_CHECK_HANDLE)
        local_tick, status2 = ctrl.dispatch_heartbeat(
            "p",
            "o",
            DUE_CHECK_HANDLE,
            {"schedule_origin": "local", "schd_machine_id": "machine-a"},
        )
    assert status == 200 and status2 == 200
    assert cloud_tick["dispatched"] == 1
    assert local_tick["dispatched"] == 1


def test_heartbeat_fanout_batches_put_events():
    ctrl = _controller(aws=True, inline=False)
    ctrl.ensure_heartbeats("p", "o")
    ctrl.subscribe("p", "o", {"handler": "pes/wakeup", "heartbeat_id": "every_1_minute", "name": "A"})
    ctrl.subscribe("p", "o", {"handler": "pes/wakeup", "heartbeat_id": "every_1_minute", "name": "B"})
    result, status = ctrl.dispatch_heartbeat("p", "o", DUE_CHECK_HANDLE)
    assert status == 200
    assert result["dispatched"] == 2
    assert len(ctrl.SHM.put_calls) == 1
    assert len(ctrl.SHM.put_calls[0]) == 2
    assert ctrl.SHL.calls == []


def test_other_machine_local_jobs_are_invisible():
    ctrl = _controller(aws=True, inline=False)
    ctrl.ensure_heartbeats("p", "o")
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-a"):
        mine = ctrl.subscribe(
            "p",
            "o",
            {
                "handler": "pes/wakeup",
                "heartbeat_id": "every_5_minutes",
                "name": "Mine",
                "schedule_origin": "local",
            },
        )
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-b"):
        other = ctrl.subscribe(
            "p",
            "o",
            {
                "handler": "pes/wakeup",
                "heartbeat_id": "every_5_minutes",
                "name": "Other laptop",
                "schedule_origin": "local",
            },
        )
        listed_b = ctrl.list_jobs("p", "o", origin="local")
        tick_b, status_b = ctrl.dispatch_heartbeat(
            "p",
            "o",
            "every_5_minutes",
            {"schedule_origin": "local", "schd_machine_id": "machine-b"},
        )
    with patch("renglo.schd.schd_schedule.schd_machine_id", return_value="machine-a"):
        listed_a = ctrl.list_jobs("p", "o", origin="local")
        tick_a, status_a = ctrl.dispatch_heartbeat(
            "p",
            "o",
            "every_5_minutes",
            {"schedule_origin": "local", "schd_machine_id": "machine-a"},
        )
    assert status_a == 200 and status_b == 200
    ids_a = {j["_id"] for j in listed_a["items"]}
    ids_b = {j["_id"] for j in listed_b["items"]}
    assert mine["schd_jobs_id"] in ids_a
    assert other["schd_jobs_id"] not in ids_a
    assert other["schd_jobs_id"] in ids_b
    assert mine["schd_jobs_id"] not in ids_b
    assert tick_a["dispatched"] == 1
    assert tick_b["dispatched"] == 1


def test_local_backend_uses_ebe_not_boto3():
    model = SchdModel(
        config={
            "EVENTBRIDGE_EMULATOR_URL": "http://127.0.0.1:5056",
            "ROLE_ARN": "arn:aws:iam::1:role/r",
            "RENGLO_INGRESS_DESTINATION": "env-renglo-process",
        }
    )
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {"success": True, "queued": 1}
    with patch("renglo.schd.schd_model.requests.request", return_value=fake) as req:
        with patch("renglo.schd.schd_model.boto3.client") as boto_client:
            created = model.create_https_target_event(
                "ebe_abc_p_o_every_1_minute",
                "rate(1 minute)",
                {"type": "heartbeat", "schedule_origin": "local", "schd_machine_id": "abc"},
                backend="local",
            )
            queued = model.put_schd_events(
                [{"type": "schd_job", "schd_jobs_id": "j1", "schedule_origin": "local"}],
                backend="local",
            )
    assert created["success"]
    assert queued["success"]
    boto_client.assert_not_called()
    assert req.call_count == 2
    assert req.call_args_list[0].args[0] == "PUT"
    assert req.call_args_list[1].args[0] == "POST"
