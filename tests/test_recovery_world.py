"""Synthetic simulator fixtures only; this module never opens the held-out corpus."""

from copy import deepcopy
import sqlite3

import pytest

from research.recovery_study.world import World, public_case


def fixture_case(domain="inventory_reservation", **configuration):
    payloads = {
        "inventory_reservation": {"warehouse": "dev-store", "sku": "dev-item", "quantity": 2,
                                  "reservation_ref": "dev-reservation"},
        "support_transition": {"ticket_id": "dev-ticket", "status": "resolved", "queue": "dev-queue"},
        "delivery_registration": {"artifact_id": "dev-artifact", "delivery_channel": "dev-channel",
                                   "checksum": "dev-checksum"},
    }
    payload = payloads[domain]
    fields = {"inventory_reservation": ["warehouse", "sku", "reservation_ref"],
              "support_transition": ["ticket_id"],
              "delivery_registration": ["artifact_id", "delivery_channel"]}[domain]
    return {"case_id": "synthetic-development", "family_id": "synthetic-only", "domain": domain,
            "operation_id": "dev-op", "actor": "dev-agent", "initial_at_ms": 0,
            "target": {"predicate": "record_present", "expected": deepcopy(payload), "exact_count": 1},
            "payload": deepcopy(payload), "deadline_ms": 50, "stability_ms": 30,
            "recovery_deadline_ms": 120, "safety_horizon_ms": 180,
            "scope_fields": fields, "scope": {k: payload[k] for k in fields},
            "native_idempotency": False, "_world": configuration}


def dispatch(world, at=0):
    return world.dispatch("dev-op", "dev-agent", at)


def test_actual_inventory_commit_and_release_are_sqlite_side_effects(tmp_path):
    case = fixture_case(dispatch_plans=[{"commit_delay_ms": 10, "remove_after_ms": 20}], inventory_capacity=7)
    with World(case, 1, tmp_path / "inventory.db") as world:
        dispatch(world)
        assert world.db.execute("SELECT COUNT(*) FROM inventory_reservations").fetchone()[0] == 0
        world.advance(10)
        with sqlite3.connect(world.db_path) as independent:
            assert independent.execute("SELECT available FROM inventory_stock").fetchone()[0] == 5
            assert independent.execute("SELECT quantity,state FROM inventory_reservations").fetchone() == (2, "active")
        world.advance(30)
        assert world.db.execute("SELECT available FROM inventory_stock").fetchone()[0] == 7
        assert world.readback(80)["records"][0]["removed_at_ms"] == 30


@pytest.mark.parametrize("domain,table", [("support_transition", "ticket_transitions"),
                                           ("delivery_registration", "delivery_registrations")])
def test_domains_write_business_tables_and_reversals(tmp_path, domain, table):
    with World(fixture_case(domain, dispatch_plans=[{"remove_after_ms": 20}]), 1, tmp_path / "business.db") as world:
        dispatch(world)
        assert world.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
        if domain == "support_transition":
            assert world.db.execute("SELECT status FROM support_tickets").fetchone()[0] == "resolved"
        world.advance(20)
        if domain == "support_transition":
            assert world.db.execute("SELECT status FROM support_tickets").fetchone()[0] == "open"
        assert world.db.execute(f"SELECT state FROM {table}").fetchone()[0] in {"reversed", "revoked"}


def test_support_superseding_state_expires_previous_state_certificate(tmp_path):
    case = fixture_case("support_transition", dispatch_plans=[{"commit_delay_ms": 5},
                       {"commit_delay_ms": 5, "value_overrides": {"status": "reopened"}}])
    with World(case, 1, tmp_path / "superseding.db") as world:
        dispatch(world)
        dispatch(world, 20)
        records = world.readback(80)["records"]
        assert records[0]["removed_at_ms"] == 25
        assert records[1]["status"] == "reopened"
        assert world.db.execute("SELECT status FROM support_tickets").fetchone()[0] == "reopened"
        assert world.truth(180)["target_satisfied"] is False


def test_timeout_after_commit_does_not_leak_effect(tmp_path):
    case = fixture_case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 0}])
    with World(case, 1, tmp_path / "after.db") as world:
        response = dispatch(world)
        assert response == {"status": "timeout", "response_at_ms": 5, "attempt_id": "dev-op:attempt-1",
                            "result": {"code": "transport_timeout"}}
        assert world.readback(80)["records"][0]["action_id"] == "dev-op"
        assert world.truth(180)["linked_target_satisfied"] is True


def test_timeout_before_commit_is_ambiguous_and_late_effect_is_real(tmp_path):
    with World(fixture_case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 90}]), 1,
               tmp_path / "before.db") as world:
        response = dispatch(world)
        assert "terminal_not_committed" not in response
        assert world.readback(80)["records"] == []
        truth = world.truth(180)
        assert truth["target_satisfied"] is False
        assert truth["eventual_recovery_satisfied"] is True
        assert truth["metrics"]["committed_effects"] == 1


