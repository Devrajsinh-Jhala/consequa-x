"""Retain a predeclared synthetic protective-decision or invalid-coalition example."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import time

from consequa_x import __version__
from consequa_x.benchmark.decision_shapley import shapley_decisions
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig
from consequa_x.benchmark.targets import episode_outcome
from consequa_x.models import AssessmentStatus, ResponseStatus, to_dict
from consequa_x.policies import PolicyDecision, PolicyReply, ScriptedRefundPolicy
from consequa_x.schema import get_trace_schema


class SeededRetryPolicy(ScriptedRefundPolicy):
    """Always select the eligible refund; use a seeded coin after a timeout."""

    @property
    def metadata(self):
        return {"provider": "synthetic", "policy": "seeded-visible-refund-retry",
                "version": "1", "retry_probability": 0.5}

    def decide(self, request, *, seed):
        if (request.stage == "after_response"
                and request.responses[-1].status is ResponseStatus.TIMEOUT
                and request.attempts_remaining
                and request.context.get("retry_instruction", "").strip()):
            decision = PolicyDecision(
                "retry" if random.Random(seed).random() < 0.5 else "stop",
                AssessmentStatus.UNKNOWN,
                "Synthetic policy uses its declared retry coin after an ambiguous timeout.",
            )
        else:
            decision = super().decide(request, seed=seed).decision
        return PolicyReply(decision, {**self.metadata, "seed": seed})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("protection", "invalid"), default="protection")
    parser.add_argument("--source-commit", help="Caller-declared installed source revision")
    args = parser.parse_args(argv)
    root = Path(args.output)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Use a new or empty output directory; preserve prior evidence")
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []

    def save(relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(to_dict(value), indent=2, sort_keys=True, allow_nan=False)
                        + "\n", encoding="utf-8")
        payload = path.read_bytes()
        artifacts.append({"path": relative, "sha256": sha256(payload).hexdigest(),
                          "size_bytes": len(payload)})

    protective = args.mode == "protection"
    pairs, samples, endpoints = (8, 2, 8) if protective else (2, 1, 2)
    factual_policy_seed = 3 if protective else 0
    config = ScenarioConfig(name=f"seeded-retry-{args.mode}", fault=Fault.TIMEOUT_AFTER_COMMIT,
                            context=RefundContext(retry_instruction=True), use_idempotency=False)
    # Both the execution settings and analytic idealization are written before
    # any factual or continuation policy decision. Truth never enters sampling.
    save("protocol.json", {
        "declared_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": args.source_commit, "package_version": __version__,
        "recipe_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "mode": args.mode, "world_seed": 0, "factual_policy_seed": factual_policy_seed,
        "continuation_seed": 100, "permutation_seed": 0, "pairs": pairs,
        "samples_per_eval": samples, "endpoint_samples": endpoints,
        "max_attempts": 2, "shared_max_calls": 400,
        "confidence": 0.95, "targets": ["action", "consequence", "action_linked_consequence"],
        "model_calls": 0, "redraws": 0,
        "scope": "Fixed synthetic mechanism integrity example, not calibration or model performance.",
    })
    save("fixture-truth.json", {
        "declared_before_policy_calls": True,
        "mechanism": "One refund commits before an ambiguous timeout. A non-idempotent "
                     "retry commits a duplicate; stopping preserves one refund. Initial selection "
                     "always refunds; new post-success decisions stop.",
        "retry_coin_idealization": 0.5,
        "factual_roles": ["initial selection", "timeout stop"] if protective else
                         ["initial selection", "timeout retry", "post-success stop"],
        "reference": {
            "action": {"population_shapley": [0.0, 0.0], "endpoint_difference": 0.0},
            "consequence": {"population_shapley": [0.0, -0.5], "endpoint_difference": -0.5},
            "action_linked_consequence": {"population_shapley": [0.0, -0.5], "endpoint_difference": -0.5},
        } if protective else None,
        "invalid_reference": None if protective else
                             "Holding post-success position 2 after resampling position 1 can "
                             "be unreachable. Such samples invalidate the positional coalition "
                             "and refuse its whole path vector; no population shares are declared.",
        "reference_limit": "Bernoulli idealization, not guaranteed finite seeded estimates. "
                           "An irrelevant player can receive finite fresh-sampling noise. This "
                           "refund example does not test recovery of interacting decisions.",
    })
    bounded = BudgetedPolicy(SeededRetryPolicy(), 400)
    started = time.perf_counter()
    factual = run_policy_scenario(config, bounded, seed=0, policy_seed=factual_policy_seed,
                                  max_attempts=2)
    factual_seconds = time.perf_counter() - started
    factual_calls = bounded.calls
    save("traces/factual.json", factual.trace)
    started = time.perf_counter()
    result = shapley_decisions(factual, bounded, pairs=pairs, samples_per_eval=samples,
                               endpoint_samples=endpoints, seed=100, permutation_seed=0,
                               targets=("action", "consequence", "action_linked_consequence"))
    continuation_seconds = time.perf_counter() - started
    by_index = {branch.slot.index: branch for branch in result.branches}
    receipts = []
    for slot in result.slots:
        receipt = to_dict(slot)
        branch = by_index.get(slot.index)
        if branch is None:
            receipt.update(status="not_started", policy_calls=0, decisions=[])
        else:
            replay = branch.replay
            receipt.update(replay.summary(), decisions=to_dict(replay.decisions))
            if replay.episode is not None:
                path = f"traces/branch_{slot.index:05d}.json"
                save(path, replay.episode.trace)
                receipt.update(trace=path, outcome=to_dict(episode_outcome(replay.episode)))
        receipts.append(receipt)
    save("results.json", {
        "source_commit": args.source_commit, "policy": result.policy_metadata,
        "factual": {"trace": "traces/factual.json", "policy_calls": factual_calls,
                    "trace_sha256": sha256((root / "traces/factual.json").read_bytes()).hexdigest(),
                    "outcome": to_dict(episode_outcome(factual))},
        "planned_schedule": result.slots, "permutations": result.permutations,
        "branches": receipts, "summary": result.summary(), "method": result.method_record(),
        "estimates": [estimate.to_dict() for estimate in result.results],
        "endpoint_checks": result.endpoint_checks,
        "calls": {"factual": factual_calls, "continuation": result.calls,
                  "total": bounded.calls, "max_calls": bounded.max_calls},
        "timing_seconds": {"factual": factual_seconds, "continuation_and_estimation": continuation_seconds},
        "scope": "Synthetic protective-decision or invalid-coalition demonstration; "
                 "no redraws, model inference, interval calibration, or domain interaction claim.",
    })
    save("trace-schema.json", get_trace_schema())
    (root / "manifest.json").write_text(json.dumps({"artifacts": artifacts}, indent=2)
                                       + "\n", encoding="utf-8")
    print(json.dumps({"summary": result.summary(), "estimates": [item.to_dict() for item in result.results]},
                     sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
