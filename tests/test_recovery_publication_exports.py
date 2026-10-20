"""Fixture-only publication guards and denominator regressions.

These hand-specified summaries use the frozen runner/auditor JSON schemas.
No simulator, case corpus, study output, database, or plotting backend is used.
"""

from copy import deepcopy
from fractions import Fraction
import hashlib
import json

import pytest

from scripts import plot_recovery_controller_study as exports


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def abstaining_group(planned, **identity):
    """All completed slots abstain; one charged dispatch/read per slot."""
    totals = {"state_abstention": planned, "action_linked_abstention": planned,
              "dispatches": planned, "reads": planned, "decision_time_ms": 20 * planned}
    return {**identity, "planned": planned, "completed": planned, "failed": 0,
            "metrics": {name: {"sum": totals.get(name, 0), "observed": planned,
                               "unavailable": 0, "mean": totals.get(name, 0) / planned}
                        for name in exports.ENDPOINTS}}


@pytest.fixture
def bound_inputs(tmp_path):
    """A complete synthetic postprocessor boundary, not a claimed study audit."""
    study, audit = tmp_path / "synthetic-study", tmp_path / "synthetic-audit"
    study.mkdir()
    audit.mkdir()
    families = [f"fixture-family-{i:02d}" for i in range(12)]
    cases = [(f"fixture-case-{i:02d}-{j}", family)
             for i, family in enumerate(families) for j in range(2)]
    schedule = [{"trial_id": f"fixture-trial-{i}-{method}", "case_id": case,
                 "family_id": family, "domain": "fixture-domain", "seed": 0,
                 "method": method}
                for i, (case, family) in enumerate(cases) for method in exports.METHODS]
    source_sha = "a" * 64
    protocol = {"schema": exports.STUDY_SCHEMA, "methods": list(exports.METHODS),
                "case_count": 24, "family_count": 12, "seed_count": 1, "schedule": schedule,
                "source": {"files": {"scripts/audit_recovery_controller_study.py":
                                     {"sha256": source_sha}}}}
    write_json(study / "protocol.json", protocol)
    protocol_sha = digest(study / "protocol.json")
    contrasts = []
    for left, right in exports.CONTRASTS:
        # Both arms have the same fixed fixture counts: every paired difference is zero.
        contrasts.append({"left": left, "right": right, "planned_pairs": 24,
                          "metrics": {name: {
                              "pairs": 24, "unavailable_pairs": 0, "mean_difference": 0.0,
                              "equal_family_mean_difference": 0.0,
                              "by_family": [{"family_id": family, "pairs": 2,
                                             "sum_difference": 0, "mean_difference": 0.0}
                                            for family in families]}
                                      for name in exports.ENDPOINTS}})
    summary = {"schema": exports.STUDY_SCHEMA, "protocol_sha256": protocol_sha,
               "collection_seconds": 1.0, "planned_trials": 120,
               "completed_trials": 120, "failed_trials": 0,
               "methods": [abstaining_group(24, method=method) for method in exports.METHODS],
               "families": [abstaining_group(2, family_id=family, method=method)
                            for family in families for method in exports.METHODS],
               "cases": [abstaining_group(1, case_id=case, method=method)
                         for case, _ in cases for method in exports.METHODS],
               "paired_contrasts": contrasts, "inference_scope": "synthetic finite fixture"}
    write_json(study / "summary.json", summary)
    files = {name: digest(study / name) for name in ("protocol.json", "summary.json")}
    write_json(study / "manifest.json", {"schema": exports.STUDY_SCHEMA,
                                         "complete": True, "files": files})
    manifest_sha = digest(study / "manifest.json")
    counts = {"planned_trials": 120, "completed_trials": 120, "failed_trials": 0}
    receipt = {"schema": exports.STUDY_SCHEMA, "complete": True,
               "protocol_sha256": protocol_sha, "manifest_sha256": manifest_sha, **counts}
    audit_receipt = {"schema": exports.AUDIT_SCHEMA, "passed": True,
                     "protocol_sha256": protocol_sha, "manifest_sha256": manifest_sha,
                     "audit_script_sha256": source_sha, "artifacts_hashed": len(files), **counts}
    write_json(study / "completion-receipt.json", receipt)
    write_json(audit / "audit-receipt.json", audit_receipt)
    recomputed = {key: value for key, value in summary.items()
                  if key not in ("protocol_sha256", "collection_seconds")}
    write_json(audit / "recomputed-summary.json", recomputed)
    return study, audit


def test_complete_bound_fixture_validates_without_rendering(bound_inputs):
    study, audit = bound_inputs
    bundle = exports.verify_inputs(study, audit)
    assert bundle["summary"]["planned_trials"] == 120
    assert len(bundle["validated"]["families"]) == 12
    assert len(bundle["validated"]["contrasts"]) == 4
    assert sorted(path.name for path in audit.iterdir()) == [
        "audit-receipt.json", "recomputed-summary.json"]


@pytest.mark.parametrize("audited_mean,accepted", [(1.0 + 2 ** -52, True), (1.1, False)])
def test_bound_audit_comparison_accepts_rounding_but_rejects_changed_mean(
        bound_inputs, audited_mean, accepted):
    study, audit = bound_inputs
    path = audit / "recomputed-summary.json"
    recomputed = json.loads(path.read_text(encoding="utf-8"))
    recomputed["methods"][0]["metrics"]["reads"]["mean"] = audited_mean
    write_json(path, recomputed)
    if accepted:
        assert exports.verify_inputs(study, audit)["summary"]["planned_trials"] == 120
    else:
        with pytest.raises(ValueError, match="summary numeric mismatch"):
            exports.verify_inputs(study, audit)


