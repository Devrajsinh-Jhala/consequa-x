"""Public-evidence and corruption boundaries for the offline migration auditor.

The fixtures are synthetic saved JSON records. No framework, collector, study
runner, retained experiment artifact, or live service is imported or executed.
"""

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "v2_migration_artifact_audit",
    Path(__file__).resolve().parents[1] / "scripts/audit_v2_migration_conformance.py",
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def public_snapshot():
    """One complete, on-time, persistent refund with explicit provenance."""
    action = {
        "trace_id": "trace-synthetic",
        "action_id": "refund-action",
        "actor": "agent",
        "registered_at_ms": 10,
        "contract": {
            "contract_id": "refund-contract",
            "expected": {"payment_id": "payment-1", "amount_minor": 100, "currency": "INR"},
            "deadline_ms": 100,
            "stability_ms": 20,
            "exact_count": 1,
        },
    }
    observation = {
        "observation_id": "snapshot-1",
        "source": "refund-ledger",
        "observed_at_ms": 121,
        "as_of_ms": 120,
        "available": True,
        "complete": True,
        "scope": {"payment_id": "payment-1", "currency": "INR"},
        "records": [{
            "effect_id": "refund-1",
            "payment_id": "payment-1",
            "amount_minor": 100,
            "currency": "INR",
            "committed_at_ms": 20,
            "status": "processed",
            "actor": "agent",
            "action_id": "refund-action",
        }],
    }
    return action, observation


