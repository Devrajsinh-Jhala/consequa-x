"""Engineering fixtures only; never scientific benchmark scores or task targets."""

from __future__ import annotations
import json
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = Path("D:/ConsequaX-Research/limbo-pinned-2db09fba")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(NATIVE))

from research.limbo_agent import audit, harness, protocol  # noqa: E402


def metadata():
    return [
        {
            "template": "invented_template_" + str(i),
            "index": 10000 + i,
            "family": "invented_family",
            "domains": ["domain" + str(i % 6)],
            "focals": [
                {
                    "label": "invented_focal",
                    "tool": "invented_tool",
                    "domain": "domain" + str(i % 6),
                    "batch": i % 2 == 0,
                    "verification": "strong",
                    "idempotency": "non_idempotent",
                    "reversible": True,
                }
            ],
        }
        for i in range(12)
    ]


def test_schedule_complete_paired_rotating_and_deterministic():
    inputs = metadata()
    slots = protocol.make_schedule(
        inputs, world_count=24, model="invented_model", max_tool_calls=16
    )
    assert len(slots) == 96
    assert slots == protocol.make_schedule(
        list(reversed(inputs)), world_count=24, model="invented_model", max_tool_calls=16
    )
    assert len({s["spec"]["template"] for s in slots}) == 12
    assert len({s["metadata"]["domain"] for s in slots}) == 6
    for rank in range(24):
        chunk = slots[rank * 4 : rank * 4 + 4]
        assert {s["arm"] for s in chunk} == set(protocol.ARMS)
        normalized = [{k: v for k, v in s["spec"].items() if k != "policy"} for s in chunk]
        assert all(v == normalized[0] for v in normalized)
        assert all(s["spec"]["human_available"] is False for s in chunk)
    for pair in range(12):
        clean, fault = slots[pair * 8], slots[pair * 8 + 4]
        assert clean["spec"]["mode"] == "none"
        assert clean["spec"]["index"] == fault["spec"]["index"]
        assert clean["spec"]["template"] == fault["spec"]["template"]
        assert fault["spec"]["mode"] in protocol.MODES
        if fault["spec"]["mode"] == "partial_timeout":
            assert fault["metadata"]["affordances"]["batch"]
    from collections import Counter

    for position in range(4):
        assert Counter(slots[i * 4 + position]["arm"] for i in range(24)) == {
            a: 6 for a in protocol.ARMS
        }


@pytest.mark.parametrize("count", [0, 6, 12, 23, 25, 48])
def test_schedule_refuses_missing_template_pairs(count):
    with pytest.raises(ValueError):
        protocol.make_schedule(metadata(), world_count=count, model="fake", max_tool_calls=16)


@pytest.mark.parametrize(
    "mode",
    [
        "none",
        "timeout_pre",
        "timeout_post",
        "timeout_late",
        "timeout_late_tail",
        "duplicate_delivery",
    ],
)
def test_actual_runtime_nested_replay_and_late_flush(mode):
    from limbo.runtime import ToolRuntime, FaultSpec
    from limbo.services import build_tools
    from limbo.world import World
    from limbo.policies import make_policy

    def execute(record):
        w = World(12345)
        w.human_available = False
        rt = ToolRuntime(
            w, build_tools(), [] if mode == "none" else [FaultSpec(mode, "social_publish", {}, 1)]
        )
        p = make_policy("guard", "invented_episode")
        args = {"platform": "mastodon", "text": "Invented harness test announcement"}
        for _ in range(3):
            p.execute(rt, "social_publish", dict(args))
        rt.flush()
        return harness.world_state(w), rt.trace()

    events = []
    with harness.record_runtime(events.append):
        first = execute(events)
    with audit.replay_instrumentation() as observed:
        second = execute(observed)
    assert first == second
    assert events == observed["events"]
    assert any(e.get("op") == "flush" for e in events)
    if mode.startswith("timeout_late"):
        assert first[0]["deferred"] == []


def test_instrumentation_normalizes_semantically_identical_default_arguments():
    from limbo.runtime import ToolRuntime
    from limbo.services import build_tools
    from limbo.world import World

    first = []
    with harness.record_runtime(first.append):
        rt = ToolRuntime(World(1), build_tools(), [])
        rt.execute("finish", {"status": "uncertain"})
    with audit.replay_instrumentation() as second:
        rt = ToolRuntime(World(1), build_tools(), [])
        rt.execute("finish", {"status": "uncertain"}, source="agent", note="")
    assert first == second["events"]


