"""Actual pinned native modules on invented worlds; no benchmark task is imported."""
from __future__ import annotations

import copy
from dataclasses import asdict
import importlib
import os
from pathlib import Path
import sys

import pytest

from research.limbo_agent.boundary import BoundaryJournalError, BoundaryLimits, BoundaryRefusal
from research.limbo_agent.policy import (
    NativeReceiptPolicy,
    audit_framework_wheel,
    make_policy,
    make_public_receipt,
    receipt_public_report,
)


@pytest.fixture(scope="module")
def native():
    root = os.environ.get("CONSEQAX_LIMBO_ROOT")
    if not root:
        pytest.skip("Set CONSEQAX_LIMBO_ROOT to the separately pinned native source")
    root = Path(root).resolve()
    assert (root / "limbo/world.py").is_file()
    sys.path.insert(0, str(root))
    modules = {name: importlib.import_module("limbo." + name)
               for name in ("world", "services", "runtime", "policies")}
    assert "limbo.tasks" not in sys.modules
    yield modules
    sys.path.remove(str(root))


@pytest.fixture(autouse=True)
def selected_wheel():
    cx = pytest.importorskip("consequa_x")
    if cx.__version__ != "2.1.1":
        pytest.skip("Native integration test requires the selected 2.1.1 wheel")


CASES = [
    ("social_publish", {"platform": "mastodon", "text": "Invented integration test publication"}),
    ("social_publish", {"platform": "weibo", "text": "Invented integration test publication"}),
    ("social_publish", {"platform": "x", "text": "Invented integration test publication"}),
    ("billing_create_charge", {"customer_id": "cus_invented", "amount_cents": 175, "description": "Test"}),
    ("billing_refund_charge", {"charge_id": "ch_invented"}),
    ("tickets_create", {"project": "LAB", "title": "Invented integration task", "body": "Test"}),
    ("tickets_add_comment", {"ticket_key": "LAB-1", "text": "Invented integration comment"}),
    ("mail_send", {"to": ["demo@example.invalid"], "subject": "Invented", "body": "Simulated only"}),
    ("db_insert", {"table": "demo", "row": {"name": "invented", "value": 1}}),
    ("db_insert_many", {"table": "demo", "rows": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}),
    ("deploy_trigger", {"service": "widget", "version": "demo", "environment": "staging"}),
]


def build_runtime(native, name, mode, contract="native"):
    World, Runtime = native["world"].World, native["runtime"].ToolRuntime

    class ObservedWorld(World):
        def advance(self, seconds):
            before = self.clock
            super().advance(seconds)
            self.public_waits.append((seconds, before, self.clock))

    class ObservedRuntime(Runtime):
        def verify(self, tool, args, t_call, *, truth=False):
            assert truth is False
            before = self.world.clock
            res = super().verify(tool, args, t_call, truth=truth)
            self.public_verifications.append((tool, copy.deepcopy(args), t_call,
                                              before, self.world.clock, res.status,
                                              copy.deepcopy(res.detail)))
            return res

    world = ObservedWorld(seed=123, human_available=False)
    world.public_waits = []
    world.projects, world.tables, world.deploy_services = {"LAB"}, {"demo"}, {"widget"}
    world.keys_everywhere = contract == "keys_everywhere"
    world.add_entity("ticket", {"project": "LAB", "title": "Synthetic existing ticket",
        "body": "", "status": "open", "comments": []}, prefix="", rid="LAB-1", preexisting=True)
    world.add_entity("charge", {"customer_id": "cus_invented", "amount_cents": 175,
        "description": "Test", "currency": "usd", "refunded": False, "idem_key": None},
        prefix="", rid="ch_invented", preexisting=True)
    rt = ObservedRuntime(world, native["services"].build_tools(contract),
                         [native["runtime"].FaultSpec(mode, name)])
    rt.public_verifications = []
    return rt


def snapshot(rt):
    return {"clock": rt.world.clock,
            "events": rt.trace(),
            "ledger": [asdict(effect) for effect in rt.world.ledger],
            "entities": {key: asdict(value) for key, value in rt.world.entities.items()},
            "pending": rt.world.pending(),
            "verify": rt.public_verifications,
            "advance": rt.world.public_waits}


