"""Synthetic DEVELOPMENT fixtures only; no application world/corpus is imported."""

import builtins
import copy
import itertools

import pytest

from research.recovery_study.controllers import Controller, METHODS


SOURCE = "sqlite:development-readback"
EXPECTED = {"tenant": "development", "resource": "widget", "state": "active"}
SCOPE = {"tenant": "development", "resource": "widget"}
READBACK_METHODS = tuple(method for method in METHODS if method != "response_retry")


def controller(method="reference", **settings):
    options = dict(action_id="development-operation", actor="development-agent",
                   expected=EXPECTED, scope=SCOPE, deadline_ms=100, stability_ms=20,
                   source=SOURCE, read_times=[20, 120, 160, 200], max_dispatches=2)
    options.update(settings)
    return Controller(method, **options)


def row(identity="development-record", committed=10, **changes):
    result = {**EXPECTED, "effect_id": identity, "committed_at_ms": committed,
              "action_id": "development-operation", "actor": "development-agent",
              "attempt_id": "development-operation:attempt-1"}
    result.update(changes)
    return result


def observation(at=120, records=None, **changes):
    result = dict(observation_id=f"development-read-{at}", source=SOURCE,
                  observed_at_ms=at, as_of_ms=at, scope=copy.deepcopy(SCOPE),
                  records=[] if records is None else copy.deepcopy(records),
                  complete=True, available=True)
    result.update(changes)
    return result


def start(method="reference", terminal=False, **settings):
    control = controller(method, **settings)
    initial = control.begin()
    reply = {"status": "timeout", "attempt_id": initial["attempt_id"]}
    if terminal:
        reply["terminal_not_committed"] = True
    control.on_response(reply, 10)
    return control


def final_read(method, records, **changes):
    control = start(method, read_times=[120, 160])
    assert control.decide(120)["kind"] == "read"
    control.on_readback(observation(records=records, **changes))
    return control


def test_response_proxy_is_classical_stable_identity_timeout_retry():
    control = start("response_retry")
    retry = control.decide(10)
    assert retry["kind"] == "dispatch"
    assert retry["idempotency_key"] == "development-operation"
    assert retry["attempt_id"] == "development-operation:attempt-2"
    control.on_response({"status": "success"}, 15)
    assert control.decide(15)["kind"] == "stop"
    report = control.finalize()
    assert report["reported_state"] is True
    assert report["reported_action_linked"] is True
    assert report["final_target_state"] is None  # The proxy has made an unsupported claim.
    assert report["dispatches"] == 2 and report["reads"] == 0


def test_response_proxy_does_not_retry_at_or_after_original_deadline():
    control = start("response_retry")
    assert control.decide(100)["kind"] == "abstain"
    assert control.finalize()["dispatches"] == 1


@pytest.mark.parametrize("method", READBACK_METHODS)
def test_declared_native_deduplication_permits_bounded_same_key_timeout_retry(method):
    control = start(method, native_idempotency=True)
    retry = control.decide(10)
    assert retry["kind"] == "dispatch"
    assert retry["idempotency_key"] == "development-operation"
    control.on_response({"status": "timeout"}, 15)
    assert control.decide(15)["kind"] != "dispatch"
    report = control.finalize()
    assert report["native_idempotency"] is True
    assert report["dispatches"] == 2 and report["reported_state"] is None


@pytest.mark.parametrize("method", READBACK_METHODS)
def test_native_deduplication_never_allows_postdeadline_timeout_retry(method):
    control = start(method, native_idempotency=True)
    assert control.decide(100)["kind"] != "dispatch"
    assert control.finalize()["dispatches"] == 1


@pytest.mark.parametrize("method", READBACK_METHODS)
def test_unknown_absence_never_opens_an_ordinary_retry(method):
    control = start(method)
    at = 120 if method == "consequax_one_read" else 20
    assert control.decide(at)["kind"] == "read"
    control.on_readback(observation(at, [], as_of_ms=at - 1))
    decision = control.decide(at)
    assert decision["kind"] != "dispatch"
    assert control.finalize()["reported_state"] is None
    assert control.finalize()["dispatches"] == 1


