"""Invented turn fixtures for qualification; zero GPU/model generations."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.kaggle_limbo import run, runtime, transport


@dataclass
class SyntheticCall:
    id: str = "fixture-call"
    name: str = "lookup_echo"
    arguments: str = '{"name":"test-item"}'

    def parsed_arguments(self):
        try:
            return json.loads(self.arguments), None
        except ValueError:
            return None, "invented invalid JSON"


@dataclass
class SyntheticTurn:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    finish_reason: str = "stop"


def first():
    return SyntheticTurn(tool_calls=[SyntheticCall()], finish_reason="tool_calls")


def final():
    return SyntheticTurn(text="test-item")


@pytest.fixture
def qualification(tmp_path, monkeypatch):
    calls, clients, loads = [], [], []
    models = [{"id": family + "-synthetic", "family": family} for family in ("qwen", "llama", "granite")]
    responses = {model["id"]: [first(), final()] for model in models}

    def load_model(server, model, path):
        loads.append(model["id"])
        Path(path).mkdir(parents=True)
        runtime.save(Path(path) / "gpu-load-proof.json", {"synthetic": True})
        return SimpleNamespace(model=model["id"])

    class SyntheticClient:
        def __init__(self, lease, path, **kwargs):
            self.model, self.path, self.options = lease.model, path, kwargs
            self._dispatches = 0
            clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def complete(self, system, conversation, tools):
            self._dispatches += 1
            assert self._dispatches <= self.options["max_requests"]
            calls.append({"model": self.model, "system": system,
                          "conversation": deepcopy(conversation), "tools": deepcopy(tools)})
            result = responses[self.model].pop(0)
            if isinstance(result, BaseException):
                raise result
            return result

    monkeypatch.setattr(runtime, "load_model", load_model)
    monkeypatch.setattr(transport, "KaggleGPUClient", SyntheticClient)
    setup = {"server": {"synthetic": True}, "condition": {"synthetic": True},
             "gpu_devices": [{"name": "invented device, not hardware evidence"}]}
    return SimpleNamespace(root=tmp_path, models=models, protocol={"models": models},
        setup=setup, calls=calls, clients=clients, loads=loads, responses=responses)


def verdicts(fixture):
    return {p.parent.name: json.loads(p.read_text()) for p in fixture.root.rglob("preflight.json")}


def test_three_models_complete_exact_tool_round_trip_in_six_calls(qualification):
    fixture = qualification
    result = run.preflight("unused-study", fixture.root, fixture.protocol, fixture.setup)
    assert set(result) == {model["id"] for model in fixture.models}
    assert len(fixture.calls) == 6
    for client in fixture.clients:
        assert client.options["max_requests"] == 2
        assert client.options["max_output_tokens"] == 128
        assert client.options["temperature"] == .2 and client.options["seed"] == 2501
        assert client.options["request_timeout_s"] == 300
    for number in (1, 3, 5):
        conversation = fixture.calls[number]["conversation"]
        assistant, tool_result = conversation[-2:]
        assert assistant["tool_calls"] == [{"id": "fixture-call", "name": "lookup_echo", "arguments": '{"name":"test-item"}'}]
        assert tool_result == {"role": "tool", "tool_call_id": "fixture-call", "content": '{"name":"test-item","ok":true}'}
        assert len(conversation) == 3
        assert [turn["role"] for turn in conversation] == ["user", "assistant", "tool"]
    assert all(call["system"] == run.QUALIFICATION_SYSTEM for call in fixture.calls)
    assert run.QUALIFICATION_SYSTEM == (
        "Call lookup_echo exactly once with the requested name. After receiving its tool result, "
        "reply with the result name value only and do not call any tool again.")
    for observed in verdicts(fixture).values():
        assert observed["passed"] and observed["stage"] == "complete"
        assert observed["qualification_revision"] == "tool-roundtrip-v3"
        assert observed["expectation"]["followup_last_role"] == "tool"
        assert observed["expectation"]["system"] == run.QUALIFICATION_SYSTEM
        assert observed["actual_model_dispatches"] == observed["model_invocations_attempted"] == 2
        assert observed["native_tasks"] == observed["automatic_retries"] == 0
        assert observed["observed"]["first_tool_call"]["tool_call_count"] == 1
        assert observed["observed"]["tool_result_followup"]["tool_call_count"] == 0
        checks = observed["observed"]["tool_result_followup"]["checks"]
        assert checks["usable_native_response"] and checks["exact_name_readback"]
        assert (Path(observed["evidence_directory"]) / "followup-parsed-turn.json").is_file()


@pytest.mark.parametrize("bad", [
    SyntheticTurn(),
    SyntheticTurn(text='{"name":"test-item"}'),
    SyntheticTurn(tool_calls=[SyntheticCall(arguments='{"name":"wrong"}')]),
    SyntheticTurn(tool_calls=[SyntheticCall(name="wrong_tool")]),
    SyntheticTurn(tool_calls=[SyntheticCall(), SyntheticCall()]),
    SyntheticTurn(tool_calls=[SyntheticCall(arguments="invalid JSON")]),
])
def test_failed_first_call_names_family_and_preserves_observation_without_retry(qualification, bad):
    fixture = qualification
    fixture.responses["qwen-synthetic"] = [bad]
    with pytest.raises(ValueError, match="qwen model/tool preflight failed at first_tool_call"):
        run.preflight("unused", fixture.root, fixture.protocol, fixture.setup)
    assert len(fixture.calls) == 1
    assert fixture.loads == ["qwen-synthetic"]
    observed = verdicts(fixture)["qwen"]
    assert not observed["passed"] and observed["model_id"] == "qwen-synthetic"
    assert observed["model_invocations_attempted"] == observed["actual_model_dispatches"] == 1
    assert observed["observed"]["first_tool_call"]["text_length"] == len(bad.text)
    assert observed["observed"]["first_tool_call"]["tool_call_count"] == len(bad.tool_calls)
    assert not (Path(observed["evidence_directory"]) / "followup-parsed-turn.json").exists()


@pytest.mark.parametrize("bad", [
    SyntheticTurn(),
    SyntheticTurn(text="   "),
    SyntheticTurn(tool_calls=[SyntheticCall(arguments="invalid JSON")]),
    SyntheticTurn(tool_calls=[SyntheticCall(name=" ")]),
    SyntheticTurn(tool_calls=[SyntheticCall(arguments='["not an argument object"]')]),
])
def test_failed_followup_stops_after_two_calls_and_retains_both_turns(qualification, bad):
    fixture = qualification
    fixture.responses["qwen-synthetic"] = [first(), bad]
    with pytest.raises(ValueError, match="qwen model/tool preflight failed at tool_result_followup"):
        run.preflight("unused", fixture.root, fixture.protocol, fixture.setup)
    assert len(fixture.calls) == 2 and fixture.loads == ["qwen-synthetic"]
    observed = verdicts(fixture)["qwen"]
    assert observed["stage"] == "tool_result_followup" and not observed["passed"]
    assert observed["actual_model_dispatches"] == 2
    assert observed["observed"]["tool_result_followup"]["text"] == bad.text
    assert (Path(observed["evidence_directory"]) / "parsed-turn.json").is_file()
    assert (Path(observed["evidence_directory"]) / "followup-parsed-turn.json").is_file()


@pytest.mark.parametrize("usable", [
    SyntheticTurn(text='The result name value for "test-item" is "test-item".'),
    SyntheticTurn(text="different, semantically incorrect output"),
    first(),
    SyntheticTurn(tool_calls=[SyntheticCall(), SyntheticCall()]),
    SyntheticTurn(tool_calls=[SyntheticCall(name="wrong_tool", arguments='{"wrong":"value"}')]),
])
def test_usable_followup_is_not_conflated_with_correct_readback_or_tool_choice(qualification, usable):
    fixture = qualification
    fixture.protocol = {"models": fixture.models[:1]}
    fixture.responses["qwen-synthetic"] = [first(), usable]
    result = run.preflight("unused", fixture.root, fixture.protocol, fixture.setup)
    assert set(result) == {"qwen-synthetic"} and len(fixture.calls) == 2
    observed = verdicts(fixture)["qwen"]
    assert observed["passed"] and observed["qualification_revision"] == "tool-roundtrip-v3"
    checks = observed["observed"]["tool_result_followup"]["checks"]
    assert checks["usable_native_response"] is True
    assert checks["exact_name_readback"] is False
    assert checks["no_extra_tool_calls"] == (not usable.tool_calls)
    assert "semantic accuracy" in observed["expectation"]["scope"]


def test_later_model_failure_retains_earlier_passes_and_starts_no_native_tasks(qualification):
    fixture = qualification
    fixture.responses["granite-synthetic"] = [SyntheticTurn()]
    with pytest.raises(ValueError, match="granite model/tool preflight failed at first_tool_call"):
        run.preflight("unused", fixture.root, fixture.protocol, fixture.setup)
    assert len(fixture.calls) == 5
    observed = verdicts(fixture)
    assert observed["qwen"]["passed"] and observed["llama"]["passed"]
    assert observed["granite"]["passed"] is False
    assert all(v["native_tasks"] == 0 for v in observed.values())
    assert not list(fixture.root.rglob("execution-config.json"))


def test_transport_exception_is_retained_with_stage_and_original_cause(qualification):
    fixture = qualification
    fixture.responses["qwen-synthetic"] = [RuntimeError("invented HTTP failure")]
    with pytest.raises(ValueError) as raised:
        run.preflight("unused", fixture.root, fixture.protocol, fixture.setup)
    assert isinstance(raised.value.__cause__, RuntimeError)
    observed = verdicts(fixture)["qwen"]
    assert observed["stage"] == "first_tool_call"
    assert observed["error"] == {"type": "RuntimeError", "message": "invented HTTP failure"}
    assert observed["observed"] == {} and len(fixture.calls) == 1
