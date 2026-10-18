"""Finalize genuine frozen offline fixtures; no provider or model calls."""

from argparse import Namespace
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import finalize_matched_local_study as finalizer
import run_matched_local_study as runner
from consequa_x.adapters.ollama import PROMPT_PROFILES
from consequa_x.models import AssessmentStatus
from consequa_x.policies import PolicyDecision, PolicyReply, ScriptedRefundPolicy


def inspection(models, settings):
    return {"server_version": {"version": "offline-fixture"}, "models": {
        model: {"tag": {"name": model, "digest": "fixture-digest"}, "inspection": {"local": True}}
        for model in models}}


class OfflineRecordingPolicy(ScriptedRefundPolicy):
    """Record deterministic fixture decisions directly, with no HTTP transport."""

    def __init__(self, model, *, directory, slot, journal, prompt_version, **settings):
        self.model, self.directory, self.slot = model, Path(directory), slot
        self.journal, self.profile, self.settings, self.calls = journal, prompt_version, settings, 0

    def list_models(self):
        return [{"name": self.model, "digest": "fixture-digest"}]

    def decide(self, request, *, seed):
        operation = "refund" if request.stage == "select" else "stop"
        assessment = AssessmentStatus.UNKNOWN if request.stage == "select" else AssessmentStatus.SUCCESS
        reply = PolicyReply(PolicyDecision(operation, assessment))
        call_id = f"{self.slot}-call-{self.calls:02d}"
        self.calls += 1
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": PROMPT_PROFILES[self.profile]},
            {"role": "user", "content": json.dumps(request.to_dict())}],
            "options": {"seed": seed, "temperature": self.settings["temperature"],
                        "num_predict": self.settings["num_predict"]}}
        request_path = self.directory / "calls" / f"{call_id}.request.json"
        runner.write_new(request_path, payload)
        self.journal.append("chat_started", slot_id=self.slot, call_id=call_id,
            request_file=request_path.relative_to(self.directory).as_posix(),
            request_sha256=sha256(request_path.read_bytes()).hexdigest())
        response_path = self.directory / "calls" / f"{call_id}.response.raw"
        runner.write_new(response_path, {"model": self.model, "done": True,
            "message": {"role": "assistant", "content": json.dumps(reply.decision.to_dict())}})
        self.journal.append("chat_received", slot_id=self.slot, call_id=call_id, status=200,
            response_file=response_path.relative_to(self.directory).as_posix(),
            response_sha256=sha256(response_path.read_bytes()).hexdigest(), elapsed_seconds=0,
            truncated=False)
        return reply


@pytest.fixture
def frozen_fixture(tmp_path, monkeypatch):
    manifest = json.loads((runner.ROOT / "docs/studies/matched-local-2026-10-18.json").read_text())
    manifest["study_id"] = "offline-finalizer-fixture"
    manifest["cases"] = [{**manifest["cases"][0], "case_id": "fixture.clean"}]
    manifest["templates"] = [template for template in manifest["templates"]
                             if template["template_id"] == manifest["cases"][0]["template_id"]]
    source = tmp_path / "fixture-manifest.json"
    runner.write_new(source, manifest)
    study = tmp_path / "study"
    monkeypatch.setattr(runner, "inspect_models", inspection)
    runner.freeze(Namespace(output=study, study=source, models=["fixture:1b"], samples=1,
        seed=50, order_seed=70, base_url="http://127.0.0.1:11435", temperature=.2,
        num_predict=384, timeout=180, max_wall_seconds=21600))
    return study


def run_fixture(study, limit=None):
    return runner.run(study, limit=limit, policy_factory=OfflineRecordingPolicy, inspector=inspection)


def test_finalizes_frozen_primary_analysis_and_disclosed_incomplete_execution(frozen_fixture, tmp_path):
    run_fixture(frozen_fixture, limit=1)
    before = finalizer.file_inventory(frozen_fixture)
    output = tmp_path / "analysis-output"
    receipt = finalizer.finalize(frozen_fixture, output)
    assert finalizer.file_inventory(frozen_fixture) == before
    assert receipt["episode_status"] == {
        "completed": 1, "failed": 0, "interrupted_partial": 0, "unstarted": 1}
    assert receipt["collection_state"] == "stopped"
    disposition = runner.read_json(output / "final-disposition.json")
    assert disposition["reason_source"] == "disclosed_incomplete_execution"
    assert disposition["analysis_sha256"] == sha256((output / "analysis.json").read_bytes()).hexdigest()
    execution = runner.read_json(output / "execution/execution-summary.json")
    assert execution["summary"]["action_selected_episodes"] == execution["summary"]["dispatched_episodes"] == 1
    assert execution["summary"]["attempted_model_calls"] == 2
    assert execution["summary"]["rates"]["dispatched_per_planned"]["value"] == .5
    inventory = runner.read_json(output / "analysis-artifacts-inventory.json")
    for path, value in inventory["files"].items():
        assert sha256((output / path).read_bytes()).hexdigest() == value["sha256"]
    assert receipt["analysis_artifacts_inventory_sha256"] == sha256(
        (output / "analysis-artifacts-inventory.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="fresh directory"):
        finalizer.finalize(frozen_fixture, output)


def test_all_attempted_slots_finalize_as_completed_with_full_accounting(frozen_fixture, tmp_path):
    run_fixture(frozen_fixture)
    receipt = finalizer.finalize(frozen_fixture, tmp_path / "all-completed")
    assert receipt["collection_state"] == "completed"
    assert receipt["episode_status"]["completed"] == 2 and receipt["episode_status"]["unstarted"] == 0
    assert receipt["stopped_reason"] == ""


def test_finalizer_refuses_live_lock_unterminated_journal_and_changed_bound_trace(frozen_fixture, tmp_path):
    run_fixture(frozen_fixture, limit=1)
    lock = frozen_fixture / "runner.lock"
    lock.write_text("{}")
    output = tmp_path / "refused-output"
    with pytest.raises(ValueError, match="live finalization"):
        finalizer.finalize(frozen_fixture, output)
    assert not output.exists()
    lock.unlink()
    trace = next((frozen_fixture / "episodes").glob("*/trace.json"))
    original = trace.read_bytes()
    trace.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="artifact changed"):
        finalizer.finalize(frozen_fixture, output)
    assert not output.exists()
    trace.write_bytes(original)
    runner.Journal(frozen_fixture / "request-journal.jsonl").append("episode_started", slot_id="late")
    with pytest.raises(ValueError, match="terminal"):
        finalizer.finalize(frozen_fixture, output)
    assert not output.exists()


def test_final_disposition_retains_wall_time_stop_reason(frozen_fixture, tmp_path):
    run_fixture(frozen_fixture, limit=1)
    journal = runner.Journal(frozen_fixture / "request-journal.jsonl")
    journal.append("wall_time_exhausted", next_slot_id="fixture-unstarted")
    journal.append("run_stopped", newly_started_episodes=1)
    output = tmp_path / "wall-time-output"
    receipt = finalizer.finalize(frozen_fixture, output)
    assert receipt["collection_state"] == "stopped" and "wall-time" in receipt["stopped_reason"]
    disposition = runner.read_json(output / "final-disposition.json")
    assert disposition["reason_source"] == "journal_event"
    assert any(event["event"] == "wall_time_exhausted" for event in disposition["stop_events"])


def test_fresh_output_cannot_be_nested_inside_study(frozen_fixture):
    with pytest.raises(ValueError, match="outside"):
        finalizer.finalize(frozen_fixture, frozen_fixture / "analysis-output")
