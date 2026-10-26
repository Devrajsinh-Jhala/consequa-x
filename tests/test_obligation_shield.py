"""Invented public responses/worlds only; no task corpus or model is used."""
from __future__ import annotations

import copy
import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from research.obligation_shield.certificates import (
    SCHEMA, check_certificate, describe_request, recompute_decision,
)
from research.obligation_shield.policy import ObligationShield, NativeObligationPolicy, make_policy


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def exact_sdk():
    """Exercise the real 2.1.1 wheel, restoring other tests' SDK imports afterward."""
    site = Path("C:/Code/ConsequaX-Research/native-agent-pilot-venv/Lib/site-packages")
    wheel = ROOT / "output/release-2.1.1-2026-10-19/consequa_x-2.1.1-py3-none-any.whl"
    if not site.is_dir() or not wheel.is_file():
        pytest.skip("Exact installed 2.1.1 research wheel is unavailable")
    saved_modules = {key: value for key, value in sys.modules.items()
                     if key == "consequa_x" or key.startswith("consequa_x.")}
    saved_path = list(sys.path)
    try:
        for key in saved_modules:
            del sys.modules[key]
        sys.path.insert(0, str(site))
        package = importlib.import_module("consequa_x")
        assert package.__version__ == "2.1.1"
        assert Path(package.__file__).resolve().is_relative_to(site.resolve())
        from research.limbo_agent.policy import audit_framework_wheel
        verified = audit_framework_wheel(wheel)
        assert verified["framework_payload_count"] == 54
        yield
    finally:
        for key in list(sys.modules):
            if key == "consequa_x" or key.startswith("consequa_x."):
                del sys.modules[key]
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


class Public:
    def __init__(self, responses=(), reports=(), *, keyed=False, idempotent=False):
        self.clock = 0.0
        self.last_dispatch_start = None
        self.responses, self.reports = list(responses), list(reports)
        self.keyed, self.idempotent = keyed, idempotent
        self.calls, self.verifications = [], []

    def tool_metadata(self):
        return {name: {} for name in ("write", "db_insert", "db_insert_many", "read")}

    def contract(self, name, args):
        identity = [name, args.get("table"), len(args.get("rows", []))] if name == "db_insert_many" else [name, "intent"]
        return {"write": name != "read", "idempotent": self.idempotent,
            "supports_key": self.keyed, "batch_field": "rows" if name == "db_insert_many" else None,
            "identity": identity}

    def execute(self, name, args, *, source="agent"):
        self.last_dispatch_start = self.clock
        self.clock += 1
        self.calls.append((name, copy.deepcopy(args), source))
        return copy.deepcopy(self.responses.pop(0) if self.responses else {"ok": True, "result": {"id": "invented"}})

    def verify(self, name, args, t_call, *, truth=False):
        assert truth is False
        self.verifications.append((name, copy.deepcopy(args), t_call))
        return copy.deepcopy(self.reports.pop(0) if self.reports else {"status": "absent", "detail": {}})


TIMEOUT = {"ok": False, "error": {"type": "timeout"}}


def decisions(policy):
    return [event["certificate"] for event in policy.interventions if event["kind"] == "obligation_decision"]


def test_persistent_ack_cache_is_explicitly_historical():
    public = Public()
    shield = ObligationShield(public, "invented")
    shield.execute("write", {"value": "a"})
    for _ in range(4):
        cached = shield.execute("write", {"value": "a"})
        assert cached["ok"] is True
        assert cached["obligation_shield"]["dispatch"] is False
        assert cached["obligation_shield"]["current_state"] == "unknown"
        assert cached["obligation_shield"]["settled_all_attempts"] is False
    assert len(public.calls) == 1 and not public.verifications
    assert all(check_certificate(item) for item in decisions(shield))


