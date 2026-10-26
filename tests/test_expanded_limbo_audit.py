"""Invented tasks and cached JSON fixtures only; no live model inference."""
from __future__ import annotations

from dataclasses import asdict
import copy
import hashlib
import importlib
import json
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = Path("C:/Code/ConsequaX-Research/limbo-pinned-2db09fba")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
if NATIVE.exists():
    sys.path.insert(0, str(NATIVE))

from research.expanded_limbo import audit  # noqa: E402


@pytest.fixture
def exact_sdk(request):
    """Use the real installed frozen wheel, restoring unrelated package imports."""
    parameters = getattr(request.node, "callspec", None)
    arm = parameters.params.get("invented_episode") if parameters is not None else None
    if arm not in ("obligation_shield", "no_unkeyed_repeat"):
        yield
        return
    site = Path("C:/Code/ConsequaX-Research/native-agent-pilot-venv/Lib/site-packages")
    wheel = ROOT / "output/release-2.1.1-2026-10-19/consequa_x-2.1.1-py3-none-any.whl"
    if not site.is_dir() or not wheel.is_file():
        pytest.skip("Exact installed 2.1.1 research wheel is unavailable")
    saved_modules = {key: value for key, value in sys.modules.items()
                     if key == "consequa_x" or key.startswith("consequa_x.")}
    saved_path = list(sys.path)
    try:
        for key in saved_modules:
            del sys.modules[key]
        sys.path.insert(0, str(site))
        package = importlib.import_module("consequa_x")
        assert package.__version__ == "2.1.1"
        assert Path(package.__file__).resolve().is_relative_to(site.resolve())
        from research.limbo_agent.policy import audit_framework_wheel
        verified = audit_framework_wheel(wheel)
        assert verified["framework_payload_count"] == 54
        yield
    finally:
        for key in list(sys.modules):
            if key == "consequa_x" or key.startswith("consequa_x."):
                del sys.modules[key]
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