def episode_fixture(kind="satisfied"):
    """Hand-authored expected conclusions, including their diagnosis order."""
    action, observation = public_snapshot()
    effect_ids = ["refund-1"]
    status, origin, targets = "satisfied", "confirmed", ["refund-1"]
    prediction = {"state": True, "origin": "confirmed", "action_linked": True}
    alignment = "consistent"
    old_codes = new_codes = ["CONSISTENT_OUTCOME"]
    findings = []
    if kind == "unknown":
        observation["complete"] = False
        status, origin, targets, effect_ids = "unknown", "unknown", None, []
        prediction = {"state": None, "origin": "unknown", "action_linked": None}
        alignment = "unassessable"
        old_codes = new_codes = ["UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT"]
    elif kind == "duplicate":
        observation["records"].append({**observation["records"][0], "effect_id": "refund-2"})
        status, targets, effect_ids = "violated", ["refund-1", "refund-2"], ["refund-1", "refund-2"]
        prediction = {"state": False, "origin": "confirmed", "action_linked": False}
        alignment = "contradicted"
        findings = [{"code": "EXCESS_EFFECTS", "effect_ids": effect_ids},
                    {"code": "DUPLICATE_EFFECT", "effect_ids": effect_ids}]
        old_codes = new_codes = ["ASSESSMENT_DIVERGENCE", "RESPONSE_EFFECT_DIVERGENCE",
                                 "CONSEQUENCE_VIOLATION", "EXCESS_EFFECTS", "DUPLICATE_EFFECT"]
    elif kind == "external":
        observation["records"][0].update(actor="other-agent", action_id="other-action")
        origin, targets = "other_actor", []
        prediction = {"state": True, "origin": "other_actor", "action_linked": False}
        alignment = "unassessable"
        old_codes = ["EXTERNAL_ACTOR_EFFECT"]
        new_codes = ["UNASSESSABLE_ASSESSMENT", "EXTERNAL_ACTOR_EFFECT"]
    elif kind != "satisfied":
        raise ValueError(kind)
    attributed = [] if kind in ("external", "unknown") else effect_ids
    receipt = {
        "contract_id": "refund-contract",
        "status": status,
        "observed_at_ms": 121,
        "evidence": [{
            "observation_id": "snapshot-1", "source": "refund-ledger", "as_of_ms": 120,
            "details": {"records": deepcopy(observation["records"])},
        }],
        "origin": origin,
        "effect_ids": effect_ids,
        "attributable_effect_ids": attributed,
        "reason": "Synthetic public snapshot result",
    }
    raw = {
        "schema_version": "0.1", "trace_id": "trace-synthetic", "action": action,
        "events": [{"trace_id": "trace-synthetic", "event_id": "event-1",
                    "payload": {"amount_minor": 100}}],
        "responses": [{"response_id": "response-1", "status": "success"}],
        "assessment": {"status": "success", "explanation": "Synthetic reported success"},
        "observations": [observation], "verifications": [receipt],
    }
    fresh = {**deepcopy(receipt), "action_id": "refund-action",
             "target_effect_ids": targets, "findings": findings}
    migrated = {
        "schema_version": "1.0", "time_base": "relative_ms", "trace_id": raw["trace_id"],
        "actions": [{k: deepcopy(v) for k, v in action.items() if k != "trace_id"}],
        "events": [{k: deepcopy(v) for k, v in raw["events"][0].items() if k != "trace_id"}],
        "responses": [{**raw["responses"][0], "action_id": "refund-action"}],
        "assessments": [{**raw["assessment"], "assessment_id": "assessment-1",
                         "action_id": "refund-action"}],
        "observations": deepcopy(raw["observations"]), "verifications": [deepcopy(fresh)],
    }
    counts = {"unavailable": int(targets is None), "empty": int(targets == []),
              "nonempty": int(bool(targets))}
    metrics = dict.fromkeys(audit.PRIMARY + audit.SECONDARY, True)
    metrics.update(migration_codes_equal=new_codes == old_codes, fresh_codes_equal=new_codes == old_codes)
    row = {
        "metrics": metrics, "clock_origin_unrecoverable": True,
        "migration_report": {"reproduced": 1, "not_reproduced": 0, "verifications": 1},
        "target_matching": counts, "fresh_target_matching": deepcopy(counts),
        "old": {"recorded_receipts": [deepcopy(receipt)], "fresh_receipts": [deepcopy(receipt)],
                "recorded_prediction": deepcopy(prediction), "fresh_prediction": deepcopy(prediction),
                "recorded_alignment": alignment, "fresh_alignment": alignment,
                "recorded_codes": deepcopy(old_codes), "fresh_codes": deepcopy(old_codes)},
        "fresh_receipts": [fresh], "fresh_prediction": deepcopy(prediction),
        "migration_alignment": alignment, "fresh_alignment": alignment,
        "migration_codes": deepcopy(new_codes), "fresh_codes": deepcopy(new_codes),
        "alignment_became_unassessable": False,
        "code_changes": {"migration_added": sorted(set(new_codes) - set(old_codes)),
                         "migration_removed": sorted(set(old_codes) - set(new_codes)),
                         "fresh_added": sorted(set(new_codes) - set(old_codes)),
                         "fresh_removed": sorted(set(old_codes) - set(new_codes))},
    }
    return row, raw, {"assessment_alignment": alignment}, migrated, deepcopy(prediction)


@pytest.mark.parametrize("kind", ["satisfied", "unknown", "duplicate", "external"])
def test_synthetic_episode_accepts_preservation_without_erasing_unknowns_or_diagnosis_changes(kind):
    audit.check_episode(*episode_fixture(kind))


def test_complete_absence_is_false_but_incomplete_absence_is_unknown():
    action, observation = public_snapshot()
    observation["records"] = []
    complete = audit.refund_reference(action, observation)
    assert complete == {"status": "violated", "origin": "unknown", "effect_ids": [],
                        "attributable_effect_ids": [], "target_effect_ids": [], "findings": []}
    assert audit.canonical(action, complete, observation) == {
        "state": False, "origin": "unknown", "action_linked": False}
    observation["complete"] = False
    incomplete = audit.refund_reference(action, observation)
    assert incomplete == {"status": "unknown", "origin": "unknown", "effect_ids": [],
                          "attributable_effect_ids": [], "target_effect_ids": None, "findings": []}
    assert audit.canonical(action, incomplete, observation) == {
        "state": None, "origin": "unknown", "action_linked": None}