@pytest.mark.parametrize("arm", ["guard", "conseqax_guard"])
def test_sdk_wrapper_actual_native_journal_conforms_to_original_guard(arm):
    from limbo.runtime import ToolRuntime, FaultSpec
    from limbo.services import build_tools
    from limbo.world import World
    from limbo.policies import make_policy as native_policy
    from research.limbo_agent.policy import make_policy
    from research.limbo_agent.boundary import BoundaryLimits

    actual, receipts = [], []
    args = {"platform": "mastodon", "text": "Invented public receipt test"}
    with harness.record_runtime(actual.append):
        rt = ToolRuntime(
            World(42), build_tools(), [FaultSpec("timeout_post", "social_publish", {}, 1)]
        )
        p = make_policy(
            arm, "fixture", journal=receipts.append, limits=BoundaryLimits(96, 64, 64, 172800)
        )
        for _ in range(3):
            p.execute(rt, "social_publish", dict(args))
        rt.flush()
    with audit.replay_instrumentation() as replay:
        rt = ToolRuntime(
            World(42), build_tools(), [FaultSpec("timeout_post", "social_publish", {}, 1)]
        )
        p = native_policy("guard", "fixture")
        for _ in range(3):
            p.execute(rt, "social_publish", dict(args))
        rt.flush()
    assert actual == replay["events"]
    if arm == "conseqax_guard":
        selected = [r for r in receipts if r.get("operation") == "package_receipt"]
        assert selected
        audit.audit_receipts(selected, actual, "fixture")
        altered = json.loads(json.dumps(selected))
        altered[0]["receipt"]["verification"]["origin"] = "current_action"
        with pytest.raises(ValueError):
            audit.audit_receipts(altered, actual, "fixture")


@pytest.mark.parametrize("which", ["execute", "verify", "wait"])
def test_uniform_work_caps_apply_to_native_and_replay(which):
    from limbo.runtime import ToolRuntime
    from limbo.services import build_tools
    from limbo.world import World

    limits = {"execute": 0, "verify": 0, "wait": 0, "total_wait_seconds": 0}
    logs = []

    def attempt():
        rt = ToolRuntime(World(1), build_tools(), [])
        if which == "execute":
            rt.execute("finish", {})
        elif which == "verify":
            rt.verify("social_publish", {}, 0, truth=False)
        else:
            rt.world.advance(1)

    with harness.record_runtime(logs.append, limits):
        with pytest.raises(RuntimeError):
            attempt()
    with audit.replay_instrumentation(limits) as replay:
        with pytest.raises(RuntimeError):
            attempt()
    assert logs == replay["events"]


def test_manifest_binds_nested_manifests_and_refuses_changed_bytes(tmp_path):
    child = tmp_path / "slot"
    child.mkdir()
    (child / "manifest.json").write_text("{}", encoding="utf8")
    (child / "x.txt").write_text("x", encoding="utf8")
    protocol.write_new(tmp_path / "manifest.json", harness.manifest(tmp_path))
    assert "slot/manifest.json" in audit.verify_manifest(tmp_path)
    (child / "manifest.json").write_text("{}\n", encoding="utf8")
    with pytest.raises(ValueError):
        audit.verify_manifest(tmp_path)


def test_partial_journal_unknown_not_zero(tmp_path):
    (tmp_path / "runtime.jsonl").write_bytes(b'{"event":"enter"}\n{"event":')
    observed = audit.partial_counts(tmp_path)
    assert observed["actual_work_may_exceed_valid_prefix"]
    assert observed["runtime.jsonl"]["valid_prefix_records"] == 1
    assert observed["runtime.jsonl"]["trailing_invalid"]
    assert observed["model/model-calls.jsonl"]["actual_count"] is None


def test_unavailable_planned_rows_remain_in_denominator():
    rows = [
        {
            "arm": a,
            "started": False,
            "operational": False,
            "audit_complete": False,
            "native_grade": None,
        }
        for a in protocol.ARMS
        for _ in range(24)
    ]
    result = audit.summarize(rows)
    for arm in protocol.ARMS:
        assert result[arm]["planned"] == 24
        assert result[arm]["operational_native_EOS"] == 0
        assert result[arm]["unavailable_native_grade"] == 24
        assert result[arm]["native_EOS_true_available"] == 0


def test_offline_audit_network_guard():
    import socket

    with audit.no_network(), pytest.raises(RuntimeError):
        socket.create_connection(("127.0.0.1", 11436))