@pytest.mark.parametrize("method", READBACK_METHODS)
def test_all_terminal_guarantees_and_fresh_absence_allow_predeadline_retry(method):
    control = start(method, terminal=True)
    assert control.decide(20)["kind"] == "read"
    control.on_readback(observation(20, []))
    assert control.finalize()["reported_state"] is None
    retry = control.decide(20)
    assert retry["kind"] == "dispatch" and retry["idempotency_key"] == control.action_id
    control.on_response({"status": "success"}, 30)
    assert control.decide(120)["kind"] == "read"
    control.on_readback(observation(120, [row(committed=30,
                                           attempt_id="development-operation:attempt-2")]))
    assert control.decide(120)["kind"] == "stop"
    report = control.finalize()
    assert report["reported_state"] is True
    assert report["reported_action_linked"] is (None if method == "readback_state" else True)
    assert report["dispatches"] == 2 and report["reads"] == 2
    if method.startswith("consequax_"):
        # The fixed contract remains unresolved in the provisional read's receipt.
        assert report["framework_trace"]["verifications"][0]["status"] == "unknown"
        assert report["provisional_verifications"][0]["effect_ids"] == []


@pytest.mark.parametrize("method", READBACK_METHODS)
@pytest.mark.parametrize("limitation", ["lag", "unavailable", "incomplete", "wrong-source",
                                       "existing-effect", "stale-decision"])
def test_terminal_guarantee_still_requires_fresh_trusted_complete_absence(method, limitation):
    control = start(method, terminal=True)
    assert control.decide(20)["kind"] == "read"
    changes = {"lag": {"as_of_ms": 19}, "unavailable": {"available": False},
               "incomplete": {"complete": False}, "wrong-source": {"source": "untrusted"},
               "existing-effect": {"records": [row()]}, "stale-decision": {}}[limitation]
    control.on_readback(observation(20, **changes))
    assert control.decide(21 if limitation == "stale-decision" else 20)["kind"] != "dispatch"


@pytest.mark.parametrize("method", READBACK_METHODS)
def test_horizon_absence_is_failure_without_a_postdeadline_rescue(method):
    control = final_read(method, [])
    assert control.decide(120)["kind"] == "stop"
    report = control.finalize()
    assert report["reported_state"] is False and report["dispatches"] == 1
    if method.startswith("consequax_"):
        assert report["retry_advice"]["advice"] == "retry_permitted"
        # Application fixed-deadline policy intentionally declines that advice.


@pytest.mark.parametrize("method", ("reference", "consequax_one_read", "consequax_poll"))
def test_global_target_and_this_action_target_are_separate(method):
    other = row(action_id="another-operation", actor="another-actor")
    report = final_read(method, [other]).finalize()
    assert report["reported_success"] is True
    assert report["reported_state"] is True and report["reported_action_linked"] is False
    unattributed = row()
    del unattributed["action_id"], unattributed["actor"], unattributed["attempt_id"]
    report = final_read(method, [unattributed]).finalize()
    assert report["reported_state"] is True
    assert report["reported_action_linked"] is None and report["action_linked_abstained"]


@pytest.mark.parametrize("method", ("reference", "consequax_one_read", "consequax_poll"))
@pytest.mark.parametrize("extra", [row("second-own", 30),
                                   row("transient-extra", 110, removed_at_ms=115)])
def test_own_matching_witness_cannot_rescue_a_violated_exact_count_target(method, extra):
    report = final_read(method, [row(), extra]).finalize()
    assert report["reported_state"] is False
    assert report["reported_action_linked"] is False