def test_absent_never_discards_unknown_and_has_symbolic_late_witness():
    public = Public([TIMEOUT])
    shield = ObligationShield(public, "invented")
    shield.execute("write", {"value": "a"})
    for _ in range(3):
        blocked = shield.execute("write", {"value": "a"})
        assert blocked["ok"] is False
    assert len(public.calls) == 1 and len(public.verifications) == 3
    assert shield.attempts[0]["disposition"] == "unknown"
    assert len(shield.attempts[0]["reports"]) == 3
    witness = decisions(shield)[-1]["decision"]["counterexample"]
    assert witness["worlds"][0]["matching_effects_after_time_2"] == 1
    assert witness["worlds"][1]["matching_effects_after_time_2"] == 2
    assert "not observed native fault truth" in witness["scope"]


def test_found_does_not_erase_underlying_ambiguous_attempt():
    public = Public([TIMEOUT], [{"status": "found", "detail": {"id": "invented"}}])
    shield = ObligationShield(public, "invented")
    shield.execute("write", {"value": "a"})
    assert shield.execute("write", {"value": "a"})["ok"] is True
    assert shield.execute("write", {"value": "a"})["ok"] is True
    assert len(public.calls) == 1 and len(public.verifications) == 1
    assert shield.attempts[0]["disposition"] == "unknown"
    assert decisions(shield)[-1]["decision"]["counterexample"] is None


def test_capability_first_same_key_replay_uses_no_read():
    public = Public([TIMEOUT, {"ok": True}], keyed=True)
    shield = ObligationShield(public, "invented")
    shield.execute("write", {"value": "a"})
    shield.execute("write", {"value": "a"})
    assert len(public.calls) == 2 and not public.verifications
    assert public.calls[0][1]["idempotency_key"] == public.calls[1][1]["idempotency_key"]
    assert decisions(shield)[-1]["decision"]["reason"] == "same_key_same_payload"


@pytest.mark.parametrize("second", [
    {"value": "b", "idempotency_key": "K"},
    {"value": "a", "idempotency_key": "DIFFERENT"},
])
def test_key_cannot_cover_changed_payload_or_different_prior_key(second):
    public = Public([TIMEOUT], keyed=True)
    shield = ObligationShield(public, "invented")
    shield.execute("write", {"value": "a", "idempotency_key": "K"})
    assert shield.execute("write", second)["ok"] is False
    assert len(public.calls) == 1


def test_intrinsic_idempotency_is_an_exact_payload_exception_only():
    public = Public([TIMEOUT], idempotent=True)
    shield = ObligationShield(public, "invented")
    shield.execute("write", {"value": "a"})
    shield.execute("write", {"value": "a"})
    assert len(public.calls) == 2 and not public.verifications
    assert decisions(shield)[-1]["decision"]["reason"] == "intrinsic_idempotent_same_payload"


def test_partial_original_batch_cannot_authorize_missing_only_retry():
    a, b = {"name": "a"}, {"name": "b"}
    public = Public([TIMEOUT], [{"status": "partial", "detail": {"present_rows": [a], "missing_rows": [b]}}])
    shield = ObligationShield(public, "invented")
    shield.execute("db_insert_many", {"table": "demo", "rows": [a, b]})
    result = shield.execute("db_insert_many", {"table": "demo", "rows": [b]})
    assert result["ok"] is False and len(public.calls) == 1
    assert public.calls[0][1]["rows"] == [a, b]
    assert shield.attempts[0]["disposition"] == "unknown"


def test_successful_batch_components_block_cross_tool_overlap():
    a, b = {"name": "a"}, {"name": "b"}
    public = Public()
    shield = ObligationShield(public, "invented")
    shield.execute("db_insert_many", {"table": "demo", "rows": [a, b]})
    assert shield.execute("db_insert", {"table": "demo", "row": a})["ok"] is False
    assert len(public.calls) == 1
    assert decisions(shield)[-1]["decision"]["reason"] == "positive_component_overlap"


def test_component_multiplicity_is_preserved_not_a_physical_count():
    row = {"name": "same"}
    public = Public()
    shield = ObligationShield(public, "invented")
    shield.execute("db_insert_many", {"table": "demo", "rows": [row, row]})
    assert len(shield.attempts[0]["components"]) == 2
    assert len(set(shield.attempts[0]["components"])) == 1