@pytest.mark.parametrize(
    "alter",
    [
        "duplicate_start",
        "duplicate_dispatch",
        "missing_dispatch",
        "duplicate_terminal",
        "wrong_start_id",
        "wrong_dispatch_id",
        "wrong_terminal_id",
        "missing_terminal",
    ],
)
def test_model_journal_independent_serial_identity_checks(alter):
    events = [
        {"event": "request_start", "invocation": 1},
        {"event": "before_dispatch", "invocation": 1, "dispatches": 1},
        {"event": "request_return", "invocation": 1},
    ]
    if alter == "duplicate_start":
        events.insert(0, dict(events[0]))
    elif alter == "duplicate_dispatch":
        events.insert(1, dict(events[1]))
    elif alter == "missing_dispatch":
        events.pop(1)
    elif alter == "duplicate_terminal":
        events.append(dict(events[-1]))
    elif alter == "wrong_start_id":
        events[0]["invocation"] = 2
    elif alter == "wrong_dispatch_id":
        events[1]["invocation"] = 2
    elif alter == "wrong_terminal_id":
        events[2]["invocation"] = 2
    else:
        events.pop()
    with pytest.raises(ValueError):
        audit.validate_model_journal(events, [{"returned": True, "dispatches": 1}], 16)


def test_model_cap_refusal_is_a_separate_predispatch_attempt():
    events = [
        {"event": "request_start", "invocation": 1},
        {"event": "before_dispatch", "invocation": 1, "dispatches": 1},
        {"event": "request_return", "invocation": 1},
        {"event": "request_start", "invocation": 2},
        {"event": "request_error", "invocation": 2},
    ]
    audit.validate_model_journal(
        events, [{"returned": True, "dispatches": 1}, {"returned": False, "dispatches": 0}], 1
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"{malformed",
        b"[]",
        b'{"choices": [], "usage": {"prompt_tokens": 12}}',
        b'{"choices": [], "usage": "malformed usage"}',
    ],
)
def test_failed_200_responses_retain_raw_identity_and_known_or_unknown_usage(tmp_path, raw):
    registered = {
        "runtime_binding": {"model": "fake-local", "context_tokens": 8192},
        "limits": {"max_output_tokens": 512},
        "seed": 1701,
    }
    native = {"system": "Invented fixture", "conversation": [], "tools": []}
    wire = json.dumps(
        {
            "model": "fake-local",
            "messages": [{"role": "system", "content": native["system"]}],
            "tools": [],
            "max_tokens": 512,
            "temperature": 0,
            "seed": 1701,
        },
        allow_nan=False,
    ).encode()
    prefix = tmp_path / "0001"
    protocol.write_new(str(prefix) + "-native-input.json", native)
    Path(str(prefix) + "-request.bin").write_bytes(wire)
    prompt = "Invented synthetic gate"
    protocol.write_new(
        str(prefix) + "-context.json",
        {
            "request": json.loads(wire),
            "passed": True,
            "same_rendered_bytes": True,
            "same_token_ids": True,
            "runtime_binding": registered["runtime_binding"],
            "offline_rendered_prompt": prompt,
            "server_preview": {"_debug_info": {"rendered_template": prompt}},
            "runtime_tokenizer": {"tokens": [1]},
            "offline_context": {
                "prompt_tokens": 1,
                "required_tokens": 577,
                "context_tokens": 8192,
                "fits": True,
                "truncation_requested": False,
                "rendered_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            },
        },
    )
    Path(str(prefix) + "-response.bin").write_bytes(raw)
    protocol.write_new(
        str(prefix) + "-response-meta.json",
        {"status": 200, "body_sha256": hashlib.sha256(raw).hexdigest()},
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    usage = None
    if isinstance(payload, dict):
        value = (
            (payload.get("usage") or {}).get("prompt_tokens")
            if isinstance(payload.get("usage"), dict)
            else None
        )
        usage = {
            name: {"available": False, "value": None}
            for name in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens")
        }
        if value is not None:
            usage["input_tokens"] = {"available": True, "value": value}
    terminal = {"invocation": 1, "dispatches": 1, "returned": False, "usage": usage}
    protocol.write_new(str(prefix) + "-terminal.json", terminal)
    turn, saved = audit.audit_model_call(tmp_path, 1, native, registered)
    assert turn is None and saved == terminal


@pytest.mark.parametrize("arm", ["vanilla", "sdk_retry3", "guard", "conseqax_guard"])
def test_full_saved_native_episode_replay_with_invented_task_and_offline_responses(
    tmp_path, monkeypatch, arm
):
    """All data invented here. Context proof is a synthetic consistency fixture."""
    from limbo import agent
    from limbo.tasks import TaskInstance, Focal, Target
    from limbo.llm import LLMClient
    from research.limbo_agent.policy import make_policy
    from research.limbo_agent.boundary import BoundaryLimits

    instruction = "Publish the invented replay fixture announcement once."
    task = TaskInstance(
        "invented",
        "invented",
        "invented",
        instruction,
        ["social"],
        [Target("post", {"platform": "mastodon", "tokens": ["invented", "replay"]})],
        [Focal("fixture", "social_publish", {}, "non_idempotent", "strong", True)],
        lambda world: None,
    )
    monkeypatch.setattr(agent, "make_task", lambda *args: task)
    spec = agent.EpisodeSpec(
        "invented",
        0,
        "fixture",
        "timeout_post",
        "fake-local",
        policy=arm,
        human_available=False,
        max_tool_calls=16,
    )
    limits = {
        "max_requests": 16,
        "max_output_tokens": 512,
        "request_timeout_s": 1200,
        "episode_timeout_s": 7200,
        "work": {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800},
    }
    registered = {
        "runtime_binding": {"model": "fake-local", "context_tokens": 8192},
        "limits": limits,
        "seed": 1701,
    }
    model = tmp_path / "model"
    model.mkdir()
    runtime, framework, model_journal = [], [], []
    calls = [
        ("social_publish", {"platform": "mastodon", "text": "Invented replay fixture"}),
        ("social_publish", {"platform": "mastodon", "text": "Invented replay fixture"}),
        ("finish", {"status": "completed"}),
    ]

    def write(path, value):
        protocol.write_new(path, value)

    class FixtureClient:
        protocol = "chat"
        model = "fake-local"
        max_output_tokens = 512
        temperature = 0
        count = 0

        def complete(self, system, conversation, tools):
            self.count += 1
            prefix = model / f"{self.count:04d}"
            self.prefix = prefix
            write(
                str(prefix) + "-native-input.json",
                {"system": system, "conversation": conversation, "tools": tools},
            )
            model_journal.append({"event": "request_start", "invocation": self.count})
            turn = LLMClient._complete_chat(self, system, conversation, tools)
            usage = {
                name: {"available": False, "value": None}
                for name in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens")
            }
            write(
                str(prefix) + "-terminal.json",
                {"invocation": self.count, "returned": True, "dispatches": 1, "usage": usage},
            )
            model_journal.append({"event": "request_return", "invocation": self.count})
            return turn

        def _post(self, path, body):
            name, args = calls[self.count - 1]
            payload = {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "fixture-" + str(self.count),
                                    "function": {"name": name, "arguments": json.dumps(args)},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
            wire = json.dumps({**body, "seed": 1701}, allow_nan=False).encode()
            Path(str(self.prefix) + "-request.bin").write_bytes(wire)
            prompt = "Invented synthetic rendering fixture"
            write(
                str(self.prefix) + "-context.json",
                {
                    "request": json.loads(wire),
                    "passed": True,
                    "same_rendered_bytes": True,
                    "same_token_ids": True,
                    "runtime_binding": registered["runtime_binding"],
                    "offline_rendered_prompt": prompt,
                    "server_preview": {"_debug_info": {"rendered_template": prompt}},
                    "runtime_tokenizer": {"tokens": [123]},
                    "offline_context": {
                        "prompt_tokens": 1,
                        "rendered_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "required_tokens": 577,
                        "context_tokens": 8192,
                        "fits": True,
                        "truncation_requested": False,
                    },
                },
            )
            raw = json.dumps(payload).encode()
            Path(str(self.prefix) + "-response.bin").write_bytes(raw)
            write(
                str(self.prefix) + "-response-meta.json",
                {"status": 200, "body_sha256": hashlib.sha256(raw).hexdigest()},
            )
            model_journal.append(
                {"event": "before_dispatch", "invocation": self.count, "dispatches": 1}
            )
            return payload, 0.0

    monkeypatch.setattr(
        agent,
        "make_policy",
        lambda name, episode: make_policy(
            name, episode, journal=framework.append, limits=BoundaryLimits(96, 64, 64, 172800)
        ),
    )
    with harness.record_runtime(runtime.append) as state:
        result = agent.run_episode(spec, client=FixtureClient())
        write(
            tmp_path / "world.json",
            {
                "initial": state["initial_world"],
                "final": harness.world_state(state["runtime"].world),
            },
        )
    write(tmp_path / "native-result.json", result)
    write(tmp_path / "parent-terminal.json", {"status": "child_returned", "exit_code": 0})
    write(tmp_path / "worker-terminal.json", {"status": "native_returned"})
    for filename, records in (
        ("runtime.jsonl", runtime),
        ("framework.jsonl", framework),
        ("model/model-calls.jsonl", model_journal),
    ):
        (tmp_path / filename).write_text(
            "".join(json.dumps(row) + "\n" for row in records), encoding="utf8"
        )
    write(tmp_path / "manifest.json", harness.manifest(tmp_path))
    with audit.no_network():
        audited = audit.audit_episode(
            tmp_path, {"slot": 0, "world_rank": 0, "arm": arm, "spec": asdict(spec)}, registered
        )
    assert audited["audit_complete"] and audited["grade_available"] and audited["operational"]
    assert audited["usage"]["input_tokens"]["unknown_invocations"] == 3
    assert (
        audited["receipt_count"] >= 1 if arm == "conseqax_guard" else audited["receipt_count"] == 0
    )
