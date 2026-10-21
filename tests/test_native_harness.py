"""Synthetic execution-capture checks; no native tasks, model or network calls."""
from copy import deepcopy
from contextlib import contextmanager
import json
import sys
from types import SimpleNamespace

import pytest

from research.native_agent import harness as h


class MemoryJournal:
    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(deepcopy(h.jsonable(row)))


class FixtureEnvironment:
    def __init__(self):
        self.agent = 0
        self.user = 0
        self.seen = []

    def get_db_hash(self):
        return f"agent-{self.agent}"

    def get_user_db_hash(self):
        return f"user-{self.user}"

    def make_tool_call(self, tool_name, requestor="assistant", **arguments):
        self.seen.append((tool_name, requestor, deepcopy(arguments)))
        if tool_name == "write":
            self.agent += 1
        elif tool_name == "user_write":
            self.user += 1
        elif tool_name == "partial_failure":
            self.agent += 1
            raise ValueError("Synthetic failure after an effect")
        return {"value": self.agent, "arguments": arguments}

    @staticmethod
    def to_json_str(value):
        return json.dumps(value, sort_keys=True)


def terminal_rows(journal):
    return [row for row in journal.rows if "outcome" in row]


def test_journal_exclusive_creation_indices_and_flush(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = h.Journal(path)
    journal.append({"kind": "one", "nested": {"values": (1, None, True)}})
    # A separate reader must see the flushed record before the writer closes.
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["event_index"] == 0 and first["recorded_utc"].endswith("+00:00")
    assert first["nested"]["values"] == [1, None, True]
    journal.append({"kind": "two"})
    journal.close()
    assert [json.loads(line)["event_index"] for line in path.read_text().splitlines()] == [0, 1]
    with pytest.raises(FileExistsError):
        h.Journal(path)


@pytest.mark.parametrize("reserved", ["event_index", "recorded_utc"])
def test_journal_refuses_forged_reserved_metadata(tmp_path, reserved):
    journal = h.Journal(tmp_path / "journal.jsonl")
    try:
        with pytest.raises(ValueError):
            journal.append({reserved: "forged"})
        assert journal.count == 0
    finally:
        journal.close()


def test_journal_non_json_and_non_finite_values_fail_without_advancing(tmp_path):
    journal = h.Journal(tmp_path / "journal.jsonl")
    try:
        with pytest.raises(TypeError):
            journal.append({"value": object()})
        with pytest.raises(ValueError):
            journal.append({"value": float("nan")})
        assert journal.count == 0
    finally:
        journal.close()


def test_observer_preserves_real_results_requestors_phase_and_hashes():
    environment, journal = FixtureEnvironment(), MemoryJournal()
    state = h.observe_environment(environment, journal)
    result = environment.make_tool_call("write", amount=3)
    assert result == {"value": 1, "arguments": {"amount": 3}}
    state["phase"] = "episode"
    environment.make_tool_call("user_write", requestor="user", amount=4)
    environment.make_tool_call("read", reservation_id="synthetic")
    rows = terminal_rows(journal)
    assert state["call_index"] == 3 and len(rows) == 3
    assert [row["call_index"] for row in rows] == [0, 1, 2]
    assert [row["phase"] for row in rows] == ["initialization", "episode", "episode"]
    assert rows[0]["before"] == {"agent_db_hash": "agent-0", "user_db_hash": "user-0"}
    assert rows[0]["after"] == {"agent_db_hash": "agent-1", "user_db_hash": "user-0"}
    assert rows[1]["request"]["requestor"] == "user"
    assert rows[2]["before"] == rows[2]["after"]
    assert json.loads(rows[0]["outcome"]["content"]) == result


def test_observer_retains_partial_effect_on_native_exception_and_reraises():
    environment, journal = FixtureEnvironment(), MemoryJournal()
    state = h.observe_environment(environment, journal)
    with pytest.raises(ValueError, match="after an effect"):
        environment.make_tool_call("partial_failure")
    row = terminal_rows(journal)[0]
    assert state["call_index"] == 1
    assert row["outcome"]["status"] == "raised" and row["outcome"]["error_type"] == "ValueError"
    assert row["before"]["agent_db_hash"] == "agent-0"
    assert row["after"]["agent_db_hash"] == "agent-1"


def test_observer_freezes_nested_arguments_before_native_mutation():
    environment, journal = FixtureEnvironment(), MemoryJournal()

    def mutate(tool_name, requestor="assistant", **arguments):
        arguments["payload"]["items"].append("native mutation")
        return "actual result"

    environment.make_tool_call = mutate
    h.observe_environment(environment, journal)
    payload = {"items": ["requested"]}
    assert environment.make_tool_call("write", payload=payload) == "actual result"
    assert payload["items"] == ["requested", "native mutation"]
    assert terminal_rows(journal)[0]["request"]["arguments"] == {"payload": {"items": ["requested"]}}


def test_observer_records_inflight_dispatch_before_native_body():
    environment, journal, starts = FixtureEnvironment(), MemoryJournal(), MemoryJournal()

    def inspect(tool_name, requestor="assistant", **arguments):
        assert starts.rows, "Dispatch must be flushed before the native body starts"
        assert not journal.rows, "Terminal journal must contain only completed dispatches"
        first = starts.rows[0]
        assert first["call_index"] == 0
        assert first["request"]["tool_name"] == tool_name
        assert "outcome" not in first
        return "completed"

    environment.make_tool_call = inspect
    state = h.observe_environment(environment, journal, starts)
    assert environment.make_tool_call("read") == "completed"
    assert terminal_rows(journal)[0]["outcome"]["status"] == "returned"
    assert state["inflight"] == [] and state["completed"] == 1


class FixtureResponse:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return deepcopy(self.payload)


def test_completion_counts_success_failure_and_hard_budget_without_extra_dispatch():
    journal = MemoryJournal()
    actual = []

    def complete(**kwargs):
        actual.append(kwargs)
        if len(actual) == 2:
            raise RuntimeError("Synthetic provider failure")
        return FixtureResponse({"usage": {"prompt_tokens": 11, "completion_tokens": 3}, "choices": []})

    module = SimpleNamespace(completion=complete)
    state = h.record_completions(module, journal, 2)
    response = module.completion(model="synthetic", num_retries=0, api_key="dummy-redact-me")
    assert response.to_dict()["usage"]["prompt_tokens"] == 11
    with pytest.raises(RuntimeError, match="provider failure"):
        module.completion(model="synthetic", num_retries=0)
    with pytest.raises(h.RequestBudgetExceeded):
        module.completion(model="synthetic", num_retries=0)
    assert len(actual) == 2
    assert {key: state[key] for key in ("attempted", "completed", "failed", "prompt_tokens", "completion_tokens")} == {
        "attempted": 2, "completed": 1, "failed": 1, "prompt_tokens": 11, "completion_tokens": 3}
    assert "dummy-redact-me" not in json.dumps(journal.rows)
    kinds = [row["kind"] for row in journal.rows]
    assert kinds == ["request_start", "request_return", "request_start", "request_error", "request_budget_exhausted"]


@pytest.mark.parametrize("positional,kwargs", [
    (("unsupported positional",), {"num_retries": 0}),
    ((), {}),
    ((), {"num_retries": 1}),
])
def test_refused_completion_arguments_have_terminal_accounting(positional, kwargs):
    journal = MemoryJournal()
    module = SimpleNamespace(completion=lambda **kwargs: pytest.fail("Rejected input dispatched"))
    state = h.record_completions(module, journal, 1)
    with pytest.raises(RuntimeError):
        module.completion(*positional, **kwargs)
    assert state["attempted"] == state["failed"] == 1
    assert state["completed"] == 0
    assert any(row.get("kind") == "request_error" for row in journal.rows)


def test_completion_capture_failure_is_not_an_unaccounted_attempt():
    class BrokenCapture:
        def to_dict(self):
            raise ValueError("Synthetic response serialization failure")

    module = SimpleNamespace(completion=lambda **kwargs: BrokenCapture())
    journal = MemoryJournal()
    state = h.record_completions(module, journal, 1)
    with pytest.raises(ValueError, match="serialization failure"):
        module.completion(num_retries=0)
    assert state["attempted"] == state["completed"] + state["failed"] == 1
    assert any(row.get("kind") == "request_error" for row in journal.rows)


def test_completion_critical_baseexception_is_recorded_and_not_retried():
    class HardRefusal(BaseException):
        pass

    calls = []

    def refused(**kwargs):
        calls.append(kwargs)
        raise HardRefusal("Synthetic context refusal")

    module, journal = SimpleNamespace(completion=refused), MemoryJournal()
    state = h.record_completions(module, journal, 2)
    with pytest.raises(HardRefusal):
        module.completion(num_retries=0)
    assert state["attempted"] == state["failed"] == len(calls) == 1
    assert journal.rows[-1]["error_type"] == "HardRefusal"


def test_completion_scope_receives_copied_public_input_and_exits_on_provider_failure():
    events = []

    @contextmanager
    def scope(request):
        assert "api_key" not in request
        events.append(("enter", deepcopy(request)))
        try:
            yield
        finally:
            events.append(("exit", None))

    def fail(**kwargs):
        assert events[0][0] == "enter"
        kwargs["messages"][0]["content"] = "provider mutation"
        raise RuntimeError("Synthetic provider failure")

    journal = MemoryJournal()
    module = SimpleNamespace(completion=fail)
    state = h.record_completions(module, journal, 1, invoke_scope=scope)
    with pytest.raises(RuntimeError):
        module.completion(num_retries=0, api_key="redacted", messages=[{"role": "user", "content": "requested"}])
    assert [event[0] for event in events] == ["enter", "exit"]
    assert events[0][1]["messages"][0]["content"] == "requested"
    assert state["attempted"] == state["failed"] == state["provider_invoked"] == 1
    assert [row["kind"] for row in journal.rows] == ["request_start", "request_error"]


def test_completion_distinguishes_missing_usage_from_known_zero():
    module = SimpleNamespace(completion=lambda **kwargs: FixtureResponse({"choices": []}))
    state = h.record_completions(module, MemoryJournal(), 1)
    module.completion(num_retries=0)
    assert state["completed"] == state["provider_returned"] == state["usage_unavailable"] == 1
    assert state["prompt_tokens"] == state["completion_tokens"] == 0


def test_completion_freezes_arguments_before_provider_mutation():
    journal = MemoryJournal()

    def mutate(**kwargs):
        kwargs["messages"][0]["content"] = "changed by provider"
        return FixtureResponse({"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}})

    module = SimpleNamespace(completion=mutate)
    h.record_completions(module, journal, 1)
    module.completion(num_retries=0, messages=[{"role": "user", "content": "requested"}])
    assert journal.rows[0]["request"]["messages"][0]["content"] == "requested"


def test_episode_guard_failure_is_recorded_before_any_native_import(tmp_path, monkeypatch):
    import builtins

    original = builtins.__import__

    def forbidden_native(name, *args, **kwargs):
        assert not name.startswith("tau2"), "Guard failure must precede native imports"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbidden_native)
    guard = SimpleNamespace(active=True, api_base="http://127.0.0.1:11436/v1", events=[])
    gate = SimpleNamespace(guard=guard, receipts=[])
    guard.before_generation = object()
    output = tmp_path / "episode"
    assert h.run_episode(native_root=tmp_path, output=output, task_id="synthetic", arm="native",
        episode_id="synthetic", seed=1701, guard=guard, context_gate=gate) == "failed"
    receipt = json.loads((output / "execution-receipt.json").read_text())
    assert receipt["stage"] == "startup" and receipt["model_requests"] is None
    assert (output / "startup-failure.json").exists()
    assert not (output / "native-simulation.json").exists()


@pytest.fixture
def fake_native(tmp_path, monkeypatch):
    """Native-shaped public interfaces, with no real corpus, provider or HTTP."""
    from types import ModuleType
    from research.native_agent.transport import LocalOnlyGuard

    captured = {}
    environment = FixtureEnvironment()
    environment.tools = SimpleNamespace(db={"fixture": "agent"})
    environment.user_tools = None
    def original_completion(**kwargs):
        pytest.fail("Synthetic run must not generate")
    llm_utils = SimpleNamespace(completion=original_completion, litellm=SimpleNamespace(cache="old"))

    class Config:
        def __init__(self, **kwargs):
            captured["config"] = kwargs
            self.kwargs = kwargs

        def model_dump(self, **kwargs):
            return deepcopy(self.kwargs)

    task = SimpleNamespace(id="synthetic", initial_state=None,
                           evaluation_criteria=SimpleNamespace(reward_basis=["DB", "COMMUNICATE"]))
    orchestrator = SimpleNamespace(environment=environment, initialize=lambda: None,
                                  get_messages=lambda: [])

    def build(config, supplied_task, **kwargs):
        assert supplied_task is task
        return orchestrator

    def simulate(supplied, **kwargs):
        assert supplied is orchestrator
        assert guard.require_native_invocation is True
        supplied.initialize()
        return SimpleNamespace(model_dump=lambda **kwargs: {"fixture": "native returned"})

    modules = {
        "tau2.data_model.simulation": {"TextRunConfig": Config},
        "tau2.data_model.tasks": {"Task": SimpleNamespace(model_validate=lambda payload: task)},
        "tau2.evaluator.evaluator": {"EvaluationType": SimpleNamespace(ALL="ALL")},
        "tau2.registry": {"registry": SimpleNamespace(register_agent_factory=lambda *a, **k: None)},
        "tau2.runner.build": {"build_text_orchestrator": build},
        "tau2.runner.simulation": {"run_simulation": simulate},
        "tau2.utils": {"llm_utils": llm_utils},
    }
    for name, attributes in modules.items():
        parts = name.split(".")
        for count in range(1, len(parts)):
            parent = ".".join(parts[:count])
            if parent not in sys.modules:
                package = ModuleType(parent)
                package.__path__ = []
                monkeypatch.setitem(sys.modules, parent, package)
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    corpus = tmp_path / "native" / "data" / "tau2" / "domains" / "airline"
    corpus.mkdir(parents=True)
    (corpus / "tasks.json").write_text('[{"id":"synthetic"}]', encoding="utf-8")
    monkeypatch.setattr(sys.modules["tau2"], "__file__",
                        str(tmp_path / "native" / "src" / "tau2" / "__init__.py"), raising=False)
    guard = LocalOnlyGuard(api_base="http://127.0.0.1:11436/v1")
    guard.active = True  # Synthetic public interfaces never invoke a network operation.
    gate = SimpleNamespace(guard=guard, receipts=[])
    guard.before_generation = gate
    return SimpleNamespace(native_root=tmp_path / "native", captured=captured, guard=guard, gate=gate,
        llm_utils=llm_utils, original_completion=original_completion, orchestrator=orchestrator,
        task=task, runner_module=sys.modules["tau2.runner.simulation"])


def test_episode_binds_isolated_listener_and_restores_completion(tmp_path, fake_native):
    fixture = fake_native
    output = tmp_path / "episode"
    status = h.run_episode(native_root=fixture.native_root, output=output, task_id="synthetic", arm="native",
        episode_id="synthetic", seed=1701, guard=fixture.guard, context_gate=fixture.gate)
    assert status == "native_returned"
    for who in ("llm_args_agent", "llm_args_user"):
        assert fixture.captured["config"][who]["api_base"] == "http://127.0.0.1:11436/v1"
        assert fixture.captured["config"][who]["num_retries"] == 0
    assert fixture.llm_utils.completion is fixture.original_completion
    assert fixture.guard.require_native_invocation is False
    final = json.loads((output / "final-state.json").read_text())
    assert final["hashes"] == {"agent_db_hash": "agent-0", "user_db_hash": "user-0"}
    assert (output / "native-simulation.json").exists()


def test_episode_partial_failure_closes_journals_and_does_not_invent_native_run(tmp_path, fake_native):
    fixture = fake_native

    def fail(orchestrator, **kwargs):
        orchestrator.initialize()
        orchestrator.environment.make_tool_call("partial_failure")

    fixture.runner_module.run_simulation = fail
    output = tmp_path / "episode"
    assert h.run_episode(native_root=fixture.native_root, output=output, task_id="synthetic", arm="native",
        episode_id="synthetic", seed=1701, guard=fixture.guard, context_gate=fixture.gate) == "failed"
    receipt = json.loads((output / "execution-receipt.json").read_text())
    assert receipt["actual_tool_dispatches"] == receipt["completed_tool_dispatches"] == 1
    assert receipt["inflight_tool_dispatches"] == []
    assert receipt["capture_errors"] == []
    assert (output / "partial-native-messages.json").exists()
    assert not (output / "native-simulation.json").exists()
    assert fixture.llm_utils.completion is fixture.original_completion
    assert fixture.guard.require_native_invocation is False
    for path in output.glob("*.jsonl"):
        # Windows refuses a rename while the writer remains open.
        path.rename(path.with_suffix(".closed"))


@pytest.mark.parametrize("failure", ["wrong_native_origin", "hosted_judge_basis"])
def test_episode_startup_refuses_wrong_native_or_reward_basis(tmp_path, fake_native, failure, monkeypatch):
    fixture = fake_native
    if failure == "wrong_native_origin":
        monkeypatch.setattr(sys.modules["tau2"], "__file__", str(tmp_path / "other" / "__init__.py"))
    else:
        fixture.task.evaluation_criteria.reward_basis.append("NL_ASSERTION")
    output = tmp_path / "episode"
    assert h.run_episode(native_root=fixture.native_root, output=output, task_id="synthetic", arm="native",
        episode_id="synthetic", seed=1701, guard=fixture.guard, context_gate=fixture.gate) == "failed"
    receipt = json.loads((output / "execution-receipt.json").read_text())
    assert receipt["stage"] == "startup" and receipt["native_reward_not_fabricated"] is True
    assert not fixture.captured
    assert fixture.guard.require_native_invocation is False
    assert fixture.llm_utils.completion is fixture.original_completion
    assert not (output / "native-simulation.json").exists()


def test_episode_rejects_framework_checkout_shadowing_installed_release(tmp_path, fake_native, monkeypatch):
    from importlib import metadata, util

    fixture = fake_native
    distribution = SimpleNamespace(version="2.1.1", locate_file=lambda name: tmp_path / "installed" / name)
    monkeypatch.setattr(metadata, "distribution", lambda name: distribution)
    monkeypatch.setattr(util, "find_spec", lambda name: SimpleNamespace(
        origin=str(tmp_path / "checkout" / "consequa_x" / "__init__.py")))
    output = tmp_path / "episode"
    assert h.run_episode(native_root=fixture.native_root, output=output, task_id="synthetic", arm="R",
        episode_id="synthetic", seed=1701, guard=fixture.guard, context_gate=fixture.gate) == "failed"
    receipt = json.loads((output / "execution-receipt.json").read_text())
    assert receipt["stage"] == "startup" and receipt["error_type"] == "RuntimeError"
    assert not fixture.captured and fixture.llm_utils.completion is fixture.original_completion


def test_episode_failed_final_capture_still_closes_journals_and_records_receipt(tmp_path, fake_native, monkeypatch):
    fixture = fake_native
    original = h.db_snapshot
    captures = []

    def fail_final(environment):
        captures.append(environment)
        if len(captures) == 2:
            raise RuntimeError("Synthetic final DB capture failure")
        return original(environment)

    monkeypatch.setattr(h, "db_snapshot", fail_final)
    output = tmp_path / "episode"
    assert h.run_episode(native_root=fixture.native_root, output=output, task_id="synthetic", arm="native",
        episode_id="synthetic", seed=1701, guard=fixture.guard, context_gate=fixture.gate) == "capture_failed"
    receipt = json.loads((output / "execution-receipt.json").read_text())
    assert receipt["capture_errors"][0]["artifact"] == "final-db.evaluator-only.json"
    assert fixture.llm_utils.completion is fixture.original_completion
    assert (output / "native-simulation.json").exists()
    for path in output.glob("*.jsonl"):
        path.rename(path.with_suffix(".closed"))


def test_sealing_binds_exact_bytes_and_refuses_overwrite(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "raw.json").write_bytes(b'{"fixture":true}\n')
    h.seal_directory(tmp_path, "synthetic-only-v1")
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["schema"] == "synthetic-only-v1" and manifest["complete"] is True
    assert set(manifest["files"]) == {"nested/raw.json"}
    with pytest.raises(FileExistsError):
        h.seal_directory(tmp_path, "replacement")
