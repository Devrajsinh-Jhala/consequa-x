"""Semantic and optional unchanged-upstream integration checks for tau transfer."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path

import pytest

from consequa_x import Action, Observation, OutcomeContract, ResponseStatus, VerificationStatus, verify

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tau_validation", ROOT / "scripts/run_tau_benchmark_validation.py")
tau = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tau)


def cancellation():
    before = {"read_tool": "get_order_details", "read_arguments": {"order_id": "#TEST"},
              "value": {"order_id": "#TEST", "status": "pending", "cancel_reason": None}}
    args = {"order_id": "#TEST", "reason": "no longer needed"}
    expected = tau.payload_contract("retail", "cancel_pending_order", args, before)
    return before, args, expected


def test_schedule_uses_every_source_task_and_fixed_controls():
    records = {"retail": [{"id": "8"}, {"id": "3"}], "airline": [{"id": "1"}]}
    schedule = tau.make_schedule(records)
    assert len(schedule) == 12
    assert [s["slot"] for s in schedule] == list(range(12))
    assert [s["task_id"] for s in schedule[::4]] == ["8", "3", "1"]
    assert [s["variant"] for s in schedule[:4]] == list(tau.VARIANTS)
    changed = deepcopy(records)
    changed["airline"][0]["new"] = 1
    assert tau.make_schedule(changed)[-1]["task_sha256"] != schedule[-1]["task_sha256"]


def test_payload_compiler_has_no_task_or_reward_input():
    import inspect
    assert list(inspect.signature(tau.payload_contract).parameters) == ["domain", "tool", "args", "before"]
    before, args, expected = cancellation()
    assert "actions" not in expected and "reward" not in expected
    assert tau.evaluate_checks(expected, before) == [False, False]
    after = deepcopy(before)
    after["value"].update(status="cancelled", cancel_reason=args["reason"])
    assert tau.evaluate_checks(expected, after) == [True, True]


@pytest.mark.parametrize("variant", ["missing", "partial", "stale", "scope", "malformed"])
def test_unavailable_incomplete_stale_or_outside_scope_never_succeeds(variant):
    before, args, expected = cancellation()
    action = Action("a", "t", "actor", "cancel_pending_order", args, 0,
                    OutcomeContract("c", "tau_record_fields", expected, 1))
    scope = {"domain": "retail", "read_arguments": {"order_id": "#TEST"}}
    record = deepcopy(before)
    record["value"].update(status="cancelled", cancel_reason=args["reason"])
    if variant == "scope":
        scope["read_arguments"]["order_id"] = "#OTHER"
    if variant == "malformed":
        record["value"].pop("status")
    observation = Observation("o", "read", 2, 0 if variant == "stale" else 2, scope,
                              () if variant == "missing" else (record,),
                              complete=variant != "partial", available=variant != "missing")
    assert verify(action, observation, verifier=tau.TauRecordVerifier()).status is VerificationStatus.UNKNOWN


def test_false_acknowledgement_cannot_establish_success_or_origin():
    before, args, expected = cancellation()
    capture = tau.audit_capture("a", "retail", "cancel_pending_order", args, expected,
                                before, ResponseStatus.SUCCESS, "Success: operation completed")
    receipt = capture["trace"]["verifications"][0]
    assert receipt["status"] == "violated"
    assert receipt["origin"] == "unknown"
    assert capture["withheld_status"] == "unknown"
    assert capture["explanation"]["assessment_alignment"] == "unassessable"
    assert capture["inputs_unchanged"] is True


def test_wrong_record_identity_cannot_pass_a_correctly_labeled_scope():
    before, args, expected = cancellation()
    before["value"].update(order_id="#OTHER", status="cancelled", cancel_reason=args["reason"])
    capture = tau.audit_capture("a", "retail", "cancel_pending_order", args, expected,
                                before, ResponseStatus.SUCCESS, "success")
    assert capture["trace"]["verifications"][0]["status"] == "unknown"


def test_booking_requires_new_matching_readback_not_existing_identical_record():
    args = {"user_id": "u", "origin": "SFO", "destination": "JFK", "flight_type": "one_way",
            "cabin": "economy", "passengers": [{"first_name": "A"}], "total_baggages": 1,
            "nonfree_baggages": 0, "insurance": "no", "flights": [{"flight_number": "F1", "date": "2024-01-01"}]}
    before = {"read_tool": "get_user_details+get_reservation_details", "read_arguments": {"user_id": "u"},
              "value": {"reservations": ["old"]}, "reservations": []}
    expected = tau.payload_contract("airline", "book_reservation", args, before)
    row = {k: deepcopy(v) for k, v in args.items()}
    row["reservation_id"] = "old"
    snapshot = {**before, "reservations": [row]}
    assert tau.evaluate_checks(expected, snapshot) == [False]
    row["reservation_id"] = "new"
    assert tau.evaluate_checks(expected, snapshot) == [True]
    row["flights"][0]["date"] = "2024-01-02"
    assert tau.evaluate_checks(expected, snapshot) == [False]


def test_new_certificate_and_payment_need_new_rows():
    before = {"read_tool": "get_user_details", "read_arguments": {"user_id": "u"},
              "value": {"payment_methods": {"certificate_old": {"source": "certificate", "amount": 10}}}}
    expected = tau.payload_contract("airline", "send_certificate", {"user_id": "u", "amount": 10}, before)
    assert tau.evaluate_checks(expected, before) == [False]
    after = deepcopy(before)
    after["value"]["payment_methods"]["certificate_new"] = {"source": "certificate", "amount": 10}
    assert tau.evaluate_checks(expected, after) == [True]


def test_network_is_denied_and_restored():
    import socket
    original = socket.create_connection
    with tau.no_network(), pytest.raises(RuntimeError, match="Networking is disabled"):
        socket.create_connection(("127.0.0.1", 1))
    assert socket.create_connection is original


def test_exclusive_output_refuses_overwrite(tmp_path):
    tau.write_new(tmp_path / "receipt.json", {"a": 1})
    with pytest.raises(FileExistsError):
        tau.write_new(tmp_path / "receipt.json", {"a": 2})


def test_frozen_protocol_refuses_even_whitespace_only_mutation(tmp_path):
    protocol = {"schema": tau.SCHEMA, "planned": 656}
    tau.write_frozen_protocol(tmp_path, protocol)
    assert tau.load_frozen_protocol(tmp_path) == protocol
    path = tmp_path / "protocol.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="protocol file bytes"):
        tau.load_frozen_protocol(tmp_path)


def test_frozen_protocol_requires_original_hash_receipt(tmp_path):
    tau.write_new(tmp_path / "protocol.json", {"schema": tau.SCHEMA})
    with pytest.raises(ValueError, match="receipt is missing"):
        tau.load_frozen_protocol(tmp_path)


def test_frozen_protocol_hash_receipt_is_exclusive(tmp_path):
    tau.write_frozen_protocol(tmp_path, {"schema": tau.SCHEMA})
    with pytest.raises(FileExistsError):
        tau.write_frozen_protocol(tmp_path, {"schema": tau.SCHEMA, "changed": True})


@pytest.mark.skipif(not os.getenv("CONSEQUA_TAU_SOURCE"), reason="Explicit reviewed upstream checkout required")
@pytest.mark.parametrize("domain,task_id", [("retail", "0"), ("airline", "19"), ("airline", "20")])
def test_native_cross_domain_reference_and_no_write_controls(domain, task_id):
    source = Path(os.environ["CONSEQUA_TAU_SOURCE"])
    native = tau.bootstrap(source)
    task = next(t for t in native["domains"][domain].get_tasks("base") if t.id == task_id)
    with tau.no_network():
        reference = tau.execute_case(native, domain, task, "reference", 0)
        omitted = tau.execute_case(native, domain, task, "false_acknowledgement", 1)
    assert reference["native_db_component"]["db_check"]["db_match"] is True
    assert omitted["native_db_component"]["db_check"]["db_match"] is False
    for result in (reference, omitted):
        assert result["model_calls"] == 0
        assert all(a["audit_disposition"] == "captured" for a in result["action_audits"])
    assert all(a["trace"]["verifications"][0]["status"] == "satisfied" for a in reference["action_audits"])
    assert all(a["trace"]["verifications"][0]["status"] == "violated" for a in omitted["action_audits"])
