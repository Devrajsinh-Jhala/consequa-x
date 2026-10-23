"""Zero-inference SDK path validation on two fresh excluded native worlds.

The first saved public dispatch from an independently audited development run
is proposed twice to each policy. The second proposal is explicitly scripted
for path coverage; this is not an autonomous episode or a performance result.
No target predicate chooses an action and no native task grade is computed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.limbo_agent import audit, harness, protocol  # noqa: E402
from research.limbo_agent.boundary import BoundaryLimits  # noqa: E402
from research.limbo_agent.policy import NativeReceiptPolicy, audit_framework_wheel  # noqa: E402


SCHEMA = "conseqax-limbo-saved-proposal-receipt-v1"
AMENDMENT = "docs/limbo-readiness-amendment-2026-10-24.md"
PARITY_FIELDS = ("observations", "interventions", "runtime_events", "initial_world",
                 "after_each_step_world", "final_world", "final_rng", "final_ledger",
                 "public_receipt_mapping")


def select_saved_proposal(events):
    """Only original public dispatch data; never inspect task targets or grades."""
    for line_number, event in enumerate(events, 1):
        if event.get("event") != "enter" or event.get("op") != "execute":
            continue
        args = event.get("args")
        audit.require(type(args) is list and len(args) == 2 and type(args[0]) is str
                      and type(args[1]) is dict, "Saved public execute has an invalid shape")
        audit.require(event.get("parent") is None and event.get("kwargs", {}).get("source") == "agent",
                      "First public dispatch is not the original agent proposal")
        return {"journal": "runtime.jsonl", "line_number": line_number,
                "event_id": event["id"], "name": args[0], "arguments": copy.deepcopy(args[1]),
                "selection": "First saved public execute; no task target, reward or later proposal used"}
    raise ValueError("Audited development run has no original public execute proposal")


def validate_inputs(root, native_root, wheel, development, development_audit):
    root, native_root = Path(root).resolve(), Path(native_root).resolve()
    development, wheel = Path(development).resolve(), Path(wheel).resolve()
    development_audit = Path(development_audit).resolve()
    if development_audit.is_dir():
        development_audit /= "audit-result.json"
    amendment = root / AMENDMENT
    audit.require(amendment.is_file(), "Prospective receipt-path amendment must exist before this fixture")
    source_inventory = audit.verify_manifest(development)
    audit.verify_manifest(development_audit.parent)
    config = audit.load(development / "worker-config.json")
    value = audit.load(development_audit)
    frozen, slot = config["protocol"], config["slot"]
    audit.require(value.get("schema") == "conseqax-limbo-development-audit-v1"
                  and value.get("passed") is True, "Passed complete native development audit is required")
    audit.require(Path(value["episode"]).resolve() == development, "Development audit episode path differs")
    audit.same(value["episode_manifest"], protocol.file_binding(development / "manifest.json"),
               "Audited source episode manifest changed")
    audit.same(value["sources"], frozen["sources"], "Source audit scientific bindings differ")
    audit.same(value["native"], frozen["native"], "Source audit native bindings differ")
    audit.same(value["spec"], slot["spec"], "Source audit native spec differs")
    row = value["row"]
    for key in ("started", "operational", "audit_complete", "grade_available", "execution_success"):
        audit.require(row.get(key) is True, "Source audit lacks a complete normal native return: " + key)
    audit.require(row.get("fault_triggered") is True and row.get("status") == "audited_native_return",
                  "Source native fault did not trigger or execution did not return normally")
    audit.same([row[key] for key in ("slot", "world_rank", "arm")],
               [slot[key] for key in ("slot", "world_rank", "arm")], "Source audit slot identity differs")
    spec = slot["spec"]
    audit.require(spec["policy"] == slot["arm"] == "conseqax_guard" and spec["index"] in (0, 1)
                  and spec["mode"] != "none" and spec["human_available"] is False,
                  "Fixture requires the excluded guarded no-human fault development spec")
    audit.same(frozen["sources"], protocol.source_binding(root), "Current measured source inventory changed")
    protocol.verify_files(root, frozen["sources"])
    audit.same(frozen["native"], protocol.native_binding(native_root), "Pinned native source changed")
    audit.same(frozen["environment"], protocol.environment_binding(), "Interpreter/dependency environment changed")
    expected_wheel = {key: frozen["wheel"][key] for key in ("sha256", "bytes")}
    audit.same(protocol.file_binding(wheel), expected_wheel, "Selected wheel bytes changed")
    audit.require(wheel == Path(frozen["wheel"]["path"]).resolve(), "Selected wheel path differs")
    installed = audit_framework_wheel(wheel)
    audit.same(audit.load(development / "installed-wheel.json"), installed,
               "Installed framework payload differs from audited development execution")
    proposal = select_saved_proposal(audit.jsonl(development / "runtime.jsonl"))
    return frozen, spec, proposal, installed, {
        "source_episode": {"path": str(development),
            "manifest": protocol.file_binding(development / "manifest.json"),
            "worker_config": protocol.file_binding(development / "worker-config.json"),
            "runtime_journal": protocol.file_binding(development / "runtime.jsonl"),
            "inventory_files": len(source_inventory)},
        "source_audit": {"path": str(development_audit), **protocol.file_binding(development_audit),
            "manifest": protocol.file_binding(development_audit.parent / "manifest.json")},
        "amendment": {"path": str(amendment), **protocol.file_binding(amendment)}}


@contextmanager
def forbid_inference_and_grading():
    """Fail, rather than silently call a model, autonomous runner, or task grader."""
    from limbo import agent, grader, llm
    counts = {"model_constructor_attempts": 0, "native_episode_attempts": 0, "task_grade_attempts": 0}
    originals = (llm.LLMClient.__init__, agent.run_episode, grader.grade, agent.grade)
    def refuse_constructor(*_args, **_kwargs):
        counts["model_constructor_attempts"] += 1
        raise RuntimeError("Model clients are forbidden in this zero-inference fixture")
    def refuse_episode(*_args, **_kwargs):
        counts["native_episode_attempts"] += 1
        raise RuntimeError("Autonomous episodes are forbidden in this scripted path fixture")
    def refuse_grade(*_args, **_kwargs):
        counts["task_grade_attempts"] += 1
        raise RuntimeError("Task grading is forbidden in this scripted path fixture")
    llm.LLMClient.__init__, agent.run_episode = refuse_constructor, refuse_episode
    grader.grade = agent.grade = refuse_grade
    try:
        yield counts
    finally:
        llm.LLMClient.__init__, agent.run_episode, grader.grade, agent.grade = originals


def fresh_runtime(spec):
    """Exact unchanged run_episode construction, without prompts/model/targets/grader."""
    from limbo.agent import EpisodeSpec
    from limbo.runtime import FaultSpec, ToolRuntime
    from limbo.services import build_tools
    from limbo.tasks import make_task
    from limbo.world import World
    value = EpisodeSpec(**spec)
    task = make_task(value.template, value.index, value.instruction_variant)
    world = World(seed=value.world_seed)
    task.setup(world)
    world.human_available = value.human_available
    world.keys_everywhere = value.contract == "keys_everywhere"
    tools = build_tools(value.contract)
    focal = next(item for item in task.focals if item.label == value.focal)
    faults = [] if value.mode == "none" else [FaultSpec(value.mode, focal.tool, focal.match, 1)]
    return ToolRuntime(world, tools, faults), value.episode_id


def execute_arm(output, spec, proposal, work_limits, *, package):
    from limbo.policies import make_policy
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    runtime_journal = harness.Journal(output / "runtime.jsonl")
    framework_journal = harness.Journal(output / "framework.jsonl")
    try:
        with harness.record_runtime(runtime_journal, work_limits) as state:
            rt, episode_id = fresh_runtime(spec)
            audit.require(proposal["name"] in rt.tools and rt.tools[proposal["name"]].contract.write,
                          "The first saved public dispatch is not a mutation")
            policy = (NativeReceiptPolicy(episode_id, journal=framework_journal,
                      limits=BoundaryLimits(**work_limits)) if package else make_policy("guard", episode_id))
            observations, steps, intervention_steps = [], [], []
            for _ in range(2):
                observations.append(harness.plain(policy.execute(rt, proposal["name"], copy.deepcopy(proposal["arguments"]))))
                steps.append(harness.world_state(rt.world))
                intervention_steps.append(harness.plain(policy.interventions))
            rt.flush()
            result = {"episode_id": episode_id, "observations": observations,
                "interventions": harness.plain(policy.interventions),
                "interventions_after_each_step": intervention_steps,
                "initial_world": state["initial_world"], "after_each_step_world": steps,
                "final_world": harness.world_state(rt.world),
                "final_rng": harness.plain(rt.world.rng.getstate()),
                "final_ledger": harness.plain(rt.world.ledger),
                "native_tool_events": harness.plain(rt.trace()),
                "fault_log": harness.plain(rt.fault_log), "fault_triggered": bool(rt.fault_log),
                "finished": harness.plain(rt.finished), "escalations": harness.plain(rt.escalations)}
        protocol.write_new(output / "state.json", result)
    finally:
        runtime_journal.close()
        framework_journal.close()
    result["runtime_events"] = audit.jsonl(output / "runtime.jsonl")
    result["framework_events"] = audit.jsonl(output / "framework.jsonl")
    return result


def compare_arms(reference, package):
    audit.same(reference["episode_id"], package["episode_id"], "Policy episode identities differ")
    fields = ("observations", "interventions", "runtime_events", "initial_world",
              "after_each_step_world", "final_world", "final_rng", "final_ledger",
              "interventions_after_each_step", "native_tool_events", "fault_log", "finished", "escalations")
    for key in fields:
        audit.same(reference[key], package[key], "Native/SDK path differs: " + key)
    audit.require(reference["fault_triggered"] is True and package["fault_triggered"] is True,
                  "Saved public proposal did not trigger the native fault on both fresh worlds")
    receipts = [row for row in package["framework_events"] if row.get("operation") == "package_receipt"]
    audit.require(bool(receipts), "Scripted identical reissue did not exercise a real SDK receipt")
    audit.require(not reference["framework_events"], "Original native guard unexpectedly used the SDK journal")
    audit.audit_receipts(receipts, package["runtime_events"], package["episode_id"])
    for row in receipts:
        audit.require(row["receipt"]["verification"]["origin"] == "unknown", "Receipt overclaims action origin")
    return len(receipts), {key: True for key in PARITY_FIELDS}


def run(native_root, wheel, development, development_audit, output, *, root=ROOT):
    root = Path(root).resolve()
    frozen, spec, proposal, installed, inputs = validate_inputs(
        root, native_root, wheel, development, development_audit)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(native_root).resolve()))
    try:
        with audit.no_network(), forbid_inference_and_grading() as forbidden:
            reference = execute_arm(output / "native_guard", spec, proposal, frozen["limits"]["work"], package=False)
            package = execute_arm(output / "conseqax_guard", spec, proposal, frozen["limits"]["work"], package=True)
            receipts, parity = compare_arms(reference, package)
            source_initial = audit.load(Path(development) / "world.json")["initial"]
            audit.same(source_initial, reference["initial_world"], "Fresh fixture world differs from original source initial world")
        audit.require(all(value == 0 for value in forbidden.values()), "Forbidden inference/grading path was attempted")
        protocol.verify_files(root, frozen["sources"])
        protocol.verify_files(native_root, frozen["native"]["files"])
        audit_framework_wheel(wheel)
        audit.verify_manifest(development)
        audit.verify_manifest(Path(development_audit).parent if Path(development_audit).is_file() else development_audit)
        audit.same(protocol.file_binding(Path(development) / "manifest.json"), inputs["source_episode"]["manifest"],
                   "Source episode changed during fixture")
        audit.same(protocol.file_binding(inputs["source_audit"]["path"]),
                   {key: inputs["source_audit"][key] for key in ("sha256", "bytes")},
                   "Source audit changed during fixture")
        proof = {"schema": SCHEMA, "passed": True, "utc": protocol.utc(), **inputs,
            "sources": frozen["sources"], "native": frozen["native"],
            "wheel": {"path": str(Path(wheel).resolve()), **protocol.file_binding(wheel)},
            "wheel_file": {"path": str(Path(wheel).resolve()), **protocol.file_binding(wheel)},
            "installed_wheel": installed, "development_spec": spec,
            "selected_proposal": proposal, "receipt_count": receipts, "fault_triggered": True,
            "parity": parity, "model_generations": 0, "model_client_instantiated": False,
            "scripted_second_identical_proposal": True, "native_task_grade_computed": False,
            "native_episode_performance_trial": False, "network_forbidden": True,
            "forbidden_path_attempts": forbidden,
            "fixture_sources": {"scripts/check_limbo_saved_proposal_receipt.py": protocol.file_binding(__file__)},
            "scope": "Deterministic path coverage only: two public proposals on fresh excluded worlds; no autonomous model performance, no independent algorithm, no production durability or causal-origin claim"}
        sources = output / "sources"
        sources.mkdir()
        (sources / "check_limbo_saved_proposal_receipt.py").write_bytes(Path(__file__).read_bytes())
        protocol.write_new(output / "selected-proposal.json", proposal)
        protocol.write_new(output / "proof.json", proof)
    except BaseException as exc:
        protocol.write_new(output / "failure.json", {"schema": SCHEMA, "passed": False,
            "utc": protocol.utc(), "error": type(exc).__name__ + ": " + str(exc),
            "traceback": traceback.format_exc(limit=8), "scope": "No replacement or model retry"})
        raise
    finally:
        protocol.write_new(output / "manifest.json", harness.manifest(output))
        sys.path.remove(str(Path(native_root).resolve()))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--development", required=True, type=Path)
    parser.add_argument("--development-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    proof = run(args.native_root, args.wheel, args.development, args.development_audit, args.output)
    print(json.dumps({"passed": proof["passed"], "receipt_count": proof["receipt_count"],
                      "model_generations": proof["model_generations"], "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