def test_single_final_read_is_horizon_eligible_and_polling_can_resolve_lag():
    one, poll = start("consequax_one_read"), start("consequax_poll")
    assert one.decide(10)["at_ms"] == 120  # skips a needless predeadline query
    assert poll.decide(20)["kind"] == "read"
    poll.on_readback(observation(20, [row()]))
    for control in (one, poll):
        assert control.decide(120)["kind"] == "read"
        control.on_readback(observation(120, [row()], as_of_ms=119))
    assert one.decide(120)["kind"] == "abstain"
    assert poll.decide(120)["at_ms"] == 160
    assert poll.decide(160)["kind"] == "read"
    poll.on_readback(observation(160, [row()]))
    assert poll.decide(160)["kind"] == "stop"
    assert one.finalize()["reported_success"] is None
    assert poll.finalize()["reported_success"] is True
    assert one.finalize()["final_reads"] == 1
    assert poll.finalize()["final_reads"] == 2


def test_reference_does_not_import_package(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith("consequa_x"):
            raise AssertionError("independent reference imported the framework")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert final_read("reference", [row()]).finalize()["reported_success"] is True


def test_development_interval_provenance_grid_matches_public_framework():
    # This grid is a synthetic rule check, never a measured application run.
    for committed, removed, origin, exact in itertools.product(
            (0, 100, 101, 120, 121), (None, 110, 120), ("own", "other", "missing"), (0, 1, None)):
        if removed is not None and removed < committed:
            continue
        record = row(committed=committed)
        if removed is not None:
            record["removed_at_ms"] = removed
        if origin == "other":
            record.update(action_id="other", actor="other")
        elif origin == "missing":
            for key in ("action_id", "actor", "attempt_id"):
                record.pop(key)
        reports = []
        for method in ("reference", "consequax_poll"):
            control = start(method, read_times=[160], exact_count=exact)
            assert control.decide(160)["kind"] == "read"
            control.on_readback(observation(160, [record]))
            reports.append(control.finalize())
        for field in ("reported_state", "reported_action_linked", "final_target_state"):
            assert reports[0][field] == reports[1][field], (committed, removed, origin, exact, field)


@pytest.mark.parametrize("records", [
    [row(), row()], [row(committed=True)], [row(committed=121)],
    [row(removed_at_ms=9)], [row(actor="")], [row(tenant="outside")],
    [row(), row("transient-extra", 110, removed_at_ms=115)],
    [row(), row("simultaneous-extra", 110, removed_at_ms=110)],
])
def test_adversarial_development_records_have_reference_framework_parity(records):
    reports = [final_read(method, records).finalize() for method in ("reference", "consequax_poll")]
    for field in ("reported_state", "reported_action_linked"):
        assert reports[0][field] == reports[1][field]


def test_input_boundary_rejects_hidden_metadata_and_unsupported_callbacks():
    control = controller()
    with pytest.raises(ValueError, match="begin"):
        control.decide(0)
    dispatch = control.begin()
    with pytest.raises(ValueError, match="outside"):
        control.on_response({"status": "timeout", "case_id": "not-admitted"}, 10)
    with pytest.raises(ValueError, match="different attempt"):
        control.on_response({"status": "timeout", "attempt_id": "foreign"}, 10)
    control.on_response({"status": "timeout", "attempt_id": dispatch["attempt_id"]}, 10)
    assert control.decide(20)["kind"] == "read"
    with pytest.raises(ValueError, match="exactly"):
        control.on_readback(observation(20, hidden_config={}))
    control.on_readback(observation(20))
    with pytest.raises(ValueError, match="chronological"):
        control.decide(19)


def test_caller_mutations_cannot_change_registered_target_or_returned_decisions():
    expected, scope = copy.deepcopy(EXPECTED), copy.deepcopy(SCOPE)
    control = controller(expected=expected, scope=scope)
    expected["state"] = "changed"
    scope["tenant"] = "changed"
    first = control.begin()
    first["idempotency_key"] = "changed"
    assert control.expected == EXPECTED and control.scope == SCOPE
    assert control.finalize()["decisions"][0]["idempotency_key"] == control.action_id