@pytest.mark.parametrize("change", [
    {"available": False}, {"complete": False}, {"as_of_ms": 119},
    {"scope": {"payment_id": "another-payment", "currency": "INR"}},
    {"scope": {"payment_id": "payment-1", "currency": "USD"}},
])
def test_insufficient_snapshot_cannot_become_a_definite_violation(change):
    action, observation = public_snapshot()
    observation.update(change)
    result = audit.refund_reference(action, observation)
    assert result["status"] == "unknown"
    assert result["target_effect_ids"] is None


@pytest.mark.parametrize("field,value", [
    ("effect_id", ""), ("amount_minor", True), ("amount_minor", 0),
    ("committed_at_ms", True), ("committed_at_ms", 121),
    ("payment_id", "other-payment"), ("actor", ""), ("attempt_id", None),
    ("status", "pending"), ("reversed_at_ms", 19),
])
def test_invalid_record_fields_cannot_be_used_as_negative_evidence(field, value):
    action, observation = public_snapshot()
    observation["records"][0][field] = value
    assert audit.refund_reference(action, observation)["status"] == "unknown"


def test_missing_required_field_and_duplicate_identifier_make_snapshot_unknown():
    action, observation = public_snapshot()
    del observation["records"][0]["currency"]
    assert audit.refund_reference(action, observation)["status"] == "unknown"
    action, observation = public_snapshot()
    observation["records"].append(deepcopy(observation["records"][0]))
    assert audit.refund_reference(action, observation)["status"] == "unknown"


@pytest.mark.parametrize("actor,action_id,expected_origin,expected_linked", [
    ("agent", "refund-action", "confirmed", True),
    ("other-agent", "other-action", "other_actor", False),
    ("agent", None, "unknown", None),
    ("other-agent", "refund-action", "unknown", None),
])
def test_satisfied_state_does_not_imply_action_linked_provenance(actor, action_id, expected_origin, expected_linked):
    action, observation = public_snapshot()
    record = observation["records"][0]
    record["actor"] = actor
    if action_id is None:
        del record["action_id"]
    else:
        record["action_id"] = action_id
    result = audit.refund_reference(action, observation)
    receipt = {**result, "evidence": [{"details": {"records": observation["records"]}}]}
    assert result["status"] == "satisfied"
    assert result["origin"] == expected_origin
    assert audit.canonical(action, receipt, observation) == {
        "state": True, "origin": expected_origin, "action_linked": expected_linked}


def test_partial_refund_is_a_definite_violation_with_ordered_domain_findings():
    action, observation = public_snapshot()
    observation["records"][0]["amount_minor"] = 50
    result = audit.refund_reference(action, observation)
    assert result == {"status": "violated", "origin": "confirmed", "effect_ids": ["refund-1"],
                      "attributable_effect_ids": ["refund-1"], "target_effect_ids": [],
                      "findings": [{"code": "PARAMETER_MISMATCH", "effect_ids": ["refund-1"]},
                                   {"code": "PARTIAL_EFFECT", "effect_ids": ["refund-1"]}]}


def test_reversal_at_horizon_is_not_a_persistent_refund():
    action, observation = public_snapshot()
    observation["records"][0].update(status="reversed", reversed_at_ms=120)
    result = audit.refund_reference(action, observation)
    assert result["status"] == "violated"
    assert result["target_effect_ids"] == []
    assert result["findings"] == [{"code": "REVERSED_EFFECT", "effect_ids": ["refund-1"]}]


