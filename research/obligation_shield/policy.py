"""Persistent public-evidence gate specialized to ambiguous write obligations.

This is a research policy, not a priority claim for generic certificates or
idempotency. It does not import task definitions, target predicates or native
world state. Public absence and read visibility lag never resolve an attempt.
"""
from __future__ import annotations

from collections import Counter
import hashlib

from .certificates import (SCHEMA, CONTRACT_FIELDS, canonical, describe_request,
                           plain, related, check_certificate, counterexample)


def _policy_choice(inputs):
    """Policy-side implementation, checked separately by the stdlib certificate module."""
    descriptor = describe_request(inputs["tool"], inputs["args"], inputs["contract"])
    history = inputs["related_attempts"]
    ids = [item["attempt_id"] for item in history]
    def answer(allowed, reason):
        decision = {"dispatch": allowed, "reason": reason, "prior_attempt_ids": ids}
        decision["counterexample"] = counterexample(inputs, decision)
        return decision
    if not inputs["contract"]["write"]:
        return answer(True, "read_only")
    if not history:
        return answer(True, "first_dispatch")
    exact = all(item["tool"] == inputs["tool"] and item["payload_digest"] == descriptor["payload_digest"] for item in history)
    keyed = (exact and descriptor["key_supported"] and bool(descriptor["key"])
        and all(item["key_supported"] and item["key"] == descriptor["key"] for item in history))
    if inputs["mode"] == "no_unkeyed_repeat":
        return answer(bool(keyed), "same_key_same_payload" if keyed else "no_unkeyed_repeat")
    for item in history:
        positive = item["disposition"] == "success" or any(report["status"] == "found" for report in item["reports"])
        if positive and item["tool"] == inputs["tool"] and item["payload_digest"] == descriptor["payload_digest"]:
            return answer(False, "prior_positive_same_payload")
    if keyed:
        return answer(True, "same_key_same_payload")
    if exact and inputs["contract"]["idempotent"] and all(item["idempotent"] for item in history):
        return answer(True, "intrinsic_idempotent_same_payload")
    current = inputs["current_report"]
    if (exact and current is not None and current["status"] == "absent"
            and current["attempt_id"] in ids and current["detail"].get("available") is True
            and current["detail"].get("complete") is True
            and type(current["detail"].get("as_of")) in (int, float)
            and current["detail"].get("as_of") == current["t_observed"]
            and all(item["disposition"] == "terminal_no_effect" for item in history)):
        return answer(True, "all_terminal_and_fresh_absence")
    for item in history:
        if descriptor["component_scope"] is None or descriptor["component_scope"] != item["component_scope"]:
            continue
        observed = Counter()
        if item["disposition"] == "success" or any(report["status"] == "found" for report in item["reports"]):
            observed.update(item["components"])
        else:
            for report in item["reports"]:
                if report["status"] == "partial" and type(report["detail"].get("present_rows")) is list:
                    from .certificates import digest
                    observed |= Counter(digest(row) for row in report["detail"]["present_rows"]) & Counter(item["components"])
        if observed & Counter(descriptor["components"]):
            return answer(False, "positive_component_overlap")
    return answer(False, "unresolved_prior_attempt" if exact else "related_payload_changed")


