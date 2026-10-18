"""Research-runner safeguards and independently specified simulator controls."""

from argparse import Namespace
from dataclasses import replace
from hashlib import sha256
import json
import io
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_matched_local_study as analysis
import run_matched_local_study as runner
from consequa_x.adapters.ollama import PROMPT_PROFILES
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig
from consequa_x.benchmark.study import study_plan_from_json
from consequa_x.models import AssessmentStatus
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy


class FixturePolicy(ScriptedRefundPolicy):
    def decide(self, request, *, seed):
        if request.stage == "select":
            return PolicyReply(PolicyDecision("refund", AssessmentStatus.UNKNOWN))
        operation = "retry" if request.context["retry_instruction"] and request.attempts_remaining else "stop"
        status = AssessmentStatus.SUCCESS if request.responses[-1].status.value == "success" else AssessmentStatus.FAILURE
        return PolicyReply(PolicyDecision(operation, status))


@pytest.mark.parametrize("fault,state", [
    (Fault.CLEAN, True), (Fault.FAIL_BEFORE_DISPATCH, False),
    (Fault.TIMEOUT_BEFORE_COMMIT, False), (Fault.TIMEOUT_AFTER_COMMIT, True),
    (Fault.FALSE_SUCCESS, False), (Fault.DELAYED_VISIBILITY, True),
    (Fault.PARTIAL_EFFECT, False), (Fault.DUPLICATE_EFFECT, False),
    (Fault.WRONG_PARAMETER, False), (Fault.WRONG_TARGET, False),
])
def test_independent_ledger_gold_and_same_info_reference(fault, state):
    episode = run_policy_scenario(ScenarioConfig(fault=fault), FixturePolicy(), seed=27)
    gold = analysis.ledger_gold(episode.trace.action, episode.ground_truth)
    assert gold["state"] is state
    assert gold["action_linked"] is state
    predictions = analysis.matched_predictions(episode.trace)
    assert predictions["independent_public_reference"] == predictions["consequa_state_origin"]
    if fault is Fault.DELAYED_VISIBILITY:
        assert predictions["consequa_state_origin"]["state"] is None
    else:
        assert predictions["consequa_state_origin"]["state"] is state


def test_external_actor_is_not_agent_origin_and_state_ablation_abstains():
    episode = run_policy_scenario(ScenarioConfig(fault=Fault.TIMEOUT_BEFORE_COMMIT,
                                  external_actor=True), FixturePolicy())
    gold = analysis.ledger_gold(episode.trace.action, episode.ground_truth)
    assert gold["state"] is True and gold["action_linked"] is False
    predictions = analysis.matched_predictions(episode.trace)
    assert predictions["consequa_state_origin"] == predictions["independent_public_reference"]
    assert predictions["consequa_state_origin"]["origin"] == "other_actor"
    assert predictions["readback_state_only"]["state"] is True
    assert predictions["readback_state_only"]["action_linked"] is None


def test_lost_acknowledgement_and_false_success_are_distinct_targets():
    lost = run_policy_scenario(ScenarioConfig(fault=Fault.TIMEOUT_AFTER_COMMIT), FixturePolicy())
    false = run_policy_scenario(ScenarioConfig(fault=Fault.FALSE_SUCCESS), FixturePolicy())
    assert analysis.matched_predictions(lost.trace)["response_only"]["state"] is None
    assert analysis.matched_predictions(false.trace)["response_only"]["state"] is True
    assert analysis.ledger_gold(false.trace.action, false.ground_truth)["state"] is False


def test_missing_provenance_never_becomes_known_origin():
    episode = run_policy_scenario(ScenarioConfig(fault=Fault.CLEAN, include_provenance=False), FixturePolicy())
    predictions = analysis.matched_predictions(episode.trace)
    assert predictions["consequa_state_origin"] == predictions["independent_public_reference"]
    assert predictions["consequa_state_origin"]["state"] is True
    assert predictions["consequa_state_origin"]["action_linked"] is None