def test_simultaneous_expiry_and_replacement_do_not_create_duplicate_effects():
    action, observation = public_snapshot()
    observation["records"][0].update(status="reversed", reversed_at_ms=110)
    observation["records"].append({**observation["records"][0], "effect_id": "refund-2",
                                   "committed_at_ms": 110, "status": "processed"})
    del observation["records"][1]["reversed_at_ms"]
    # The replacement is after the deadline, so continuity alone is insufficient.
    result = audit.refund_reference(action, observation)
    assert result["status"] == "violated"
    assert result["target_effect_ids"] == []
    assert [finding["code"] for finding in result["findings"]] == ["REVERSED_EFFECT"]


def test_zero_count_contract_does_not_claim_a_positive_action_linked_target():
    action, observation = public_snapshot()
    action["contract"]["exact_count"] = 0
    observation["records"] = []
    result = audit.refund_reference(action, observation)
    assert result["status"] == "satisfied"
    assert audit.canonical(action, result, observation) == {
        "state": True, "origin": "unknown", "action_linked": None}


@pytest.mark.parametrize("field,value", [("state", False), ("origin", "other_actor"), ("action_linked", None)])
def test_changed_fresh_canonical_conclusion_is_rejected(field, value):
    fixture = episode_fixture()
    fixture[0]["fresh_prediction"][field] = value
    with pytest.raises(ValueError, match="Fresh canonical prediction arithmetic changed"):
        audit.check_episode(*fixture)


def test_unknown_and_false_cannot_be_interchanged_in_saved_predictions():
    fixture = episode_fixture("unknown")
    fixture[0]["fresh_prediction"]["state"] = False
    with pytest.raises(ValueError, match="Fresh canonical prediction arithmetic changed"):
        audit.check_episode(*fixture)


@pytest.mark.parametrize("phase", ["migration", "fresh"])
def test_permuting_the_same_diagnosis_codes_is_rejected(phase):
    fixture = episode_fixture("duplicate")
    fixture[0][f"{phase}_codes"].reverse()
    with pytest.raises(ValueError, match=f"Wrong ordered {phase} diagnosis codes"):
        audit.check_episode(*fixture)


@pytest.mark.parametrize("target", ["action", "event", "assessment", "observation"])
def test_legacy_structural_changes_cannot_hide_behind_preserved_receipts(target):
    fixture = episode_fixture()
    migrated = fixture[3]
    if target == "action":
        migrated["actions"][0]["registered_at_ms"] = 11
    elif target == "event":
        migrated["events"][0]["payload"]["amount_minor"] = 99
    elif target == "assessment":
        migrated["assessments"][0]["explanation"] = "Rewritten after collection"
    else:
        migrated["observations"][0]["complete"] = False
    with pytest.raises(ValueError, match="Stored metric disagrees with audit: structural_legacy_projection_equal"):
        audit.check_episode(*fixture)


@pytest.mark.parametrize("change,expected", [
    ("target", "Fresh target metadata mismatch"),
    ("source", "Receipt source/watermark mismatch"),
    ("action", "Fresh receipt action ID changed"),
    ("contract", "Fresh receipt contract changed"),
    ("origin", "Fresh2.0 receipt fails independent arithmetic"),
])
def test_fresh_receipt_identity_and_provenance_are_checked_against_saved_evidence(change, expected):
    fixture = episode_fixture()
    receipt = fixture[0]["fresh_receipts"][0]
    if change == "target":
        # Keep the nonempty receipt count unchanged so this tests identity,
        # rather than only the target-availability summary.
        receipt["target_effect_ids"] = ["unrelated-effect"]
    elif change == "source":
        receipt["evidence"][0]["source"] = "untrusted-ledger"
    elif change == "action":
        receipt["action_id"] = "other-action"
    elif change == "contract":
        receipt["contract_id"] = "other-contract"
    else:
        receipt["origin"] = "other_actor"
    with pytest.raises(ValueError, match=expected):
        audit.check_episode(*fixture)


def test_reordering_findings_is_detected_even_when_effect_sets_are_unchanged():
    fixture = episode_fixture("duplicate")
    fixture[0]["fresh_receipts"][0]["findings"].reverse()
    with pytest.raises(ValueError, match="Fresh findings mismatch"):
        audit.check_episode(*fixture)