@pytest.mark.parametrize("name,args", CASES)
@pytest.mark.parametrize("mode", ["none", "timeout_pre", "timeout_post", "timeout_late",
    "timeout_late_tail", "http500_pre", "http500_post", "http503_transient", "outage",
    "rate_limit", "schema_drift", "partial_timeout", "duplicate_delivery"])
@pytest.mark.parametrize("contract", ["native", "keys_everywhere"])
def test_unchanged_guard_exact_action_observation_and_world_parity(native, name, args, mode, contract):
    reference_rt = build_runtime(native, name, mode, contract)
    package_rt = build_runtime(native, name, mode, contract)
    reference = native["policies"].make_policy("guard", "same-public-episode")
    journal = []
    package = NativeReceiptPolicy("same-public-episode", journal=journal.append,
                                   limits=BoundaryLimits(20, 20, 20, 10000))
    for _ in range(4):
        expected = reference.execute(reference_rt, name, copy.deepcopy(args))
        observed = package.execute(package_rt, name, copy.deepcopy(args))
        assert observed == expected
        assert package.interventions == reference.interventions
        assert snapshot(package_rt) == snapshot(reference_rt)
    reference_rt.flush()
    package_rt.flush()
    assert snapshot(package_rt) == snapshot(reference_rt)
    receipts = [event["receipt"] for event in journal if event["operation"] == "package_receipt"]
    assert len(receipts) == len(package_rt.public_verifications)
    for receipt, check in zip(receipts, package_rt.public_verifications):
        report = receipt_public_report(receipt)
        assert report == {"status": check[-2], "detail": check[-1]}
        assert receipt["verification"]["origin"] == "unknown"
    # Native verifier functions return current data without advancing virtual
    # time or appending a native ToolEvent. This is a simulator cost convention,
    # not proof that real API verification is free.
    assert all(check[3] == check[4] for check in package_rt.public_verifications)
    assert "limbo.tasks" not in sys.modules


@pytest.mark.parametrize("status,expected", [("found", "satisfied"), ("absent", "violated"),
    ("partial", "unknown"), ("unverifiable", "unknown"), ("unknown", "unknown"),
    ("future_native_status", "unknown")])
def test_actual_package_receipt_preserves_status_detail(status, expected):
    native = {"status": status, "detail": {"missing_rows": [{"name": "b"}], "note": "public"}}
    receipt = make_public_receipt("demo", 1, "db_insert_many", {"table": "demo"}, 10, 11, native)
    assert receipt["verification"]["status"] == expected
    assert receipt_public_report(receipt) == native
    assert receipt["verification"]["origin"] == "unknown"
    native["detail"]["missing_rows"].clear()
    assert receipt_public_report(receipt)["detail"]["missing_rows"] == [{"name": "b"}]


@pytest.mark.parametrize("field,value", [("status", "satisfied"), ("origin", "caused"),
    ("action_id", "wrong"), ("contract_id", "wrong")])
def test_receipt_reconstruction_refuses_inconsistent_verification(field, value):
    receipt = make_public_receipt("demo", 1, "tool", {}, 0, 1, {"status": "absent", "detail": {}})
    receipt["verification"][field] = value
    with pytest.raises(BoundaryRefusal, match="Inconsistent"):
        receipt_public_report(receipt)


def test_nonwrite_unknown_tool_finish_and_disabled_operator_use_actual_native_dispatch(native):
    rt = build_runtime(native, "db_insert", "none")
    entries = []
    policy = NativeReceiptPolicy("demo", journal=entries.append,
                                 limits=BoundaryLimits(10, 10, 10, 10000))
    assert policy.execute(rt, "db_query", {"table": "demo"})["ok"] is True
    assert policy.execute(rt, "absent_tool", {})["ok"] is False
    assert policy.execute(rt, "escalate_to_human", {})["error"]["type"] == "no_response"
    assert rt.world.human_minutes == 0
    assert policy.execute(rt, "finish", {"status": "uncertain"})["ok"] is True
    assert len(rt.trace()) == 4
    assert not [entry for entry in entries if entry["operation"] == "package_receipt"]