def test_false_ack_is_not_a_record(tmp_path):
    with World(fixture_case(dispatch_plans=[{"status": "success", "commit_delay_ms": None}]), 1,
               tmp_path / "ack.db") as world:
        assert dispatch(world)["status"] == "success"
        assert world.readback(80)["records"] == []
        assert world.truth(180)["own_effect_count"] == 0


def test_native_idempotency_reserves_pending_identity(tmp_path):
    case = fixture_case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 30}])
    case["native_idempotency"] = True
    with World(case, 1, tmp_path / "native.db") as world:
        dispatch(world)
        dispatch(world, 10)
        assert world.db.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0] == 1
        truth = world.truth(180)
        assert truth["metrics"]["native_replays"] == 1
        assert truth["own_effect_count"] == 1
        assert truth["duplicate_count"] == 0


def test_without_idempotency_retries_write_twice_and_duplicate_at_safety_horizon(tmp_path):
    case = fixture_case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 30}])
    with World(case, 1, tmp_path / "duplicates.db") as world:
        dispatch(world)
        dispatch(world, 100)
        truth = world.truth(180)
        assert truth["target_satisfied"] is True
        assert truth["eventual_recovery_satisfied"] is False
        assert truth["duplicate_count"] == 1
        assert truth["own_unwanted_effect_count"] == 1
        assert truth["metrics"]["committed_effects"] == 2


def test_external_match_is_satisfied_but_not_causally_linked(tmp_path):
    case = fixture_case(dispatch_plans=[{"commit_delay_ms": None}],
                        external_events=[{"at_ms": 20, "actor": "dev-human"}])
    with World(case, 1, tmp_path / "external.db") as world:
        dispatch(world)
        observation = world.readback(80)
        assert observation["records"][0]["actor"] == "dev-human"
        truth = world.truth(180)
        assert truth["target_satisfied"] is True
        assert truth["linked_target_satisfied"] is False
        assert truth["own_effect_count"] == 0


@pytest.mark.parametrize("provenance", [[], ["actor"]])
def test_wrong_values_and_missing_provenance_never_forge_linkage(tmp_path, provenance):
    case = fixture_case(dispatch_plans=[{"value_overrides": {"quantity": 3}, "provenance": provenance}])
    with World(case, 1, tmp_path / "wrong.db") as world:
        dispatch(world)
        record = world.readback(80)["records"][0]
        assert record["quantity"] == 3
        assert (record.get("actor") == "dev-agent") == bool(provenance)
        assert "action_id" not in record and "attempt_id" not in record
        assert not any(k.startswith("_causal") for k in record)
        truth = world.truth(180)
        assert truth["target_satisfied"] is False
        assert truth["own_unwanted_effect_count"] == 1
        assert truth["records"][0]["_causal_action_id"] == "dev-op"


def test_stale_partial_unavailable_views_are_honest(tmp_path):
    case = fixture_case(dispatch_plans=[{"commit_delay_ms": 20}], readback={"windows": [
        {"start_ms": 0, "until_ms": 35, "lag_ms": 30},
        {"start_ms": 35, "until_ms": 60, "record_limit": 0},
        {"start_ms": 60, "until_ms": 90, "available": False},
    ]})
    with World(case, 1, tmp_path / "views.db") as world:
        dispatch(world)
        stale = world.readback(30)
        assert stale["as_of_ms"] == 0 and stale["records"] == [] and stale["complete"] is True
        partial = world.readback(40)
        assert partial["records"] == [] and partial["complete"] is False
        unavailable = world.readback(80)
        assert unavailable["available"] is False and unavailable["complete"] is False
        full = world.readback(100)
        assert full["complete"] is True and len(full["records"]) == 1
        assert world.truth(180)["metrics"]["readback_calls"] == 4


def test_removed_history_is_visible_only_after_removal_watermark(tmp_path):
    case = fixture_case(dispatch_plans=[{"commit_delay_ms": 10, "remove_after_ms": 30}], readback={"lag_ms": 20})
    with World(case, 1, tmp_path / "history.db") as world:
        dispatch(world)
        assert "removed_at_ms" not in world.readback(50)["records"][0]
        assert world.readback(80)["records"][0]["removed_at_ms"] == 40
        assert world.truth(180)["target_satisfied"] is False


