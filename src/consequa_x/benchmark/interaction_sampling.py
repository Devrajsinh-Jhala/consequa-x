"""Dedicated repeated physical-refund sampling; historical calibration is unchanged."""

from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import random
from statistics import NormalDist

from .. import __version__
from ..models import to_dict
from ..policies import PolicyError
from ..schema import get_trace_schema
from .decision_shapley import shapley_decisions, with_shapley_intervals
from .evaluation import BudgetedPolicy
from .interaction_mechanisms import INTERACTION_MECHANISMS, TARGETS
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .targets import episode_outcome


GAMES = ("strict", "on_reach")
VARIANTS = ("normal", "hoeffding_exact_endpoints")
SCHEMA_VERSION = "refund-interaction-sampling-v1"


@dataclass(frozen=True)
class InteractionSamplingPlan:
    repeats: int = 128
    pairs: int = 32
    samples_per_eval: int = 1
    endpoint_samples: int = 32
    confidence: float = 0.95
    seed: int = 20_000_000
    max_calls: int = 1000
    mechanisms: tuple[str, ...] = tuple(INTERACTION_MECHANISMS)
    games: tuple[str, ...] = GAMES

    def __post_init__(self):
        for name, minimum in (
            ("repeats", 1),
            ("pairs", 2),
            ("samples_per_eval", 1),
            ("endpoint_samples", 2),
            ("max_calls", 3),
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        try:
            valid_confidence = (
                type(self.confidence) in (int, float)
                and math.isfinite(self.confidence)
                and 0 < self.confidence < 1
            )
        except OverflowError:
            valid_confidence = False
        if not valid_confidence:
            raise ValueError("confidence must be finite and strictly between zero and one")
        if type(self.seed) is not int or self.seed < 20_000_000:
            raise ValueError("seed must be an integer at least 20000000")
        for values, allowed, name in (
            (self.mechanisms, INTERACTION_MECHANISMS, "mechanisms"),
            (self.games, GAMES, "games"),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(type(value) is not str or value not in allowed for value in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError(f"{name} must be a nonempty tuple of unique supported names")
        if self.seed + self.trial_count * self.trial_stride - 1 > MAX_TRIAL_SEED:
            raise ValueError(
                "Complete factual/continuation phase reservation exceeds MAX_TRIAL_SEED"
            )
        if (
            self.seed + self.trial_count * self.trial_stride
        ) * 6 + self.trial_count - 1 > 2**31 - 1:
            raise ValueError("Disjoint permutation reservation exceeds the supported RNG key range")

    @property
    def branches_per_trial(self):
        return 2 * self.endpoint_samples + 8 * self.pairs * self.samples_per_eval

    @property
    def trial_stride(self):
        return 1 + self.branches_per_trial

    @property
    def trial_count(self):
        return len(self.mechanisms) * len(self.games) * self.repeats


@dataclass(frozen=True)
class InteractionTrialPlan:
    index: int
    mechanism: str
    coalition_game: str
    replicate: int
    factual_seed: int
    continuation_seed: int
    permutation_seed: int
    planned_branches: int
    max_calls: int


def predeclare_interaction_sampling(plan):
    if not isinstance(plan, InteractionSamplingPlan):
        raise TypeError("plan must be an InteractionSamplingPlan")
    return tuple(_expected_entry(plan, index) for index in range(plan.trial_count))


def _expected_entry(plan, index):
    name = plan.mechanisms[index // (len(plan.games) * plan.repeats)]
    game = plan.games[(index // plan.repeats) % len(plan.games)]
    factual_seed = plan.seed + index * plan.trial_stride
    return InteractionTrialPlan(
        index,
        name,
        game,
        index % plan.repeats,
        factual_seed,
        factual_seed + 1,
        (plan.seed + plan.trial_count * plan.trial_stride) * 6 + index,
        plan.branches_per_trial,
        4 if name == "budget-p50-q50" else plan.max_calls,
    )


def _permutations(plan, entry):
    rng = random.Random(entry.permutation_seed)
    orders = []
    for _ in range(plan.pairs):
        order = [0, 1, 2]
        rng.shuffle(order)
        orders.append(order)
    return orders


def _slots(plan, entry, orders):
    slots = []

    def add(role, pair, walk, step, held, sample):
        index = len(slots)
        slots.append(
            {
                "index": index,
                "role": role,
                "pair_index": pair,
                "walk": walk,
                "step": step,
                "held_indices": list(held),
                "sample_index": sample,
                "continuation_seed": entry.continuation_seed + index,
            }
        )

    for role, held in (("endpoint_empty", ()), ("endpoint_full", (0, 1, 2))):
        for sample in range(plan.endpoint_samples):
            add(role, None, None, None, held, sample)
    for pair, order in enumerate(orders):
        for walk, sequence in (("forward", order), ("reverse", list(reversed(order)))):
            for step in range(4):
                for sample in range(plan.samples_per_eval):
                    add("walk", pair, walk, step, sorted(sequence[:step]), sample)
    return slots


def interaction_sampling_protocol(plan, *, source_revision):
    if type(source_revision) is not str or not source_revision.strip():
        raise ValueError("source_revision must be a nonempty frozen source identifier")
    schedule = predeclare_interaction_sampling(plan)
    return {
        "schema_version": SCHEMA_VERSION,
        "package_version": __version__,
        "source_revision": source_revision,
        "source_revision_trust": "caller supplied; no Git inspection",
        "plan": to_dict(plan),
        "trial_schedule": to_dict(schedule),
        "planned_trials": plan.trial_count,
        "planned_branches": plan.trial_count * plan.branches_per_trial,
        "targets": TARGETS,
        "variants": VARIANTS,
        "collection_intervals": {"pair": "normal", "endpoint": "normal"},
        "comparison_intervals": {"pair": "hoeffding", "endpoint": "clopper_pearson_difference"},
        "references": {
            name: {
                game: INTERACTION_MECHANISMS[name].analytic_reference(coalition_game=game)
                for game in plan.games
            }
            for name in plan.mechanisms
        },
        "mechanisms": {name: to_dict(INTERACTION_MECHANISMS[name]) for name in plan.mechanisms},
        "budget": "One study cap per trial including three factual calls; four-call control. The study cap overrides nonbudget enumeration caps.",
        "seed_rule": "Disjoint factual/continuation trial seeds; six phase keys per seed. Permutation keys beyond entire model-phase reservation.",
        "factual": "Predeclared planted refund/retry/stop, not natural factual selection or seed search",
        "retention": {
            "all_trials": "trials/<mechanism>__<game>.jsonl.gz",
            "full_evidence_replicates": [0],
            "gold": "evaluator_truth/, separate from public evidence",
            "all_planned_slots": True,
            "gzip_mtime": 0,
        },
        "scoring": "Planned, available, refused and population-reference eligibility stay separate; only eligible available intervals enter coverage.",
        "limits": [
            "Synthetic seeded policy only; no model calls or model independence claim",
            "Strict-game finite availability does not establish a population game",
            "No multiplicity correction or template generalization",
            "Same draws/points/refusals across interval variants; zero additional comparison calls",
            "Pooled coalition interaction diagnostic is a point only, not a calibrated interval",
        ],
    }


class _FactualRecorder:
    def __init__(self, bounded):
        self.bounded, self.receipts = bounded, []

    @property
    def metadata(self):
        return self.bounded.metadata

    def decide(self, request, *, seed):
        before = self.bounded.calls
        record = {
            "index": len(self.receipts),
            "stage": request.stage,
            "model_seed": seed,
            "request": to_dict(request),
            "reply": None,
            "error_type": None,
            "error": None,
        }
        try:
            reply = self.bounded.decide(request, seed=seed)
            record["reply"] = to_dict(reply)
            return reply
        except PolicyError as error:
            record.update(error_type=type(error).__name__, error=str(error))
            raise
        finally:
            record["policy_calls"] = self.bounded.calls - before
            self.receipts.append(record)


@dataclass(frozen=True)
class InteractionSamplingTrial:
    entry: InteractionTrialPlan
    factual: object
    factual_receipts: tuple
    factual_calls: int
    experiment: object
    comparison: object
    error: dict | None = None


def run_interaction_trial(plan, entry):
    if (
        not isinstance(plan, InteractionSamplingPlan)
        or not isinstance(entry, InteractionTrialPlan)
        or type(entry.index) is not int
        or not 0 <= entry.index < plan.trial_count
        or entry != _expected_entry(plan, entry.index)
    ):
        raise ValueError("trial entry must belong to the complete declared schedule")
    mechanism = INTERACTION_MECHANISMS[entry.mechanism]
    policy = mechanism.make_policy(factual_policy_seed=entry.factual_seed)
    budget = BudgetedPolicy(policy, entry.max_calls)
    recorder = _FactualRecorder(budget)
    factual = None
    try:
        factual = run_policy_scenario(
            mechanism.scenario_config(),
            recorder,
            seed=entry.factual_seed,
            policy_seed=entry.factual_seed,
            max_attempts=2,
        )
    except PolicyError as error:
        return InteractionSamplingTrial(
            entry,
            None,
            tuple(recorder.receipts),
            budget.calls,
            None,
            None,
            {"operation": "factual", "error_type": type(error).__name__, "error": str(error)},
        )
    factual_calls = budget.calls
    experiment = shapley_decisions(
        factual,
        budget,
        pairs=plan.pairs,
        samples_per_eval=plan.samples_per_eval,
        endpoint_samples=plan.endpoint_samples,
        confidence=plan.confidence,
        seed=entry.continuation_seed,
        permutation_seed=entry.permutation_seed,
        targets=TARGETS,
        interval_method="normal",
        endpoint_interval_method="normal",
        coalition_game=entry.coalition_game,
    )
    before = budget.calls
    comparison = with_shapley_intervals(
        experiment,
        interval_method="hoeffding",
        endpoint_interval_method="clopper_pearson_difference",
    )
    if budget.calls != before:
        raise RuntimeError("Interval comparison unexpectedly made policy calls")
    return InteractionSamplingTrial(
        entry, factual, tuple(recorder.receipts), factual_calls, experiment, comparison
    )


def _canonical(value):
    return json.dumps(to_dict(value), sort_keys=True, allow_nan=False, separators=(",", ":"))


def _measurement(episode):
    if episode is None:
        return None
    outcome = episode_outcome(episode)
    obs = episode.trace.observations[-1]
    verified = episode.trace.verifications[-1]
    details = verified.evidence[-1].details
    return {
        "target_values": {target: outcome.target_value(target) for target in TARGETS},
        "verification": verified.status.value,
        "origin": verified.origin.value,
        "watermark_ms": obs.as_of_ms,
        "horizon_ms": episode.trace.single_action.contract.horizon_ms,
        "available": obs.available,
        "complete": obs.complete,
        "readback_records": len(obs.records),
        "matching_count": details.get("matching_count"),
        "eligible_count": details.get("eligible_count"),
        "peak_matching_count": details.get("peak_matching_count"),
        "linked_count": len(verified.attributable_effect_ids),
        "trace_sha256": sha256(_canonical(episode.trace).encode()).hexdigest(),
    }


def _decision(receipt):
    reply = receipt.reply
    return {
        "index": receipt.index,
        "source": receipt.source,
        "stage": receipt.stage,
        "continuation_model_seed": receipt.continuation_model_seed,
        "factual_model_seed": receipt.factual_model_seed,
        "factual_event_id": receipt.factual_event_id,
        "policy_calls": receipt.policy_calls,
        "error_type": receipt.error_type,
        "error": receipt.error,
        "operation": reply["decision"]["operation"] if reply is not None else None,
        "attempts_remaining": receipt.request["attempts_remaining"],
        "response_statuses": [item["status"] for item in receipt.request["responses"]],
    }


def _variant(experiment):
    if experiment is None:
        return None
    return {
        "estimates": [item.to_dict() for item in experiment.results],
        "endpoint_checks": to_dict(experiment.endpoint_checks),
        "summary": experiment.summary(),
    }


def compact_interaction_trial(plan, trial):
    entry, experiment = trial.entry, trial.experiment
    orders = _permutations(plan, entry)
    slots = _slots(plan, entry, orders)
    reached = (
        {}
        if experiment is None
        else {branch.slot.index: branch.replay for branch in experiment.branches}
    )
    if experiment is not None and (
        to_dict(experiment.slots) != slots or to_dict(experiment.permutations) != orders
    ):
        raise RuntimeError("Production sampler differs from the predeclared schedule")
    branches = []
    for slot in slots:
        replay = reached.get(slot["index"])
        branches.append(
            {
                "slot_index": slot["index"],
                "status": replay.status if replay else "unstarted",
                "policy_calls": replay.policy_calls if replay else 0,
                "measurement": _measurement(replay.episode) if replay else None,
                "decisions": [_decision(item) for item in replay.decisions] if replay else [],
                "unreached_held_indices": list(replay.unreached_held_indices) if replay else None,
                "inactive_held_indices": list(replay.inactive_held_indices) if replay else [],
                "budget_exhausted": replay.budget_exhausted if replay else False,
                "error_type": replay.error_type if replay else None,
                "error": replay.error if replay else None,
            }
        )
    calls = sum(item["policy_calls"] for item in branches)
    return {
        "schema_version": SCHEMA_VERSION,
        "trial_plan": to_dict(entry),
        "factual": {
            "status": "completed" if trial.factual else "failed",
            "calls": trial.factual_calls,
            "measurement": _measurement(trial.factual),
            "decisions": to_dict(trial.factual_receipts),
        },
        "permutations": orders,
        "slots": slots,
        "branches": branches,
        "variants": {
            "normal": _variant(experiment),
            "hoeffding_exact_endpoints": _variant(trial.comparison),
        },
        "calls": {
            "factual": trial.factual_calls,
            "continuations": calls,
            "total": trial.factual_calls + calls,
            "additional_comparison": 0,
        },
        "error": trial.error,
    }


def _rate(n, d, confidence):
    if not d:
        return {"numerator": n, "denominator": d, "rate": None, "confidence_interval": None}
    z = -NormalDist().inv_cdf((1 - confidence) / 2)
    p = n / d
    scale = 1 + z * z / d
    center = (p + z * z / (2 * d)) / scale
    radius = z / scale * math.sqrt(p * (1 - p) / d + z * z / (4 * d * d))
    return {
        "numerator": n,
        "denominator": d,
        "rate": p,
        "confidence_interval": [
            0.0 if n == 0 else center - radius,
            1.0 if n == d else center + radius,
        ],
    }


def _metrics(observations, reference, planned, confidence):
    intervals = [item[1] for item in observations if item[1] is not None]
    errors = [point - reference for point, _ in observations] if reference is not None else []
    covered = (
        sum(low <= reference <= high for low, high in intervals) if reference is not None else 0
    )
    bias = sum(errors) / len(errors) if errors else None
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors)) if errors else None
    mcse = (
        math.sqrt(sum((error - bias) ** 2 for error in errors) / ((len(errors) - 1) * len(errors)))
        if len(errors) > 1
        else None
    )
    sign = (
        sum(low > 0 if reference > 0 else high < 0 for low, high in intervals)
        if reference not in (None, 0)
        else 0
    )
    null_flags = sum(low > 0 or high < 0 for low, high in intervals) if reference == 0 else 0
    return {
        "reference": reference,
        "planned_trials": planned,
        "available_estimates": len(observations),
        "refused_estimates": planned - len(observations),
        "reference_eligible_trials": planned if reference is not None else 0,
        "reference_eligible_available": len(errors),
        "bias": bias,
        "bias_mcse": mcse,
        "rmse": rmse,
        "available_intervals": len(intervals),
        "interval_coverage": _rate(
            covered, len(intervals) if reference is not None else 0, confidence
        ),
        "mean_interval_width": sum(high - low for low, high in intervals) / len(intervals)
        if intervals
        else None,
        "degenerate_intervals": sum(low == high for low, high in intervals),
        "reference_sign_detection": _rate(
            sign, len(intervals) if reference not in (None, 0) else 0, confidence
        ),
        "false_nonzero_flag": _rate(
            null_flags, len(intervals) if reference == 0 else 0, confidence
        ),
    }


def _interaction(record, target):
    """Pooled existing coalition draws; refuse any missing planned arm draw."""
    cells = {mask: [] for mask in (0, 1, 2, 3)}
    refused = False
    for slot, branch in zip(record["slots"], record["branches"]):
        mask = sum(1 << i for i in slot["held_indices"])
        if mask not in cells:
            continue
        measurement = branch["measurement"]
        value = measurement["target_values"][target] if measurement else None
        if branch["status"] != "completed" or value is None:
            refused = True
        else:
            cells[mask].append(int(not value))
    means = {mask: sum(values) / len(values) if values else None for mask, values in cells.items()}
    available = not refused and all(value is not None for value in means.values())
    return {
        "status": "estimated" if available else "refused",
        "counts_by_mask": {str(mask): len(values) for mask, values in cells.items()},
        "coalition_bad_rates": {str(mask): value for mask, value in means.items()},
        "interaction": means[3] - means[1] - means[2] + means[0] if available else None,
        "confidence_interval": None,
        "reason": None if available else "missing or unobserved required coalition draw",
    }


class _Analyzer:
    def __init__(self, plan):
        self.plan, self.schedule, self.index = plan, predeclare_interaction_sampling(plan), 0
        self.groups = defaultdict(
            lambda: {
                "statuses": Counter(),
                "calls": Counter(),
                "inactive": 0,
                "numeric": defaultdict(list),
                "refusals": defaultdict(Counter),
                "interaction": defaultdict(list),
            }
        )

    def add(self, record):
        if self.index >= len(self.schedule) or record["trial_plan"] != to_dict(
            self.schedule[self.index]
        ):
            raise ValueError("Trial inventory/order differs from the frozen schedule")
        entry = self.schedule[self.index]
        self.index += 1
        if (
            len(record["slots"]) != entry.planned_branches
            or len(record["branches"]) != entry.planned_branches
        ):
            raise ValueError("Every planned branch must be retained")
        if any(
            branch["slot_index"] != i or slot["index"] != i
            for i, (slot, branch) in enumerate(zip(record["slots"], record["branches"]))
        ):
            raise ValueError("Branch inventory contains missing or duplicate slots")
        group = self.groups[(entry.mechanism, entry.coalition_game)]
        group["calls"].update(record["calls"])
        group["statuses"].update(branch["status"] for branch in record["branches"])
        group["inactive"] += sum(
            bool(branch["inactive_held_indices"]) for branch in record["branches"]
        )
        for variant in VARIANTS:
            data = record["variants"][variant]
            if data is None:
                for target in TARGETS:
                    for position in range(3):
                        group["refusals"][(variant, target, position)]["factual_failure"] += 1
                    group["refusals"][(variant, target, "endpoint")]["factual_failure"] += 1
                continue
            if len(data["estimates"]) != 9 or {
                (item["target"], item["decision_index"]) for item in data["estimates"]
            } != {(target, i) for target in TARGETS for i in range(3)}:
                raise ValueError("Coefficient inventory changed")
            if len(data["endpoint_checks"]) != 3 or {
                item["target"] for item in data["endpoint_checks"]
            } != set(TARGETS):
                raise ValueError("Endpoint inventory changed")
            for item in data["estimates"] + data["endpoint_checks"]:
                position = item.get("decision_index", "endpoint")
                key = (variant, item["target"], position)
                if item["status"] == "estimated":
                    point = (
                        item["shapley_value"]
                        if position != "endpoint"
                        else item["endpoint_difference"]
                    )
                    group["numeric"][key].append((point, item["confidence_interval"]))
                else:
                    coverage = (
                        item.get("coverage", {})
                        if position != "endpoint"
                        else {
                            name: item["empty_coverage"][name] + item["full_coverage"][name]
                            for name in ("unstarted", "failed", "invalid", "unknown")
                        }
                    )
                    reason = next(
                        (
                            name
                            for name in ("unstarted", "failed", "invalid", "unknown")
                            if coverage.get(name)
                        ),
                        "unavailable",
                    )
                    group["refusals"][key][reason] += 1
        for target in TARGETS:
            item = _interaction(record, target)
            if item["status"] == "estimated":
                group["interaction"][target].append((item["interaction"], None))

    def finish(self):
        if self.index != len(self.schedule):
            raise ValueError("Every planned trial must be retained")
        estimates, endpoints, branch_rows, interactions = [], [], [], []
        for name in self.plan.mechanisms:
            for game in self.plan.games:
                group = self.groups[(name, game)]
                references = INTERACTION_MECHANISMS[name].analytic_reference(coalition_game=game)[
                    "targets"
                ]
                branch_rows.append(
                    {
                        "mechanism": name,
                        "coalition_game": game,
                        "planned_trials": self.plan.repeats,
                        "planned_branches": self.plan.repeats * self.plan.branches_per_trial,
                        "status_counts": {
                            status: group["statuses"][status]
                            for status in ("completed", "invalid", "failed", "unstarted")
                        },
                        "inactive_held_branches": group["inactive"],
                        "calls": dict(group["calls"]),
                    }
                )
                for variant in VARIANTS:
                    for target in TARGETS:
                        ref = references[target]
                        for position in (*range(3), "endpoint"):
                            key = (variant, target, position)
                            reference = (
                                ref["endpoint_difference"]
                                if position == "endpoint"
                                else (
                                    ref["shapley_values"][position]
                                    if ref["shapley_eligible"]
                                    else None
                                )
                            )
                            row = {
                                "mechanism": name,
                                "coalition_game": game,
                                "variant": variant,
                                "target": target,
                                "decision_index": position,
                                **_metrics(
                                    group["numeric"][key],
                                    reference,
                                    self.plan.repeats,
                                    self.plan.confidence,
                                ),
                                "refusal_counts": dict(group["refusals"][key]),
                            }
                            (endpoints if position == "endpoint" else estimates).append(row)
                for target in TARGETS:
                    interactions.append(
                        {
                            "mechanism": name,
                            "coalition_game": game,
                            "target": target,
                            **_metrics(
                                group["interaction"][target],
                                references[target]["selection_retry_interaction"],
                                self.plan.repeats,
                                self.plan.confidence,
                            ),
                            "uncertainty": "point-only diagnostic pooled from existing draw occurrences; no interval",
                        }
                    )
        return {
            "schema_version": SCHEMA_VERSION,
            "planned_trials": self.plan.trial_count,
            "retained_trials": self.index,
            "planned_branches": self.plan.trial_count * self.plan.branches_per_trial,
            "actual_policy_calls": sum(row["calls"].get("total", 0) for row in branch_rows),
            "additional_comparison_policy_calls": 0,
            "branch_rows": branch_rows,
            "coefficient_rows": estimates,
            "endpoint_rows": endpoints,
            "interaction_rows": interactions,
        }


def analyze_interaction_sampling(plan, records):
    analyzer = _Analyzer(plan)
    for record in records:
        analyzer.add(record)
    return analyzer.finish()


def _worker_count(workers):
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("workers must be an integer from 1 through 8")


def _collect_interaction_trial(task):
    plan, entry = task
    trial = run_interaction_trial(plan, entry)
    return trial, compact_interaction_trial(plan, trial)


def _collected_trials(plan, schedule, workers):
    if workers == 1:
        for entry in schedule:
            yield _collect_interaction_trial((plan, entry))
        return
    # Bound pending results and retain the declared order independently of
    # process completion order. Every submitted entry is collected exactly once.
    entries = iter(schedule)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = deque()
        for _ in range(workers * 2):
            entry = next(entries, None)
            if entry is None:
                break
            pending.append((entry, pool.submit(_collect_interaction_trial, (plan, entry))))
        while pending:
            expected, future = pending.popleft()
            result = future.result()
            if result[0].entry != expected:
                raise RuntimeError("Worker returned a trial outside its assigned schedule")
            yield result
            entry = next(entries, None)
            if entry is not None:
                pending.append((entry, pool.submit(_collect_interaction_trial, (plan, entry))))


def run_interaction_sampling(plan, *, on_trial=None, workers=1):
    _worker_count(workers)
    if on_trial is not None and not callable(on_trial):
        raise TypeError("on_trial must be callable or None")
    analyzer = _Analyzer(plan)
    for trial, record in _collected_trials(plan, analyzer.schedule, workers):
        analyzer.add(record)
        if on_trial is not None:
            on_trial(trial, record)
    return analyzer.finish()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_dict(value), sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _gzip(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream,
    ):
        stream.write((_canonical(value) + "\n").encode())


def export_interaction_sampling(plan, output, *, source_revision, on_trial=None, workers=1):
    _worker_count(workers)
    protocol = interaction_sampling_protocol(plan, source_revision=source_revision)
    protocol["execution"] = {
        "workers": workers, "max_in_flight": 2 * workers if workers > 1 else 1,
        "result_order": "declared_trial_schedule", "resampling_on_failure": False,
    }
    if on_trial is not None and not callable(on_trial):
        raise TypeError("on_trial must be callable or None")
    root = Path(output)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Interaction sampling requires a new or empty output directory")
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "protocol.json", protocol)
    _write(root / "trace-schema.json", get_trace_schema())
    with ExitStack() as stack:
        streams = {}
        for name in plan.mechanisms:
            for game in plan.games:
                path = root / "trials" / f"{name}__{game}.jsonl.gz"
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = stack.enter_context(path.open("wb"))
                streams[(name, game)] = stack.enter_context(
                    gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0)
                )

        def retain(trial, record):
            entry = trial.entry
            streams[(entry.mechanism, entry.coalition_game)].write(
                (_canonical(record) + "\n").encode()
            )
            if entry.replicate == 0:
                public = {
                    "trial_plan": to_dict(entry),
                    "factual": {"decisions": to_dict(trial.factual_receipts)},
                    "branches": {},
                }
                gold = {"trial_plan": to_dict(entry), "episodes": {}}
                episodes = [("factual", trial.factual)]
                if trial.experiment is not None:
                    for branch in trial.experiment.branches:
                        key = f"branch_{branch.slot.index}"
                        public["branches"][key] = {
                            "slot": to_dict(branch.slot),
                            "summary": branch.replay.summary(),
                            "decisions": to_dict(branch.replay.decisions),
                        }
                        episodes.append((key, branch.replay.episode))
                for key, episode in episodes:
                    if episode is None:
                        continue
                    target = public["factual"] if key == "factual" else public["branches"][key]
                    target.update(
                        trace=to_dict(episode.trace), explanation=episode.explanation.to_dict()
                    )
                    gold["episodes"][key] = {
                        "seed": episode.seed,
                        "config": to_dict(episode.config),
                        "records": to_dict(episode.ground_truth),
                    }
                stem = f"{entry.mechanism}__{entry.coalition_game}.json.gz"
                _gzip(root / "evidence" / stem, public)
                _gzip(root / "evaluator_truth" / stem, gold)
            if on_trial is not None:
                on_trial(trial, record)
            if entry.replicate == plan.repeats - 1:
                print(
                    f"Completed {entry.mechanism}/{entry.coalition_game}: {plan.repeats} trials",
                    flush=True,
                )

        summary = run_interaction_sampling(plan, on_trial=retain, workers=workers)
    _write(root / "summary.json", summary)
    report = [
        "# Repeated physical refund interaction sampling",
        "",
        f"Retained {summary['retained_trials']} planned synthetic trials and {summary['planned_branches']} planned branches. Actual scripted calls: {summary['actual_policy_calls']}. No language model was called.",
        "",
        "Normal and Hoeffding/exact-endpoint variants reuse the same draws, points and refusals, with zero extra policy calls. The strict and on-reach games stay distinct. Undefined population references never enter numerical coverage denominators.",
        "",
        "All planned trials/slots are retained in compressed JSONL. Replicate zero was selected before sampling for complete public evidence and separately stored evaluator truth. Refusals, unknown evidence, invalid positions and budgets remain visible.",
        "",
        "The summary reports availability, refusal, reference eligibility, bias/RMSE, individual interval coverage, width, degeneracy and sign/dummy detection. Interaction diagnostics pool existing coalition occurrences and have no confidence interval.",
        "",
        "This is a predeclared synthetic sampler study, not live-model accuracy, template generalization or superiority over a matched attribution method. File hashes detect changed bytes, not authenticity.",
    ]
    (root / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    _write(
        root / "manifest.json",
        {
            "package_version": __version__,
            "status": "completed",
            "completed": True,
            "artifacts": [
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
                for path in sorted(root.rglob("*"))
                if path.is_file()
            ],
        },
    )
    return summary