@pytest.mark.parametrize("fault", [Fault.CLEAN, Fault.DUPLICATE_EFFECT])
def test_compensation_and_unsafe_retry_controls(fault):
    compensated = run_policy_scenario(ScenarioConfig(fault=fault, compensate=True), FixturePolicy())
    assert analysis.ledger_gold(compensated.trace.action, compensated.ground_truth)["state"] is (fault is Fault.DUPLICATE_EFFECT)
    assert analysis.matched_predictions(compensated.trace)["independent_public_reference"] == analysis.matched_predictions(compensated.trace)["consequa_state_origin"]
    duplicate = run_policy_scenario(ScenarioConfig(context=RefundContext(retry_instruction=True),
                                   use_idempotency=False), FixturePolicy())
    assert analysis.ledger_gold(duplicate.trace.action, duplicate.ground_truth)["state"] is False


def test_schedule_has_exact_pairs_and_disjoint_phase_reservation():
    plan = study_plan_from_json((runner.ROOT / "docs/studies/refund-family-candidates-v1.json").read_text())
    cases = plan.select("validation")
    models = ("family-a:3b", "family-b:1b", "family-c:4b")
    schedule = runner.make_schedule(cases, models, tuple(PROMPT_PROFILES), 14, 18000000, 18000099)
    assert len(schedule) == 504
    pairs = {}
    for slot in schedule:
        key = slot["case_id"], slot["repetition"]
        pairs.setdefault(key, []).append(slot)
    assert len(pairs) == 84
    assert all(len(value) == 6 for value in pairs.values())
    assert all(len({row["trial_seed"] for row in value}) == 1 for value in pairs.values())
    phase = [number for value in pairs.values() for number in value[0]["reserved_phase_seeds"]]
    assert len(phase) == len(set(phase))
    assert schedule == runner.make_schedule(cases, models, tuple(PROMPT_PROFILES), 14, 18000000, 18000099)


def inspection(models, settings):
    return {"server_version": {"version": "fixture"},
            "models": {model: {"tag": {"name": model, "digest": f"digest-{model}"},
                               "inspection": {"no_declared_remote_routing": True}}
                       for model in models}}


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "inspect_models", inspection)
    protocol_source = tmp_path / "protocol.md"
    protocol_source.write_bytes(runner.PROTOCOL_DOCUMENT.read_bytes())
    args = Namespace(output=str(tmp_path / "study"), study=str(runner.ROOT / "docs/studies/refund-family-candidates-v1.json"),
                     protocol=str(protocol_source),
                     models=["fixture:1b"], samples=1, seed=18000000, order_seed=18000099,
                     base_url="http://127.0.0.1:11434", temperature=0.2, num_predict=384,
                     timeout=180, max_wall_seconds=21600)
    runner.freeze(args)
    return Path(args.output)


class RecordingFixture(runner.RecordingPolicy):
    def validate_local_model(self, *, force=False):
        return {"no_declared_remote_routing": True}

    def list_models(self):
        return ({"name": self.model, "digest": f"digest-{self.model}"},)

    def _request(self, path, payload=None):
        if path != "/api/chat":
            raise AssertionError("Offline fixture must not contact a provider")
        call_id = f"{self.slot}-call-{self.calls:02d}"
        self.calls += 1
        request_path = self.directory / "calls" / f"{call_id}.request.json"
        runner.write_new(request_path, payload)
        self.journal.append("chat_started", slot_id=self.slot, call_id=call_id,
                            request_file=request_path.relative_to(self.directory).as_posix(),
                            request_sha256=sha256(request_path.read_bytes()).hexdigest())
        public = json.loads(payload["messages"][1]["content"])
        decision = {"operation": "refund" if public["stage"] == "select" else "stop",
                    "assessment": "unknown", "rationale": "Offline runner fixture."}
        return {"model": self.model, "done": True,
                "message": {"role": "assistant", "content": json.dumps(decision)}}