def test_conservative_baseline_literal_unkeyed_repeat_block_and_same_keys():
    public = Public([TIMEOUT], idempotent=True)
    baseline = ObligationShield(public, "invented", mode="no_unkeyed_repeat")
    baseline.execute("write", {"value": "a"})
    assert baseline.execute("write", {"value": "a"})["ok"] is False
    assert len(public.calls) == 1 and not public.verifications
    keyed = Public([TIMEOUT], keyed=True)
    baseline = ObligationShield(keyed, "invented", mode="no_unkeyed_repeat")
    baseline.execute("write", {"value": "a"})
    baseline.execute("write", {"value": "a"})
    assert len(keyed.calls) == 2 and not keyed.verifications


def test_finish_read_and_unknown_tools_keep_native_dispatch():
    public = Public()
    shield = ObligationShield(public, "invented")
    for name in ("finish", "read", "unknown_tool"):
        shield.execute(name, {})
    assert [item[0] for item in public.calls] == ["finish", "read", "unknown_tool"]
    assert not shield.attempts and not decisions(shield)


def test_actual_sdk_receipt_maps_only_public_report():
    pytest.importorskip("consequa_x")
    public = Public([TIMEOUT])
    shield = ObligationShield(public, "invented")
    shield.execute("write", {})
    shield.execute("write", {})
    receipt = next(event["receipt"] for event in shield.interventions if event["kind"] == "package_receipt")
    assert receipt["framework_version"] == "2.1.1"
    assert receipt["verification"]["origin"] == "unknown"
    assert receipt["verification"]["status"] == "violated"
    assert shield.attempts[0]["disposition"] == "unknown"


def test_every_prior_attempt_must_be_terminal_not_only_latest():
    public = Public([TIMEOUT])
    shield = ObligationShield(public, "invented")
    shield.execute("write", {})
    first = copy.deepcopy(shield.attempts[0])
    second = copy.deepcopy(first)
    second.update(attempt_id="invented:attempt:2", disposition="terminal_no_effect",
                  observation={"ok": False, "terminal_not_committed": True})
    report = {"attempt_id": second["attempt_id"], "status": "absent",
        "detail": {"available": True, "complete": True, "as_of": 1}, "t_call": 0, "t_observed": 1}
    second["reports"] = [report]
    inputs = {"mode": "obligation_shield", "tool": "write", "args": {},
        "contract": public.contract("write", {}), "related_attempts": [first, second], "current_report": report}
    assert recompute_decision(inputs)["dispatch"] is False
    first.update(disposition="terminal_no_effect", observation={"ok": False, "terminal_not_committed": True})
    assert recompute_decision(inputs)["dispatch"] is True


def test_counterexample_and_decision_corruption_are_rejected():
    public = Public([TIMEOUT])
    shield = ObligationShield(public, "invented")
    shield.execute("write", {})
    shield.execute("write", {})
    certificate = copy.deepcopy(decisions(shield)[-1])
    assert check_certificate(certificate)
    certificate["decision"]["counterexample"]["worlds"][1]["matching_effects_after_time_2"] = 1
    with pytest.raises(ValueError):
        check_certificate(certificate)
    certificate = copy.deepcopy(decisions(shield)[-1])
    certificate["decision"]["dispatch"] = True
    with pytest.raises(ValueError):
        check_certificate(certificate)


def test_no_visibility_or_fault_fields_enter_contract_certificate():
    public = Public()
    contract = public.contract("write", {})
    for field in ("visibility_sla", "fault_truth", "inflight_due"):
        malformed = {**contract, field: 90}
        with pytest.raises(ValueError):
            describe_request("write", {}, malformed)


