"""Execution diagnostics distinguish scheduled conditions from realized faults."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import summarize_matched_execution as summary
from run_matched_local_study import Journal, write_new
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig
from consequa_x.models import AssessmentStatus, to_dict
from consequa_x.policies import PolicyDecision, PolicyReply, ScriptedRefundPolicy


class FixturePolicy(ScriptedRefundPolicy):
    def __init__(self, selected=True):
        self.selected = selected

    def decide(self, request, *, seed):
        if request.stage == "select":
            return PolicyReply(PolicyDecision("refund" if self.selected else "stop", AssessmentStatus.UNKNOWN))
        last = request.responses[-1].status.value
        retry = last == "timeout" and request.context["retry_instruction"] and request.attempts_remaining
        status = {"success": AssessmentStatus.SUCCESS, "error": AssessmentStatus.FAILURE}.get(
            last, AssessmentStatus.UNKNOWN)
        return PolicyReply(PolicyDecision("retry" if retry else "stop", status))


def measured(config, selected=True):
    episode = run_policy_scenario(config, FixturePolicy(selected))
    return summary.episode_execution(episode.trace, {
        "records": episode.ground_truth, "scenario": to_dict(config), "action_selected": selected})


def test_no_action_does_not_exercise_its_scheduled_fault_or_provenance_omission():
    value = measured(ScenarioConfig(fault=Fault.FALSE_SUCCESS, include_provenance=False), False)
    assert value["intended_conditions"]["fault"] == "false_success"
    assert value["action_selected"] is False and value["attempt_count"] == value["dispatch_count"] == 0
    assert value["realized_fault_attempt_counts"] == {}
    assert value["refund_effect_count"] == value["manifestation_signals"]["public_records_with_omitted_origin_fields"] == 0
    assert value["response_status_history"] == [] and value["structured_assessment"] == "unknown"


def test_failed_dispatch_is_a_provider_attempt_but_not_a_dispatch():
    value = measured(ScenarioConfig(fault=Fault.FAIL_BEFORE_DISPATCH))
    assert value["action_selected"] is True and value["attempt_count"] == 1
    assert value["dispatch_count"] == 0 and value["response_status_history"] == ["error"]
    assert value["realized_fault_attempt_counts"] == {"fail_before_dispatch": 1}


@pytest.mark.parametrize("idempotent,effects,cache_hits", [(True, 1, 1), (False, 2, 0)])
def test_retry_effect_and_cache_exposure_are_measured_from_attempts(idempotent, effects, cache_hits):
    value = measured(ScenarioConfig(fault=Fault.TIMEOUT_AFTER_COMMIT, use_idempotency=idempotent,
                                    context=RefundContext(retry_instruction=True)))
    assert value["attempt_count"] == value["dispatch_count"] == 2
    assert value["retry_intent_count"] == value["retry_attempt_count"] == value["repeat_dispatch_count"] == 1
    assert value["refund_effect_count"] == effects
    assert value["response_status_history"] == ["timeout", "success"]
    assert value["realized_fault_attempt_counts"] == {"timeout_after_commit": 1}
    assert value["manifestation_signals"]["cache_hit_attempts"] == cache_hits
    assert value["manifestation_signals"]["timeout_with_new_commit_attempts"] == 1
    assert value["manifestation_signals"]["excess_payload_matching_effects"] == effects - 1


def test_false_acknowledgement_external_effects_provenance_and_lag_have_distinct_signals():
    false_ack = measured(ScenarioConfig(fault=Fault.FALSE_SUCCESS))
    assert false_ack["refund_effect_count"] == 0
    assert false_ack["manifestation_signals"]["success_without_new_commit_or_cache_attempts"] == 1
    external = measured(ScenarioConfig(external_actor=True), False)
    assert external["dispatch_count"] == 0 and external["external_effect_count"] == 1
    assert external["realized_fault_attempt_counts"] == {}
    hidden = measured(ScenarioConfig(include_provenance=False))
    assert hidden["manifestation_signals"]["public_records_with_omitted_origin_fields"] == 1
    stale = measured(ScenarioConfig(read_lag_ms=200, stability_ms=20))
    assert stale["refund_effect_count"] == 1 and stale["visible_ledger_record_count"] == 0
    assert stale["manifestation_signals"]["readback_horizon_gap_ms"] == 120
    assert stale["manifestation_signals"]["public_records_with_omitted_origin_fields"] == 0


def test_aggregate_does_not_invent_execution_values_for_failed_partial_or_unstarted():
    value = measured(ScenarioConfig())
    rows = [{"status": "completed", "execution": value, "attempted_model_calls": 2},
            {"status": "failed", "attempted_model_calls": 2},
            {"status": "interrupted_partial", "attempted_model_calls": 1},
            {"status": "unstarted", "attempted_model_calls": 0}]
    for row in rows:
        row["scheduled_conditions"] = value["intended_conditions"]
    result = summary.aggregate(rows)
    assert result["planned_episodes"] == 4 and result["completed_episodes"] == 1
    assert result["attempted_model_calls"] == 5 and result["attempt_count"] == 1
    assert result["rates"]["dispatched_per_completed"]["value"] == 1
    assert result["rates"]["dispatched_per_planned"]["value"] == .25
    missing = summary.aggregate(rows[1:])
    assert missing["rates"]["dispatched_per_completed"]["value"] is None
    assert missing["rates"]["dispatched_per_planned"]["value"] == 0


@pytest.fixture
def closed_study(tmp_path, monkeypatch):
    """Independent closed fixture; no generation provider or live study access."""
    study = tmp_path / "study"
    study.mkdir()
    config = ScenarioConfig(name="case", fault=Fault.TIMEOUT_AFTER_COMMIT,
                            context=RefundContext(retry_instruction=True))
    episode = run_policy_scenario(config, FixturePolicy())
    slots = [{"slot_id": f"slot-{number}", "model": "fixture:1b", "prompt_version": "fixture-profile",
              "case_id": "case", "family_id": "family", "repetition": number} for number in range(3)]
    manifest = {"fixture": True}
    write_new(study / "study-plan.source.json", manifest)
    protocol = {"schedule": slots, "planned_episodes": 3, "source_revision": "fixture-source",
                "manifest_sha256": sha256((study / "study-plan.source.json").read_bytes()).hexdigest(),
                "selected_cases": [{"case_id": "case", "scenario": to_dict(config)}],
                "source_inventory": {}}
    write_new(study / "protocol.json", protocol)
    protocol_sha = sha256((study / "protocol.json").read_bytes()).hexdigest()
    write_new(study / "protocol.sha256.json", {"sha256": protocol_sha})
    monkeypatch.setattr(summary, "validate_freeze", lambda path: protocol)
    journal = Journal(study / "request-journal.jsonl")
    journal.append("run_started")
    for selected, status in zip(slots[:2], ("completed", "failed")):
        folder = study / "episodes" / selected["slot_id"]
        write_new(folder / "started.json", {"slot": selected, "protocol_sha256": protocol_sha})
        journal.append("episode_started", slot_id=selected["slot_id"])
        calls = 3 if status == "completed" else 1
        for number in range(calls):
            call_id = f"{selected['slot_id']}-call-{number}"
            path = study / "calls" / f"{call_id}.request.json"
            write_new(path, {"fixture": True})
            journal.append("chat_started", slot_id=selected["slot_id"], call_id=call_id,
                           request_file=path.relative_to(study).as_posix(),
                           request_sha256=sha256(path.read_bytes()).hexdigest())
            response_path = study / "calls" / f"{call_id}.response.raw"
            write_new(response_path, {"fixture": True, "done": True})
            journal.append("chat_received", slot_id=selected["slot_id"], call_id=call_id,
                           status=200, response_file=response_path.relative_to(study).as_posix(),
                           response_sha256=sha256(response_path.read_bytes()).hexdigest())
        receipt = {"slot": selected, "status": status, "policy_calls": calls}
        if status == "completed":
            for name, value in (("trace.json", episode.trace.to_dict()),
                                ("explanation.json", episode.explanation.to_dict()),
                                ("evaluator-truth.json", {"records": to_dict(episode.ground_truth),
                                    "scenario": to_dict(config), "action_selected": True})):
                write_new(folder / name, value)
            receipt["artifact_sha256"] = {name: sha256((folder / name).read_bytes()).hexdigest()
                for name in ("trace.json", "explanation.json", "evaluator-truth.json")}
        write_new(folder / "receipt.json", receipt)
        journal.append("episode_finished", slot_id=selected["slot_id"], status=status,
                       receipt_sha256=sha256((folder / "receipt.json").read_bytes()).hexdigest())
    journal.append("run_stopped")
    journal_sha = sha256((study / "request-journal.jsonl").read_bytes()).hexdigest()
    analysis_path = tmp_path / "analysis.json"
    write_new(analysis_path, {"protocol_sha256": protocol_sha, "journal_sha256": journal_sha,
        "episode_status": {"completed": 1, "failed": 1, "interrupted_partial": 0, "unstarted": 1}})
    disposition_path = tmp_path / "disposition.json"
    write_new(disposition_path, {"schema_version": "consequa-matched-study-disposition-v1",
        "final": True, "no_active_runner": True, "collection_state": "stopped",
        "stopped_reason": "Synthetic fixture declares the last slot unstarted.",
        "protocol_sha256": protocol_sha, "journal_sha256": journal_sha,
        "analysis_sha256": sha256(analysis_path.read_bytes()).hexdigest()})
    return study, analysis_path, disposition_path


def test_closed_fixture_has_all_strata_and_binds_immutable_input_hashes(closed_study):
    result, inventory = summary.summarize(*closed_study)
    assert result["summary"]["action_selected_episodes"] == result["summary"]["dispatched_episodes"] == 1
    assert result["summary"]["attempted_model_calls"] == 4
    assert result["summary"]["rates"]["action_selected_per_planned"]["denominator"] == 3
    assert result["summary"]["realized_fault_attempt_counts"] == {"timeout_after_commit": 1}
    repetitions = result["strata"]["repetition"]
    assert repetitions['{"repetition": 2}']["completed_episodes"] == 0
    assert repetitions['{"repetition": 2}']["planned_episodes"] == 1
    assert result["postprocessing_disclosure"].startswith("Post-freeze descriptive addition")
    for path, binding in inventory["files"].items():
        assert sha256(Path(path).read_bytes()).hexdigest() == binding["sha256"]


def test_finalization_refuses_runner_lock_nonterminal_journal_and_wrong_bindings(closed_study):
    study, analysis, disposition = closed_study
    (study / "runner.lock").write_text("{}")
    with pytest.raises(ValueError, match="live finalization"):
        summary.summarize(study, analysis, disposition)
    (study / "runner.lock").unlink()
    data = json.loads(disposition.read_text())
    disposition.write_text(json.dumps({**data, "analysis_sha256": "wrong"}))
    with pytest.raises(ValueError, match="disposition"):
        summary.summarize(study, analysis, disposition)
    disposition.write_text(json.dumps(data))
    Journal(study / "request-journal.jsonl").append("chat_started", call_id="late", slot_id="slot-2")
    with pytest.raises(ValueError, match="terminal"):
        summary.summarize(study, analysis, disposition)


def test_completed_disposition_cannot_hide_an_unstarted_slot(closed_study):
    study, analysis, disposition = closed_study
    data = json.loads(disposition.read_text())
    disposition.write_text(json.dumps({**data, "collection_state": "completed"}))
    with pytest.raises(ValueError, match="unstarted"):
        summary.summarize(study, analysis, disposition)


def test_dispatch_ledger_inconsistency_is_rejected():
    config = ScenarioConfig()
    episode = run_policy_scenario(config, FixturePolicy())
    trace = replace(episode.trace, events=tuple(
        replace(event, data={**event.data, "attempt_id": "unbound-attempt"})
        if event.type.value == "action_dispatch" else event for event in episode.trace.events))
    with pytest.raises(ValueError, match="dispatch"):
        summary.episode_execution(trace, {"records": episode.ground_truth,
            "scenario": to_dict(config), "action_selected": True})