class ObligationShield:
    """One serial episode, one explicit PublicRuntimeBoundary-compatible view."""
    prompt_variant = "vanilla"
    reflect = False

    def __init__(self, public, episode_id, *, journal=None, mode="obligation_shield"):
        if mode not in ("obligation_shield", "no_unkeyed_repeat") or type(episode_id) is not str:
            raise ValueError("Explicit obligation mode and episode identity are required")
        self.public, self.episode_id, self.name = public, episode_id, mode
        self._journal = journal if journal is not None else lambda event: None
        self.attempts, self.interventions = [], []
        self._receipt_sequence = 0
        self._failed = False
        self._tool_names = set(public.tool_metadata())

    def _record(self, event):
        if self._failed:
            raise RuntimeError("Obligation audit sink previously failed")
        event = plain(event)
        self.interventions.append(event)
        try:
            self._journal(event)
        except BaseException:
            self._failed = True
            raise

    def _verify(self, attempt):
        from research.limbo_agent.policy import make_public_receipt, receipt_public_report
        native = self.public.verify(attempt["tool"], attempt["args"], attempt["t_call"], truth=False)
        now = self.public.clock
        self._receipt_sequence += 1
        receipt = make_public_receipt(self.episode_id, self._receipt_sequence, attempt["tool"],
                                     attempt["args"], attempt["t_call"], now, native)
        restored = receipt_public_report(receipt)
        report = {"attempt_id": attempt["attempt_id"], **restored,
                  "t_call": attempt["t_call"], "t_observed": now}
        attempt["reports"].append(plain(report))
        self._record({"kind": "package_receipt", "operation": "package_receipt", "phase": "return",
                      "receipt_sequence": self._receipt_sequence, "receipt": receipt,
                      "attempt_id": attempt["attempt_id"]})
        return report

    def execute(self, name, args):
        if self._failed:
            raise RuntimeError("Obligation audit sink previously failed")
        args = plain(args)
        if name not in self._tool_names:
            # Native finish and unknown-tool observations retain their native
            # behavior without manufacturing a nonexistent tool contract.
            return self.public.execute(name, args, source="agent")
        full_contract = self.public.contract(name, args)
        contract = {key: plain(full_contract[key]) for key in CONTRACT_FIELDS}
        if not contract["write"]:
            return self.public.execute(name, args, source="agent")
        before = describe_request(name, args, contract)
        if contract["supports_key"] and not args.get("idempotency_key"):
            raw = canonical([self.episode_id, name, before["intent_key"], before["payload_digest"]])
            args["idempotency_key"] = "cx-obligation-" + hashlib.sha256(raw).hexdigest()[:24]
            self._record({"kind": "auto_key", "tool": name, "key": args["idempotency_key"]})
        descriptor = describe_request(name, args, contract)
        history = [item for item in self.attempts if related(descriptor, item)]
        inputs = {"mode": self.name, "tool": name, "args": args, "contract": contract,
                  "related_attempts": plain(history), "current_report": None}
        preliminary = _policy_choice(inputs)
        # Capability-safe exact replay needs no paid read. Other unresolved
        # repeats get one real public verification; no SLA-derived finality.
        if (self.name == "obligation_shield" and history
                and preliminary["reason"] not in ("prior_positive_same_payload", "same_key_same_payload",
                                                   "intrinsic_idempotent_same_payload", "positive_component_overlap")):
            candidate = next((item for item in history if item["disposition"] != "success"), None)
            if candidate is not None:
                inputs["current_report"] = self._verify(candidate)
                inputs["related_attempts"] = plain(history)
        decision = _policy_choice(inputs)
        certificate = {"schema": SCHEMA, "inputs": plain(inputs), "decision": decision}
        check_certificate(certificate)
        self._record({"kind": "obligation_decision", "certificate": certificate})
        if not decision["dispatch"]:
            # A historic success/cache entry is never a fresh service response,
            # a current-state verdict, ownership proof or a settlement claim.
            positive = decision["reason"] == "prior_positive_same_payload"
            result = {"ok": positive, "obligation_shield": {"dispatch": False,
                "reason": decision["reason"], "cache_scope": "historical public report for one episode intent",
                "current_state": "unknown", "origin": "unknown", "settled_all_attempts": False},
                "reliability_guard": "Request NOT sent. Persistent earlier obligation evidence retained; "
                    "current absence and visibility lag do not establish request finality."}
            if positive:
                result["result"] = {"prior_matching_intent_reported_positive": True}
            else:
                result["error"] = {"type": "guard_blocked", "message": "Prior operation remains unresolved or overlaps a retained obligation."}
            return result
        started = self.public.clock
        try:
            observation = plain(self.public.execute(name, args, source="agent"))
        except BaseException:
            # Dispatch may have reached the service. A caller must not reuse
            # this in-memory policy after a missing response/journal boundary.
            self._failed = True
            raise
        # Native public timestamps, not hidden world events, bind the attempt.
        dispatched_at = self.public.last_dispatch_start
        if dispatched_at is None:
            dispatched_at = started
        disposition = "success" if observation.get("ok") is True else (
            "terminal_no_effect" if observation.get("terminal_not_committed") is True else "unknown")
        attempt = {"attempt_id": self.episode_id + ":attempt:" + str(len(self.attempts) + 1),
            "tool": name, "args": plain(args), **descriptor, "t_call": dispatched_at,
            "disposition": disposition, "observation": observation, "reports": []}
        self.attempts.append(attempt)
        self._record({"kind": "obligation_attempt", "attempt": plain(attempt)})
        return observation


class NativeObligationPolicy:
    prompt_variant = "vanilla"
    reflect = False

    def __init__(self, episode_id, *, journal=None, limits=None, mode="obligation_shield"):
        from research.limbo_agent.boundary import BoundaryLimits
        self.episode_id, self.name = episode_id, mode
        self._journal = journal if journal is not None else lambda event: None
        self._limits = limits if limits is not None else BoundaryLimits(96, 64, 64, 172800)
        self._policy = None
        self._runtime_id = None

    @property
    def interventions(self):
        return self._policy.interventions if self._policy is not None else []

    def execute(self, rt, name, args):
        from research.limbo_agent.boundary import bind_public_runtime
        if self._policy is None:
            public = bind_public_runtime(rt, limits=self._limits, journal=self._journal)
            self._policy = ObligationShield(public, self.episode_id, journal=self._journal, mode=self.name)
            self._runtime_id = id(rt)
        elif id(rt) != self._runtime_id:
            raise ValueError("An obligation policy cannot span native runtimes")
        return self._policy.execute(name, args)


def make_policy(name, episode_id, *, journal=None, limits=None):
    if name in ("obligation_shield", "no_unkeyed_repeat"):
        return NativeObligationPolicy(episode_id, journal=journal, limits=limits, mode=name)
    if name not in ("vanilla", "guard", "sdk_retry3", "rules", "vbr"):
        raise ValueError("Only declared non-oracle comparison policies are allowed")
    from limbo.policies import make_policy as native_factory
    return native_factory(name, episode_id)
