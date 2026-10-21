"""Matched public-readback wrappers around the pinned native tau LLMAgent.

This module never loads tasks, gold actions, databases, or evaluation criteria.
Native calls are emitted to the orchestrator, not executed through Tool._func.
Importing the module does not import tau2 or ConsequaX or generate a model call.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import time
from typing import Callable

ARMS = ("B", "C", "R", "G")
WRITES = frozenset({
    "book_reservation", "cancel_reservation", "send_certificate",
    "update_reservation_baggages", "update_reservation_flights",
    "update_reservation_passengers",
})
COMMON_INSTRUCTION = """Research recovery instruction (the complete native policy still applies):
Mutation proposals receive actual native public reads before and after dispatch.
Use the raw read results to check requested fields. An acknowledgement alone is
not proof of the requested state, action origin, payment settlement, or durability.
If results are missing or unclear, explain uncertainty and avoid claiming success.
Do not assume a repeated mutation is idempotent. Do not invent tool arguments.
""".strip()
SCOPE = ("Requested public record fields only; not native task success, policy "
         "compliance, settlement, causal origin, or real-world durability.")


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def operation_key(episode_id: str, name: str, arguments: dict) -> str:
    """Episode-wide exact-payload identity, never a model tool-call identifier.

    This conservative guard does not recognize a later semantically new intent.
    User turns do not clear an unresolved or completed identical operation.
    """
    return sha256(canonical({"episode": episode_id, "domain": "airline",
                             "tool": name, "arguments": arguments}).encode()).hexdigest()


def resource_key(name: str, arguments: dict) -> tuple[str, str]:
    if "reservation_id" in arguments:
        return "reservation", str(arguments["reservation_id"])
    if "user_id" in arguments:
        return "user", str(arguments["user_id"])
    return "unsupported", name


def read_plan(name: str, arguments: dict) -> list[dict]:
    """Only documented native lookup tools, using the proposed public identity."""
    if name not in WRITES:
        return []
    if name in {"book_reservation", "send_certificate"}:
        if not isinstance(arguments.get("user_id"), str):
            return []
        return [{"name": "get_user_details", "arguments": {"user_id": arguments["user_id"]}}]
    if not isinstance(arguments.get("reservation_id"), str):
        return []
    return [{"name": "get_reservation_details",
             "arguments": {"reservation_id": arguments["reservation_id"]}}]


def parsed_read(message: dict) -> dict:
    """Errors, non-JSON and non-object values never become complete evidence."""
    if message.get("error") or not isinstance(message.get("content"), str):
        return {"available": False, "value": None}
    try:
        value = json.loads(message["content"])
    except (ValueError, TypeError):
        return {"available": False, "value": None}
    return {"available": isinstance(value, dict), "value": value}


def compile_contract(name: str, arguments: dict, before: dict) -> dict:
    """Compile intended record fields without task/gold/DB or ACK semantics."""
    plan = read_plan(name, arguments)
    contract = {"tool": name, "arguments": deepcopy(arguments), "read_plan": plan,
                "scope": SCOPE, "supported": name in WRITES, "checks": []}
    if not plan or not before.get("available"):
        contract["supported"] = False
        contract["unknown_reason"] = "Unsupported tool or unavailable preflight read"
        return contract
    value = before["value"]
    if not isinstance(value, dict):
        contract["supported"] = False
        contract["unknown_reason"] = "Preflight value is not an object"
        return contract
    identity = plan[0]["arguments"]
    if not all(value.get(k) == v for k, v in identity.items()):
        contract["supported"] = False
        contract["unknown_reason"] = "Preflight identity mismatch"
        return contract
    try:
        if name == "cancel_reservation":
            checks = [{"field": "status", "expected": "cancelled"}]
        elif name == "update_reservation_baggages":
            checks = [{"field": k, "expected": arguments[k]}
                      for k in ("total_baggages", "nonfree_baggages")]
        elif name == "update_reservation_passengers":
            checks = [{"field": "passengers", "expected": arguments["passengers"]}]
        elif name == "update_reservation_flights":
            checks = [{"field": "cabin", "expected": arguments["cabin"]},
                      {"field": "flights", "projection": ["flight_number", "date"],
                       "expected": arguments["flights"]}]
        elif name == "send_certificate":
            checks = [{"field": "payment_methods", "new_mapping": True,
                       "before_keys": sorted(value["payment_methods"]),
                       "expected": {"source": "certificate", "amount": arguments["amount"]}}]
        else:
            fields = ("user_id", "origin", "destination", "flight_type", "cabin",
                      "passengers", "total_baggages", "nonfree_baggages", "insurance")
            checks = [{"field": "reservations", "new_reservation": True,
                       "before_ids": list(value["reservations"]),
                       "expected": {k: arguments[k] for k in fields},
                       "flights": arguments["flights"]}]
        contract["checks"] = checks
    except (KeyError, TypeError):
        contract["supported"] = False
        contract["unknown_reason"] = "Missing public preflight or proposed payload fields"
    return contract


def _project(rows, fields):
    if not isinstance(rows, (list, tuple)):
        raise TypeError("Expected an ordered native list")
    return [{k: row[k] for k in fields} for row in rows]


def field_status(contract: dict, after: dict, details: list[dict]) -> tuple[str, str]:
    """Transparent application predicate; origin is deliberately not evaluated."""
    if not contract.get("supported") or not after.get("available"):
        return "unknown", contract.get("unknown_reason", "Unavailable postflight read")
    value = after.get("value")
    if not isinstance(value, dict):
        return "unknown", "Postflight value is not an object"
    identity = contract["read_plan"][0]["arguments"]
    if not all(value.get(k) == v for k, v in identity.items()):
        return "unknown", "Postflight identity mismatch"
    matches = []
    try:
        for check in contract["checks"]:
            field = value[check["field"]]
            if check.get("new_mapping"):
                new = [v for k, v in field.items() if k not in check["before_keys"]]
                matches.append(len(new) == 1 and all(
                    new[0].get(k) == v for k, v in check["expected"].items()))
            elif check.get("new_reservation"):
                new_ids = [rid for rid in field if rid not in check["before_ids"]]
                rows = [d["value"] for d in details if d.get("available")]
                if len(rows) != len(new_ids) or {r["reservation_id"] for r in rows} != set(new_ids):
                    return "unknown", "Incomplete or mismatched newly listed reservation readbacks"
                matches.append(len(rows) == 1 and all(
                    rows[0].get(k) == v for k, v in check["expected"].items()) and
                    _project(rows[0]["flights"], ("flight_number", "date")) ==
                    _project(check["flights"], ("flight_number", "date")))
            elif check.get("projection"):
                matches.append(_project(field, check["projection"]) ==
                               _project(check["expected"], check["projection"]))
            else:
                matches.append(field == check["expected"])
    except (KeyError, TypeError, AttributeError):
        return "unknown", "Missing or malformed required public record fields"
    if not matches:
        return "unknown", "Empty field contract"
    return ("satisfied", "Requested public record fields match") if all(matches) else (
        "violated", "Requested public record fields differ")


def make_receipt(key: str, contract: dict, after: dict, details: list[dict],
                 *, registered_ms: int, observed_ms: int) -> dict:
    """Use the explicitly selected installed 2.1.1 verifier, never ACK truth."""
    import consequa_x as cx

    if cx.__version__ != "2.1.1":
        raise RuntimeError("Native research receipt requires explicitly selected ConsequaX 2.1.1")
    if observed_ms < registered_ms:
        raise ValueError("Native receipt requires post-dispatch monotonic ordering")
    status, reason = field_status(contract, after, details)
    action = cx.Action(action_id=key, actor="native_assistant", name=contract["tool"],
                       arguments=contract["arguments"], registered_at_ms=registered_ms,
                       contract=cx.OutcomeContract(contract_id=key + ":fields",
                           predicate="native_airline_public_fields", expected=contract,
                           deadline_ms=registered_ms, exact_count=None))
    observation = cx.Observation(observation_id=key + ":public_read", source="native_public_tool",
        observed_at_ms=observed_ms, as_of_ms=observed_ms,
        scope={"domain": "airline", "read_plan": contract["read_plan"]},
        records=({"after": after, "details": details},), available=after.get("available", False),
        complete=status != "unknown")

    class PublicFieldVerifier:
        def verify(self, action, observation):
            captured = observation.to_dict()["records"][0]
            actual_status, actual_reason = field_status(action.to_dict()["contract"]["expected"],
                captured["after"], captured["details"])
            if (observation.source != "native_public_tool" or not observation.available
                    or not observation.complete or observation.as_of_ms < action.registered_at_ms):
                actual_status, actual_reason = "unknown", "Unavailable, incomplete or unordered public read"
            return cx.VerificationResult(contract_id=action.contract.contract_id,
                action_id=action.action_id, status=cx.VerificationStatus(actual_status),
                observed_at_ms=observation.observed_at_ms, origin=cx.OriginStatus.UNKNOWN,
                evidence=(cx.Evidence(observation_id=observation.observation_id,
                    source=observation.source, as_of_ms=observation.as_of_ms,
                    details={"scope": SCOPE, "public_field_status": actual_status}),), reason=actual_reason)

    before_bytes = canonical({"action": action.to_dict(), "observation": observation.to_dict()})
    result = cx.verify(action, observation, verifier=PublicFieldVerifier())
    if before_bytes != canonical({"action": action.to_dict(), "observation": observation.to_dict()}):
        raise RuntimeError("Receipt verification changed public evidence")
    return {"schema": "conseqax-native-field-receipt-v1", "operation_key": key,
            "framework_version": cx.__version__, "action": action.to_dict(),
            "observation": observation.to_dict(), "verification": result.to_dict(), "scope": SCOPE,
            "time_base": "actual_monotonic_elapsed_ms",
            "deadline_scope": "Schema registration horizon only; predicate checks current post-return fields, not delivery by a deadline"}


class DuplicateGuard:
    """Fixed conservative episode history, with no privileged benchmark state."""
    def __init__(self):
        self.operations = {}

    def reason(self, key, resource):
        previous = self.operations.get(key)
        if previous and previous["status"] == "satisfied":
            return "Identical episode payload was already witnessed satisfied"
        if previous:
            return "Identical episode payload was dispatched; partial side effects cannot be excluded"
        if any(op["resource"] == resource and op["status"] == "unknown"
               for op in self.operations.values()):
            return "A mutation on this public resource remains unresolved"
        return None

    def dispatched(self, key, resource):
        self.operations[key] = {"resource": resource, "status": "unknown"}

    def resolved(self, key, status):
        self.operations[key]["status"] = status


def make_agent_factory(arm: str, episode_id: str,
                       event_sink: Callable[[dict], None] | None = None):
    """Return the pinned native registry's public factory signature.

    Call only after the harness establishes pinned tau source and installed
    ConsequaX 2.1.1 module origins. ``task`` in native factory kwargs is ignored.
    Parallel proposals containing mutations are refused as unsupported execution,
    not silently serialized or replaced by a successful trajectory.
    """
    if arm not in ARMS or not episode_id:
        raise ValueError("Expected arm B, C, R or G and a nonempty episode identifier")
    from tau2.agent.llm_agent import LLMAgent
    from tau2.data_model.message import (
        AssistantMessage, MultiToolMessage, SystemMessage, ToolCall, ToolMessage,
        UserMessage,
    )
    from tau2.utils.llm_utils import generate

    class MatchedNativeAgent(LLMAgent):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.events = []
            self.pending = None
            self.guard = DuplicateGuard()
            self.started_ns = time.monotonic_ns()
            self.call_counter = 0

        def emit_event(self, event, **data):
            record = {"schema": "conseqax-native-controller-event-v1", "index": len(self.events),
                      "arm": arm, "episode_id": episode_id, "event": event,
                      "monotonic_elapsed_ns": time.monotonic_ns() - self.started_ns, **deepcopy(data)}
            self.events.append(record)
            if event_sink is not None:
                event_sink(deepcopy(record))

        def get_init_state(self, message_history=None):
            if self.events or self.pending:
                raise RuntimeError("One native research agent instance per episode")
            state = super().get_init_state(message_history)
            state.system_messages.append(SystemMessage(role="system", content=COMMON_INSTRUCTION))
            return state

        def output(self, state, message):
            state.messages.append(message)
            self.emit_event("native_emit", message=message.model_dump(mode="json"))
            return message, state

        def issue_read(self, state, spec, phase):
            self.call_counter += 1
            call = ToolCall(id=f"cx-read-{self.call_counter}", name=spec["name"],
                            arguments=deepcopy(spec["arguments"]))
            self.pending["awaiting"] = {"id": call.id, "phase": phase}
            self.emit_event("read_dispatch", phase=phase, operation_key=self.pending["key"],
                            call=call.model_dump(mode="json"))
            return self.output(state, AssistantMessage(role="assistant", tool_calls=[call]))

        def dispatch_pending(self, state):
            pending = self.pending
            pending["contract"] = compile_contract(pending["call"].name,
                pending["call"].arguments, pending["before"])
            self.emit_event("contract", operation_key=pending["key"], contract=pending["contract"])
            pending["registered_ms"] = (time.monotonic_ns() - self.started_ns) // 1_000_000
            pending["awaiting"] = {"id": pending["call"].id, "phase": "mutation"}
            self.guard.dispatched(pending["key"], pending["resource"])
            self.emit_event("mutation_dispatch", operation_key=pending["key"],
                            call=pending["call"].model_dump(mode="json"))
            return self.output(state, pending["proposal"])

        def finish(self, state):
            pending = self.pending
            if arm == "B":
                self.emit_event("raw_public_capture", operation_key=pending["key"],
                    contract=pending["contract"], after=pending["after"], details=pending["details"])
                self.pending = None
                return
            if arm == "C":
                status, reason = field_status(pending["contract"], pending["after"], pending["details"])
                receipt = {"schema": "conseqax-native-classical-field-report-v1",
                           "operation_key": pending["key"], "scope": SCOPE,
                           "verification": {"status": status, "origin": "unknown", "reason": reason}}
            else:
                receipt = make_receipt(pending["key"], pending["contract"], pending["after"],
                    pending["details"], registered_ms=pending["registered_ms"],
                    observed_ms=(time.monotonic_ns() - self.started_ns) // 1_000_000)
            self.guard.resolved(pending["key"], receipt["verification"]["status"])
            self.emit_event("receipt", receipt=receipt, model_visible=arm in {"C", "R", "G"})
            if arm in {"C", "R", "G"}:
                state.system_messages.append(SystemMessage(role="system", content=
                    ("Derived classical public-field report (not task success):\n" if arm == "C" else
                     "Derived ConsequaX public-field receipt (not task success):\n") + canonical(receipt)))
            self.pending = None

        def generate_next_message(self, message, state):
            if isinstance(message, MultiToolMessage):
                incoming = message.tool_messages
            else:
                incoming = [message]
            for item in incoming:
                if isinstance(item, UserMessage) and item.is_audio:
                    raise ValueError("Native research wrapper is text only")
                state.messages.append(item)
                self.emit_event("native_input", message=item.model_dump(mode="json"))
            if self.pending:
                awaiting = self.pending["awaiting"]
                if len(incoming) != 1 or not isinstance(incoming[0], ToolMessage) or incoming[0].id != awaiting["id"]:
                    raise RuntimeError("Pending native call has no unique matching actual ToolMessage")
                result = parsed_read(incoming[0].model_dump(mode="json"))
                phase = awaiting["phase"]
                if phase == "pre":
                    self.pending["before"] = result
                    return self.dispatch_pending(state)
                if phase == "mutation":
                    self.pending["mutation_response"] = incoming[0].model_dump(mode="json")
                    if self.pending["plan"]:
                        return self.issue_read(state, self.pending["plan"][0], "post")
                    self.pending["after"] = {"available": False, "value": None}
                if phase == "post":
                    self.pending["after"] = result
                    if self.pending["call"].name == "book_reservation" and result.get("available"):
                        before_ids = self.pending["before"].get("value")
                        before_ids = before_ids if isinstance(before_ids, dict) else {}
                        old = before_ids.get("reservations", [])
                        ids = result["value"].get("reservations")
                        if isinstance(ids, list) and all(isinstance(rid, str) for rid in ids):
                            self.pending["detail_ids"] = [rid for rid in ids if rid not in old]
                    if self.pending["detail_ids"]:
                        rid = self.pending["detail_ids"].pop(0)
                        return self.issue_read(state, {"name": "get_reservation_details",
                            "arguments": {"reservation_id": rid}}, "detail")
                elif phase == "detail":
                    self.pending["details"].append(result)
                    if self.pending["detail_ids"]:
                        rid = self.pending["detail_ids"].pop(0)
                        return self.issue_read(state, {"name": "get_reservation_details",
                            "arguments": {"reservation_id": rid}}, "detail")
                self.finish(state)
            self.emit_event("model_input", system_messages=[m.model_dump(mode="json") for m in state.system_messages],
                            messages=[m.model_dump(mode="json") for m in state.messages])
            proposal = generate(model=self.llm, tools=self.tools,
                messages=state.system_messages + state.messages, call_name="agent_response", **self.llm_args)
            self.emit_event("model_proposal", proposal=proposal.model_dump(mode="json"))
            calls = proposal.tool_calls or []
            writes = [c for c in calls if c.name in WRITES]
            if writes and len(calls) != 1:
                self.emit_event("unsupported_parallel_mutation", proposal=proposal.model_dump(mode="json"))
                raise RuntimeError("Research wrapper refuses parallel mutation proposals")
            if not writes:
                return self.output(state, proposal)
            call = writes[0]
            key = operation_key(episode_id, call.name, call.arguments)
            resource = resource_key(call.name, call.arguments)
            reason = self.guard.reason(key, resource) if arm in {"C", "G"} else None
            if reason:
                self.emit_event("guard_block", operation_key=key, reason=reason,
                                proposal=proposal.model_dump(mode="json"))
                return self.output(state, proposal.model_copy(update={"tool_calls": None, "content":
                    "I have not repeated that action because its previous result is already "
                    "present or remains uncertain. Please clarify whether you intend a different "
                    "operation; I cannot safely assume this repeated request is idempotent."}))
            plan = read_plan(call.name, call.arguments)
            self.pending = {"key": key, "resource": resource, "proposal": proposal,
                "call": call, "plan": plan, "details": [], "detail_ids": [],
                "before": {"available": False, "value": None}}
            if not plan:
                return self.dispatch_pending(state)
            return self.issue_read(state, plan[0], "pre")

    def factory(tools, domain_policy, **kwargs):
        return MatchedNativeAgent(tools=tools, domain_policy=domain_policy,
                                  llm=kwargs.get("llm"), llm_args=kwargs.get("llm_args"))

    return factory
