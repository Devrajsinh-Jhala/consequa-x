"""Independent saved-native transcript and replay checks.

No research controller, model transport, collection runner or ConseqaX module is
imported. Native imports occur only inside the offline replay/regrade function.
Artifact inventories and prospective protocol bindings are the caller's gates.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess


UPSTREAM_COMMIT = "96a3ef92329baf908ffe9dfe188cea34e8701d2a"
NORMAL_TERMINATIONS = {"agent_stop", "user_stop"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_value(value):
    """Reject unsupported/nonfinite values without coercing their types."""
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        require(math.isfinite(value), "nonfinite JSON value")
        return
    if type(value) is list:
        for item in value:
            strict_value(item)
        return
    require(type(value) is dict and all(type(key) is str for key in value), "non-JSON value")
    for item in value.values():
        strict_value(item)


def content_value(content):
    if type(content) is not str:
        return content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def flat_messages(messages):
    require(type(messages) is list, "native messages must be a list")
    result = []
    for message in messages:
        require(type(message) is dict, "native message must be an object")
        strict_value(message)
        if message.get("role") == "tool" and "tool_messages" in message:
            require(type(message["tool_messages"]) is list, "invalid multi-tool result")
            require(all(type(item) is dict and item.get("role") == "tool" for item in message["tool_messages"]),
                    "invalid flattened tool result")
            result.extend(message["tool_messages"])
        else:
            result.append(message)
    return result


def extract_tool_pairs(messages, *, allow_pending=False):
    """Check every actual native call/result; retain an unfinished final batch."""
    pending, pairs = [], []
    for message in flat_messages(messages):
        role = message.get("role")
        require(role in {"system", "assistant", "user", "tool"}, "unknown native message role")
        if role == "tool":
            require(pending, "orphan native tool result")
            call = pending.pop(0)
            require(message.get("id") == call["id"], "native call/result ID mismatch")
            require(message.get("requestor", "assistant") == call["requestor"], "tool result requestor mismatch")
            require(type(message.get("error", False)) is bool, "native error flag must be boolean")
            pairs.append({"call": call, "result": message})
            continue
        require(not pending, "participant message before required tool results")
        calls = message.get("tool_calls")
        if not calls:
            continue
        require(role in {"assistant", "user"} and type(calls) is list, "invalid native tool-call message")
        for call in calls:
            require(type(call) is dict and type(call.get("id")) is str, "missing native call ID")
            require(type(call.get("name")) is str and bool(call["name"]) and type(call.get("arguments")) is dict,
                    "invalid native call name/arguments")
            requestor = call.get("requestor", "assistant")
            require(requestor == role, "tool-call requestor differs from speaker")
            pending.append({**deepcopy(call), "requestor": requestor})
    require(allow_pending or not pending, "unfinished native tool-call batch")
    return {"pairs": pairs, "pending": pending}


def semantic_message(message):
    value = {key: message.get(key) for key in ("role", "content", "tool_calls")}
    if message.get("role") == "tool":
        value.update(id=message.get("id"), error=message.get("error", False),
                     requestor=message.get("requestor", "assistant"))
    return value


def episode_suffix(messages, initial_history):
    messages, initial_history = flat_messages(messages), flat_messages(initial_history)
    require(len(messages) >= len(initial_history), "native initialization prefix is missing")
    require([semantic_message(item) for item in messages[:len(initial_history)]]
            == [semantic_message(item) for item in initial_history], "native initialization prefix differs")
    return messages[len(initial_history):]


def message_costs(messages):
    """Native monetary metadata and usage observations, not generation counts."""
    result = {}
    for role in ("assistant", "user"):
        rows = [row for row in flat_messages(messages) if row.get("role") == role]
        costs = [row.get("cost") for row in rows]
        require(all(value is None or (type(value) in (int, float) and math.isfinite(value) and value >= 0)
                    for value in costs), "invalid message monetary cost")
        observed = [value for value in costs if value is not None]
        usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            values = [row.get("usage", {}).get(key) if type(row.get("usage")) is dict else None for row in rows]
            require(all(value is None or (type(value) is int and value >= 0) for value in values), "invalid token usage")
            known = [value for value in values if value is not None]
            usage[key] = {"sum_observed": sum(known), "observed_messages": len(known),
                          "unavailable_messages": len(rows) - len(known)}
        result[role] = {"messages": len(rows), "native_cost": sum(observed) if len(observed) == len(rows) else None,
                        "sum_observed_cost": sum(observed), "unavailable_cost_messages": len(rows) - len(observed),
                        "usage": usage,
                        "scope": "message metadata; deterministic wrapper messages are not model requests"}
    return result


def hashes(environment):
    return {"agent_db_hash": environment.get_db_hash(), "user_db_hash": environment.get_user_db_hash()}


def request_of(call):
    return {"tool_name": call["name"], "requestor": call.get("requestor", "assistant"),
            "arguments": call["arguments"]}


def call_once(environment, request):
    before = hashes(environment)
    try:
        result = environment.make_tool_call(request["tool_name"], requestor=request["requestor"], **request["arguments"])
        outcome = {"status": "returned", "content": environment.to_json_str(result)}
    except Exception as exc:
        outcome = {"status": "raised", "error_type": type(exc).__name__, "error": str(exc)}
    return before, outcome, hashes(environment)


def validate_journal(journal):
    require(type(journal) is list, "native call journal must be a list")
    episode_seen = False
    for index, row in enumerate(journal):
        require(row.get("schema") == "native-tool-dispatch-v1" and row.get("call_index") == index,
                "native call journal schema/index differs")
        require(row.get("phase") in {"initialization", "episode"}, "unknown call journal phase")
        if row["phase"] == "episode":
            episode_seen = True
        require(not episode_seen or row["phase"] == "episode", "initialization call after episode started")
        request = row["request"]
        require(set(request) == {"tool_name", "requestor", "arguments"}
                and request["requestor"] in {"assistant", "user"} and type(request["arguments"]) is dict,
                "invalid journal request")
        strict_value(row)
        for key in ("before", "after"):
            require(set(row[key]) == {"agent_db_hash", "user_db_hash"}, "invalid DB hash fields")
            require(all(value is None or type(value) is str for value in row[key].values()), "invalid DB hash value")
        outcome = row["outcome"]
        required = {"status", "content"} if outcome.get("status") == "returned" else {"status", "error_type", "error"}
        require(set(outcome) == required and outcome["status"] in {"returned", "raised"}, "invalid journal outcome")


def replay_episode_calls(environment, journal, pairs):
    """Replay all calls, including reads skipped by native strict DB grading."""
    require(len(journal) == len(pairs), "episode call journal/transcript denominator differs")
    counters = Counter(calls=len(pairs))
    rows = []
    for saved, pair in zip(journal, pairs):
        request = request_of(pair["call"])
        require(saved["phase"] == "episode" and saved["request"] == request, "journal/transcript request differs")
        before, outcome, after = call_once(environment, request)
        require(before == saved["before"] and after == saved["after"], "replayed before/after DB hash differs")
        require(outcome == saved["outcome"], "replayed native tool outcome differs")
        returned = outcome["status"] == "returned"
        if returned:
            environment.sync_tools()
            content = outcome["content"]
        else:
            content = "Error: " + outcome["error"]
        result = pair["result"]
        require(result.get("error", False) is (not returned)
                and content_value(result.get("content")) == content_value(content), "native ToolMessage differs from replay")
        changed = before != after
        counters["returned" if returned else "raised"] += 1
        counters["db_changed_calls"] += int(changed)
        rows.append({"call_index": saved["call_index"], "id": pair["call"]["id"],
                     "tool_name": request["tool_name"], "requestor": request["requestor"],
                     "returned": returned, "db_changed": changed})
    return {"counts": dict(counters), "calls": rows, "final_hashes": hashes(environment)}


def verify_native_source(root):
    """Hash source and airline data against immutable Git bytes; read no gold semantics."""
    root = Path(root).resolve()
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    require(head == UPSTREAM_COMMIT, "native checkout revision differs")
    names = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "--name-only", UPSTREAM_COMMIT,
                                     "src/tau2", "data/tau2/domains/airline"]).decode().splitlines()
    files = {}
    for name in names:
        if Path(name).suffix not in {".py", ".json", ".md"}:
            continue
        expected = subprocess.check_output(["git", "-C", str(root), "show", f"{UPSTREAM_COMMIT}:{name}"])
        actual = (root / name).read_bytes()
        mode = "exact_git_bytes" if actual == expected else "git_lf_to_windows_crlf"
        require(actual == expected or (b"\r\n" not in expected and actual == expected.replace(b"\n", b"\r\n")),
                f"native source/data bytes changed beyond checkout EOL: {name}")
        files[name] = {"runtime_sha256": hashlib.sha256(actual).hexdigest(),
                       "git_sha256": hashlib.sha256(expected).hexdigest(), "checkout_mode": mode,
                       "runtime_bytes": len(actual), "git_bytes": len(expected)}
    require("src/tau2/evaluator/evaluator.py" in files and "src/tau2/environment/environment.py" in files,
            "native source inventory is incomplete")
    return {"commit": UPSTREAM_COMMIT, "files": files}


@contextmanager
def no_network():
    """Development/runtime audit guard, not an OS-level firewall."""
    originals = [(socket.socket, "connect", socket.socket.connect),
                 (socket.socket, "connect_ex", socket.socket.connect_ex),
                 (socket, "create_connection", socket.create_connection),
                 (socket, "getaddrinfo", socket.getaddrinfo)]
    attempts = []
    def refused(*args, **kwargs):
        attempts.append("network attempt")
        raise RuntimeError("Network is forbidden during saved-native audit")
    for target, name, _ in originals:
        setattr(target, name, refused)
    try:
        yield attempts
        require(not attempts, "network attempted during offline native audit")
    finally:
        for target, name, original in originals:
            setattr(target, name, original)


def audit_native_episode(simulation_payload, task, journal, episode_start_hashes, final_hashes, native_root):
    """Offline native initialization + every-call replay + intact ALL regrading.

    ``task`` is the original official native Task, loaded only by evaluator-side
    analysis after collection. It must never be supplied to a research agent.
    This helper assumes caller-verified artifact/prospective protocol bindings.
    """
    source = verify_native_source(native_root)
    validate_journal(journal)
    require({basis.value for basis in task.evaluation_criteria.reward_basis} == {"DB", "COMMUNICATE"},
            "pilot task has an unexpected required component/judge")
    with no_network() as attempts:
        from tau2.data_model.simulation import SimulationRun
        from tau2.domains.airline.environment import get_environment
        from tau2.domains.airline.utils import AIRLINE_DB_PATH, AIRLINE_POLICY_PATH, AIRLINE_TASK_SET_PATH
        from tau2.environment.environment import Environment
        from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
        from tau2.orchestrator.modes import CommunicationMode
        from tau2.registry import registry

        expected = Path(native_root).resolve() / "src/tau2"
        data_root = Path(native_root).resolve() / "data/tau2/domains/airline"
        for path, name in ((AIRLINE_DB_PATH, "db.json"), (AIRLINE_POLICY_PATH, "policy.md"),
                           (AIRLINE_TASK_SET_PATH, "tasks.json")):
            require(Path(path).resolve() == data_root / name, "native data source points outside verified checkout")
        require(registry.get_env_constructor("airline") is get_environment,
                "native airline environment constructor was replaced")
        for function, relative in ((Environment.get_response, "environment/environment.py"),
                                   (get_environment, "domains/airline/environment.py"),
                                   (evaluate_simulation, "evaluator/evaluator.py")):
            require(Path(function.__code__.co_filename).resolve() == expected / relative,
                    "native replay/evaluator imported from another checkout")
        simulation = SimulationRun.model_validate(simulation_payload)
        require(simulation.task_id == task.id and simulation.mode == "half_duplex", "native task/mode differs")
        initial = task.initial_state
        history = initial.message_history if initial is not None and initial.message_history is not None else []
        initialization_data = initial.initialization_data if initial is not None else None
        initialization_actions = initial.initialization_actions if initial is not None else None
        environment = get_environment(solo_mode=False)
        initialization_rows = [row for row in journal if row["phase"] == "initialization"]
        original_call, captured = environment.make_tool_call, []
        def capture(tool_name, requestor="assistant", **arguments):
            before = hashes(environment)
            try:
                value = original_call(tool_name, requestor=requestor, **arguments)
                outcome = {"status": "returned", "content": environment.to_json_str(value)}
            except Exception as exc:
                outcome = {"status": "raised", "error_type": type(exc).__name__, "error": str(exc)}
                captured.append({"request": {"tool_name": tool_name, "requestor": requestor, "arguments": arguments},
                                 "before": before, "outcome": outcome, "after": hashes(environment)})
                raise
            captured.append({"request": {"tool_name": tool_name, "requestor": requestor, "arguments": arguments},
                             "before": before, "outcome": outcome, "after": hashes(environment)})
            return value
        environment.make_tool_call = capture
        environment.set_state(initialization_data=initialization_data, initialization_actions=initialization_actions,
                              message_history=deepcopy(history), strict=True)
        environment.make_tool_call = original_call
        require(captured == [{key: row[key] for key in ("request", "before", "outcome", "after")}
                             for row in initialization_rows], "native initialization journal differs")
        require(hashes(environment) == episode_start_hashes, "post-initialization native DB hashes differ")
        messages = [message.model_dump(mode="json") for message in simulation.messages]
        suffix = episode_suffix(messages, [message.model_dump(mode="json") for message in history])
        normal = simulation.termination_reason.value in NORMAL_TERMINATIONS
        extracted = extract_tool_pairs(suffix, allow_pending=not normal)
        replay = replay_episode_calls(environment, [row for row in journal if row["phase"] == "episode"], extracted["pairs"])
        require(replay["final_hashes"] == final_hashes, "final replay/native DB hashes differ")
        reward = evaluate_simulation(simulation=simulation, task=task, evaluation_type=EvaluationType.ALL,
            solo_mode=False, domain="airline", mode=CommunicationMode.HALF_DUPLEX, env_kwargs=None, strict_replay=True)
        recomputed = reward.model_dump(mode="json")
        require(simulation.reward_info is not None
                and recomputed == simulation.reward_info.model_dump(mode="json"), "native required reward/components differ")
        costs = message_costs(messages)
        for role, attribute in (("assistant", "agent_cost"), ("user", "user_cost")):
            recorded = getattr(simulation, attribute)
            value = costs[role]["native_cost"]
            require((recorded is None and value is None) or (type(recorded) in (int, float) and value is not None
                    and math.isclose(recorded, value, rel_tol=1e-12, abs_tol=1e-12)), "native monetary metadata differs")
    return {"passed": True, "native_source_commit": source["commit"], "native_bound_files": len(source["files"]),
            "reward": recomputed, "normal_termination": normal,
            "required_task_basis": [basis.value for basis in task.evaluation_criteria.reward_basis],
            "pending_native_calls": len(extracted["pending"]), "replay": replay, "message_costs": costs,
            "new_model_calls": 0, "network_attempts": len(attempts),
            "limitations": ["Offline same-project automated audit, not independent human validation.",
                "Message count/usage does not independently authenticate attempted model generations; use bound transport records.",
                "Current field match, full native end state and this-action origin are distinct claims."]}