def test_resumption_does_not_regenerate_started_slots_and_accounts_for_partials(frozen):
    runner.run(frozen, limit=1, policy_factory=RecordingFixture, inspector=inspection)
    protocol = runner.read_json(frozen / "protocol.json")
    partial = protocol["schedule"][1]
    runner.write_new(frozen / "episodes" / partial["slot_id"] / "started.json", {
        "utc": runner.now(), "slot": partial,
        "protocol_sha256": runner.read_json(frozen / "protocol.sha256.json")["sha256"]})
    first = frozen / "episodes" / protocol["schedule"][0]["slot_id"] / "trace.json"
    initial = first.read_bytes()
    runner.run(frozen, limit=1, policy_factory=RecordingFixture, inspector=inspection)
    result = analysis.analyze(frozen)
    assert result["episode_status"] == {"completed": 2, "failed": 0, "interrupted_partial": 1, "unstarted": 9}
    assert first.read_bytes() == initial
    assert not (frozen / "episodes" / partial["slot_id"] / "receipt.json").exists()
    assert result["summary"]["agent_self_report"]["state"]["claim_error"]["value"] is None


def test_source_and_protocol_changes_refuse_resume(frozen, monkeypatch):
    monkeypatch.setattr(runner, "code_hashes", lambda: {"changed": "bytes"})
    with pytest.raises(ValueError, match="source changed"):
        runner.run(frozen, inspector=inspection)
    assert not (frozen / "runner.lock").exists()


def test_written_protocol_manifest_and_research_tests_are_bound(frozen):
    protocol = runner.read_json(frozen / "protocol.json")
    inventory = protocol["source_inventory"]
    assert set(inventory) == {
        "written-protocol.source.md", "study-plan.source.json",
        "research-tests/test_matched_local_study.py",
        "research-tests/test_matched_baseline_audit.py",
    }
    for name, source in inventory.items():
        source_path = Path(source["source_path"])
        source_path = source_path if source_path.is_absolute() else runner.ROOT / source_path
        assert (frozen / name).read_bytes() == source_path.read_bytes()
        assert sha256((frozen / name).read_bytes()).hexdigest() == source["sha256"]
    assert inventory["research-tests/test_matched_local_study.py"]["source_path"] == "tests/test_matched_local_study.py"
    source = frozen.parent / "protocol.md"
    source.write_bytes(source.read_bytes() + b"\nChanged after freeze.\n")
    with pytest.raises(ValueError, match="Declared study source changed"):
        runner.run(frozen, inspector=inspection)
    assert not (frozen / "runner.lock").exists()


def test_changed_written_protocol_snapshot_refuses_resume(frozen):
    path = frozen / "written-protocol.source.md"
    path.write_bytes(path.read_bytes() + b"\nChanged frozen bytes.\n")
    with pytest.raises(ValueError, match="Frozen source snapshot changed"):
        runner.run(frozen, inspector=inspection)
    assert not (frozen / "runner.lock").exists()


def test_model_digest_change_and_parallel_lock_refuse_calls(frozen):
    def changed(models, settings):
        value = inspection(models, settings)
        value["models"][models[0]]["tag"]["digest"] = "different"
        return value
    with pytest.raises(PolicyError, match="digest changed"):
        runner.run(frozen, inspector=changed)
    assert not list((frozen / "episodes").glob("*/started.json")) if (frozen / "episodes").exists() else True
    runner.write_new(frozen / "runner.lock", {"pid": 123})
    with pytest.raises(FileExistsError):
        runner.run(frozen, inspector=inspection)


