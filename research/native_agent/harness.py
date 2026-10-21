"""Observed native execution, with no reference actions in policy inputs.

The native builder, orchestration loop, tools and ALL reward evaluator are used
unchanged. The live environment observer records evaluator-only hashes/results;
it never supplies privileged state to an agent or user.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import traceback


def utc():
    return datetime.now(timezone.utc).isoformat()


def jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"Non-JSON journal value: {type(value).__name__}")


def dump_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(jsonable(value), stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


class Journal:
    def __init__(self, path):
        self.stream = Path(path).open("x", encoding="utf-8", newline="\n")
        self.count = 0

    def append(self, value):
        captured = jsonable(value)
        if not isinstance(captured, dict) or {"event_index", "recorded_utc"} & set(captured):
            raise ValueError("Journal records cannot replace reserved metadata")
        row = {"event_index": self.count, "recorded_utc": utc(), **captured}
        self.stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()
        self.count += 1

    def close(self):
        self.stream.close()


def hashes(environment):
    return {"agent_db_hash": environment.get_db_hash(),
            "user_db_hash": environment.get_user_db_hash()}


def db_snapshot(environment):
    """Evaluator-only capture. Never passed to a policy, receipt or user."""
    result = {}
    for label, toolkit in (("agent", environment.tools), ("user", environment.user_tools)):
        db = getattr(toolkit, "db", None) if toolkit is not None else None
        result[label] = jsonable(db) if db is not None else None
    return result


def observe_environment(environment, journal, start_journal=None):
    original = environment.make_tool_call
    state = {"phase": "initialization", "call_index": 0, "completed": 0, "inflight": []}

    def observed(tool_name, requestor="assistant", **arguments):
        before = hashes(environment)
        started = time.monotonic()
        request = jsonable({"tool_name": tool_name, "requestor": requestor, "arguments": arguments})
        call = state["call_index"]
        if start_journal is not None:
            start_journal.append({"schema": "native-tool-dispatch-start-v1", "call_index": call,
                "phase": state["phase"], "request": request, "before": before})
        state["call_index"] += 1
        state["inflight"].append(call)
        try:
            result = original(tool_name, requestor=requestor, **arguments)
        except BaseException as exc:
            journal.append({"schema": "native-tool-dispatch-v1", "call_index": call,
                "phase": state["phase"], "request": request, "before": before,
                "outcome": {"status": "raised", "error_type": type(exc).__name__, "error": str(exc)},
                "after": hashes(environment), "wall_seconds": time.monotonic() - started})
            state["completed"] += 1
            state["inflight"].remove(call)
            raise
        journal.append({"schema": "native-tool-dispatch-v1", "call_index": call,
            "phase": state["phase"], "request": request, "before": before,
            "outcome": {"status": "returned", "content": environment.to_json_str(result)},
            "after": hashes(environment), "wall_seconds": time.monotonic() - started})
        state["completed"] += 1
        state["inflight"].remove(call)
        return result

    environment.make_tool_call = observed
    return state


class RequestBudgetExceeded(RuntimeError):
    pass


def record_completions(module, journal, maximum, *, invoke_scope=None):
    """Count actual completion invocations, including errors; no corrective retry."""
    if type(maximum) is not int or maximum < 1:
        raise ValueError("Completion budget must be a positive integer")
    original = module.completion
    state = {"attempted": 0, "completed": 0, "failed": 0,
             "provider_invoked": 0, "provider_returned": 0, "refused_before_provider": 0,
             "usage_unavailable": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def completion(*args, **kwargs):
        if state["attempted"] >= maximum:
            journal.append({"kind": "request_budget_exhausted", "maximum": maximum})
            raise RequestBudgetExceeded("Frozen assistant+user attempted-request ceiling exhausted")
        call = state["attempted"]
        state["attempted"] += 1
        started = time.monotonic()
        invoked = False
        try:
            public = {k: v for k, v in kwargs.items() if k.lower() not in {"api_key", "authorization"}}
            journal.append({"kind": "request_start", "call_index": call, "request": public,
                            "positional_argument_count": len(args)})
            if args:
                raise RuntimeError("Native completion arguments must be explicit keywords")
            if type(kwargs.get("num_retries")) is not int or kwargs["num_retries"] != 0:
                raise RuntimeError("Native completion retries must be explicitly zero")
            with invoke_scope(public) if invoke_scope is not None else nullcontext():
                invoked = True
                state["provider_invoked"] += 1
                response = original(**kwargs)
            state["provider_returned"] += 1
            payload = jsonable(response.to_dict())
            if not isinstance(payload, dict):
                raise TypeError("Native completion response must serialize to an object")
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                usage = {}
            tokens = {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens")}
            if not all(type(value) is int and value >= 0 for value in tokens.values()):
                state["usage_unavailable"] += 1
            journal.append({"kind": "request_return", "call_index": call, "response": payload,
                            "wall_seconds": time.monotonic() - started})
        except BaseException as exc:
            state["failed"] += 1
            if not invoked:
                state["refused_before_provider"] += 1
            journal.append({"kind": "request_error", "call_index": call,
                "error_type": type(exc).__name__, "error": str(exc),
                "wall_seconds": time.monotonic() - started})
            raise
        for key, value in tokens.items():
            if type(value) is int and value >= 0:
                state[key] += value
        state["completed"] += 1
        return response

    module.completion = completion
    return state


def run_episode(*, native_root, output, task_id, arm, episode_id, seed, guard,
                context_gate, max_requests=48, max_steps=80, timeout_seconds=3600,
                request_timeout_seconds=600):
    """Call only inside the configured, active local-only guard and source pin.

    The supplied context gate must already be installed on actual HTTP sends.
    A separate parent enforces a hard process deadline. This function retains a
    native run only if the unchanged runner returned one; exceptions do not get
    invented rewards, tool responses, annotations or successful trajectories.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    journals, state, orchestrator, llm_utils, original_completion = {}, None, None, None, None
    original_context_sink = getattr(context_gate, "on_receipt", None)
    original_scope_requirement = getattr(guard, "require_native_invocation", None)
    scope_requirement_changed = False
    phase = {"call_index": 0, "completed": 0, "inflight": []}
    status, error, stage, capture_errors = "failed", None, "startup", []

    def capture(name, callback):
        try:
            dump_new(output / name, callback())
        except BaseException as exc:
            capture_errors.append({"artifact": name, "error_type": type(exc).__name__, "error": str(exc)})

    try:
        # Check before importing provider-dependent native modules. A non-null
        # gate alone does not establish that actual HTTP sends use that gate.
        if (not getattr(guard, "active", False) or context_gate is None
                or getattr(guard, "before_generation", None) is not context_gate
                or getattr(context_gate, "guard", None) is not guard
                or not callable(getattr(guard, "native_invocation", None))):
            raise RuntimeError("Active local-only guard and installed exact context gate required")
        guard.require_native_invocation = True
        scope_requirement_changed = True
        from research.native_agent.transport import LITELLM_MODEL, local_model_kwargs

        # Bind the native provider to the listener actually allowed by this
        # guard. An isolated-server run must never silently use normal Ollama.
        kwargs = local_model_kwargs(max_tokens=512, seed=seed, timeout=request_timeout_seconds,
                                    api_base=getattr(guard, "api_base", None))
        for name in ("model-calls", "tool-dispatch", "tool-dispatch-starts", "controller-events", "context-events"):
            journals[name] = Journal(output / f"{name}.jsonl")

        def context_pass(receipt):
            journals["context-events"].append({"kind": "context_gate_result", "receipt": receipt})
            if original_context_sink is not None:
                original_context_sink(receipt)

        context_gate.on_receipt = context_pass
        import tau2

        native_origin = Path(native_root).resolve() / "src" / "tau2" / "__init__.py"
        if Path(tau2.__file__).resolve() != native_origin:
            raise RuntimeError("Native package import is outside the pinned upstream source")
        from tau2.data_model.simulation import TextRunConfig
        from tau2.data_model.tasks import Task
        from tau2.evaluator.evaluator import EvaluationType
        from tau2.registry import registry
        from tau2.runner.build import build_text_orchestrator
        from tau2.runner.simulation import run_simulation
        from tau2.utils import llm_utils
        from research.native_agent.controller import make_agent_factory

        original_completion = llm_utils.completion
        state = record_completions(llm_utils, journals["model-calls"], max_requests,
                                   invoke_scope=guard.native_invocation)
        # Process-local configuration only: do not use cached model outputs.
        llm_utils.litellm.cache = None
        tasks = json.loads((Path(native_root) / "data/tau2/domains/airline/tasks.json").read_text(encoding="utf-8"))
        matching = [task for task in tasks if str(task["id"]) == str(task_id)]
        if len(matching) != 1:
            raise ValueError("Native task ID must identify exactly one task")
        task = Task.model_validate(matching[0])
        required_basis = [getattr(item, "value", str(item))
                          for item in task.evaluation_criteria.reward_basis]
        if len(required_basis) != 2 or set(required_basis) != {"DB", "COMMUNICATE"}:
            raise RuntimeError("Frozen airline execution requires exactly DB and COMMUNICATE reward basis")
        framework_identity = None
        if arm in {"R", "G"}:
            # Metadata/spec inspection does not import the framework into B/C.
            # Version alone would allow a checkout to shadow installed 2.1.1.
            from importlib import metadata, util

            distribution = metadata.distribution("consequa-x")
            spec = util.find_spec("consequa_x")
            installed = Path(distribution.locate_file("consequa_x/__init__.py")).resolve()
            if (distribution.version != "2.1.1" or spec is None or not spec.origin
                    or Path(spec.origin).resolve() != installed):
                raise RuntimeError("Research policy requires the installed ConseqaX 2.1.1 package")
            framework_identity = {"version": distribution.version, "module_origin": str(installed)}
        # The official task goes only to native initialization, native user
        # construction and native evaluator. The research factory ignores task.
        agent_name = "llm_agent"
        if arm != "native":
            agent_name = "conseqax_research_" + arm + "_" + hashlib.sha256(episode_id.encode()).hexdigest()[:16]
            registry.register_agent_factory(make_agent_factory(arm, episode_id,
                event_sink=journals["controller-events"].append), name=agent_name)
        config = TextRunConfig(domain="airline", agent=agent_name, user="user_simulator",
            llm_agent=LITELLM_MODEL, llm_user=LITELLM_MODEL,
            llm_args_agent=dict(kwargs), llm_args_user=dict(kwargs), num_trials=1,
            max_steps=max_steps, max_errors=5, max_concurrency=1, workers=0,
            max_retries=0, auto_resume=False, auto_review=False,
            hallucination_retries=0, timeout=timeout_seconds, seed=seed,
            enforce_communication_protocol=False, verbose_logs=False)
        dump_new(output / "configuration.json", {"episode_id": episode_id, "task_id": str(task_id),
            "arm": arm, "config": config.model_dump(mode="json"), "maximum_attempted_requests": max_requests,
            "required_reward_basis": required_basis, "native_module_origin": str(native_origin),
            "framework_identity": framework_identity,
            "evaluation_type": "ALL", "native_strict_replay": True,
            "task_object_not_supplied_to_research_policy": True})
        orchestrator = build_text_orchestrator(config, task, seed=seed, simulation_id=episode_id)
        phase = observe_environment(orchestrator.environment, journals["tool-dispatch"],
                                    journals["tool-dispatch-starts"])
        initialize = orchestrator.initialize

        def initialized():
            initialize()
            phase["phase"] = "episode"
            dump_new(output / "episode-start.json", {"hashes": hashes(orchestrator.environment),
                "initialization_dispatches": phase["call_index"],
                "initial_history_messages": len(task.initial_state.message_history or [])
                    if task.initial_state is not None else 0})
            dump_new(output / "initial-db.evaluator-only.json", db_snapshot(orchestrator.environment))

        orchestrator.initialize = initialized
        dump_new(output / "startup-receipt.json", {"status": "prepared", "episode_id": episode_id,
            "arm": arm, "guard_verified_before_native_imports": True, "context_gate_installed": True})
        stage = "execution"
        simulation = run_simulation(orchestrator, evaluation_type=EvaluationType.ALL)
        dump_new(output / "native-simulation.json", simulation.model_dump(mode="json"))
        status = "native_returned"
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        capture("execution-error.json", lambda: {"stage": stage, **error})
        if stage == "startup":
            capture("startup-failure.json", lambda: {"status": "failed", "episode_id": episode_id, **error})
        if orchestrator is not None:
            capture("partial-native-messages.json", lambda: {
                "messages": [message.model_dump(mode="json") for message in orchestrator.get_messages()]})
    finally:
        if scope_requirement_changed:
            guard.require_native_invocation = original_scope_requirement
        if context_gate is not None:
            context_gate.on_receipt = original_context_sink
        if llm_utils is not None and original_completion is not None:
            llm_utils.completion = original_completion
        if orchestrator is not None:
            capture("final-state.json", lambda: {"hashes": hashes(orchestrator.environment),
                "hash_boundary": "after native runner return or failure capture"})
            capture("final-db.evaluator-only.json", lambda: db_snapshot(orchestrator.environment))
        capture("network-guard.json", lambda: {"events": getattr(guard, "events", []),
            "scope": "Process-local Python/HTTP defense, not an OS firewall for arbitrary native code"})
        capture("context-checks.json", lambda: {"checks": getattr(context_gate, "receipts", [])})
        for journal in journals.values():
            try:
                journal.close()
            except BaseException as exc:
                capture_errors.append({"artifact": "journal-close", "error_type": type(exc).__name__, "error": str(exc)})
        if capture_errors:
            status = "capture_failed"
        # This independent final record is attempted even after a failed DB
        # snapshot or journal closure. Original captures are never overwritten.
        dump_new(output / "execution-receipt.json", {"status": status, "episode_id": episode_id,
            "task_id": str(task_id), "arm": arm, "stage": stage,
            "wall_seconds": time.monotonic() - started, "model_requests": state,
            "actual_tool_dispatches": phase["call_index"], "completed_tool_dispatches": phase["completed"],
            "inflight_tool_dispatches": phase["inflight"], "capture_errors": capture_errors,
            "error_type": error["type"] if error else None,
            "native_reward_not_fabricated": True, "corrective_reruns": 0})
    return status


def seal_directory(directory, schema):
    directory = Path(directory)
    files = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(directory.rglob("*")) if p.is_file()}
    dump_new(directory / "manifest.json", {"schema": schema, "complete": True, "files": files})
