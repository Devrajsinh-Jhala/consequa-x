"""Standard-library reconstruction of declared public-data dispatch certificates.

This checker imports no policy, SDK, native runtime, task, or evaluator. It
checks arithmetic over supplied evidence, not authenticity or source semantics.
An auditor must reconstruct every supplied attempt/report from actual saved
calls; a self-consistent certificate alone cannot establish those inputs true.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math

SCHEMA = "conseqax-obligation-decision-v1"
MODES = ("obligation_shield", "no_unkeyed_repeat")
CONTRACT_FIELDS = ("write", "idempotent", "supports_key", "batch_field", "identity")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plain(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) in (list, tuple):
        return [plain(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: plain(item) for key, item in value.items()}
    raise ValueError("Certificate inputs must be finite plain JSON data")


def canonical(value):
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def describe_request(tool, args, contract):
    require(type(tool) is str and type(args) is dict, "A tool and public argument dictionary are required")
    require(type(contract) is dict and set(CONTRACT_FIELDS) == set(contract), "Public contract inventory differs")
    for key in ("write", "idempotent", "supports_key"):
        require(type(contract[key]) is bool, "Public capability flags must be boolean")
    require(contract["batch_field"] is None or type(contract["batch_field"]) is str,
            "Batch field must be a declared public string or null")
    args = plain(args)
    key = args.get("idempotency_key")
    require(key is None or type(key) is str, "A provider key must be a string or null")
    key = key or None
    business = {name: value for name, value in args.items() if name != "idempotency_key"}
    payload = digest(business)
    identity = contract["identity"]
    intent = [tool, identity] if identity is not None else [tool, "full_payload", payload]
    batch_field = contract["batch_field"]
    scope, components = None, []
    if tool in ("db_insert", "db_insert_many"):
        field = "row" if tool == "db_insert" else "rows"
        rows = [business[field]] if tool == "db_insert" and field in business else business.get(field, [])
        if type(rows) is list:
            scope = digest(["data_insert", {name: value for name, value in business.items() if name != field}])
            components = [digest(row) for row in rows]
    elif batch_field is not None and type(business.get(batch_field)) is list:
        scope = digest(["batch:" + tool, {name: value for name, value in business.items() if name != batch_field}])
        components = [digest(row) for row in business[batch_field]]
    return {"tool": tool, "intent_key": digest(intent), "payload_digest": payload, "key": key,
            "key_supported": contract["supports_key"], "idempotent": contract["idempotent"],
            "component_scope": scope, "components": components}


def related(current, attempt):
    overlap = (current["component_scope"] is not None
        and current["component_scope"] == attempt["component_scope"]
        and bool(Counter(current["components"]) & Counter(attempt["components"])))
    shared_key = (current["tool"] == attempt["tool"] and current["key"] is not None
                  and current["key"] == attempt["key"])
    return current["intent_key"] == attempt["intent_key"] or overlap or shared_key


def positive(attempt):
    return attempt["disposition"] == "success" or any(report["status"] == "found" for report in attempt["reports"])


def positive_components(attempt):
    """Reported component membership, never an exact count of physical effects."""
    if positive(attempt):
        return Counter(attempt["components"])
    present = Counter()
    for report in attempt["reports"]:
        if report["status"] == "partial" and type(report["detail"].get("present_rows")) is list:
            observed = Counter(digest(row) for row in report["detail"]["present_rows"])
            # Public native matching can reuse one physical row for multiple
            # identical requested values. These are obligation labels only.
            present |= observed & Counter(attempt["components"])
    return present


def validate_attempt(attempt):
    require(type(attempt) is dict and type(attempt.get("attempt_id")) is str, "Missing prior attempt identity")
    for key in ("tool", "payload_digest", "intent_key"):
        require(type(attempt.get(key)) is str, "Malformed prior attempt: " + key)
    for key in ("key_supported", "idempotent"):
        require(type(attempt.get(key)) is bool, "Malformed prior capability")
    require(attempt.get("key") is None or type(attempt["key"]) is str, "Malformed prior provider key")
    require(type(attempt.get("components")) is list and all(type(item) is str for item in attempt["components"]),
            "Malformed component multiset")
    require(attempt.get("component_scope") is None or type(attempt["component_scope"]) is str,
            "Malformed component scope")
    require(attempt.get("disposition") in ("success", "unknown", "terminal_no_effect"), "Unknown attempt disposition")
    observation = attempt.get("observation")
    require(type(observation) is dict, "Prior attempt lacks its actual observation")
    expected = "success" if observation.get("ok") is True else (
        "terminal_no_effect" if observation.get("terminal_not_committed") is True else "unknown")
    require(expected == attempt["disposition"], "Disposition was not supported by the public response")
    require(type(attempt.get("args")) is dict and type(attempt.get("reports")) is list, "Malformed prior public evidence")
    require(type(attempt.get("t_call")) in (int, float) and attempt["t_call"] >= 0,
            "Malformed dispatch time")
    business = {key: value for key, value in attempt["args"].items() if key != "idempotency_key"}
    require(attempt["payload_digest"] == digest(business), "Prior payload digest disagrees with its arguments")
    require(attempt["key"] == (attempt["args"].get("idempotency_key") or None), "Prior provider key disagrees")
    for report in attempt["reports"]:
        require(report.get("attempt_id") == attempt["attempt_id"] and report.get("t_call") == attempt.get("t_call"),
                "Public report is linked to another attempt")
        require(type(report.get("status")) is str and type(report.get("detail")) is dict,
                "Malformed public verification")
        require(type(report.get("t_observed")) in (int, float)
                and report["t_observed"] >= report["t_call"], "Invalid public verification time")


def counterexample(inputs, decision):
    """A contract-level indistinguishable-prefix witness, never observed truth."""
    if decision["dispatch"] or inputs["mode"] != "obligation_shield":
        return None
    current = describe_request(inputs["tool"], inputs["args"], inputs["contract"])
    if inputs["contract"]["idempotent"] or current["key"] is not None:
        return None
    if any(positive(item) or any(report["status"] == "partial" for report in item["reports"])
           for item in inputs["related_attempts"]):
        return None
    for attempt in inputs["related_attempts"]:
        if (attempt["disposition"] == "unknown" and attempt["key"] is None and not attempt["idempotent"]
                and attempt["tool"] == inputs["tool"] and attempt["payload_digest"] == current["payload_digest"]
                and all(report["status"] in ("absent", "unknown", "unverifiable") for report in attempt["reports"])):
            return {"schema": "conseqax-obligation-late-commit-witness-v1",
                "scope": "Symbolic provider continuations compatible with admitted public capabilities; not observed native fault truth",
                "prior_attempt_id": attempt["attempt_id"], "relative_observed_prefix_end": 0,
                "assumptions": ["non_idempotent", "no_shared_honored_key", "no_terminal_no_effect_guarantee",
                                "no_admitted_inflight_upper_bound"],
                "worlds": [{"name": "prior_never_commits", "prior_commit_times": [],
                            "retry_commit_times": [1], "matching_effects_after_time_2": 1},
                           {"name": "prior_commits_late", "prior_commit_times": [2],
                            "retry_commit_times": [1], "matching_effects_after_time_2": 2}]}
    return None


def recompute_decision(inputs):
    inputs = plain(inputs)
    require(type(inputs) is dict and inputs.get("mode") in MODES, "Unknown obligation mode")
    require(set(inputs) == {"mode", "tool", "args", "contract", "related_attempts", "current_report"},
            "Decision input inventory differs")
    current = describe_request(inputs["tool"], inputs["args"], inputs["contract"])
    attempts = inputs["related_attempts"]
    require(type(attempts) is list, "Prior attempts must remain a list")
    for attempt in attempts:
        validate_attempt(attempt)
        require(related(current, attempt), "Unrelated prior attempt was supplied")
    require(len({item["attempt_id"] for item in attempts}) == len(attempts), "Prior attempt identity duplicated")
    report = inputs["current_report"]
    if report is not None:
        require(type(report) is dict and type(report.get("detail")) is dict
                and type(report.get("status")) is str and type(report.get("t_observed")) in (int, float),
                "Malformed current public report")
        require(any(report == item for attempt in attempts for item in attempt["reports"]),
                "Current public report is not retained evidence")
    ids = [item["attempt_id"] for item in attempts]
    def result(dispatch, reason):
        answer = {"dispatch": dispatch, "reason": reason, "prior_attempt_ids": ids}
        answer["counterexample"] = counterexample(inputs, answer)
        return answer
    if not inputs["contract"]["write"]:
        return result(True, "read_only")
    if not attempts:
        return result(True, "first_dispatch")
    same_payload = all(item["tool"] == inputs["tool"] and item["payload_digest"] == current["payload_digest"]
                       for item in attempts)
    same_key = (current["key_supported"] and current["key"] is not None and same_payload
        and all(item["key_supported"] and item["key"] == current["key"] for item in attempts))
    if inputs["mode"] == "no_unkeyed_repeat":
        return result(bool(same_key), "same_key_same_payload" if same_key else "no_unkeyed_repeat")
    if any(item["payload_digest"] == current["payload_digest"] and item["tool"] == inputs["tool"]
           and positive(item) for item in attempts):
        return result(False, "prior_positive_same_payload")
    if same_key:
        return result(True, "same_key_same_payload")
    if inputs["contract"]["idempotent"] and same_payload and all(item["idempotent"] for item in attempts):
        return result(True, "intrinsic_idempotent_same_payload")
    fresh = (type(report) is dict and report.get("status") == "absent"
        and report.get("attempt_id") in ids and report["detail"].get("available") is True
        and report["detail"].get("complete") is True
        and type(report["detail"].get("as_of")) in (int, float)
        and report["detail"].get("as_of") == report["t_observed"])
    if same_payload and fresh and all(item["disposition"] == "terminal_no_effect" for item in attempts):
        require(any(report == item for attempt in attempts for item in attempt["reports"]),
                "Fresh-absence report is not retained in prior evidence")
        return result(True, "all_terminal_and_fresh_absence")
    if any(current["component_scope"] is not None and item["component_scope"] == current["component_scope"]
           and bool(Counter(current["components"]) & positive_components(item)) for item in attempts):
        return result(False, "positive_component_overlap")
    if not same_payload:
        return result(False, "related_payload_changed")
    return result(False, "unresolved_prior_attempt")


def check_certificate(certificate):
    require(type(certificate) is dict and set(certificate) == {"schema", "inputs", "decision"}
            and certificate["schema"] == SCHEMA, "Unsupported obligation certificate")
    expected = recompute_decision(certificate["inputs"])
    require(canonical(certificate["decision"]) == canonical(expected), "Obligation decision certificate disagrees")
    return True
