"""Hand-specified matched-pair checks; no cases, measured files, or worlds."""

from copy import deepcopy

import pytest

from scripts import analyze_recovery_comparisons as comparisons


ENDPOINTS = ("operational_safe_recovery", "safe_recovery", "reads")


def completed_trial(safe=True, reads=1):
    """Only the real trial-schema fields consumed by the pure comparison helpers."""
    return {
        "status": "completed",
        "report": {"reported_state": safe, "reported_action_linked": safe},
        "metrics": {"completed": True, "operational_safe_recovery": safe,
                    "safe_recovery": safe, "reads": reads},
        "truth": {"target_satisfied": safe, "records": []},
        "trajectory": [
            {"kind": "dispatch", "at_ms": 0,
             "decision": {"kind": "dispatch", "at_ms": 0, "reason": "fixture initial",
                          "action_id": "fixture-operation", "attempt_id": "fixture-attempt-1",
                          "idempotency_key": "fixture-operation"}},
            {"kind": "response", "at_ms": 1, "response": {"status": "timeout"}},
            {"kind": "read", "at_ms": 10, "decision": {"reason": "fixture query"}},
            {"kind": "readback", "at_ms": 10, "observation": {"available": True}},
            {"kind": "wait", "at_ms": 11, "decision": {"reason": "fixture wait"}},
            {"kind": "stop", "at_ms": 12, "decision": {"reason": "fixture stop"}},
        ],
    }


def failed_trial():
    # The frozen runner retains operational false but no invented semantic/resource metrics.
    return {"status": "failed",
            "metrics": {"completed": False, "operational_safe_recovery": False}}


def test_action_sequence_ignores_callbacks_and_diagnostic_wording():
    left = completed_trial()
    right = deepcopy(left)
    right["trajectory"][0]["decision"]["reason"] = "different implementation wording"
    right["trajectory"][1]["response"]["status"] = "success"
    right["trajectory"][2]["decision"]["reason"] = "other query rationale"
    right["trajectory"][3]["observation"]["available"] = False
    assert comparisons.action_sequence(left) == comparisons.action_sequence(right) == [
        {"kind": "dispatch", "at_ms": 0, "dispatch_identity": {
            "action_id": "fixture-operation", "attempt_id": "fixture-attempt-1",
            "idempotency_key": "fixture-operation"}},
        {"kind": "read", "at_ms": 10},
        {"kind": "wait", "at_ms": 11},
        {"kind": "stop", "at_ms": 12},
    ]


@pytest.mark.parametrize("key", ["action_id", "attempt_id", "idempotency_key", "actor"])
def test_dispatch_identity_differences_remain_visible(key):
    left = completed_trial()
    right = deepcopy(left)
    right["trajectory"][0]["decision"][key] = "different-fixture-identity"
    outcome = comparisons.compare_pair(left, right)
    assert outcome["comparable"] is True
    assert "action_sequence" in outcome["mismatches"]


def test_equal_complete_pair_ignores_package_specific_report_metadata():
    left = completed_trial()
    right = deepcopy(left)
    right["report"]["package_diagnosis"] = ["fixture-only-metadata"]
    outcome = comparisons.compare_pair(left, right)
    assert outcome == {"comparable": True, "mismatches": [], "claims": {
        "final_state_claim": {"left": True, "right": True},
        "final_action_linked_claim": {"left": True, "right": True}}}


@pytest.mark.parametrize("target,path,value", [
    ("final_state_claim", ("report", "reported_state"), False),
    ("final_action_linked_claim", ("report", "reported_action_linked"), None),
    ("endpoint_vector", ("metrics", "reads"), 2),
    ("action_sequence", ("trajectory", 2, "at_ms"), 20),
    ("full_ledger_truth", ("truth", "target_satisfied"), False),
])
def test_each_declared_pair_target_is_checked_directly(target, path, value):
    left = completed_trial()
    right = deepcopy(left)
    nested = right
    for key in path[:-1]:
        nested = nested[key]
    nested[path[-1]] = value
    outcome = comparisons.compare_pair(left, right)
    assert outcome["comparable"] is True
    assert outcome["mismatches"] == [target]


def test_stop_and_abstain_are_distinct_actions():
    left = completed_trial()
    right = deepcopy(left)
    right["trajectory"][-1]["kind"] = "abstain"
    assert comparisons.compare_pair(left, right)["mismatches"] == ["action_sequence"]


def test_equal_aggregate_means_do_not_establish_per_pair_parity():
    left = [completed_trial(True), completed_trial(False)]
    right = [completed_trial(False), completed_trial(True)]
    assert comparisons.aggregate(left, ENDPOINTS) == comparisons.aggregate(right, ENDPOINTS)
    outcomes = [comparisons.compare_pair(a, b) for a, b in zip(left, right)]
    assert all(row["comparable"] for row in outcomes)
    assert all("endpoint_vector" in row["mismatches"] for row in outcomes)
    assert all("final_state_claim" in row["mismatches"] for row in outcomes)
    assert sum(bool(row["mismatches"]) for row in outcomes) == 2


@pytest.mark.parametrize("left_failed,right_failed", [(True, False), (False, True), (True, True)])
def test_failed_pairs_are_incomparable_without_accessing_missing_semantic_fields(
        left_failed, right_failed):
    left = failed_trial() if left_failed else completed_trial()
    right = failed_trial() if right_failed else completed_trial()
    assert comparisons.compare_pair(left, right) == {
        "comparable": False, "mismatches": [], "claims": {}}


def test_aggregate_retains_failures_only_as_operational_false():
    summary = comparisons.aggregate(
        [completed_trial(True, reads=2), completed_trial(False, reads=1), failed_trial()],
        ENDPOINTS,
    )
    assert (summary["planned"], summary["completed"], summary["failed"]) == (3, 2, 1)
    assert summary["metrics"] == {
        "operational_safe_recovery": {"sum": 1, "observed": 3, "unavailable": 0, "mean": 1 / 3},
        "safe_recovery": {"sum": 1, "observed": 2, "unavailable": 1, "mean": 0.5},
        "reads": {"sum": 3, "observed": 2, "unavailable": 1, "mean": 1.5},
    }


def test_all_failed_stratum_has_undefined_semantic_and_resource_means():
    summary = comparisons.aggregate([failed_trial(), failed_trial()], ENDPOINTS)
    assert (summary["planned"], summary["completed"], summary["failed"]) == (2, 0, 2)
    assert summary["metrics"]["operational_safe_recovery"] == {
        "sum": 0, "observed": 2, "unavailable": 0, "mean": 0.0}
    for endpoint in ("safe_recovery", "reads"):
        assert summary["metrics"][endpoint] == {
            "sum": 0, "observed": 0, "unavailable": 2, "mean": None}