def test_journal_tamper_and_torn_tail_are_hard_stops(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = runner.Journal(path)
    journal.append("original", value=1)
    path.write_bytes(path.read_bytes().replace(b'"value":1', b'"value":2'))
    with pytest.raises(ValueError, match="chain changed"):
        runner.Journal(path)
    path.write_bytes(b'{"partial":')
    with pytest.raises(ValueError, match="Torn"):
        runner.Journal(path)


def test_absence_of_denominator_stays_null():
    summary = analysis.summarize([])
    assert summary["response_only"]["state"]["claim_error"] == {"numerator": 0, "denominator": 0, "value": None}


def test_reference_rejects_stale_incomplete_and_malformed_readback():
    episode = run_policy_scenario(ScenarioConfig(fault=Fault.CLEAN), FixturePolicy())
    observation = episode.trace.observations[-1]
    for altered in (replace(observation, complete=False), replace(observation, available=False),
                    replace(observation, as_of_ms=99),
                    replace(observation, records=({"effect_id": "incomplete"},))):
        assert analysis.public_reference(episode.trace.action, altered)["state"] is None


class FakeResponse:
    status = 200

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.data[:size]


class FakeOpener:
    def __init__(self, data=None, error=None):
        self.data, self.error = data, error

    def open(self, request, *, timeout):
        if self.error:
            raise self.error
        return FakeResponse(self.data)


@pytest.mark.parametrize("data", [b'{"model":"fixture"}', b"not-json", b"\xff"])
def test_exact_provider_bytes_retained_even_for_invalid_envelopes(tmp_path, data):
    journal = runner.Journal(tmp_path / "journal.jsonl")
    policy = runner.RecordingPolicy("fixture", directory=tmp_path, slot="episode_00000",
                                    journal=journal, max_calls=1)
    policy._opener = FakeOpener(data)
    if data.startswith(b"{"):
        assert policy._request("/api/chat", {"model": "fixture"}) == {"model": "fixture"}
    else:
        with pytest.raises(PolicyError):
            policy._request("/api/chat", {"model": "fixture"})
    assert [row["event"] for row in journal.records] == ["chat_started", "chat_received"]
    assert (tmp_path / journal.records[-1]["response_file"]).read_bytes() == data
    with pytest.raises(PolicyError, match="cap reached"):
        policy._request("/api/chat", {"model": "fixture"})
    assert policy.calls == 1


def test_http_and_transport_failure_receipts_are_not_semantic_outcomes(tmp_path):
    journal = runner.Journal(tmp_path / "journal.jsonl")
    policy = runner.RecordingPolicy("fixture", directory=tmp_path, slot="episode_00000",
                                    journal=journal, max_calls=2)
    policy._opener = FakeOpener(error=HTTPError("http://localhost", 503, "offline", {}, io.BytesIO(b"failure body")))
    with pytest.raises(PolicyError, match="HTTP 503"):
        policy._request("/api/chat", {"model": "fixture"})
    assert (tmp_path / journal.records[-1]["response_file"]).read_bytes() == b"failure body"
    policy._opener = FakeOpener(error=URLError("offline"))
    with pytest.raises(PolicyError, match="no sample retry"):
        policy._request("/api/chat", {"model": "fixture"})
    assert journal.records[-1]["event"] == "chat_transport_failed"


def test_wall_time_cap_refuses_generation_before_recording_a_call(tmp_path):
    journal = runner.Journal(tmp_path / "journal.jsonl")
    policy = runner.RecordingPolicy("fixture", directory=tmp_path, slot="episode_00000",
                                    journal=journal, max_calls=2, deadline_utc=time.time()-1)
    policy._opener = FakeOpener(error=AssertionError("No provider call permitted"))
    with pytest.raises(PolicyError, match="wall-time budget"):
        policy._request("/api/chat", {"model": "fixture"})
    assert policy.calls == 0
    assert journal.records[-1]["event"] == "wall_time_exhausted"


def test_slow_identity_check_cannot_dispatch_after_wall_cutoff(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(runner.time, "time", lambda: clock[0])
    journal = runner.Journal(tmp_path / "journal.jsonl")
    policy = runner.RecordingPolicy("fixture", directory=tmp_path, slot="episode_00000",
                                    journal=journal, max_calls=2, deadline_utc=11.0,
                                    expected_digest="fixture-digest")
    def identity():
        clock[0] = 12.0
        return ({"name": "fixture", "digest": "fixture-digest"},)
    monkeypatch.setattr(policy, "list_models", identity)
    policy._opener = FakeOpener(error=AssertionError("No provider call permitted"))
    with pytest.raises(runner.InfrastructurePolicyError, match="wall-time budget"):
        policy._request("/api/chat", {"model": "fixture"})
    assert policy.calls == 0
    assert not list((tmp_path / "calls").glob("*"))


def test_http_wait_is_bounded_by_remaining_wall_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.time, "time", lambda: 10.0)
    journal = runner.Journal(tmp_path / "journal.jsonl")
    policy = runner.RecordingPolicy("fixture", directory=tmp_path, slot="episode_00000",
                                    journal=journal, max_calls=2, deadline_utc=11.5,
                                    timeout=180)
    observed = []
    class BoundedOpener:
        def open(self, request, *, timeout):
            observed.append(timeout)
            return FakeResponse(b'{"model":"fixture"}')
    policy._opener = BoundedOpener()
    assert policy._request("/api/chat", {"model": "fixture"}) == {"model": "fixture"}
    assert observed == [1.5]


@pytest.mark.parametrize("envelope", [
    {"model": "different"}, {"done": True}, {"model": "fixture", "remote_host": "https://remote"},
    {"model": "fixture", "remote_model": 7},
])
def test_returned_identity_or_routing_failure_is_infrastructure(tmp_path, envelope):
    journal = runner.Journal(tmp_path / "journal.jsonl")
    policy = runner.RecordingPolicy("fixture", directory=tmp_path, slot="episode_00000",
                                    journal=journal, max_calls=2)
    raw = json.dumps(envelope).encode()
    policy._opener = FakeOpener(raw)
    with pytest.raises(runner.InfrastructurePolicyError):
        policy._request("/api/chat", {"model": "fixture"})
    assert journal.records[-1]["event"] == "chat_identity_failed"
    received = next(event for event in journal.records if event["event"] == "chat_received")
    assert (tmp_path / received["response_file"]).read_bytes() == raw


def test_identity_infrastructure_failure_stops_before_starting_next_slot(frozen):
    class WrongIdentity(RecordingFixture):
        def _request(self, path, payload=None):
            super()._request(path, payload)
            self.journal.append("chat_identity_failed", slot_id=self.slot)
            raise runner.InfrastructurePolicyError("Wrong returned identity")
    result = runner.run(frozen, policy_factory=WrongIdentity, inspector=inspection)
    assert result["newly_started_episodes"] == 1
    analysis_result = analysis.analyze(frozen)
    assert analysis_result["episode_status"] == {
        "completed": 0, "failed": 1, "interrupted_partial": 0, "unstarted": 11}
    assert analysis_result["episodes"][0]["infrastructure_failure"] is True


def test_malformed_decision_remains_failed_sample_and_continues(frozen):
    class Malformed(RecordingFixture):
        def _request(self, path, payload=None):
            super()._request(path, payload)
            raise PolicyError("Malformed model decision")
    result = runner.run(frozen, limit=2, policy_factory=Malformed, inspector=inspection)
    assert result["newly_started_episodes"] == 2
    analysis_result = analysis.analyze(frozen)
    assert analysis_result["episode_status"] == {
        "completed": 0, "failed": 2, "interrupted_partial": 0, "unstarted": 10}


def test_failed_slot_is_not_regenerated(frozen):
    class Failed(RecordingFixture):
        def _request(self, path, payload=None):
            super()._request(path, payload)
            raise PolicyError("Deliberate offline protocol failure")
    runner.run(frozen, limit=1, policy_factory=Failed, inspector=inspection)
    first_slot = runner.read_json(frozen / "protocol.json")["schedule"][0]["slot_id"]
    first = frozen / "episodes" / first_slot / "receipt.json"
    before = first.read_bytes()
    runner.run(frozen, limit=1, policy_factory=RecordingFixture, inspector=inspection)
    result = analysis.analyze(frozen)
    assert result["episode_status"] == {"completed": 1, "failed": 1, "interrupted_partial": 0, "unstarted": 10}
    assert first.read_bytes() == before


def test_analyzer_refuses_changed_captured_request_bytes(frozen):
    runner.run(frozen, limit=1, policy_factory=RecordingFixture, inspector=inspection)
    path = next((frozen / "calls").glob("*.request.json"))
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="provider bytes changed"):
        analysis.analyze(frozen)