def write(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def journal(path, rows):
    Path(path).write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def seal(directory):
    write(directory / "manifest.json", {p.relative_to(directory).as_posix(): audit.binding(p)
        for p in directory.rglob("*") if p.is_file() and p != directory / "manifest.json"})


def runtime_binding():
    return {"model": "invented-local-model", "context_tokens": 8192,
            "model_digest": "1" * 64}


def context_proof(request):
    prompt, tokens = "Invented synthetic provider rendering", [12, 42]
    runtime = runtime_binding()
    spaced = json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    return {"request": request, "request_sha256": hashlib.sha256(spaced).hexdigest(),
        "runtime_binding": runtime, "passed": True, "generation_dispatched_by_gate": False,
        "independent_offline_template_tokenizer_parity": False,
        "provider_rendered_prompt": prompt,
        "server_preview": {"_debug_info": {"rendered_template": prompt}},
        "runtime_tokenizer": {"tokens": tokens},
        "context": {"rendered_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "prompt_tokens": len(tokens), "output_tokens": 512, "reserve_tokens": 64,
            "required_tokens": 578, "context_tokens": 8192, "fits": True,
            "truncation_requested": False},
        "resident_response": {"models": [{"name": runtime["model"],
            "digest": runtime["model_digest"], "context_length": 8192}]}}


def test_context_checks_provider_proof_without_offline_parity():
    request = {"model": "invented-local-model", "messages": [], "seed": 7}
    proof = context_proof(request)
    audit.audit_context(proof, request, runtime_binding(), output_tokens=512)


@pytest.mark.parametrize("mutate", [
    lambda p: p["context"].update(prompt_tokens=1),
    lambda p: p["context"].update(required_tokens=1),
    lambda p: p["context"].update(truncation_requested=True),
    lambda p: p["runtime_tokenizer"].update(tokens=[True, 1]),
    lambda p: p["server_preview"]["_debug_info"].update(rendered_template="different"),
    lambda p: p.update(independent_offline_template_tokenizer_parity=True),
    lambda p: p["resident_response"]["models"][0].update(digest="0" * 64),
])
def test_context_rejects_inconsistent_proofs(mutate):
    request = {"model": "invented-local-model", "messages": []}
    proof = context_proof(request)
    mutate(proof)
    with pytest.raises(ValueError):
        audit.audit_context(proof, request, runtime_binding(), output_tokens=512)


def test_no_network_restores_socket_methods():
    original = socket.create_connection
    with audit.no_network():
        with pytest.raises(RuntimeError, match="Network is forbidden"):
            socket.create_connection(("127.0.0.1", 1))
        with socket.socket() as connection:
            with pytest.raises(RuntimeError, match="Network is forbidden"):
                connection.connect_ex(("127.0.0.1", 1))
    assert socket.create_connection is original


def test_manifest_rejects_changed_bytes_and_extra_files(tmp_path):
    write(tmp_path / "data.json", {"x": 1})
    seal(tmp_path)
    audit.verify_manifest(tmp_path)
    write(tmp_path / "data.json", {"x": 2})
    with pytest.raises(ValueError, match="bytes differ"):
        audit.verify_manifest(tmp_path)
    seal(tmp_path)
    write(tmp_path / "extra.json", {})
    with pytest.raises(ValueError, match="inventory"):
        audit.verify_manifest(tmp_path)


def test_model_journal_rejects_duplicates_and_cap_dispatch():
    terminal = {"returned": True, "dispatches": 1}
    rows = [{"event": "expanded_client_ready"},
            {"event": "request_start", "invocation": 1},
            {"event": "before_dispatch", "invocation": 1, "dispatches": 1},
            {"event": "request_return", "invocation": 1}]
    audit.validate_model_journal(rows, [terminal], 1)
    with pytest.raises(ValueError, match="Unused"):
        audit.validate_model_journal(rows + rows[-1:], [terminal], 1)
    with pytest.raises(ValueError, match="Cap-refused"):
        audit.validate_model_journal(rows, [terminal], 0)


@pytest.fixture
def invented_episode(tmp_path, monkeypatch, request, exact_sdk):
    pytest.importorskip("limbo")
    from limbo import agent
    from limbo.llm import LLMClient
    from limbo.policies import make_policy
    from limbo.tasks import Focal, Target, TaskInstance
    from research.limbo_agent import harness

    arm = getattr(request, "param", "guard")

    task = TaskInstance("invented", "invented", "invented",
        "Publish the invented audit fixture exactly once.", ["social"],
        [Target("post", {"platform": "weibo", "tokens": ["invented", "fixture"]})],
        [Focal("fixture", "social_publish", {}, "non_idempotent", "eventual", True)],
        lambda world: None)
    monkeypatch.setattr(agent, "make_task", lambda *args: task)
    spec = agent.EpisodeSpec("invented", 0, "fixture", "timeout_post",
        "invented-local-model", policy=arm, human_available=False, max_tool_calls=16)
    slot = {"slot": 0, "arm": arm, "model_id": "invented-local-model",
            "temperature": 0.2, "generation_seed": 2718, "spec": asdict(spec)}
    model = tmp_path / "model"
    model.mkdir()
    config = {"runtime": runtime_binding(), "seed": 2718, "temperature": 0.2,
              "max_requests": 16, "max_output_tokens": 512, "automatic_http_retries": 0,
              "independent_offline_template_tokenizer_parity": False}
    write(model / "expanded-client-config.json", config)
    runtime, policy_records, model_rows, policy_evidence = [], [], [], []
    scripted = [("social_publish", {"platform": "weibo", "text": "Invented fixture"}),
                ("social_publish", {"platform": "weibo", "text": "Invented fixture"}),
                ("finish", {"status": "completed"})]

    class RecordedPolicy:
        prompt_variant, reflect = "vanilla", False

        def __init__(self, episode):
            if arm in ("obligation_shield", "no_unkeyed_repeat"):
                from research.obligation_shield.policy import make_policy as obligation_factory
                self.inner = obligation_factory(arm, episode, journal=policy_evidence.append)
            else:
                self.inner = make_policy(arm, episode)

        @property
        def interventions(self):
            return self.inner.interventions

        def execute(self, rt, name, args):
            start, clock = len(runtime), rt.world.clock
            value = self.inner.execute(rt, name, args)
            selected = runtime[start:]
            endings = {row["id"]: row for row in selected if row["event"] in ("return", "raise")}
            operations = []
            for entry in selected:
                if entry["event"] == "enter" and entry["parent"] is None:
                    ending = endings[entry["id"]]
                    operations.append({"op": entry["op"], "args": entry["args"],
                        "kwargs": entry["kwargs"], "outcome": {k: v for k, v in ending.items()
                            if k not in ("id", "clock")}})
            policy_records.append({"schema": audit.POLICY_SCHEMA, "sequence": len(policy_records) + 1,
                "name": name, "args": copy.deepcopy(args), "clock_before": clock,
                "clock_after": rt.world.clock, "operations": operations,
                "outcome": {"event": "return", "result": copy.deepcopy(value)},
                "interventions": copy.deepcopy(self.interventions)})
            return value

    class CachedFixtureClient:
        protocol, model, max_output_tokens, temperature = "chat", "invented-local-model", 512, 0.2
        count = 0

        def complete(self, system, conversation, tools):
            self.count += 1
            self.prefix = model / f"{self.count:04d}"
            write(str(self.prefix) + "-native-input.json",
                  {"system": system, "conversation": conversation, "tools": tools})
            model_rows.append({"event": "request_start", "invocation": self.count})
            turn = LLMClient._complete_chat(self, system, conversation, tools)
            write(str(self.prefix) + "-terminal.json", {"invocation": self.count, "returned": True,
                "dispatches": 1, "usage": audit._usage(self.payload),
                "native_usage_aggregate": turn.usage.as_dict()})
            model_rows.append({"event": "request_return", "invocation": self.count})
            return turn

        def _post(self, path, body):
            name, arguments = scripted[self.count - 1]
            self.payload = {"choices": [{"message": {"tool_calls": [{"id": f"fixture-{self.count}",
                "function": {"name": name, "arguments": json.dumps(arguments)}}]},
                "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 14, "completion_tokens": 7}}
            request = {**body, "seed": slot["generation_seed"]}
            Path(str(self.prefix) + "-request.bin").write_bytes(json.dumps(request, allow_nan=False).encode())
            write(str(self.prefix) + "-context.json", context_proof(request))
            raw = json.dumps(self.payload).encode()
            Path(str(self.prefix) + "-response.bin").write_bytes(raw)
            write(str(self.prefix) + "-response-meta.json", {"status": 200,
                "body_sha256": hashlib.sha256(raw).hexdigest()})
            model_rows.append({"event": "before_dispatch", "invocation": self.count, "dispatches": 1})
            return self.payload, 0.0

    monkeypatch.setattr(agent, "make_policy", lambda name, episode: RecordedPolicy(episode))
    with harness.record_runtime(runtime.append) as observed:
        result = agent.run_episode(spec, client=CachedFixtureClient())
        write(tmp_path / "world.json", {"initial": observed["initial_world"],
            "final": harness.world_state(observed["runtime"].world)})
    assert result["error"] is None
    write(tmp_path / "native-result.json", result)
    journal(tmp_path / "runtime.jsonl", runtime)
    journal(tmp_path / "policy.jsonl", policy_records)
    journal(tmp_path / "policy-evidence.jsonl", policy_evidence)
    journal(model / "model-calls.jsonl", model_rows)
    seal(tmp_path)
    return tmp_path, slot


@pytest.mark.parametrize("invented_episode", ["guard", "obligation_shield", "no_unkeyed_repeat"], indirect=True)
def test_full_native_scripted_physical_replay(invented_episode):
    directory, slot = invented_episode
    row = audit.audit_episode(directory, slot)
    assert row["passed"] and row["grade_available"] and row["normal_execution_return"]
    assert row["model_dispatches"] == 3
    assert row["usage"]["input_tokens"] == {"known_total": 42, "unknown_invocations": 0, "complete": True}
    assert row["scope"]["independent_native_physical_replay"]
    assert not row["scope"]["independent_measured_policy_execution"]
    assert not row["scope"]["independent_template_or_tokenizer_reconstruction"]
    if slot["arm"] != "no_unkeyed_repeat":
        assert row["work"]["verify"] >= 1
    if slot["arm"] in ("obligation_shield", "no_unkeyed_repeat"):
        assert row["certificate_count"] == 2


@pytest.mark.parametrize("target", ["grade", "world", "operation", "proposal", "wire", "intervention"])
def test_resealed_scientific_tampering_fails_physical_replay(invented_episode, target):
    directory, slot = invented_episode
    if target == "grade":
        path = directory / "native-result.json"
        value = audit.load(path)
        value["grade"]["EOS"] = not value["grade"]["EOS"]
        write(path, value)
    elif target == "world":
        path = directory / "world.json"
        value = audit.load(path)
        value["final"]["clock"] += 1
        write(path, value)
    elif target == "wire":
        path = directory / "model/0001-request.bin"
        value = audit.load(path)
        value["temperature"] = 0.0
        path.write_bytes(json.dumps(value).encode())
    else:
        path = directory / "policy.jsonl"
        rows = audit.jsonl(path)
        if target == "operation":
            rows[0]["operations"][0]["outcome"]["result"]["ok"] = True
        elif target == "proposal":
            rows[0]["args"]["text"] = "Forged proposal"
        else:
            rows[0]["interventions"] = [{"kind": "forged_earlier_intervention"}]
        journal(path, rows)
    seal(directory)
    with pytest.raises(ValueError):
        audit.audit_episode(directory, slot)


def test_checker_failure_cannot_be_swallowed_by_native_exception_handler(invented_episode):
    directory, slot = invented_episode

    def reject(*args):
        raise ValueError("Synthetic certificate input mismatch")

    with pytest.raises(ValueError, match="Policy replay validation failed"):
        audit.audit_episode(directory, slot, certificate_checker=reject)


def test_obligation_arm_refuses_missing_certificates(invented_episode):
    directory, slot = invented_episode
    slot["arm"] = slot["spec"]["policy"] = "obligation_shield"
    path = directory / "native-result.json"
    value = audit.load(path)
    value["spec"]["policy"] = "obligation_shield"
    write(path, value)
    seal(directory)
    with pytest.raises(ValueError):
        audit.audit_episode(directory, slot)


def test_audit_source_does_not_import_measured_policy_or_collector():
    source = (ROOT / "research/expanded_limbo/audit.py").read_text(encoding="utf-8")
    assert "from research.obligation_shield.policy" not in source
    assert "from .harness" not in source
    assert "from .transport" not in source
