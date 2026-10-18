"""Pinned upstream tau3 state-transfer validation (not an agent benchmark).

The upstream tools, environment, task parser and DB evaluator run unchanged.
Only package initializers which eagerly import LLM/voice runners are bypassed.
No user simulator, model generation, LLM judge or leaderboard metric is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types

from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Evidence, Event, EventType,
    Observation, OriginStatus, OutcomeContract, ResponseStatus, ToolResponse,
    Trace, VerificationResult, VerificationStatus, explain, verify,
)

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/sierra-research/tau2-bench"
UPSTREAM_COMMIT = "96a3ef92329baf908ffe9dfe188cea34e8701d2a"
SCHEMA = "consequa-tau3-state-transfer-v1"
DOMAINS = ("retail", "airline")
VARIANTS = ("reference", "omit_writes", "false_acknowledgement", "altered_first_write")
PROTOCOL = ROOT / "docs/tau-benchmark-validation.md"
TEST_SOURCE = ROOT / "tests/test_tau_benchmark_validation.py"
BOOTSTRAP_NAMESPACES = ("tau2", "tau2.voice.audio_native.openai")


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def digest(value):
    return sha256(value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def write_frozen_protocol(output, protocol):
    """Seal the exact protocol bytes before any study cell can start."""
    output = Path(output)
    write_new(output / "protocol.json", protocol)
    write_new(output / "protocol.sha256.json", {
        "schema": SCHEMA + "-protocol-sha256-v1", "file": "protocol.json",
        "sha256": digest((output / "protocol.json").read_bytes()),
    })


def load_frozen_protocol(output):
    output = Path(output)
    protocol_bytes = (output / "protocol.json").read_bytes()
    try:
        receipt = json.loads((output / "protocol.sha256.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError("Frozen protocol SHA-256 receipt is missing or invalid") from error
    expected_receipt = {"schema": SCHEMA + "-protocol-sha256-v1", "file": "protocol.json",
                        "sha256": digest(protocol_bytes)}
    if receipt != expected_receipt:
        raise ValueError("Frozen protocol file bytes do not match the SHA-256 receipt")
    return json.loads(protocol_bytes)


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def verify_source_identity(source):
    source = Path(source).resolve()
    if git(source, "rev-parse", "HEAD") != UPSTREAM_COMMIT:
        raise ValueError("Upstream checkout must have the exact reviewed commit")
    if git(source, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Upstream tracked sources must be clean")
    return source


def source_hashes(source):
    """Bind all upstream Python, domain inputs and license, not only task IDs."""
    source = verify_source_identity(source)
    paths = list((source / "src/tau2").rglob("*.py"))
    for domain in DOMAINS:
        paths += [p for p in (source / "data/tau2/domains" / domain).rglob("*")
                  if p.is_file()]
    paths += [source / "LICENSE", source / "pyproject.toml",
              source / "docs/evaluation.md"]
    if any(p.is_symlink() for p in paths):
        raise ValueError("Symlink sources are refused")
    return {p.relative_to(source).as_posix(): digest(p.read_bytes()) for p in sorted(paths)}


def local_hashes():
    import consequa_x
    package = Path(consequa_x.__file__).resolve().parent
    result = {"runner": digest(Path(__file__).read_bytes()),
              "protocol": digest(PROTOCOL.read_bytes()),
              "tests": digest(TEST_SOURCE.read_bytes())}
    result.update({"runtime/" + p.relative_to(package).as_posix(): digest(p.read_bytes())
                   for p in sorted(package.rglob("*.py"))})
    return result


@contextmanager
def no_network():
    """Neither upstream import nor execution may contact a model or service."""
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    original_create = socket.create_connection

    def refused(*args, **kwargs):
        raise RuntimeError("Networking is disabled for model-free state validation")

    socket.socket.connect = refused
    socket.socket.connect_ex = refused
    socket.create_connection = refused
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex = original_connect, original_connect_ex
        socket.create_connection = original_create


def bootstrap(source):
    """Import unchanged source modules without the two eager package facades.

    This is an import adapter, not a stand-in for tools or evaluator classes.
    PYTHON_DOTENV_DISABLED prevents upstream dotenv from loading credentials.
    """
    source = verify_source_identity(source)
    root = source / "src/tau2"
    os.environ["TAU2_DATA_DIR"] = str(source / "data")
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    for name in BOOTSTRAP_NAMESPACES:
        relative = name.split(".")[1:]
        target = root.joinpath(*relative)
        existing = sys.modules.get(name)
        if existing is not None:
            if list(getattr(existing, "__path__", [])) != [str(target)]:
                raise ValueError("A different tau2 checkout is already imported")
            continue
        module = types.ModuleType(name)
        module.__path__ = [str(target)]
        module.__package__ = name
        sys.modules[name] = module
    with no_network():
        from loguru import logger
        logger.remove()
        logger.add(sys.stderr, level="ERROR")
        from tau2.data_model.message import AssistantMessage, ToolCall
        from tau2.evaluator.evaluator_env import EnvironmentEvaluator
        domains = {domain: importlib.import_module(f"tau2.domains.{domain}.environment")
                   for domain in DOMAINS}
    return {"domains": domains, "AssistantMessage": AssistantMessage,
            "ToolCall": ToolCall, "EnvironmentEvaluator": EnvironmentEvaluator}


def dependencies():
    names = ("pydantic", "pydantic-core", "loguru", "docstring-parser", "deepdiff",
             "addict", "python-dotenv", "PyYAML", "toml", "numpy", "pandas",
             "python-dateutil", "tzdata", "typing-extensions")
    return {name: importlib.metadata.version(name) for name in names}


def loaded_dependency_hashes():
    """Bind the actual imported third-party bodies, not version labels alone."""
    result = {}
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_file() and "tau-native-dependencies" in path.parts:
            if path.suffix == ".pyc" and path.with_suffix(".py").exists():
                path = path.with_suffix(".py")
            result[str(path)] = digest(path.read_bytes())
    return result


def task_records(source):
    return {domain: json.loads((Path(source) / "data/tau2/domains" / domain /
                               "tasks.json").read_text(encoding="utf-8"))
            for domain in DOMAINS}


def make_schedule(records):
    """All canonical base tasks, source order; no outcome-based selection."""
    return [{"slot": len_before + task_index * len(VARIANTS) + variant_index,
             "domain": domain, "task_id": task["id"], "source_index": task_index,
             "task_sha256": digest(encoded(task)), "variant": variant}
            for domain_index, domain in enumerate(DOMAINS)
            for len_before in [sum(len(records[d]) * len(VARIANTS)
                                   for d in DOMAINS[:domain_index])]
            for task_index, task in enumerate(records[domain])
            for variant_index, variant in enumerate(VARIANTS)]


def freeze(source, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Freeze needs a new output directory")
    hashes = source_hashes(source)
    native = bootstrap(source)
    records = task_records(source)
    # Parse every task before freeze; no tool actions or evaluation occurs here.
    for domain in DOMAINS:
        parsed = native["domains"][domain].get_tasks("base")
        if [t.id for t in parsed] != [t["id"] for t in records[domain]]:
            raise ValueError("Base split differs from complete source task order")
    protocol = {"schema": SCHEMA, "created_utc": now(), "upstream": UPSTREAM,
                "source_revision": git(ROOT, "rev-parse", "HEAD"),
                "upstream_commit": UPSTREAM_COMMIT,
                "upstream_hashes": hashes, "local_hashes": local_hashes(),
                "dependencies": dependencies(), "python": sys.version,
                "loaded_dependency_hashes": loaded_dependency_hashes(),
                "source": str(Path(source).resolve()), "schedule": make_schedule(records),
                "task_counts": {d: len(records[d]) for d in DOMAINS},
                "bootstrap_namespaces": list(BOOTSTRAP_NAMESPACES),
                "model_calls": 0, "scope": "Native DB-component state transfer; not pass@k",
                "variants": list(VARIANTS)}
    write_frozen_protocol(output, protocol)
    with (output / "upstream-MIT-LICENSE.txt").open("xb") as stream:
        stream.write((Path(source) / "LICENSE").read_bytes())
    with (output / "written-protocol.source.md").open("xb") as stream:
        stream.write(PROTOCOL.read_bytes())
    return protocol


def plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


def read_snapshot(environment, domain, arguments):
    """Only public native lookup tools enter an auditor observation."""
    if domain == "retail":
        name, keys = (("get_order_details", ("order_id",)) if "order_id" in arguments
                      else ("get_user_details", ("user_id",)))
        return {"read_tool": name, "read_arguments": {k: arguments[k] for k in keys},
                "value": plain(environment.make_tool_call(name, **{k: arguments[k] for k in keys}))}
    if "reservation_id" in arguments:
        kwargs = {"reservation_id": arguments["reservation_id"]}
        return {"read_tool": "get_reservation_details", "read_arguments": kwargs,
                "value": plain(environment.make_tool_call("get_reservation_details", **kwargs))}
    kwargs = {"user_id": arguments["user_id"]}
    user = plain(environment.make_tool_call("get_user_details", **kwargs))
    reservations = [plain(environment.make_tool_call("get_reservation_details", reservation_id=rid))
                    for rid in user["reservations"]]
    return {"read_tool": "get_user_details+get_reservation_details", "read_arguments": kwargs,
            "value": user, "reservations": reservations}


def payload_contract(domain, tool, args, before):
    """Compile postconditions from intended payload and public preflight readback.

    No task, expected reference actions, gold DB, reward or hidden label accepted.
    It covers requested record fields, not every financial side effect or policy.
    """
    checks = []

    def eq(path, value):
        checks.append({"path": path.split("."), "operation": "equals", "value": value})

    def projected(path, fields, value):
        checks.append({"path": path.split("."), "operation": "projected_list",
                       "fields": fields, "value": value})

    if domain == "retail":
        if tool == "cancel_pending_order":
            eq("status", "cancelled")
            eq("cancel_reason", args["reason"])
        elif tool in {"modify_user_address", "modify_pending_order_address"}:
            eq("address", {k: args[k] for k in ("address1", "address2", "city", "state", "country", "zip")})
        elif tool == "exchange_delivered_order_items":
            eq("status", "exchange requested")
            eq("exchange_items", sorted(args["item_ids"]))
            eq("exchange_new_items", sorted(args["new_item_ids"]))
            eq("exchange_payment_method_id", args["payment_method_id"])
        elif tool == "return_delivered_order_items":
            eq("status", "return requested")
            eq("return_items", sorted(args["item_ids"]))
            eq("return_payment_method_id", args["payment_method_id"])
        elif tool == "modify_pending_order_items":
            ids = [item["item_id"] for item in before["value"]["items"]]
            for old, new in zip(args["item_ids"], args["new_item_ids"]):
                if old not in ids:
                    raise ValueError("Requested old item is absent from preflight readback")
                ids[ids.index(old)] = new
            eq("status", "pending (item modified)")
            projected("items", ["item_id"], [{"item_id": i} for i in ids])
        elif tool == "modify_pending_order_payment":
            checks.append({"path": ["payment_history"], "operation": "new_matching_rows",
                           "value": {"transaction_type": "payment", "payment_method_id": args["payment_method_id"]},
                           "before": before["value"]["payment_history"], "minimum_new": 1})
        else:
            raise ValueError(f"Unsupported retail write: {tool}")
    elif tool == "cancel_reservation":
        eq("status", "cancelled")
    elif tool == "update_reservation_baggages":
        eq("total_baggages", args["total_baggages"])
        eq("nonfree_baggages", args["nonfree_baggages"])
    elif tool == "update_reservation_flights":
        eq("cabin", args["cabin"])
        projected("flights", ["flight_number", "date"], args["flights"])
    elif tool == "update_reservation_passengers":
        eq("passengers", args["passengers"])
    elif tool == "book_reservation":
        fields = ("user_id", "origin", "destination", "flight_type", "cabin", "passengers",
                  "total_baggages", "nonfree_baggages", "insurance")
        checks.append({"path": ["reservations"], "operation": "new_reservation",
                       "before_ids": before["value"]["reservations"],
                       "value": {k: args[k] for k in fields}, "flights": args["flights"]})
    elif tool == "send_certificate":
        checks.append({"path": ["payment_methods"], "operation": "new_mapping_value",
                       "before_keys": list(before["value"]["payment_methods"]),
                       "value": {"source": "certificate", "amount": args["amount"]}})
    else:
        raise ValueError(f"Unsupported airline write: {tool}")
    return {"domain": domain, "read_tool": before["read_tool"],
            "read_arguments": before["read_arguments"], "checks": checks,
            "scope_note": "Requested record fields only; no settlement, policy or causal-origin claim"}


def subset(value, expected):
    return isinstance(value, dict) and all(k in value and value[k] == v for k, v in expected.items())


def project_list(rows, fields):
    return [{key: row[key] for key in fields} for row in rows]


def evaluate_checks(expected, record):
    """Transparent application semantics, not an independent accuracy oracle."""
    results = []
    for check in expected["checks"]:
        value = record if check["operation"] == "new_reservation" else record["value"]
        try:
            for key in check["path"]:
                value = value[key]
            operation = check["operation"]
            if operation == "equals":
                match = value == check["value"]
            elif operation == "projected_list":
                match = project_list(value, check["fields"]) == project_list(check["value"], check["fields"])
            elif operation == "new_matching_rows":
                def matching(rows):
                    return sum(subset(row, check["value"]) for row in rows)
                match = matching(value) - matching(check["before"]) >= check["minimum_new"]
            elif operation == "new_mapping_value":
                match = any(key not in check["before_keys"] and subset(row, check["value"])
                            for key, row in value.items())
            elif operation == "new_reservation":
                match = any(row["reservation_id"] not in check["before_ids"]
                            and subset(row, check["value"])
                            and project_list(row["flights"], ["flight_number", "date"])
                            == project_list(check["flights"], ["flight_number", "date"])
                            for row in value)
            else:
                raise ValueError("Unknown application predicate operation")
            results.append(bool(match))
        except (KeyError, TypeError):
            return None
    return results


class TauRecordVerifier:
    """Read-only custom application verifier; leaves provenance unknown."""

    def verify(self, action, observation):
        expected = action.contract.expected
        details = {"scope": observation.scope, "checks": expected["checks"],
                   "complete": observation.complete, "available": observation.available,
                   "as_of_ms": observation.as_of_ms, "records": list(observation.records)}
        evidence = (Evidence(observation.observation_id, observation.source,
                             observation.as_of_ms, details),)
        status, reason = VerificationStatus.UNKNOWN, "Readback is unavailable, incomplete, stale or outside scope"
        if (observation.source == "upstream_native_read_tool"
                and observation.available and observation.complete
                and observation.as_of_ms >= action.contract.horizon_ms
                and observation.scope == {"domain": expected["domain"],
                                          "read_arguments": expected["read_arguments"]}
                and len(observation.records) == 1):
            record = observation.records[0]
            coherent_identity = all(record.get("value", {}).get(key) == value
                                    for key, value in expected["read_arguments"].items())
            if (coherent_identity and record.get("read_tool") == expected["read_tool"]
                    and record.get("read_arguments") == expected["read_arguments"]):
                results = evaluate_checks(expected, record)
                if results is not None:
                    status = VerificationStatus.SATISFIED if all(results) else VerificationStatus.VIOLATED
                    reason = "Requested record fields match captured readback" if all(results) else "Requested record fields differ from captured readback"
        return VerificationResult(action.contract.contract_id, status, observation.observed_at_ms,
                                  evidence, origin=OriginStatus.UNKNOWN, reason=reason)


def audit_capture(action_id, domain, name, args, expected, snapshot, response_status, response_content):
    """The auditor receives only intent, acknowledgement and captured readback."""
    action = Action(action_id, action_id, "reference_replay", name, args, 0,
                    OutcomeContract(action_id + ":contract", "tau_record_fields", expected,
                                    deadline_ms=1, exact_count=None))
    scope = {"domain": domain, "read_arguments": expected["read_arguments"]}
    observation = Observation(action_id + ":read", "upstream_native_read_tool", 2, 2,
                              scope, (snapshot,), available=True, complete=True)
    before_bytes = encoded({"action": action.to_dict(), "observation": observation.to_dict()})
    result = verify(action, observation, verifier=TauRecordVerifier())
    if before_bytes != encoded({"action": action.to_dict(), "observation": observation.to_dict()}):
        raise ValueError("Application verifier mutated captured inputs")
    # Missing readback must abstain even if a fabricated acknowledgement claims success.
    missing = Observation(action_id + ":withheld", observation.source, 2, 2, scope,
                          (), available=False, complete=False)
    missing_result = verify(action, missing, verifier=TauRecordVerifier())
    if missing_result.status is not VerificationStatus.UNKNOWN:
        raise ValueError("Missing readback must remain unknown")
    events = (
        Event(action_id + ":intent", action_id, EventType.ACTION_INTENT, 0,
              data={"name": name, "arguments": args}),
        Event(action_id + ":read_event", action_id, EventType.EXTERNAL_OBSERVATION, 2,
              parent_ids=(action_id + ":intent",), data={"observation_id": observation.observation_id}),
    )
    trace = Trace(action_id, action, events,
                  (ToolResponse(action_id + ":attempt", response_status, 1,
                                action_id + ":request", {"content": response_content}),),
                  AgentAssessment(AssessmentStatus.UNKNOWN, 1, rationale="Model-free replay has no reported agent assessment"),
                  (observation,), (result,))
    trace_bytes = trace.to_json()
    explanation = explain(trace)
    if trace.to_json() != trace_bytes:
        raise ValueError("Explanation mutated captured evidence")
    if result.origin is not OriginStatus.UNKNOWN:
        raise ValueError("Native tools do not emit ConsequaX action-origin witnesses")
    return {"trace": trace.to_dict(), "explanation": explanation.to_dict(),
            "withheld_status": missing_result.status.value,
            "input_sha256": digest(before_bytes), "inputs_unchanged": True}


def initialize(environment, task):
    state = task.initial_state
    environment.set_state(
        initialization_data=None if state is None else state.initialization_data,
        initialization_actions=None if state is None else state.initialization_actions,
        message_history=[] if state is None else (state.message_history or []), strict=True,
    )


def execute_case(native, domain, task, variant, slot, progress=None):
    if progress is None:
        progress = {}
    progress.update(stage="initializing", native_calls=[], action_audits=[])
    constructor = native["domains"][domain].get_environment
    environment = constructor()
    initialize(environment, task)
    initial_hash = environment.get_db_hash()
    history = [] if task.initial_state is None else list(task.initial_state.message_history or [])
    action_audits, native_calls = progress["action_audits"], progress["native_calls"]
    altered = False
    for index, intended in enumerate(task.evaluation_criteria.actions or []):
        progress.update(stage="executing_reference_action", source_action_index=index)
        args = deepcopy(intended.arguments)
        name = intended.name
        is_write = environment._is_mutating_tool(name)
        expected = before = None
        preflight_error = None
        if is_write:
            try:
                before = read_snapshot(environment, domain, args)
                expected = payload_contract(domain, name, args, before)
            except (KeyError, ValueError) as error:
                preflight_error = f"{type(error).__name__}: {error}"
        actual_args = deepcopy(args)
        execute = not (is_write and variant in {"omit_writes", "false_acknowledgement"})
        if is_write and variant == "altered_first_write" and not altered:
            identity_key = next(k for k in ("reservation_id", "order_id", "user_id") if k in actual_args)
            actual_args[identity_key] += "__CX_INVALID_SCOPE__"
            altered = True
        response = None
        if execute:
            tc = native["ToolCall"](id=f"{slot}:{index}", name=name,
                                    arguments=actual_args, requestor=intended.requestor)
            response = environment.get_response(tc)
            role = "assistant" if intended.requestor == "assistant" else "user"
            if role != "assistant":
                raise ValueError("Retail/airline reference corpus unexpectedly contains user tool calls")
            history.extend([native["AssistantMessage"](role="assistant", tool_calls=[tc]), response])
        content = (response.content if response is not None else
                   ("Success: operation completed" if variant == "false_acknowledgement" else "Operation omitted by fixed control"))
        status = (ResponseStatus.ERROR if response is not None and response.error
                  else ResponseStatus.SUCCESS if execute or variant == "false_acknowledgement"
                  else ResponseStatus.TIMEOUT)
        native_calls.append({"source_action_index": index, "name": name,
                             "intended_arguments": args, "actual_arguments": actual_args,
                             "mutates_state": is_write, "executed": execute,
                             "response": None if response is None else response.model_dump(mode="json"),
                             "auditor_acknowledgement": content})
        if is_write:
            if expected is None:
                action_audits.append({"source_action_index": index, "name": name,
                                      "audit_disposition": "preflight_unavailable", "error": preflight_error})
                continue
            state_before_read = environment.get_db_hash()
            try:
                snapshot = read_snapshot(environment, domain, args)
            except (KeyError, ValueError) as error:
                action_audits.append({"source_action_index": index, "name": name,
                                      "audit_disposition": "readback_unavailable", "error": f"{type(error).__name__}: {error}"})
                continue
            capture = audit_capture(f"tau:{domain}:{task.id}:{variant}:{index}",
                                    domain, name, args, expected, snapshot, status, content)
            if environment.get_db_hash() != state_before_read:
                raise ValueError("Read-only capture or explanation changed the upstream DB")
            action_audits.append({"source_action_index": index, "name": name,
                                  "audit_disposition": "captured", **capture})
    final_hash = environment.get_db_hash()
    progress.update(stage="native_evaluation", final_db_hash=final_hash)
    reward = native["EnvironmentEvaluator"].calculate_reward(
        environment_constructor=constructor, task=task, full_trajectory=history,
        solo_mode=False, strict_replay=True,
    )
    if environment.get_db_hash() != final_hash:
        raise ValueError("Native evaluator mutated the independently executed environment")
    return {"schema": SCHEMA, "slot": slot, "domain": domain, "task_id": task.id,
            "variant": variant, "initial_db_hash": initial_hash, "final_db_hash": final_hash,
            "native_db_component": reward.model_dump(mode="json"),
            "task_reward_basis": list(task.evaluation_criteria.reward_basis),
            "task_target": "Whole native database state; excludes communication/NL criteria",
            "action_target": "Requested record fields immediately after each intended operation",
            "native_calls": native_calls, "action_audits": action_audits,
            "model_calls": 0, "completed_utc": now()}


def verify_frozen(protocol, source):
    if protocol["schema"] != SCHEMA or protocol["upstream_commit"] != UPSTREAM_COMMIT:
        raise ValueError("Unsupported validation protocol")
    if source_hashes(source) != protocol["upstream_hashes"]:
        raise ValueError("Frozen upstream source/data changed")
    if local_hashes() != protocol["local_hashes"]:
        raise ValueError("Frozen runner/protocol/tests/runtime changed")
    if dependencies() != protocol["dependencies"] or sys.version != protocol["python"]:
        raise ValueError("Frozen interpreter/dependencies changed")
    for filename, expected_hash in protocol["loaded_dependency_hashes"].items():
        path = Path(filename)
        if not path.is_file() or digest(path.read_bytes()) != expected_hash:
            raise ValueError("Frozen imported dependency body changed")
    if make_schedule(task_records(source)) != protocol["schedule"]:
        raise ValueError("Task selection or order changed")


def run(output, source):
    output = Path(output).resolve()
    protocol = load_frozen_protocol(output)
    verify_frozen(protocol, source)
    if (output / "episodes").exists() or (output / "summary.json").exists():
        raise ValueError("Existing results are immutable; this invocation will not regenerate slots")
    lock = output / "runner.lock"
    write_new(lock, {"pid": os.getpid(), "started_utc": now(), "protocol_sha256": digest(encoded(protocol))})
    native = bootstrap(source)
    tasks = {d: {t.id: t for t in native["domains"][d].get_tasks("base")} for d in DOMAINS}
    counts = Counter()
    action_counts = Counter()
    try:
        with no_network():
            for slot in protocol["schedule"]:
                if load_frozen_protocol(output) != protocol:
                    raise ValueError("Frozen protocol changed during execution")
                verify_frozen(protocol, source)
                path = output / "episodes" / f"episode_{slot['slot']:04d}.json"
                write_new(output / "started" / f"episode_{slot['slot']:04d}.json", {**slot, "started_utc": now()})
                partial = {}
                try:
                    result = execute_case(native, slot["domain"], tasks[slot["domain"]][slot["task_id"]], slot["variant"], slot["slot"], progress=partial)
                    result["source_task_sha256"] = slot["task_sha256"]
                    result["disposition"] = "completed"
                    db_match = result["native_db_component"]["db_check"]["db_match"]
                    counts[(slot["domain"], slot["variant"], str(db_match))] += 1
                    for audit in result["action_audits"]:
                        label = (audit["trace"]["verifications"][0]["status"]
                                 if audit["audit_disposition"] == "captured" else audit["audit_disposition"])
                        action_counts[(slot["domain"], slot["variant"], label)] += 1
                except Exception as error:
                    result = {**slot, "schema": SCHEMA, "disposition": "failed",
                              "error": f"{type(error).__name__}: {error}", "completed_utc": now(),
                              "partial_execution": partial, "fully_audited": False}
                write_new(path, result)
                print(json.dumps({"slot": slot["slot"], "total": len(protocol["schedule"]),
                                  "disposition": result["disposition"]}), flush=True)
        if load_frozen_protocol(output) != protocol:
            raise ValueError("Frozen protocol changed during execution")
        verify_frozen(protocol, source)
        files = sorted((output / "episodes").glob("episode_*.json"))
        dispositions = Counter({"completed": 0, "failed": 0, "unstarted": 0})
        dispositions.update(json.loads(p.read_text(encoding="utf-8"))["disposition"] for p in files)
        dispositions["unstarted"] = len(protocol["schedule"]) - len(files)
        summary = {"schema": SCHEMA, "upstream_commit": UPSTREAM_COMMIT, "completed_utc": now(),
                   "planned": len(protocol["schedule"]), "dispositions": dict(dispositions),
                   "native_db_component_counts": [{"domain": d, "variant": v, "db_match": s == "True", "count": n}
                                                  for (d, v, s), n in sorted(counts.items())],
                   "action_field_counts": [{"domain": d, "variant": v, "status": s, "count": n}
                                           for (d, v, s), n in sorted(action_counts.items())],
                   "files": {str(p.relative_to(output)).replace("\\", "/"): digest(p.read_bytes()) for p in files},
                   "model_calls": 0, "interpretation": "Model-free native task/tool state transfer; not autonomous benchmark performance or independent predicate accuracy"}
        write_new(output / "summary.json", summary)
        return summary
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "verify"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.source, args.output)
        print(json.dumps({"planned": len(result["schedule"]), "task_counts": result["task_counts"]}))
    elif args.command == "run":
        print(json.dumps(run(args.output, args.source)))
    else:
        protocol = load_frozen_protocol(args.output)
        verify_frozen(protocol, args.source)
        print("Frozen protocol/source/dependency identity verified")


if __name__ == "__main__":
    main()