def test_sink_failure_and_dispatch_exception_close_future_writes():
    public = Public()
    def fail(_event):
        raise RuntimeError("invented sink failure")
    shield = ObligationShield(public, "invented", journal=fail)
    with pytest.raises(RuntimeError):
        shield.execute("write", {})
    with pytest.raises(RuntimeError):
        shield.execute("write", {})
    assert not public.calls
    public = Public()
    def dispatch_fails(*_args, **_kwargs):
        public.calls.append("uncertain")
        raise RuntimeError("invented response loss")
    public.execute = dispatch_fails
    shield = ObligationShield(public, "invented")
    with pytest.raises(RuntimeError):
        shield.execute("write", {})
    with pytest.raises(RuntimeError):
        shield.execute("write", {})
    assert len(public.calls) == 1


def test_checker_import_does_not_import_policy_sdk_or_native():
    result = subprocess.run([sys.executable, "-B", "-c",
        "import sys; import research.obligation_shield.certificates; "
        "assert 'research.obligation_shield.policy' not in sys.modules; "
        "assert 'consequa_x' not in sys.modules; assert 'limbo.tasks' not in sys.modules"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


@pytest.fixture(scope="module")
def native():
    path = Path(os.environ.get("CONSEQAX_LIMBO_ROOT",
        "C:/Code/ConsequaX-Research/limbo-pinned-2db09fba")).resolve()
    if not (path / "limbo/world.py").is_file():
        pytest.skip("Pinned native implementation is unavailable for invented-world checks")
    from research.limbo_agent.protocol import PIN, native_binding
    assert native_binding(path)["commit"] == PIN
    saved_modules = {key: value for key, value in sys.modules.items()
                     if key == "limbo" or key.startswith("limbo.")}
    saved_path = list(sys.path)
    try:
        for key in saved_modules:
            del sys.modules[key]
        sys.path.insert(0, str(path))
        modules = {name: importlib.import_module("limbo." + name)
                   for name in ("world", "services", "runtime", "policies")}
        assert "limbo.tasks" not in sys.modules
        assert all(Path(module.__file__).resolve().is_relative_to(path)
                   for module in modules.values())
        yield modules
    finally:
        for key in list(sys.modules):
            if key == "limbo" or key.startswith("limbo."):
                del sys.modules[key]
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


def invented_runtime(native, mode):
    world = native["world"].World(seed=1701, human_available=False)
    world.tables = {"invented"}
    runtime = native["runtime"].ToolRuntime(world, native["services"].build_tools("native"),
        [] if mode == "none" else [native["runtime"].FaultSpec(mode, "db_insert")])
    return runtime


def test_invented_late_commit_counterexample_differs_from_native_guard(native):
    args = {"table": "invented", "row": {"name": "x"}}
    original = invented_runtime(native, "timeout_late")
    guarded = invented_runtime(native, "timeout_late")
    reference = native["policies"].make_policy("guard", "invented")
    shield = make_policy("obligation_shield", "invented")
    for _ in range(3):
        reference.execute(original, "db_insert", copy.deepcopy(args))
        shield.execute(guarded, "db_insert", copy.deepcopy(args))
    original.flush()
    guarded.flush()
    assert len(original.world.ledger) > 1 and len(guarded.world.ledger) == 1
    assert any(event.get("kind") == "obligation_decision" for event in shield.interventions)


def test_first_transport_redelivery_is_not_prevented_by_client_shield(native):
    runtime = invented_runtime(native, "duplicate_delivery")
    shield = NativeObligationPolicy("invented")
    args = {"table": "invented", "row": {"name": "x"}}
    shield.execute(runtime, "db_insert", args)
    shield.execute(runtime, "db_insert", args)
    runtime.flush()
    assert len(runtime.world.ledger) == 2


def test_no_unkeyed_repeat_and_shield_delegate_finish(native):
    for name in ("no_unkeyed_repeat", "obligation_shield"):
        runtime = invented_runtime(native, "none")
        policy = make_policy(name, "invented")
        result = policy.execute(runtime, "finish", {"status": "uncertain", "summary": "Invented test"})
        assert result["ok"] and runtime.finished["status"] == "uncertain"