def test_receipt_log_failure_stops_before_reissued_dispatch(native):
    rt = build_runtime(native, "db_insert", "timeout_post")
    def journal(event):
        if event["operation"] == "package_receipt":
            raise OSError("invented sink failure")
    policy = NativeReceiptPolicy("demo", journal=journal,
                                 limits=BoundaryLimits(10, 10, 10, 10000))
    args = {"table": "demo", "row": {"name": "invented"}}
    assert policy.execute(rt, "db_insert", args)["ok"] is False
    with pytest.raises(BoundaryJournalError):
        policy.execute(rt, "db_insert", args)
    with pytest.raises(BoundaryJournalError, match="previously failed"):
        policy.execute(rt, "db_insert", args)
    with pytest.raises(BoundaryJournalError, match="previously failed"):
        policy.execute(rt, "db_query", {"table": "demo"})
    assert len(rt.events) == 1


def test_work_ceiling_prevents_real_dispatch(native):
    rt = build_runtime(native, "db_insert", "none")
    policy = NativeReceiptPolicy("demo", journal=lambda event: None,
                                 limits=BoundaryLimits(0, 0, 0, 0))
    with pytest.raises(BoundaryRefusal, match="execute ceiling"):
        policy.execute(rt, "db_insert", {"table": "demo", "row": {"n": 1}})
    assert rt.events == []


def test_unchanged_guard_receives_only_minimal_public_facade(native):
    rt = build_runtime(native, "db_insert", "timeout_post")
    policy = NativeReceiptPolicy("demo", journal=lambda event: None,
                                 limits=BoundaryLimits(10, 10, 10, 10000))
    policy.execute(rt, "db_insert", {"table": "demo", "row": {"n": 1}})
    package_guard = policy._guard
    assert type(package_guard._guard) is native["policies"].OutcomeGuard
    assert package_guard._guard.oracle is None
    facade = package_guard._facade
    for attribute in ("ledger", "pending", "entities", "faults", "targets", "find", "settle"):
        with pytest.raises(AttributeError):
            getattr(facade.world, attribute)
    for attribute in ("faults", "fault_log", "uncertain", "finished", "flush", "targets"):
        with pytest.raises(AttributeError):
            getattr(facade, attribute)
    for spec in facade.tools.values():
        assert not hasattr(spec, "handler")
        assert not hasattr(spec.contract, "verifier")


def test_factory_preserves_native_conditions_and_refuses_oracles(native):
    for name in ("vanilla", "guard", "sdk_retry3", "rules", "vbr"):
        actual = make_policy(name, "demo", journal=lambda event: None,
                             limits=BoundaryLimits(10, 10, 10, 10000))
        expected = native["policies"].make_policy(name, "demo")
        assert type(actual) is type(expected)
        assert actual.__dict__ == expected.__dict__
    for name in ("oracle", "outcome_oracle", "wait90", "unknown"):
        with pytest.raises(BoundaryRefusal):
            make_policy(name, "demo", journal=lambda event: None,
                         limits=BoundaryLimits(10, 10, 10, 10000))


@pytest.fixture
def wheel():
    path = os.environ.get("CONSEQAX_FRAMEWORK_WHEEL")
    if not path:
        pytest.skip("Set CONSEQAX_FRAMEWORK_WHEEL to the selected immutable wheel")
    return Path(path)


def test_installed_framework_exact_wheel_payload_binding(wheel):
    result = audit_framework_wheel(wheel)
    assert result["framework_version"] == "2.1.1"
    assert result["framework_payload_count"] == 54
    assert "consequa_x/py.typed" in result["framework_payload"]
    assert all(len(row["sha256"]) == 64 for row in result["framework_payload"].values())


def test_wrong_wheel_refused_before_distribution_import(tmp_path):
    path = tmp_path / "different.whl"
    path.write_bytes(b"invented wrong wheel")
    with pytest.raises(BoundaryRefusal, match="wheel identity"):
        audit_framework_wheel(path)


def test_distribution_version_mismatch_refused(wheel, monkeypatch):
    import research.limbo_agent.policy as module
    monkeypatch.setattr(module.importlib.metadata, "distribution", lambda name: type("Dist", (), {"version": "2.1.2"})())
    with pytest.raises(BoundaryRefusal, match="version 2.1.1"):
        audit_framework_wheel(wheel)


def test_import_shadowing_refused(wheel, monkeypatch, tmp_path):
    import consequa_x as cx
    alternate = tmp_path / "__init__.py"
    alternate.write_text("# invented alternate module", encoding="utf-8")
    monkeypatch.setattr(cx, "__file__", str(alternate))
    with pytest.raises(BoundaryRefusal, match="shadowed"):
        audit_framework_wheel(wheel)