@pytest.mark.parametrize("retry_at", [10, 90])
def test_terminal_no_commit_is_attempt_scoped_and_enables_real_recovery(tmp_path, retry_at):
    case = fixture_case(dispatch_plans=[
        {"status": "error", "commit_delay_ms": None, "terminal_not_committed": True},
        {"status": "success", "commit_delay_ms": 10},
    ])
    with World(case, 1, tmp_path / "terminal.db") as world:
        response = dispatch(world)
        assert response["terminal_not_committed"] is True
        assert response["attempt_id"] == "dev-op:attempt-1"
        dispatch(world, retry_at)
        truth = world.truth(180)
        assert truth["target_satisfied"] == (retry_at + 10 <= 50)
        assert truth["linked_recovery_satisfied"] is True
        assert truth["records"][0]["_causal_attempt_id"] == "dev-op:attempt-2"
        assert truth["pending_event_count"] == 0


def test_terminal_attempt_does_not_cancel_earlier_ambiguous_work(tmp_path):
    case = fixture_case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 80},
                                       {"status": "error", "commit_delay_ms": None,
                                        "terminal_not_committed": True}])
    with World(case, 1, tmp_path / "attempt-scope.db") as world:
        dispatch(world)
        terminal = dispatch(world, 10)
        assert terminal["terminal_not_committed"] is True
        assert terminal["attempt_id"] == "dev-op:attempt-2"
        truth = world.truth(180)
        assert truth["records"][0]["_causal_attempt_id"] == "dev-op:attempt-1"
        assert truth["records"][0]["committed_at_ms"] == 80


def test_terminal_commit_contradiction_is_rejected_and_replay_does_not_claim_finality(tmp_path):
    case = fixture_case(dispatch_plans=[{"commit_delay_ms": 10, "terminal_not_committed": True}])
    with World(case, 1, tmp_path / "invalid.db") as world:
        with pytest.raises(ValueError, match="cannot schedule"):
            dispatch(world)
    case = fixture_case(dispatch_plans=[{"commit_delay_ms": 90},
                                       {"commit_delay_ms": None, "terminal_not_committed": True}])
    case["native_idempotency"] = True
    with World(case, 1, tmp_path / "replay.db") as world:
        dispatch(world)
        assert "terminal_not_committed" not in dispatch(world, 10)
        assert world.truth(180)["own_effect_count"] == 1


def test_seed_jitters_exogenous_time_without_changing_payload_or_authorship(tmp_path):
    case = fixture_case(external_events=[{"at_ms": 10, "jitter_ms": 15}])
    times = set()
    for seed in range(5):
        with World(case, seed, tmp_path / f"seed-{seed}.db") as world:
            record = world.readback(80)["records"][0]
            times.add(record["committed_at_ms"])
            assert 10 <= record["committed_at_ms"] <= 25
            assert record["quantity"] == 2 and record["actor"] == "external-operator"
    assert len(times) > 1


def test_same_seed_history_and_query_times_produce_identical_public_json(tmp_path):
    case = fixture_case(external_events=[{"at_ms": 5, "jitter_ms": 10}],
                        dispatch_plans=[{"status": "timeout", "commit_delay_ms": 25}])
    captures = []
    for name in ("left", "right"):
        with World(case, 91, tmp_path / f"{name}.db") as world:
            captures.append([dispatch(world), world.readback(10), world.readback(80)])
    assert captures[0] == captures[1]


def test_identity_scope_admission_and_public_case_are_separate_from_truth(tmp_path):
    case = fixture_case(readback={"scope": {"warehouse": "another-store"}})
    with World(case, 1, tmp_path / "scope.db") as world:
        assert world.dispatch("wrong-op", "dev-agent", 0)["status"] == "error"
        dispatch(world, 1)
        observation = world.readback(80)
        assert observation["scope"] == {"warehouse": "another-store"} and observation["records"] == []
        assert "_world" not in public_case(case)
        assert "trusted" not in observation
        assert world.source_receipt["trusted"] is True
        assert world.truth(180)["metrics"]["identity_rejections"] == 1
        with pytest.raises(ValueError, match="backwards"):
            world.readback(50)
    with pytest.raises(FileExistsError):
        World(case, 1, tmp_path / "scope.db")


def test_package_record_verifier_accepts_real_application_observation(tmp_path):
    from consequa_x.models import Action, Observation, OutcomeContract
    from consequa_x.record_verifier import RecordVerifier

    case = fixture_case()
    action = Action(action_id="dev-op", actor="dev-agent", name="reserve", arguments=case["payload"],
                    registered_at_ms=0, contract=OutcomeContract(contract_id="dev-contract",
                    deadline_ms=50, stability_ms=30, **case["target"]))
    with World(case, 1, tmp_path / "compatibility.db") as world:
        dispatch(world)
        raw = world.readback(80)
        raw["records"] = tuple(raw["records"])
        receipt = RecordVerifier(scope_fields=tuple(case["scope_fields"])).verify(action, Observation(**raw))
        assert receipt.status.value == "satisfied"
        assert receipt.origin.value == "confirmed"
        assert receipt.target_effect_ids == ("dev-op:attempt-1:effect-1",)
