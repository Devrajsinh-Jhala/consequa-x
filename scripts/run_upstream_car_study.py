"""Isolated, pinned CAR comparison on a scripted-simulator refund decision game.

No third-party source is vendored, no model is called, and no estimator in CAR is
patched. ``plan`` freezes the inputs; ``run`` requires that saved plan. The native
transport reruns deterministic payment glue to reconstruct public requests, while
only fresh calls of the declared policy consume the shared actual-call budget.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from copy import deepcopy
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
import gzip
import importlib
from importlib.metadata import PackageNotFoundError, version
import itertools
import json
import logging
import math
from multiprocessing import get_context
from pathlib import Path
import random
import subprocess
import sys
import time

from consequa_x.benchmark.decision_contrastive import contrastive_decisions, with_contrastive_interval
from consequa_x.benchmark.decision_shapley import shapley_decisions, with_shapley_intervals
from consequa_x.benchmark.evaluation import BudgetedPolicy, CallBudgetExceeded
from consequa_x.benchmark.interaction_mechanisms import INTERACTION_MECHANISMS
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.targets import episode_outcome
from consequa_x.models import AssessmentStatus, EventType, ResponseStatus, ToolResponse, to_dict
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, PolicyRequest, validate_reply


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_URL = "https://github.com/jaineet17/causal-agent-replay"
UPSTREAM_REVISION = "db90fa28b97164c35e7c524e4597b8cbdb3035af"
SCHEMA = "upstream-car-refund-comparison-v1"
ENGINES = ("upstream_car", "consequa_x")
METHODS = ("contrastive", "shapley")
MECHANISMS = tuple(INTERACTION_MECHANISMS)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def write_new_gzip(path, value):
    with Path(path).open("xb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as stream:
            stream.write(canonical(value) + b"\n")


@dataclass(frozen=True)
class StudyPlan:
    repeats: int = 64
    samples: int = 32
    pairs: int = 32
    endpoint_samples: int = 16
    seed: int = 70_000_000
    max_calls: int = 1200
    confidence: float = .95
    workers: int = 4
    mechanisms: tuple[str, ...] = MECHANISMS

    def __post_init__(self):
        for key, minimum in (("repeats", 1), ("samples", 2), ("pairs", 2),
                             ("endpoint_samples", 2), ("seed", 0), ("max_calls", 3)):
            if type(getattr(self, key)) is not int or getattr(self, key) < minimum:
                raise ValueError(f"{key} must be an integer >= {minimum}")
        if type(self.workers) is not int or not 1 <= self.workers <= 8:
            raise ValueError("workers must be an integer in 1..8")
        if (type(self.confidence) not in (int, float)
                or not math.isfinite(self.confidence) or not 0 < self.confidence < 1):
            raise ValueError("confidence must be finite and strictly between zero and one")
        if (type(self.mechanisms) is not tuple or not self.mechanisms
                or any(type(item) is not str or item not in MECHANISMS for item in self.mechanisms)
                or len(set(self.mechanisms)) != len(self.mechanisms)):
            raise ValueError("mechanisms must be a nonempty unique tuple of supported names")
        if self.seed + len(self.mechanisms) * self.repeats * 2 * self.stride > MAX_TRIAL_SEED:
            raise ValueError("Complete paired seed reservation exceeds MAX_TRIAL_SEED")

    @property
    def shapley_branches(self):
        return 2 * self.endpoint_samples + 8 * self.pairs

    @property
    def stride(self):
        return 1 + max(3 * self.samples, self.shapley_branches)


def target_for(mechanism):
    return ("action_linked_consequence" if mechanism.startswith("unknown-provenance")
            else "consequence")


def exact_reference(mechanism):
    """Independent finite Bernoulli enumeration, not estimator/replay output.

    Count exactly-one simulated refund. A factual selection+retry produces two
    refunds except with idempotency; an unselected positive contract is false.
    """
    item = INTERACTION_MECHANISMS[mechanism]
    p, q = Fraction(str(item.selection_probability)), Fraction(str(item.retry_probability))
    target = target_for(mechanism)
    values, unknown_mass = [], []
    for mask in range(8):
        bad = unknown = Fraction(0)
        for selected, retry in itertools.product((False, True), repeat=2):
            weight = (p if selected else 1 - p) * (q if retry else 1 - q)
            select_now, retry_now = bool(mask & 1) or selected, bool(mask & 2) or retry
            count = 0 if not select_now else (1 if item.use_idempotency or not retry_now else 2)
            missing = bool(item.read_lag_ms) or (
                target == "action_linked_consequence" and not item.include_provenance and count == 1)
            if missing:
                unknown += weight
            elif count != 1:
                bad += weight
        values.append(None if unknown else float(bad))
        unknown_mass.append(float(unknown))
    contrastive = [None if values[mask] is None or values[7] is None else values[mask] - values[7]
                   for mask in (0, 1, 3)]
    shares = None
    if all(value is not None for value in values):
        shares = [0., 0., 0.]
        for perm in itertools.permutations(range(3)):
            mask = 0
            for player in perm:
                nxt = mask | (1 << player)
                shares[player] += (values[nxt] - values[mask]) / 6
                mask = nxt
    negative = [index for index, effect in enumerate(contrastive) if effect is not None and effect < 0]
    return {"target": target, "coalition_bad_rates": values, "unknown_probabilities": unknown_mass,
            "contrastive": contrastive, "shapley": shares,
            "latest_population_rescue": max(negative) if negative and None not in contrastive else None,
            "population_locus_eligible": None not in contrastive,
            "endpoint_difference": None if values[0] is None or values[7] is None else values[7] - values[0],
            "reference_kind": "exact independent Bernoulli enumeration of simulated refund count"}


def trial_schedule(plan):
    rows = []
    for mechanism in plan.mechanisms:
        for replicate in range(plan.repeats):
            for method in METHODS:
                group = len(rows)
                factual_seed = plan.seed + group * plan.stride
                rows.append({"group_index": group, "mechanism": mechanism, "replicate": replicate,
                             "method": method, "factual_seed": factual_seed,
                             "continuation_seed": factual_seed + 1,
                             "permutation_seed": 210_000_000 + group,
                             "max_calls": 4 if mechanism.startswith("budget-") else plan.max_calls,
                             "target": target_for(mechanism)})
    return rows


def slots_for(plan, trial):
    slots = []
    def add(role, held, **extra):
        index = len(slots)
        slots.append({"index": index, "role": role, "held_indices": sorted(held),
                      "continuation_seed": trial["continuation_seed"] + index, **extra})
    if trial["method"] == "contrastive":
        for position in range(3):
            for sample in range(plan.samples):
                add("contrastive", range(position), decision_index=position, sample_index=sample)
    else:
        for role, held in (("endpoint_empty", ()), ("endpoint_full", (0, 1, 2))):
            for sample in range(plan.endpoint_samples):
                add(role, held, sample_index=sample)
        rng = random.Random(trial["permutation_seed"])
        for pair in range(plan.pairs):
            order = list(range(3))
            rng.shuffle(order)
            for name, walk in (("forward", order), ("reverse", list(reversed(order)))):
                for step in range(4):
                    add("walk", walk[:step], pair_index=pair, walk=name, step=step, sample_index=0)
    return slots


def bound_sources():
    paths = sorted((ROOT / "src/consequa_x").rglob("*.py")) + [Path(__file__).resolve(),
        ROOT / "tests/test_upstream_car_study.py", ROOT / "docs/upstream-car-comparison.md"]
    return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths}


def dependency_fingerprint():
    packages = {}
    for name in ("numpy", "scipy", "pydantic", "structlog"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {"python_version": sys.version, "implementation": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag, "dependencies": packages}


def make_protocol(plan, source_revision):
    if (type(source_revision) is not str or len(source_revision) != 40
            or any(char not in "0123456789abcdef" for char in source_revision)):
        raise ValueError("source_revision must be a complete lowercase Git commit hash")
    return {"schema": SCHEMA, "source_revision": source_revision, "source_files": bound_sources(),
            "execution_environment": dependency_fingerprint(),
            "upstream": {"repository": UPSTREAM_URL, "revision": UPSTREAM_REVISION,
                         "version": "0.2.0", "vendored": False},
            "plan": asdict(plan), "trials": trial_schedule(plan), "engines": list(ENGINES),
            "references": {name: exact_reference(name) for name in plan.mechanisms},
            "design": {
                "game": "on_reach positional factual selection/retry/terminal stop",
                "policy": "RefundInteractionPolicy seeded Bernoulli; planted factual refund/retry/stop",
                "paired_randomness": "same fresh branch/phase keys, world seed and permutation order in both engines",
                "actual_call_budget": "same factual plus attempted fresh policy calls; held calls cost zero",
                "primary_gate": "all planned branches known and completed; no partial upstream numeric advantage",
                "upstream_intervals": "unmodified NumPy percentile bootstrap and SciPy normal pair-mean intervals",
                "cx_intervals": "original bootstrap/normal and same-draw Clopper-Pearson/Hoeffding alternatives",
                "endpoints": "same extra independent empty/full diagnostics before both Shapley paths",
                "independent_unit": "one repeat within a fixed synthetic mechanism, not an independent task",
                "reason_for_64_repeats": "nominal .95 coverage has binomial MCSE about .027 at 64 repeats; descriptive precision only",
                "no_model_calls": True, "no_github_actions": True,
                "parallelism": "independent complete paired groups in spawn-safe processes; no shared environment",
                "timing_interpretation": "actual wall time includes worker contention; equal call caps do not imply equal compute",
                "limitations": ["same scripted simulator and policy, not cross-domain validation",
                    "planted factual intervention, not natural failure frequency",
                    "conditional nominal intervals, no multiplicity adjustment",
                    "paired seed experiment, not hidden-model determinism evidence",
                    "adapted refund transport and evidence/refusal wrapper, not a complete CAR reproduction"]}}


def load_car(upstream_root):
    root = Path(upstream_root).resolve()
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True)
    if result.stdout.strip() != UPSTREAM_REVISION:
        raise ValueError("Upstream checkout does not match the pinned CAR revision")
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                            check=True, capture_output=True, text=True)
    if status.stdout.strip():
        raise ValueError("Upstream checkout must be clean, including untracked source")
    source = root / "src"
    existing = sys.modules.get("car")
    if existing is not None and not Path(existing.__file__).resolve().is_relative_to(source):
        raise ValueError("A different CAR installation is already imported")
    sys.path.insert(0, str(source))
    modules = {key: importlib.import_module(name) for key, name in {
        "contrastive": "car.attribute.contrastive", "shapley": "car.attribute.shapley",
        "budget": "car.budget.budget", "forward": "car.replay.forward",
        "trajectory": "car.schemas.trajectory", "recorder": "car.record.recorder"}.items()}
    modules["provenance"] = {"repository": UPSTREAM_URL, "revision": UPSTREAM_REVISION,
        "source_files": {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
                         for path in sorted((source / "car").rglob("*.py"))},
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "pydantic", "structlog")}}
    return modules


def request_from_dict(value):
    return PolicyRequest(value["stage"], value["task"], value["context"], tuple(ToolResponse(
        item["attempt_id"], ResponseStatus(item["status"]), item["time_ms"],
        item["provider_request_id"], item["result"]) for item in value["responses"]),
        value["attempts_remaining"])


def reply_from_dict(value):
    row = value["decision"]
    return PolicyReply(PolicyDecision(row["operation"], AssessmentStatus(row["assessment"]),
                                     row["rationale"]), value["metadata"])


def evidence_record(episode, target):
    outcome = episode_outcome(episode)
    outcomes = {name: outcome.target_value(name) for name in
                ("action", "consequence", "action_linked_consequence")}
    value = outcomes[target]
    trace = to_dict(episode.trace)
    return {"target_values": outcomes, "bad": None if value is None else int(not value),
            "trace_sha256": digest(trace), "action": trace["action"],
            "observations": trace["observations"], "verifications": trace["verifications"]}


class _PrefixPolicy:
    """Reconstruct deterministic glue; never samples the declared fresh policy."""
    def __init__(self, metadata, replies):
        self.metadata, self.replies, self.requests = deepcopy(metadata), replies, []

    def decide(self, request, *, seed):
        index = len(self.requests)
        self.requests.append(deepcopy(request))
        reply = self.replies[index] if index < len(self.replies) else PolicyReply(
            PolicyDecision("stop", AssessmentStatus.UNKNOWN, "Deterministic transport probe."))
        validate_reply(request, reply)
        return deepcopy(reply)


class NativeRefundBridge:
    """Serial CAR interfaces using public requests and production-simulator readback.

    Native CAR has no environment-factory hook. Every transition reconstructs a
    fresh payment world from the current forced reply prefix, and every scored
    rollout resets that prefix. No world state is shared across branches.
    """
    provider = "synthetic"
    model_id = "consequa-refund-interaction-v1"

    def __init__(self, car, plan, trial, factual, bounded):
        self.car, self.plan, self.trial = car, plan, trial
        self.factual, self.bounded = factual, bounded
        self.slots, self.receipts, self.prefix, self.decisions = slots_for(plan, trial), [], [], []
        self.glue_runs = 0
        self.glue_completed_runs = 0
        self.glue_tool_dispatches = 0
        self.glue_decision_reuses = 0
        self.glue_elapsed_seconds = 0.
        self.factual_events = [event for event in factual.trace.events if event.type is EventType.AGENT_DECISION]
        self.codec = car["recorder"].SyntheticCodec()
        self.factual_native = None
        self.first_request = self._simulate([], trial["factual_seed"])[1][0]

    @property
    def slot(self):
        if len(self.receipts) >= len(self.slots):
            raise PolicyError("Native CAR attempted an unplanned rollout")
        return self.slots[len(self.receipts)]

    def _simulate(self, replies, policy_seed):
        recorder = _PrefixPolicy(self.bounded.metadata, replies)
        self.glue_runs += 1
        start = time.perf_counter()
        try:
            episode = run_policy_scenario(self.factual.config, recorder, seed=self.trial["factual_seed"],
                                          policy_seed=policy_seed, max_attempts=2)
        finally:
            self.glue_elapsed_seconds += time.perf_counter() - start
        self.glue_completed_runs += 1
        self.glue_decision_reuses += len(recorder.requests)
        self.glue_tool_dispatches += sum(event.type is EventType.ACTION_DISPATCH for event in episode.trace.events)
        return episode, recorder.requests

    def action(self, reply, request, *, source, seed):
        operation = reply.decision.operation
        return self.car["trajectory"].Action(kind="final" if operation == "stop" else "tool_call",
            text=reply.decision.rationale, tool_name=None if operation == "stop" else operation,
            tool_args=None if operation == "stop" else {},
            raw={"policy_reply": to_dict(reply), "stage": request.stage, "source": source,
                 "model_seed": seed})

    def _public_request(self, state):
        value = json.loads(state.messages[-1]["content"])
        if set(value) != {"public_policy_request"}:
            raise PolicyError("Native policy transport has unexpected fields")
        return request_from_dict(value["public_policy_request"])

    async def sample(self, state):
        request = self._public_request(state)
        index = (len(state.messages) - 1) // 2
        seed = self.slot["continuation_seed"] * 6 + index
        try:
            reply = self.bounded.decide(request, seed=seed)
            validate_reply(request, reply)
        except CallBudgetExceeded as error:
            self.decisions.append({"index": index, "source": "resampled", "request": to_dict(request),
                                   "reply": None, "model_seed": seed, "error_type": type(error).__name__})
            raise self.car["budget"].BudgetExceeded(str(error)) from error
        return self.action(reply, request, source="resampled", seed=seed)

    def _accept(self, action, *, factual=False):
        index = len(self.prefix)
        seed = self.trial["factual_seed"] if factual else self.slot["continuation_seed"]
        _, requests = self._simulate(self.prefix, seed)
        request = requests[index]
        reply = reply_from_dict(action.raw["policy_reply"])
        operation = reply.decision.operation
        if (action.kind == "final") != (operation == "stop") or (
                action.kind == "tool_call" and action.tool_name != operation):
            raise PolicyError("Native action encoding disagrees with its captured policy decision")
        if action.raw["stage"] != request.stage:
            raise PolicyError("A held native action reached an incompatible typed stage")
        validate_reply(request, reply)
        if not factual:
            held = index in self.slot["held_indices"]
            if (action.raw["source"] == "held_factual") != held:
                raise PolicyError("Native CAR action source disagrees with the frozen coalition")
            if held and action.raw["policy_reply"] != self.factual_events[index].data["policy_reply"]:
                raise PolicyError("Native CAR changed a held factual reply")
            if not held and action.raw["model_seed"] != seed * 6 + index:
                raise PolicyError("Native CAR fresh phase key changed")
        self.prefix.append(reply)
        self.decisions.append({"index": index, "source": action.raw["source"],
            "request": to_dict(request), "reply": to_dict(reply),
            "model_seed": seed * 6 + index})

    async def observe(self, action):
        self._accept(action, factual=self.factual_native is None)
        seed = self.trial["factual_seed"] if self.factual_native is None else self.slot["continuation_seed"]
        _, requests = self._simulate(self.prefix, seed)
        value = {"public_policy_request": to_dict(requests[len(self.prefix)])}
        return self.car["trajectory"].Observation(tool_name=action.tool_name,
            result=canonical(value).decode("utf-8"), source="mocked")

    async def make_factual(self):
        messages = [{"role": "user", "content": canonical(
            {"public_policy_request": to_dict(self.first_request)}).decode("utf-8")}]
        steps = []
        for index, event in enumerate(self.factual_events):
            request = request_from_dict(event.data["policy_request"])
            action = self.action(reply_from_dict(event.data["policy_reply"]), request,
                                 source="held_factual", seed=event.data["model_seed"])
            state = self.car["trajectory"].State(system_prompt="Typed public refund decision transport v1",
                tool_schemas=[], model=self.model_id, provider=self.provider,
                sampling={"declared_policy": deepcopy(self.bounded.metadata)}, messages=deepcopy(messages))
            if to_dict(self._public_request(state)) != to_dict(request):
                raise PolicyError("Native transport cannot reconstruct the factual public request exactly")
            observation = None if action.kind == "final" else await self.observe(action)
            steps.append(self.car["trajectory"].Step(index=index, state_before=state,
                                                     action=action, observation=observation))
            if observation is not None:
                messages.extend((self.codec.assistant_message(action), self.codec.tool_result_message(action, observation)))
        self.factual_native = self.car["trajectory"].Trajectory(
            trajectory_id=f"group-{self.trial['group_index']}:factual", steps=steps,
            final_output=steps[-1].action.text or "")
        self.prefix, self.decisions = [], []
        return self.factual_native

    async def score(self, trajectory):
        if trajectory is self.factual_native:
            value = evidence_record(self.factual, self.trial["target"])["bad"]
        else:
            self._accept(trajectory.steps[-1].action)
            episode, requests = self._simulate(self.prefix, self.slot["continuation_seed"])
            if len(requests) != len(self.prefix):
                raise PolicyError("Native trajectory ended before a required production decision")
            evidence = evidence_record(episode, self.trial["target"])
            held = set(self.slot["held_indices"])
            self.receipts.append({"slot": self.slot, "status": "unknown" if evidence["bad"] is None else "known",
                "decisions": self.decisions, "policy_calls": sum(item["source"] == "resampled" for item in self.decisions),
                "inactive_held_indices": sorted(held - set(range(len(self.prefix)))),
                "native_trajectory_id": trajectory.trajectory_id, **evidence})
            value = evidence["bad"]
            self.prefix, self.decisions = [], []
        # Upstream has no abstention outcome. This placeholder is never eligible
        # for primary inference: the complete-method gate below rejects unknowns.
        return self.car["trajectory"].Outcome(label="unavailable" if value is None else "bad" if value else "ok",
                                              score=0. if value is None else float(value))

    def fail_current(self, error):
        if len(self.receipts) < len(self.slots):
            self.receipts.append({"slot": self.slot, "status": "failed", "decisions": self.decisions,
                "policy_calls": sum(item["source"] == "resampled" and item["reply"] is not None for item in self.decisions),
                "error_type": type(error).__name__, "error": str(error), "bad": None})
            self.prefix, self.decisions = [], []


def complete_receipts(slots, attempted):
    by_index = {row["slot"]["index"]: row for row in attempted}
    if len(by_index) != len(attempted) or set(by_index) - set(range(len(slots))):
        raise ValueError("Duplicate or unplanned draw receipts")
    return [by_index.get(slot["index"], {"slot": slot, "status": "unstarted", "policy_calls": 0,
                                       "decisions": [], "bad": None}) for slot in slots]


def primary_gate(receipts, factual_bad):
    counts = Counter(row["status"] for row in receipts)
    eligible = factual_bad is not None and counts.get("known", 0) == len(receipts)
    return {"eligible": eligible, "planned": len(receipts), "counts": dict(counts),
            "reason": None if eligible else "factual or at least one planned draw unavailable; no partial numeric estimate"}


async def run_native(car, plan, trial, factual, bounded):
    bridge = NativeRefundBridge(car, plan, trial, factual, bounded)
    native = await bridge.make_factual()
    raw, error = None, None
    native_budget = car["budget"].Budget(max_samples=(3 * plan.samples if trial["method"] == "contrastive"
                                                     else 8 * plan.pairs))
    try:
        if trial["method"] == "contrastive":
            raw = await car["contrastive"].contrastive_attribution(native, policy=bridge,
                environment=bridge, codec=bridge.codec, outcome_fn=bridge, bad_label="bad",
                k_samples=plan.samples, confidence=plan.confidence,
                budget=native_budget, max_concurrency=1)
        else:
            for slot in bridge.slots[:2 * plan.endpoint_samples]:
                child = await car["forward"].coalition_forward(trajectory_id=f"endpoint-{slot['index']}",
                    factual=native, held=set(slot["held_indices"]), policy=bridge,
                    environment=bridge, codec=bridge.codec)
                await bridge.score(child)
            raw = await car["shapley"].shapley_attribution(native, policy=bridge,
                environment=bridge, codec=bridge.codec, outcome_fn=bridge, bad_label="bad",
                n_permutations=plan.pairs, samples_per_eval=1, antithetic=True,
                confidence=plan.confidence, budget=native_budget,
                seed=trial["permutation_seed"], max_concurrency=1)
    except car["budget"].BudgetExceeded as caught:
        error = {"type": type(caught).__name__, "message": str(caught)}
        bridge.fail_current(caught)
    # CAR Shapley catches BudgetExceeded internally. Preserve its failed branch,
    # and exclude any internally returned partial coefficient vector.
    if raw is not None and trial["method"] == "shapley" and raw.budget_truncated:
        bridge.fail_current(car["budget"].BudgetExceeded("Actual-call budget truncated the native Shapley path"))
    receipts = complete_receipts(bridge.slots, bridge.receipts)
    factual_bad = evidence_record(factual, trial["target"])["bad"]
    gate = primary_gate(receipts, factual_bad)
    estimates = []
    if gate["eligible"]:
        if raw is None:
            raise ValueError("Complete native study has no estimator result")
        if trial["method"] == "contrastive":
            estimates = [{"position": item.index, "point": item.effect.point,
                          "interval": [item.effect.ci_low, item.effect.ci_high]} for item in raw.per_step]
        else:
            if raw.permutations_completed != plan.pairs or raw.budget_truncated:
                raise ValueError("Native returned partial pairs despite complete draw inventory")
            estimates = [{"position": item.index, "point": item.value,
                          "interval": [item.ci_low, item.ci_high]} for item in raw.per_step]
    return {"receipts": receipts, "gate": gate,
            "variants": {"upstream_bootstrap" if trial["method"] == "contrastive" else "upstream_normal": estimates},
            "locus": raw.causal_locus if gate["eligible"] and trial["method"] == "contrastive" else None,
            "unfiltered_native_diagnostic": None if raw is None else raw.model_dump(mode="json"),
            "unfiltered_diagnostic_eligible_for_inference": gate["eligible"],
            "error": error, "deterministic_glue_reexecutions": bridge.glue_runs,
            "execution_cost": {"native_budget_charged_path_rollouts": native_budget.used_samples,
                "supplemental_endpoint_rollouts": sum(row["slot"]["role"].startswith("endpoint") for row in bridge.receipts),
                "deterministic_glue_world_runs": bridge.glue_runs,
                "completed_glue_world_runs": bridge.glue_completed_runs,
                "glue_tool_dispatches": bridge.glue_tool_dispatches,
                "glue_reused_or_probe_decisions": bridge.glue_decision_reuses,
                "glue_elapsed_seconds": bridge.glue_elapsed_seconds,
                "live_model_calls": 0,
                "note": "Glue is extra simulator compute, not fresh stochastic policy calls; total elapsed also includes it."}}


def run_cx(plan, trial, factual, bounded):
    slots = slots_for(plan, trial)
    kwargs = {"targets": (trial["target"],), "seed": trial["continuation_seed"], "confidence": plan.confidence}
    if trial["method"] == "contrastive":
        result = contrastive_decisions(factual, bounded, samples=plan.samples,
            interval_method="percentile_bootstrap", **kwargs)
        indexed = {row.index: row.replay for row in result.branches}
        variants = {"cx_bootstrap": result,
                    "cx_clopper_pearson": with_contrastive_interval(result, interval_method="clopper_pearson")}
    else:
        result = shapley_decisions(factual, bounded, pairs=plan.pairs, samples_per_eval=1,
            endpoint_samples=plan.endpoint_samples, permutation_seed=trial["permutation_seed"],
            coalition_game="on_reach", interval_method="normal", endpoint_interval_method="normal", **kwargs)
        indexed = {row.slot.index: row.replay for row in result.branches}
        variants = {"cx_normal": result,
                    "cx_hoeffding": with_shapley_intervals(result, interval_method="hoeffding",
                                                          endpoint_interval_method="clopper_pearson_difference")}
    receipts = []
    for slot in slots:
        replay = indexed.get(slot["index"])
        if replay is None:
            continue
        decisions = [{"index": item.index, "source": item.source, "request": item.request,
                      "reply": item.reply, "model_seed": item.continuation_model_seed,
                      **({"error_type": item.error_type} if item.error_type else {})} for item in replay.decisions]
        row = {"slot": slot, "status": "failed", "decisions": decisions,
               "policy_calls": replay.policy_calls, "bad": None}
        if replay.episode is not None:
            row.update(evidence_record(replay.episode, trial["target"]))
            row["status"] = "unknown" if row["bad"] is None else "known"
            row["inactive_held_indices"] = list(getattr(replay, "inactive_held_indices", ()))
        else:
            row.update(error_type=replay.error_type, error=replay.error)
            if getattr(replay, "status", None) == "invalid":
                row["status"] = "invalid"
        receipts.append(row)
    receipts = complete_receipts(slots, receipts)
    gate = primary_gate(receipts, evidence_record(factual, trial["target"])["bad"])
    estimates = {}
    for name, variant in variants.items():
        estimates[name] = []
        if gate["eligible"]:
            for item in variant.results:
                if item.status != "estimated":
                    raise ValueError("Complete CX draw inventory has a refused estimate")
                estimates[name].append({"position": item.decision_index,
                    "point": item.effect if trial["method"] == "contrastive" else item.shapley_value,
                    "interval": list(item.confidence_interval)})
    return {"receipts": receipts, "gate": gate, "variants": estimates,
            "locus": result.loci[0].decision_index if gate["eligible"] and trial["method"] == "contrastive" else None,
            "deterministic_glue_reexecutions": None,
            "execution_cost": {"completed_replay_worlds": sum(row["status"] in ("known", "unknown") for row in receipts),
                "full_hold_preflight_worlds": 1, "live_model_calls": 0,
                "note": "Total elapsed includes native CX deterministic replay/preflight glue; no extra prefix reconstruction adapter."},
            "method_record": result.method_record()}


def run_trial(car, plan, trial, engine):
    start = time.perf_counter()
    mechanism = INTERACTION_MECHANISMS[trial["mechanism"]]
    bounded = BudgetedPolicy(mechanism.make_policy(factual_policy_seed=trial["factual_seed"]), trial["max_calls"])
    factual = run_policy_scenario(mechanism.scenario_config(), bounded, seed=trial["factual_seed"], max_attempts=2)
    factual_calls = bounded.calls
    result = (asyncio.run(run_native(car, plan, trial, factual, bounded)) if engine == "upstream_car"
              else run_cx(plan, trial, factual, bounded))
    if bounded.calls > trial["max_calls"]:
        raise ValueError("Actual policy-call cap was exceeded")
    if sum(row["policy_calls"] for row in result["receipts"]) != bounded.calls - factual_calls:
        raise ValueError("Per-draw policy-call accounting does not reconcile")
    return {"schema": SCHEMA, "trial": trial, "engine": engine,
            "factual": {"calls": factual_calls, "trace": to_dict(factual.trace),
                        "evidence": evidence_record(factual, trial["target"])},
            "calls": {"factual": factual_calls, "continuation": bounded.calls - factual_calls,
                      "total": bounded.calls, "cap": trial["max_calls"]},
            "elapsed_seconds": time.perf_counter() - start, **result}


def compare_pair(left, right):
    """Same-draw validation; failures are retained rather than reconciled away."""
    def comparable_decisions(rows):
        values = deepcopy(rows)
        for item in values:
            if item["source"] == "held_factual" and item["reply"] is not None:
                metadata = item["reply"]["metadata"]
                for wrapper in ("decision_prefix_replay", "decision_coalition_replay"):
                    if wrapper in metadata:
                        metadata = metadata[wrapper]["factual_reply_metadata"]
                        break
                item["reply"]["metadata"] = metadata
        return values
    mismatches = []
    for a, b in zip(left["receipts"], right["receipts"], strict=True):
        fields = ("slot", "status", "policy_calls", "bad", "decisions",
                  "target_values", "action", "observations", "verifications")
        changed = [name for name in fields if (
            comparable_decisions(a[name]) != comparable_decisions(b[name]) if name == "decisions"
            else a.get(name) != b.get(name))]
        if changed:
            mismatches.append({"slot": a["slot"]["index"], "fields": changed})
    native_values = next(iter(left["variants"].values()))
    point_differences = []
    for variant, values in right["variants"].items():
        if len(values) == len(native_values):
            for native_item, cx_item in zip(native_values, values, strict=True):
                point_differences.append({"variant": variant, "position": cx_item["position"],
                    "absolute_difference": abs(native_item["point"] - cx_item["point"])})
    return {"same_factual_trace": left["factual"]["trace"] == right["factual"]["trace"],
            "same_actual_calls": left["calls"] == right["calls"],
            "draws_compared": len(left["receipts"]), "mismatches": mismatches,
            "point_differences": point_differences,
            "max_absolute_point_difference": max((item["absolute_difference"] for item in point_differences), default=None),
            "metadata_comparison": "CX held-reply replay wrapper unwrapped to retained factual_reply_metadata; raw receipts unchanged",
            "interpretation": "paired implementation validation, not method-superiority evidence"}


def summarize(rows, references):
    groups = defaultdict(list)
    for row in rows:
        for variant, estimates in row["variants"].items():
            by_position = {item["position"]: item for item in estimates}
            for position in range(3):
                groups[(row["trial"]["mechanism"], row["trial"]["method"], variant, position)].append(
                    (row, by_position.get(position)))
    output = []
    for (mechanism, method, variant, position), items in sorted(groups.items()):
        truth = references[mechanism][method]
        reference = None if truth is None else truth[position]
        available = [estimate for _, estimate in items if estimate is not None]
        errors = [] if reference is None else [item["point"] - reference for item in available]
        covered = None if reference is None else sum(item["interval"][0] <= reference <= item["interval"][1]
                                                     for item in available)
        output.append({"mechanism": mechanism, "method": method, "variant": variant, "position": position,
            "planned": len(items), "available": len(available), "reference": reference,
            "scored": len(errors), "covered": covered,
            "coverage_available": covered / len(errors) if errors else None,
            "coverage_planned": covered / len(items) if covered is not None else None,
            "bias": sum(errors) / len(errors) if errors else None,
            "rmse": math.sqrt(sum(value * value for value in errors) / len(errors)) if errors else None,
            "mean_width": sum(item["interval"][1] - item["interval"][0] for item in available) / len(available) if available else None,
            "zero_width": sum(item["interval"][0] == item["interval"][1] for item in available),
            "nonzero_flags": sum(item["interval"][0] > 0 or item["interval"][1] < 0 for item in available)})
    return {"schema": SCHEMA, "rows": output,
            "limitations": "Conditional simulation calibration; no pooled independent-task CI, model score, or superiority claim."}


def verify_final_bindings(protocol, car):
    if (protocol["source_files"] != bound_sources()
            or protocol["execution_environment"] != dependency_fingerprint()):
        raise ValueError("Frozen local sources or execution environment changed during collection")
    root = Path(car["trajectory"].__file__).resolve().parents[3]
    current = {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
               for path in sorted((root / "src/car").rglob("*.py"))}
    if current != car["provenance"]["source_files"]:
        raise ValueError("Upstream CAR source changed during collection")


_WORKER_CAR = None


def _initialize_worker(upstream_root, source_files, environment):
    global _WORKER_CAR
    if source_files != bound_sources() or environment != dependency_fingerprint():
        raise ValueError("Frozen sources or dependencies changed before a worker started")
    _WORKER_CAR = load_car(upstream_root)
    # Silence routine upstream progress only; estimator code and error receipts
    # remain unchanged. The parent emits bounded group-level progress.
    structlog = importlib.import_module("structlog")
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))


def _compute_group(plan, trial):
    pair = []
    try:
        for engine in ENGINES:
            pair.append(run_trial(_WORKER_CAR, plan, trial, engine))
        comparison = compare_pair(*pair)
        discrepant = (comparison["mismatches"] or not comparison["same_factual_trace"]
                      or not comparison["same_actual_calls"]
                      or (comparison["max_absolute_point_difference"] or 0.) > 1e-12)
        status = ("semantic_mismatch" if discrepant and not trial["mechanism"].startswith("budget-")
                  else "completed")
        return {"trial": trial, "status": status, "engine_rows": pair, "comparison": comparison}
    except Exception as error:
        # Retain an engine that completed before another engine failed. There
        # is no retry, seed replacement or claim of a completed current engine.
        return {"trial": trial, "status": "failed", "engine_rows": pair,
                "error_type": type(error).__name__, "error": str(error),
                "failed_engine": ENGINES[len(pair)] if len(pair) < 2 else None}


def iter_group_results(plan, trials, upstream_root, source_files=None, environment=None):
    """Bounded parallel dispatch; after any failure drain already dispatched work.

    The parent receives each completed result and alone writes its unique files.
    Never-submitted groups remain explicitly unstarted. A failed process is not
    redrawn, even if it produced no recoverable engine result.
    """
    args = (str(Path(upstream_root).resolve()), source_files or bound_sources(),
            environment or dependency_fingerprint())
    if plan.workers == 1:
        _initialize_worker(*args)
        for trial in trials:
            result = _compute_group(plan, trial)
            yield result
            if result["status"] != "completed":
                break
        return
    with ProcessPoolExecutor(max_workers=plan.workers, mp_context=get_context("spawn"), initializer=_initialize_worker,
                             initargs=args) as executor:
        iterator = iter(trials)
        pending = {}
        halted = False
        def submit_one():
            trial = next(iterator, None)
            if trial is not None:
                pending[executor.submit(_compute_group, plan, trial)] = trial
        for _ in range(plan.workers):
            submit_one()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in sorted(finished, key=lambda item: pending[item]["group_index"]):
                trial = pending.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = {"trial": trial, "status": "failed_process", "engine_rows": [],
                              "error_type": type(error).__name__, "error": str(error),
                              "execution_progress_unknown": True}
                if result["status"] != "completed":
                    halted = True
                yield result
            if not halted:
                for _ in range(plan.workers - len(pending)):
                    submit_one()


def semantic_group_digest(group):
    """Exclude timing from deterministic serial/parallel comparison only."""
    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items()
                    if key not in {"elapsed_seconds", "glue_elapsed_seconds"}}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value
    return digest(strip(group))


def verify_local_revision(protocol):
    revision = protocol["source_revision"]
    subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", revision + "^{commit}"],
                   check=True, capture_output=True)
    names = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", revision,
                            "--", *protocol["source_files"]],
                           check=True, capture_output=True, text=True)
    if set(names.stdout.splitlines()) != set(protocol["source_files"]):
        raise ValueError("A frozen source/test/design file is absent from the declared Git revision")
    changed = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", revision,
                              "--", *protocol["source_files"]],
                             check=True, capture_output=True, text=True)
    if changed.stdout.strip():
        raise ValueError("Frozen local source revision does not match the working implementation")


def run_protocol(protocol, output, upstream_root):
    runner_started = time.perf_counter()
    if protocol.get("schema") != SCHEMA or protocol.get("source_files") != bound_sources():
        raise ValueError("Protocol schema or frozen local source hashes changed")
    config = dict(protocol["plan"])
    config["mechanisms"] = tuple(config["mechanisms"])
    plan = StudyPlan(**config)
    expected = make_protocol(plan, protocol["source_revision"])
    if canonical(expected) != canonical(protocol):
        raise ValueError("Protocol content differs from the complete declared design")
    verify_local_revision(protocol)
    car = load_car(upstream_root)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=False)
    write_new(destination / "protocol.json", protocol)
    write_new(destination / "upstream-provenance.json", car["provenance"])
    (destination / "trials").mkdir()
    compact, comparisons, files, dispositions = [], [], [], {}
    started = time.perf_counter()
    last_progress = started
    for group in iter_group_results(plan, protocol["trials"], upstream_root,
                                   protocol["source_files"], protocol["execution_environment"]):
        trial = group["trial"]
        for row in group["engine_rows"]:
            path = destination / "trials" / f"{trial['group_index']:05d}-{row['engine']}.json.gz"
            write_new_gzip(path, row)
            files.append(path)
            compact.append({key: row[key] for key in ("trial", "engine", "variants", "gate", "calls", "locus")})
        disposition = {key: value for key, value in group.items() if key not in {"engine_rows", "comparison"}}
        disposition["semantic_digest"] = semantic_group_digest(group)
        dispositions[trial["group_index"]] = disposition
        if "comparison" in group:
            comparisons.append({"trial": trial, **group["comparison"]})
        now = time.perf_counter()
        if now - last_progress >= 10 or len(dispositions) == len(protocol["trials"]) or group["status"] != "completed":
            print(json.dumps({"groups_finished": len(dispositions), "groups_planned": len(protocol["trials"]),
                              "last_group": trial["group_index"], "last_status": group["status"],
                              "workers": plan.workers}), flush=True)
            last_progress = now
    all_dispositions = [dispositions.get(trial["group_index"], {"trial": trial, "status": "unstarted"})
                        for trial in protocol["trials"]]
    write_new(destination / "disposition.json", {"schema": SCHEMA, "groups": all_dispositions,
        "counts": dict(Counter(item["status"] for item in all_dispositions)),
        "workers": plan.workers, "collection_wall_seconds": time.perf_counter() - started,
        "total_wall_seconds": time.perf_counter() - runner_started,
        "execution_setup_seconds": started - runner_started,
        "timing_scope": "runner entry through setup, workers, collection and per-trial writes; excludes final summary serialization",
        "redraws": 0})
    comparisons.sort(key=lambda row: row["trial"]["group_index"])
    compact.sort(key=lambda row: (row["trial"]["group_index"], ENGINES.index(row["engine"])))
    write_new(destination / "paired-validation.json", comparisons)
    binding_error = None
    try:
        verify_final_bindings(protocol, car)
    except ValueError as error:
        binding_error = str(error)
    if binding_error is not None or any(item["status"] != "completed" for item in all_dispositions):
        write_new(destination / "incomplete-receipt.json", {"schema": SCHEMA,
            "complete": False, "binding_error": binding_error,
            "retained_trial_files": len(files), "planned_trial_files": len(protocol["trials"]) * 2,
            "files": {path.relative_to(destination).as_posix(): sha256(path.read_bytes()).hexdigest()
                      for path in sorted(destination.rglob("*")) if path.is_file()}})
        raise ValueError("Study incomplete; retained completed/failed group dispositions without any redraw")
    write_new(destination / "summary.json", summarize(compact, protocol["references"]))
    manifest = {path.relative_to(destination).as_posix(): sha256(path.read_bytes()).hexdigest()
                for path in sorted(destination.rglob("*")) if path.is_file()}
    write_new(destination / "manifest.json", {"schema": SCHEMA, "files": manifest,
        "trial_files": len(files), "planned_trial_files": len(protocol["trials"]) * 2,
        "complete": len(files) == len(protocol["trials"]) * 2})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--output", required=True)
    plan_parser.add_argument("--source-revision", required=True)
    for name, default in (("repeats", 64), ("samples", 32), ("pairs", 32), ("endpoint-samples", 16),
                          ("seed", 70_000_000), ("max-calls", 1200), ("workers", 4)):
        plan_parser.add_argument("--" + name, type=int, default=default)
    plan_parser.add_argument("--mechanism", action="append", choices=MECHANISMS)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--protocol", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--upstream-root", required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        values = {key: getattr(args, key) for key in ("repeats", "samples", "pairs", "endpoint_samples", "seed", "max_calls", "workers")}
        values["mechanisms"] = tuple(args.mechanism or MECHANISMS)
        write_new(args.output, make_protocol(StudyPlan(**values), args.source_revision))
    else:
        run_protocol(json.loads(Path(args.protocol).read_text(encoding="utf-8")), args.output, args.upstream_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
