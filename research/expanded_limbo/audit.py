"""Offline physical replay for the new multi-model native study.

The measured policy is never imported. Saved policy-level operation scripts are
executed against unchanged native services, while saved policy observations are
fed back to unchanged native orchestration. This checks physical execution and
grading, not independent synthesis of the policy. Admission certificates receive
a separate public-input reconstruction/check. Provider render/token proofs are
checked for internal consistency, not independently tokenized or authenticated.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
import socket


SCHEMA = "conseqax-expanded-limbo-offline-audit-v1"
POLICY_SCHEMA = "conseqax-expanded-limbo-policy-call-v1"
DEFAULT_WORK = {"execute": 96, "verify": 64, "wait": 64,
                "total_wait_seconds": 172800}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def same(left, right, message):
    require(canonical(left) == canonical(right), message)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load(path):
    def refuse_constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=refuse_constant)


def jsonl(path):
    raw = Path(path).read_bytes()
    require(not raw or raw.endswith(b"\n"), "Journal has incomplete trailing record")
    return [json.loads(row) for row in raw.splitlines()]


def binding(path):
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def verify_manifest(directory):
    directory = Path(directory).resolve(strict=True)
    inventory = load(directory / "manifest.json")
    require(type(inventory) is dict, "Artifact manifest must be a flat mapping")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
              if p.is_file() and p != directory / "manifest.json"}
    require(actual == set(inventory), "Artifact inventory differs")
    for name, expected in inventory.items():
        path = directory / name
        require(path.resolve().is_relative_to(directory)
                and ".." not in Path(name).parts, "Unsafe artifact path")
        same(binding(path), expected, "Artifact bytes differ: " + name)
    return inventory


def verify_sources(root, files):
    root = Path(root).resolve(strict=True)
    require(type(files) is dict and bool(files), "Source inventory is required")
    for name, expected in files.items():
        path = root / name
        require(path.resolve().is_relative_to(root), "Source path escapes bound root")
        same(binding(path), expected, "Source bytes differ: " + name)


@contextmanager
def no_network():
    original = (socket.socket.connect, socket.socket.connect_ex,
                socket.create_connection)

    def refuse(*args, **kwargs):
        raise RuntimeError("Network is forbidden during offline replay")

    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = refuse
    try:
        yield
    finally:
        (socket.socket.connect, socket.socket.connect_ex,
         socket.create_connection) = original


def serial(value):
    """Independent deterministic serialization of trusted native state."""
    if is_dataclass(value):
        return serial(asdict(value))
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, (tuple, list)):
        return [serial(item) for item in value]
    if isinstance(value, set):
        return sorted((serial(item) for item in value), key=canonical)
    if isinstance(value, dict):
        if all(type(k) is str for k in value):
            return {k: serial(v) for k, v in value.items()}
        return {"__mapping_pairs__": sorted([[serial(k), serial(v)]
            for k, v in value.items()], key=lambda pair: canonical(pair[0]))}
    raise TypeError("Unexpected native state type")


def snapshot(world):
    state = {k: v for k, v in vars(world).items() if k not in ("rng", "deferred")}
    state["rng_state"] = world.rng.getstate()
    state["deferred"] = [[due, sequence, metadata]
                         for due, sequence, _callback, metadata in world.deferred]
    return serial(state)


def _public_contract(rt, name, args):
    """Evaluate only trusted public contract declarations, never a handler."""
    require(name in rt.tools, "Certificate names an undeclared tool")
    contract = rt.tools[name].contract
    return serial({"write": contract.write, "idempotent": contract.idempotent,
        "supports_key": contract.supports_key(serial(args)),
        "batch_field": contract.batch_field,
        "identity": contract.identity(serial(args)) if contract.identity is not None else None})


def _descriptor(name, args, contract):
    """Independent reproduction of the public operation/component schema."""
    business = {key: value for key, value in args.items() if key != "idempotency_key"}
    payload = digest(business)
    intent = ([name, contract["identity"]] if contract["identity"] is not None
              else [name, "full_payload", payload])
    scope, components = None, []
    field = contract["batch_field"]
    if name in ("db_insert", "db_insert_many"):
        field = "row" if name == "db_insert" else "rows"
        rows = [business[field]] if name == "db_insert" and field in business else business.get(field, [])
        if type(rows) is list:
            scope = digest(["data_insert", {key: value for key, value in business.items() if key != field}])
            components = [digest(row) for row in rows]
    elif field is not None and type(business.get(field)) is list:
        scope = digest(["batch:" + name, {key: value for key, value in business.items() if key != field}])
        components = [digest(row) for row in business[field]]
    return {"tool": name, "intent_key": digest(intent), "payload_digest": payload,
        "key": args.get("idempotency_key") or None, "key_supported": contract["supports_key"],
        "idempotent": contract["idempotent"], "component_scope": scope, "components": components}


def _related(current, old):
    return current["intent_key"] == old["intent_key"] or (
        current["component_scope"] is not None
        and current["component_scope"] == old["component_scope"]
        and bool(Counter(current["components"]) & Counter(old["components"]))) or (
        current["tool"] == old["tool"] and current["key"] is not None and current["key"] == old["key"])


def _reconstruct_operation(rt, operation, attempts, episode_id):
    """Account only actual returned public calls; preserve every older attempt."""
    ending = operation["outcome"]
    if ending["event"] != "return":
        return None
    if operation["op"] == "execute":
        name, args = operation["args"]
        contract = _public_contract(rt, name, args)
        if not contract["write"]:
            return None
        observation = ending["result"]
        require(type(observation) is dict, "Write result is not public observation data")
        disposition = "success" if observation.get("ok") is True else (
            "terminal_no_effect" if observation.get("terminal_not_committed") is True else "unknown")
        attempt = {"attempt_id": episode_id + ":attempt:" + str(len(attempts) + 1),
            "tool": name, "args": serial(args), **_descriptor(name, args, contract),
            "t_call": operation["clock_before"], "disposition": disposition,
            "observation": serial(observation), "reports": []}
        attempts.append(attempt)
        return {"attempt": serial(attempt)}
    if operation["op"] == "verify":
        name, args, t_call = operation["args"]
        matches = [item for item in attempts if item["tool"] == name
                   and canonical(item["args"]) == canonical(args) and item["t_call"] == t_call]
        require(len(matches) == 1, "Public verification lacks one exact earlier attempt")
        returned = ending["result"]
        report = {"attempt_id": matches[0]["attempt_id"], "status": returned["status"],
            "detail": serial(returned["detail"]), "t_call": t_call,
            "t_observed": operation["clock_after"]}
        matches[0]["reports"].append(report)
        return {"report": serial(report), "operation": operation}
    return None


def audit_public_receipt(receipt, report, *, episode_id, sequence, operation):
    """Recompute current-report mapping; no SDK invocation or origin inference."""
    content = {key: value for key, value in receipt.items() if key != "content_sha256"}
    require(receipt["content_sha256"] == digest(content), "Package receipt hash differs")
    require(receipt["schema"] == "conseqax-limbo-public-verification-v1"
            and receipt["framework_version"] == "2.1.1", "Package receipt version/schema differs")
    name, args, t_call = operation["args"]
    native = {"status": report["status"], "detail": report["detail"]}
    key = "limbo-public-" + digest([episode_id, sequence, name, args, t_call,
                                    report["t_observed"], native])
    action, observation, result = receipt["action"], receipt["observation"], receipt["verification"]
    require(action["action_id"] == key and action["name"] == name
            and action["registered_at_ms"] == round(t_call * 1000), "Receipt action differs")
    same(action["arguments"], args, "Receipt verification arguments differ")
    contract = action["contract"]
    require(contract["contract_id"] == key + ":current-visible-match"
            and contract["predicate"] == "limbo_current_public_verifier_match"
            and contract["deadline_ms"] == round(t_call * 1000)
            and contract["exact_count"] is None, "Receipt contract scope differs")
    same(contract["expected"], {"tool": name, "arguments": args}, "Receipt predicate input differs")
    same(observation["records"], [{"native": native}], "Receipt public report differs")
    require(observation["observation_id"] == key + ":public-report"
            and observation["source"] == "limbo_public_verifier"
            and observation["observed_at_ms"] == round(report["t_observed"] * 1000)
            and observation["as_of_ms"] == observation["observed_at_ms"], "Receipt observation differs")
    status = {"found": "satisfied", "absent": "violated"}.get(report["status"], "unknown")
    require(result["status"] == status and result["origin"] == "unknown"
            and result["action_id"] == key and result["contract_id"] == contract["contract_id"]
            and result["observed_at_ms"] == observation["observed_at_ms"], "Receipt mapped result differs")
    evidence = result["evidence"]
    require(len(evidence) == 1 and evidence[0]["observation_id"] == observation["observation_id"]
            and evidence[0]["source"] == observation["source"]
            and evidence[0]["as_of_ms"] == observation["as_of_ms"]
            and evidence[0]["details"]["native_status"] == report["status"], "Receipt evidence differs")


class PublicCertificateChecker:
    """Rebuild certificate premises from actual replayed public history.

    Only the independently authored standard-library certificate arithmetic is
    imported. Measured policy code and its ledger/descriptor helpers are not.
    """
    def __init__(self, mode, episode_id):
        require(mode in ("obligation_shield", "no_unkeyed_repeat"), "Unknown obligation arm")
        self.mode, self.episode_id = mode, episode_id
        self.certificates, self.receipts, self.attempts = 0, 0, []

    def __call__(self, rt, record, earlier_records, earlier_interventions):
        from research.obligation_shield.certificates import check_certificate

        if (record["outcome"]["event"] == "raise" and not record["_audit_operations"]
                and len(record["interventions"]) == len(earlier_interventions)):
            # No delegated work or asserted certificate exists to validate.
            # Physical replay still checks the resulting native error/grade.
            return
        name, original_args = record["name"], serial(record["args"])
        new = record["interventions"][len(earlier_interventions):]
        decisions = [row for row in new if row.get("kind") == "obligation_decision"]
        receipt_rows = [row for row in new if row.get("kind") == "package_receipt"]
        attempt_rows = [row for row in new if row.get("kind") == "obligation_attempt"]
        if name not in rt.tools:
            require(not decisions and not receipt_rows and not attempt_rows,
                    "Native control/unknown tool fabricated a write certificate")
            same([operation["args"] for operation in record["_audit_operations"]
                  if operation["op"] == "execute"], [[name, original_args]],
                 "Native control/unknown tool dispatch was rewritten")
            return
        contract = _public_contract(rt, name, original_args)
        if not contract["write"]:
            require(not decisions and not receipt_rows and not attempt_rows,
                    "Read-only call has fabricated write evidence")
            return
        # Key insertion is a deterministic policy transformation, not a model
        # proposal rewrite silently justified by its own certificate.
        args = serial(original_args)
        descriptor = _descriptor(name, args, contract)
        auto_keys = [row for row in new if row.get("kind") == "auto_key"]
        if contract["supports_key"] and not args.get("idempotency_key"):
            args["idempotency_key"] = "cx-obligation-" + digest(
                [self.episode_id, name, descriptor["intent_key"], descriptor["payload_digest"]])[:24]
            same(auto_keys, [{"kind": "auto_key", "tool": name, "key": args["idempotency_key"]}],
                 "Inserted provider key was not derived from the registered operation")
        else:
            require(not auto_keys, "Unexpected provider-key replacement")
        descriptor = _descriptor(name, args, contract)
        operations = record["_audit_operations"]
        write_operations = [op for op in operations if op["op"] == "execute"
                            and _public_contract(rt, op["args"][0], op["args"][1])["write"]]
        require(len(write_operations) <= 1, "One proposal made multiple unaccounted write dispatches")
        current_reports, current_attempts = [], []
        # The policy performs its optional verification before admission. Rebuild
        # these reports before testing the certificate; append a new actual
        # attempt only after admission has been independently checked.
        passed_write = False
        for operation in operations:
            if operation in write_operations:
                passed_write = True
                continue
            if operation["op"] == "verify":
                require(not passed_write, "Verification occurred after the admission dispatch")
                item = _reconstruct_operation(rt, operation, self.attempts, self.episode_id)
                if item is not None:
                    current_reports.append(item)
            elif operation["op"] == "execute":
                require(False, "Write policy issued an unrelated read tool instead of its declared verification API")
        require(len(decisions) == 1, "Write admission lacks one complete certificate")
        inputs = {"mode": self.mode, "tool": name, "args": args, "contract": contract,
            "related_attempts": serial([item for item in self.attempts if _related(descriptor, item)]),
            "current_report": current_reports[-1]["report"] if current_reports else None}
        same(decisions[0]["certificate"]["inputs"], inputs,
             "Certificate inputs differ from independently reconstructed public calls")
        check_certificate(decisions[0]["certificate"])
        self.certificates += 1
        decision = decisions[0]["certificate"]["decision"]
        require(bool(write_operations) == decision["dispatch"] or (
            decision["dispatch"] is True and not write_operations and record["outcome"]["event"] == "raise"),
            "Certificate gate and actual dispatch differ")
        for operation in write_operations:
            same(operation["args"], [name, args], "Actual write payload differs from admission certificate")
            item = _reconstruct_operation(rt, operation, self.attempts, self.episode_id)
            if item is not None:
                current_attempts.append(item["attempt"])
        same([item["attempt"] for item in attempt_rows], current_attempts,
             "Persistent attempt evidence differs from actual dispatch response")
        require(len(receipt_rows) == len(current_reports), "Missing/extraneous public-report receipt")
        for row, item in zip(receipt_rows, current_reports):
            self.receipts += 1
            require(row["receipt_sequence"] == self.receipts
                    and row["attempt_id"] == item["report"]["attempt_id"], "Receipt attempt/order differs")
            audit_public_receipt(row["receipt"], item["report"], episode_id=self.episode_id,
                                 sequence=self.receipts, operation=item["operation"])
        if not decision["dispatch"] and record["outcome"]["event"] == "return":
            labels = record["outcome"]["result"].get("obligation_shield", {})
            require(labels.get("dispatch") is False and labels.get("reason") == decision["reason"]
                    and labels.get("current_state") == "unknown" and labels.get("origin") == "unknown"
                    and labels.get("settled_all_attempts") is False,
                    "Suppression was presented as a fresh verified or settled native outcome")


def audit_policy_evidence(rt, records, interventions):
    """Check recorded admission precedes the public dispatch boundary.

    This journal is bound to the physical native journal by replay and the
    independently reconstructed certificates, not by a provider signature.
    """
    same([row for row in records if "kind" in row], interventions,
         "Policy evidence journal/intervention snapshots differ")
    pending = None
    for row in records:
        if row.get("kind") == "obligation_decision":
            pending = row["certificate"]
        if row.get("operation") == "execute" and row.get("phase") == "start":
            inputs = row["inputs"]
            name, args = inputs["name"], inputs["args"]
            if name not in rt.tools or not rt.tools[name].contract.write:
                continue
            require(pending is not None and pending["decision"]["dispatch"] is True,
                    "Public write started before its admission certificate")
            same([pending["inputs"]["tool"], pending["inputs"]["args"]], [name, args],
                 "Pre-dispatch certificate names another public write")
            pending = None


@contextmanager
def replay_instrumentation(work_limits=None):
    """Reconstruct full nesting, initial/final world and identical public caps."""
    from limbo.runtime import ToolRuntime
    from limbo.world import World

    limits = dict(DEFAULT_WORK if work_limits is None else work_limits)
    require(set(limits) == set(DEFAULT_WORK), "Work-limit inventory differs")
    for key, value in limits.items():
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                "Invalid work ceiling: " + key)
    old_init, old_advance = ToolRuntime.__init__, World.advance
    originals = {name: getattr(ToolRuntime, name) for name in ("execute", "verify", "flush")}
    state = {"rt": None, "initial": None, "events": [], "stack": [], "next": 0,
             "counts": {"execute": 0, "verify": 0, "advance": 0}, "wait_seconds": 0.0}

    def initialize(rt, *args, **kwargs):
        old_init(rt, *args, **kwargs)
        require(state["rt"] is None, "More than one native runtime in replay")
        state["rt"], state["initial"] = rt, snapshot(rt.world)

    def wrap(op, original):
        def call(obj, *args, **kwargs):
            rt = state["rt"]
            if rt is None or (op == "advance" and obj is not rt.world):
                return original(obj, *args, **kwargs)
            bound = inspect.signature(original).bind(obj, *args, **kwargs)
            bound.apply_defaults()
            fields = bound.arguments
            require(op != "verify" or fields["truth"] is False,
                    "Privileged verification is forbidden")
            positions = ([fields["name"], fields["args"]] if op == "execute" else
                         [fields["name"], fields["args"], fields["t_call"]] if op == "verify" else
                         [fields["seconds"]] if op == "advance" else [])
            keywords = ({"source": fields["source"], "note": fields["note"]} if op == "execute" else
                        {"truth": fields["truth"]} if op == "verify" else {})
            ident, parent = state["next"], state["stack"][-1] if state["stack"] else None
            state["next"] += 1
            state["events"].append({"event": "enter", "id": ident, "parent": parent,
                "op": op, "args": serial(positions), "kwargs": serial(keywords), "clock": rt.world.clock})
            state["stack"].append(ident)
            try:
                if op in ("execute", "verify"):
                    state["counts"][op] += 1
                    if state["counts"][op] > limits[op]:
                        raise RuntimeError("Uniform native " + op + " budget exhausted")
                if op == "advance" and parent is None:
                    state["counts"]["advance"] += 1
                    state["wait_seconds"] += float(fields["seconds"])
                    if (state["counts"]["advance"] > limits["wait"]
                            or state["wait_seconds"] > limits["total_wait_seconds"]):
                        raise RuntimeError("Uniform native wait budget exhausted")
                result = original(obj, *args, **kwargs)
            except BaseException as exc:
                state["events"].append({"event": "raise", "id": ident,
                    "type": type(exc).__name__, "message": str(exc), "clock": rt.world.clock})
                raise
            else:
                state["events"].append({"event": "return", "id": ident,
                                       "result": serial(result), "clock": rt.world.clock})
                return result
            finally:
                state["stack"].pop()
        return call

    ToolRuntime.__init__ = initialize
    for name, original in originals.items():
        setattr(ToolRuntime, name, wrap(name, original))
    World.advance = wrap("advance", old_advance)
    try:
        yield state
    finally:
        ToolRuntime.__init__, World.advance = old_init, old_advance
        for name, original in originals.items():
            setattr(ToolRuntime, name, original)


class ScriptedPolicy:
    """Re-execute saved native work, never import or evaluate measured policy."""
    prompt_variant = "vanilla"
    reflect = False

    def __init__(self, name, records, *, checker=None):
        self.name, self.records, self.checker = name, records, checker
        self.position, self.interventions = 0, []
        self.public_history = []
        self.validation_error = None

    def execute(self, rt, name, args):
        try:
            ending = self._execute(rt, name, args)
        except BaseException as exc:
            self.validation_error = exc
            raise
        if ending["event"] == "raise":
            # A native error's type/message can be reproduced without importing
            # its policy implementation. Its descriptive traceback cannot.
            error = ending["type"]
            require(type(error) is str and error.isidentifier(), "Invalid recorded error type")
            raise type(error, (RuntimeError,), {})(ending["message"])
        return serial(ending["result"])

    def _execute(self, rt, name, args):
        require(self.position < len(self.records), "Missing saved policy call")
        record = self.records[self.position]
        self.position += 1
        require(record.get("schema") == POLICY_SCHEMA
                and record.get("sequence") == self.position, "Policy call identity differs")
        same([record["name"], record["args"]], [name, args], "Policy proposal differs")
        same(record["clock_before"], rt.world.clock, "Policy entry clock differs")
        operations = record["operations"]
        require(type(operations) is list, "Policy operation script must be a list")
        observed_operations = []
        for operation in operations:
            op = operation["op"]
            require(op in ("execute", "verify", "advance"), "Unsupported scripted public operation")
            positional, keywords = operation["args"], operation["kwargs"]
            require(type(positional) is list and type(keywords) is dict, "Invalid operation arguments")
            if op == "verify":
                require(keywords == {"truth": False}, "Privileged or unspecified verification")
            method = rt.world.advance if op == "advance" else getattr(rt, op)
            clock_before = rt.world.clock
            try:
                value = method(*positional, **keywords)
            except BaseException as exc:
                outcome = {"event": "raise", "type": type(exc).__name__, "message": str(exc)}
            else:
                outcome = {"event": "return", "result": serial(value)}
            same(operation["outcome"], outcome, "Scripted public operation result differs")
            observed_operations.append({**serial(operation), "clock_before": clock_before,
                                        "clock_after": rt.world.clock})
        same(record["clock_after"], rt.world.clock, "Policy exit clock differs")
        require(type(record["interventions"]) is list, "Missing policy intervention snapshot")
        same(record["interventions"][:len(self.interventions)], self.interventions,
             "Policy intervention history was rewritten")
        if self.checker is not None:
            checked_record = {**serial(record), "_audit_operations": observed_operations}
            self.checker(rt, checked_record, self.public_history, self.interventions)
        else:
            checked_record = {**serial(record), "_audit_operations": observed_operations}
        self.interventions = serial(record["interventions"])
        self.public_history.append(checked_record)
        ending = record["outcome"]
        require(ending.get("event") in ("return", "raise"), "Invalid policy terminal")
        if ending["event"] == "return":
            require(type(ending.get("result")) is dict, "Policy observation is not an object")
        else:
            require(type(ending.get("type")) is str and ending["type"].isidentifier()
                    and type(ending.get("message")) is str, "Invalid saved policy error")
        return ending

    def assert_consumed(self):
        if self.validation_error is not None:
            raise ValueError("Policy replay validation failed inside native orchestration") from self.validation_error
        require(self.position == len(self.records), "Unused saved policy calls")


def _usage(payload):
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    prompt = usage.get("prompt_tokens_details")
    output = usage.get("completion_tokens_details")
    values = {"input_tokens": usage.get("prompt_tokens"),
              "output_tokens": usage.get("completion_tokens"),
              "cached_tokens": prompt.get("cached_tokens") if isinstance(prompt, dict) else None,
              "reasoning_tokens": usage.get("reasoning_tokens",
                  output.get("reasoning_tokens") if isinstance(output, dict) else None)}
    return {name: {"available": type(value) is int and value >= 0,
                   "value": value if type(value) is int and value >= 0 else None}
            for name, value in values.items()}


def audit_context(proof, request, runtime, *, output_tokens):
    """Saved provider-native context proof consistency, not offline parity."""
    same(proof["request"], request, "Context proof request differs")
    # The provider transport's canonical hash has spaced JSON separators.
    spaced = json.dumps(request, sort_keys=True, allow_nan=False, ensure_ascii=False).encode("utf-8")
    require(proof["request_sha256"] == hashlib.sha256(spaced).hexdigest(), "Context request hash differs")
    same(proof["runtime_binding"], runtime, "Context runtime binding differs")
    require(proof.get("passed") is True
            and proof.get("generation_dispatched_by_gate") is False
            and proof.get("independent_offline_template_tokenizer_parity") is False,
            "Context gate failed or has an unsupported parity claim")
    prompt = proof["provider_rendered_prompt"]
    require(type(prompt) is str and bool(prompt), "Full provider prompt missing")
    same(prompt, proof["server_preview"]["_debug_info"]["rendered_template"],
         "Provider preview prompt differs")
    tokens = proof["runtime_tokenizer"]["tokens"]
    require(type(tokens) is list and bool(tokens)
            and all(type(token) is int and token >= 0 for token in tokens), "Invalid runtime token IDs")
    context = proof["context"]
    require(context["rendered_prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
            and context["prompt_tokens"] == len(tokens)
            and context["output_tokens"] == output_tokens
            and context["reserve_tokens"] == 64
            and context["required_tokens"] == len(tokens) + output_tokens + 64
            and context["context_tokens"] == runtime["context_tokens"]
            and context["required_tokens"] <= runtime["context_tokens"]
            and context["fits"] is True and context["truncation_requested"] is False,
            "Context token accounting differs")
    profiles = [item for item in proof["resident_response"].get("models", [])
                if item.get("name") == runtime["model"] or item.get("model") == runtime["model"]]
    require(len(profiles) == 1 and profiles[0].get("digest") == runtime["model_digest"]
            and profiles[0].get("context_length") == runtime["context_tokens"],
            "Saved residency model/context/digest differs")


def audit_model_call(directory, number, native_input, slot, config):
    """Pinned native serializer/parser with one retained response and no socket."""
    from limbo.llm import LLMClient

    prefix = Path(directory) / f"{number:04d}"
    terminal = load(str(prefix) + "-terminal.json")
    same(load(str(prefix) + "-native-input.json"), native_input, "Native model input/history/tools differs")
    require(terminal["invocation"] == number and terminal["dispatches"] in (0, 1),
            "Invalid model invocation terminal")
    require(type(terminal["returned"]) is bool, "Missing invocation return disposition")
    captures = []

    class CaptureStop(BaseException):
        pass

    class NativeCapture:
        model = config["runtime"]["model"]
        max_output_tokens = config["max_output_tokens"]
        temperature = slot["temperature"]

        def _post(self, path, body):
            require(path == "/chat/completions", "Native model route changed")
            captures.append(body)
            raise CaptureStop()

    try:
        LLMClient._complete_chat(NativeCapture(), native_input["system"],
                                native_input["conversation"], native_input["tools"])
    except CaptureStop:
        pass
    require(len(captures) == 1, "Native serialization did not yield exactly one request")
    request = {**captures[0], "seed": slot["generation_seed"]}
    wire = Path(str(prefix) + "-request.bin")
    if wire.exists():
        same(json.loads(wire.read_bytes()), request, "Native serialized model request differs")
        require(wire.read_bytes() == json.dumps(request, allow_nan=False).encode("utf-8"),
                "Exact model request wire serializer differs")
    if terminal["dispatches"]:
        require(wire.exists(), "Model dispatch lacks request bytes")
        audit_context(load(str(prefix) + "-context.json"), request, config["runtime"],
                      output_tokens=config["max_output_tokens"])
    response = Path(str(prefix) + "-response.bin")
    if not response.exists():
        require(terminal["returned"] is False and terminal["usage"] is None,
                "Missing model response was treated as returned or known usage")
        return None, terminal
    require(terminal["dispatches"] == 1, "Response exists without generation dispatch")
    raw, meta = response.read_bytes(), load(str(prefix) + "-response-meta.json")
    require(meta["body_sha256"] == hashlib.sha256(raw).hexdigest(), "Raw response hash differs")
    if meta["status"] != 200:
        require(terminal["returned"] is False and terminal["usage"] is None,
                "HTTP error counted as returned completion or parsed usage")
        return None, terminal
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        require(terminal["returned"] is False and terminal["usage"] is None,
                "Malformed response was treated as returned or metered")
        return None, terminal
    if not isinstance(payload, dict):
        require(terminal["returned"] is False and terminal["usage"] is None,
                "Non-object response was counted as a completion")
        return None, terminal
    same(terminal["usage"], _usage(payload), "Model usage availability/counts differ")

    class NativeResponse(NativeCapture):
        def _post(self, path, body):
            same({**body, "seed": slot["generation_seed"]}, request, "Native parse reconstruction differs")
            return payload, 0.0

    try:
        turn = LLMClient._complete_chat(NativeResponse(), native_input["system"],
                                      native_input["conversation"], native_input["tools"])
    except Exception:
        require(terminal["returned"] is False, "Native parser rejects purported returned completion")
        return None, terminal
    require(terminal["returned"] is True, "Native parser succeeds but saved terminal claims a parse failure")
    if "native_usage_aggregate" in terminal:
        same(terminal["native_usage_aggregate"], turn.usage.as_dict(), "Native usage aggregation differs")
    return turn, terminal


def validate_model_journal(records, terminals, max_requests):
    records = [row for row in records if row.get("event") not in ("client_ready", "expanded_client_ready")]
    position = 0
    for number, terminal in enumerate(terminals, 1):
        require(position < len(records), "Model invocation journal lacks start")
        start = records[position]
        require(start.get("event") == "request_start" and start.get("invocation") == number,
                "Model invocation starts differ or are not serial")
        position += 1
        dispatched = position < len(records) and records[position].get("event") == "before_dispatch"
        if dispatched:
            require(records[position].get("invocation") == number
                    and records[position].get("dispatches") == 1, "Model dispatch identity differs")
            position += 1
        require(position < len(records), "Model invocation journal lacks terminal")
        ending = records[position]
        require(ending.get("event") == ("request_return" if terminal["returned"] else "request_error")
                and ending.get("invocation") == number, "Model invocation terminal differs")
        require(terminal["dispatches"] == int(dispatched), "Model terminal/journal dispatch mismatch")
        if number > max_requests:
            require(not dispatched and not terminal["returned"], "Cap-refused invocation dispatched")
        position += 1
    require(position == len(records), "Unused model journal events")


def audit_episode(directory, slot, *, certificate_checker=None, work_limits=None,
                  expected_limits=None, expected_model=None):
    """Audit one sealed returned episode; caller binds the exact protocol row.

    The optional checker receives (native_runtime, completed_policy_record,
    earlier_policy_records, earlier_interventions). It must reconstruct public
    certificate inputs, not merely trust self-contained certificate assertions.
    A measured obligation arm cannot pass without this checker.
    """
    from limbo import agent
    from limbo.llm import LLMError

    directory = Path(directory)
    before = binding(directory / "manifest.json")
    verify_manifest(directory)
    saved = load(directory / "native-result.json")
    same(saved["spec"], slot["spec"], "Saved native specification differs from scheduled slot")
    for filename, expected in (("planned-slot.json", slot), ("specification.json", slot["spec"])):
        if (directory / filename).exists():
            same(load(directory / filename), expected, "Bound planned slot/specification differs")
    require(slot["spec"]["human_available"] is False, "Human-enabled episode is outside study")
    model_dir = directory / "model"
    config = load(model_dir / "expanded-client-config.json")
    require(config["seed"] == slot["generation_seed"]
            and config["temperature"] == slot["temperature"]
            and config["automatic_http_retries"] == 0
            and config["independent_offline_template_tokenizer_parity"] is False,
            "Expanded model config differs from prospective slot")
    require(config["runtime"]["model"] == slot["spec"]["model"], "Runtime model alias differs")
    if expected_limits is not None:
        require(config["max_requests"] == expected_limits["max_requests"]
                and config["max_output_tokens"] == expected_limits["max_output_tokens"],
                "Model budget differs from frozen protocol")
        work_limits = expected_limits["work"]
    if expected_model is not None:
        require(config["runtime"]["context_tokens"] == expected_model["context_tokens"]
                and config["runtime"]["model_blob_sha256"] == expected_model["weights"]["sha256"],
                "Runtime context/weights differ from frozen model")
    policy_records = jsonl(directory / "policy.jsonl")
    if (directory / "policy-starts.jsonl").exists():
        starts = jsonl(directory / "policy-starts.jsonl")
        expected_starts = [{"schema": POLICY_SCHEMA, "sequence": row["sequence"],
            "name": row["name"], "args": row["args"], "clock_before": row["clock_before"],
            "event": "policy_start"} for row in policy_records]
        same(starts, expected_starts, "Policy start/completion journal pairing differs")
    if slot["arm"] in ("obligation_shield", "no_unkeyed_repeat"):
        if certificate_checker is None:
            certificate_checker = PublicCertificateChecker(slot["arm"], saved["episode_id"])
    policy = ScriptedPolicy(slot["arm"], policy_records, checker=certificate_checker)
    model_terminals = []
    model_validation_errors = []
    terminal_paths = sorted(model_dir.glob("*-terminal.json"))
    require(len(terminal_paths) <= config["max_requests"] + 1, "Model invocation cap exceeded")

    class ReplayClient:
        protocol = "chat"

        def complete(self, system, conversation, tools):
            try:
                turn, terminal = audit_model_call(model_dir, len(model_terminals) + 1,
                    {"system": system, "conversation": conversation, "tools": tools}, slot, config)
            except BaseException as exc:
                model_validation_errors.append(exc)
                raise
            model_terminals.append(terminal)
            if turn is None:
                require(saved["stop_reason"] == "llm_error"
                        and saved["error"].startswith("LLMError: "), "Missing native LLM failure disposition")
                raise LLMError(saved["error"][len("LLMError: "):], retryable=False)
            return turn

    original = agent.make_policy

    def factory(name, episode_id):
        require(name == slot["arm"] and episode_id == saved["episode_id"], "Native policy identity differs")
        return policy

    agent.make_policy = factory
    try:
        with no_network(), replay_instrumentation(work_limits) as observed:
            replay = agent.run_episode(agent.EpisodeSpec(**slot["spec"]), client=ReplayClient())
            if model_validation_errors:
                raise ValueError("Model replay validation failed inside native orchestration") from model_validation_errors[0]
            policy.assert_consumed()
            same(jsonl(directory / "runtime.jsonl"), observed["events"], "Native operation replay differs")
            same(load(directory / "world.json"), {"initial": observed["initial"],
                "final": snapshot(observed["rt"].world)}, "Native world/ledger/RNG replay differs")
            if slot["arm"] in ("obligation_shield", "no_unkeyed_repeat"):
                audit_policy_evidence(observed["rt"], jsonl(directory / "policy-evidence.jsonl"),
                                      policy.interventions)
    finally:
        agent.make_policy = original
    require(len(model_terminals) == len(terminal_paths), "Unused/missing model artifacts")
    validate_model_journal(jsonl(model_dir / "model-calls.jsonl"), model_terminals, config["max_requests"])
    # Physical wall time and generation latency are descriptive measurements.
    excluded = {"wall_s", "llm_latency_s"}
    expected = {k: v for k, v in saved.items() if k not in excluded}
    actual = {k: v for k, v in replay.items() if k not in excluded}
    if saved["stop_reason"] == "harness_error":
        require(type(saved["error"]) is str and type(replay["error"]) is str,
                "Missing native harness error")
        expected["error"], actual["error"] = saved["error"].split("\n", 1)[0], replay["error"].split("\n", 1)[0]
    same(expected, actual,
         "Native orchestration, conversation, physical effects or grade differs")
    verify_manifest(directory)
    same(binding(directory / "manifest.json"), before, "Episode changed during audit")
    counts = Counter(event["op"] for event in observed["events"] if event["event"] == "enter")
    normal = saved["error"] is None and saved["stop_reason"] not in ("harness_error", "llm_error")
    usage = {}
    for name in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
        values = [(item.get("usage") or {}).get(name, {}).get("value") for item in model_terminals]
        usage[name] = {"known_total": sum(value for value in values if value is not None),
                       "unknown_invocations": sum(value is None for value in values),
                       "complete": all(value is not None for value in values)}
    return {"schema": SCHEMA, "passed": True, "slot": slot["slot"], "arm": slot["arm"],
        "model_id": slot["model_id"], "generation_seed": slot["generation_seed"],
        "grade_available": True, "normal_execution_return": normal,
        "native_grade": saved["grade"], "native_stop_reason": saved["stop_reason"],
        "model_invocations": len(model_terminals),
        "model_dispatches": sum(item["dispatches"] for item in model_terminals),
        "work": dict(counts), "usage": usage, "episode_manifest": before,
        "certificate_count": getattr(certificate_checker, "certificates", None),
        "receipt_count": getattr(certificate_checker, "receipts", None),
        "scope": {"independent_native_physical_replay": True,
            "independent_measured_policy_execution": False,
            "scripted_saved_policy_observations": True,
            "public_input_certificate_checker_used": certificate_checker is not None,
            "saved_provider_render_token_consistency": True,
            "independent_template_or_tokenizer_reconstruction": False,
            "human_or_network_used": False,
            "descriptive_harness_traceback_reconstructed": False,
            "SDK_execution_repeated": False}}