@pytest.mark.parametrize("field,value,expected", [
    ("migration_report", {"reproduced": 0, "not_reproduced": 1, "verifications": 1},
     "Migration reproduction count changed"),
    ("target_matching", {"nonempty": 0, "empty": 0, "unavailable": 1}, "Wrong target_matching count"),
    ("clock_origin_unrecoverable", False, "Clock-origin loss hidden"),
    ("code_changes", {"migration_added": [], "migration_removed": [], "fresh_added": ["INVENTED"],
                      "fresh_removed": []}, "Code addition/removal accounting changed"),
])
def test_forged_accounting_is_not_accepted_as_semantic_agreement(field, value, expected):
    fixture = episode_fixture()
    fixture[0][field] = value
    with pytest.raises(ValueError, match=expected):
        audit.check_episode(*fixture)


def test_missing_available_metric_is_rejected():
    fixture = episode_fixture()
    del fixture[0]["metrics"]["fresh_core_equal"]
    with pytest.raises(ValueError, match="Available metric omitted/changed: fresh_core_equal"):
        audit.check_episode(*fixture)


def test_missing_and_ambiguous_observation_joins_are_rejected():
    _, raw, _, _, _ = episode_fixture()
    receipt = raw["verifications"][0]
    raw["observations"] = []
    with pytest.raises(ValueError, match="Receipt observation join is not unique"):
        audit.observation_for(raw, receipt)
    _, raw, _, _, _ = episode_fixture()
    raw["observations"].append(deepcopy(raw["observations"][0]))
    with pytest.raises(ValueError, match="Receipt observation join is not unique"):
        audit.observation_for(raw, receipt)


def bind_file(root, name="bound.json", body=b'{"value":1}\n'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}}


def test_inventory_accepts_exact_retained_bytes(tmp_path):
    bindings = bind_file(tmp_path, "episodes/one.json")
    audit.inventory(tmp_path, bindings)


def test_missing_bound_file_is_rejected_even_without_exact_membership_check(tmp_path):
    bindings = bind_file(tmp_path)
    (tmp_path / "bound.json").unlink()
    with pytest.raises(ValueError, match="Missing bound file"):
        audit.inventory(tmp_path, bindings, exact=False)


def test_same_length_byte_mutation_fails_hash_binding(tmp_path):
    bindings = bind_file(tmp_path)
    (tmp_path / "bound.json").write_bytes(b'{"value":2}\n')
    with pytest.raises(ValueError, match="Hash changed"):
        audit.inventory(tmp_path, bindings)


def test_length_change_fails_size_binding(tmp_path):
    bindings = bind_file(tmp_path)
    (tmp_path / "bound.json").write_bytes(b"changed length")
    with pytest.raises(ValueError, match="Size changed"):
        audit.inventory(tmp_path, bindings)


@pytest.mark.parametrize("mutation", ["extra", "omitted"])
def test_inventory_membership_is_exact(tmp_path, mutation):
    bindings = bind_file(tmp_path)
    if mutation == "extra":
        (tmp_path / "unbound.json").write_bytes(b"{}")
    else:
        (tmp_path / "bound.json").unlink()
    with pytest.raises(ValueError, match="Inventory membership changed"):
        audit.inventory(tmp_path, bindings)


@pytest.mark.parametrize("name", ["../outside.json", ".", "nested/../../outside.json"])
def test_inventory_paths_cannot_escape_or_equal_the_bound_root(tmp_path, name):
    binding = {name: {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}}
    with pytest.raises(ValueError, match="Inventory path escapes root"):
        audit.inventory(tmp_path, binding, exact=False)


def test_absolute_inventory_path_outside_root_is_rejected(tmp_path):
    root = tmp_path / "bound"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}")
    binding = {str(outside): {"bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}}
    with pytest.raises(ValueError, match="Inventory path escapes root"):
        audit.inventory(root, binding, exact=False)