def test_recursive_means_allow_last_bit_difference_without_coercing_counts():
    exports.same_summary({"count": 3, "rows": [{"mean": 0.1 + 0.2, "flag": True}]},
                         {"count": 3, "rows": [{"mean": 0.3, "flag": True}]})


@pytest.mark.parametrize("left,right", [
    ({"n": 3}, {"n": 4}),
    ({"n": 3}, {"n": 3.0}),
    ({"flag": True}, {"flag": 1}),
    ({"a": 1}, {"b": 1}),
    ({"rows": [1]}, {"rows": [1, 2]}),
    ({"rows": [1]}, {"rows": (1,)}),
    ({"mean": 0.1}, {"mean": 0.2}),
    ({"mean": float("nan")}, {"mean": float("nan")}),
    ({"mean": float("inf")}, {"mean": float("inf")}),
])
def test_recursive_comparison_rejects_changed_structure_types_or_nonfinite_values(left, right):
    with pytest.raises(ValueError, match="summary"):
        exports.same_summary(left, right)


@pytest.mark.parametrize("location,key,value,message", [
    ("receipt", "complete", False, "incomplete collection"),
    ("receipt", "manifest_sha256", "0" * 64, "manifest hash mismatch"),
    ("receipt", "protocol_sha256", "0" * 64, "protocol hash mismatch"),
    ("audit", "passed", False, "audit has not passed"),
    ("audit", "protocol_sha256", "0" * 64, "not bound"),
    ("audit", "manifest_sha256", "0" * 64, "not bound"),
    ("audit", "artifacts_hashed", 3, "not bound"),
    ("audit", "audit_script_sha256", "0" * 64, "audit source differs"),
    ("audit", "completed_trials", 119, "receipts disagree"),
])
def test_receipt_and_audit_mismatches_fail_closed(bound_inputs, location, key, value, message):
    study, audit = bound_inputs
    path = (study / "completion-receipt.json" if location == "receipt"
            else audit / "audit-receipt.json")
    value_dict = json.loads(path.read_text(encoding="utf-8"))
    value_dict[key] = value
    write_json(path, value_dict)
    with pytest.raises(ValueError, match=message):
        exports.verify_inputs(study, audit)


def test_changed_retained_bytes_fail_before_summary_can_be_used(bound_inputs):
    study, audit = bound_inputs
    with (study / "summary.json").open("a", encoding="utf-8") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="retained artifact hash mismatch: summary.json"):
        exports.verify_inputs(study, audit)


def test_unmanifested_retained_file_is_rejected(bound_inputs):
    study, audit = bound_inputs
    (study / "unexpected.txt").write_text("synthetic unexpected artifact", encoding="utf-8")
    with pytest.raises(ValueError, match="unmanifested"):
        exports.verify_inputs(study, audit)


def mixed_group():
    """Four planned slots: correct, wrong, abstained, and operationally failed."""
    group = abstaining_group(3, method="fixture-method")
    group.update(planned=4, completed=3, failed=1)
    totals = {"operational_safe_recovery": 2, "safe_recovery": 2,
              "original_completion": 1, "recovery_completion": 2,
              "state_definite": 2, "state_wrong_definite": 1, "state_false_success": 1,
              "state_abstention": 1, "action_linked_definite": 1,
              "action_linked_abstention": 2, "dispatches": 5, "reads": 4,
              "decision_time_ms": 60}
    for name, metric in group["metrics"].items():
        observed = 4 if name == exports.PRIMARY else 3
        total = totals.get(name, 0)
        metric.update(sum=total, observed=observed, unavailable=4 - observed,
                      mean=total / observed)
    return group


def test_failures_remain_primary_false_but_semantic_and_resource_unavailable():
    group = mixed_group()
    exports.validate_group(group, 4)
    primary = group["metrics"][exports.PRIMARY]
    semantic = group["metrics"]["safe_recovery"]
    resources = group["metrics"]["reads"]
    assert primary == {"sum": 2, "observed": 4, "unavailable": 0, "mean": 0.5}
    assert semantic == {"sum": 2, "observed": 3, "unavailable": 1, "mean": 2 / 3}
    row = exports.metric_row("methods", group, "reads", resources)
    assert (row["observed_denominator"], row["unavailable"], row["mean_exact"]) == (3, 1, "4/3")


@pytest.mark.parametrize("endpoint,observed,unavailable", [
    (exports.PRIMARY, 3, 1), ("safe_recovery", 4, 0), ("reads", 4, 0),
])
def test_operational_and_semantic_denominators_cannot_be_interchanged(
        endpoint, observed, unavailable):
    group = mixed_group()
    metric = group["metrics"][endpoint]
    metric.update(observed=observed, unavailable=unavailable, mean=metric["sum"] / observed)
    with pytest.raises(ValueError, match="unexpected observed denominator"):
        exports.validate_group(group, 4)


def test_claim_yield_keeps_failure_and_abstention_separate_from_conditional_error():
    group = mixed_group()
    bundle = {"validated": {"groups": {"methods": {
        (method,): {**deepcopy(group), "method": method} for method in exports.METHODS}}}}
    rows = [row for row in exports.claim_rows(bundle) if row["method"] == "reference"]
    assert {row["category"]: row["numerator"] for row in rows} == {
        "correct_definite": 1, "incorrect_definite": 1, "abstention": 1, "unavailable": 1}
    assert all(row["planned_denominator"] == 4 and row["yield_exact"] == "1/4"
               for row in rows)
    metrics = group["metrics"]
    conditional_error = Fraction(metrics["state_wrong_definite"]["sum"],
                                 metrics["state_definite"]["sum"])
    assert conditional_error == Fraction(1, 2)
    assert conditional_error != Fraction(1, 4)  # Wrong/planned is an error yield, not error/definite.
