"""Reproduce a declared seeded retry mechanism using an installed Consequa-X.

This synthetic fixture has an analytic reference independent of the estimator.
It performs no model inference and uses only simulated payments. The source
revision supplied by the caller is a declaration, not package authentication.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import time

from consequa_x import __version__
from consequa_x.benchmark.decision_contrastive import contrastive_decisions
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig
from consequa_x.benchmark.targets import episode_outcome
from consequa_x.models import AssessmentStatus, ResponseStatus, to_dict
from consequa_x.policies import PolicyDecision, PolicyReply, ScriptedRefundPolicy
from consequa_x.schema import get_trace_schema


class SeededRetryPolicy(ScriptedRefundPolicy):
    """Select the eligible refund; flip a seeded fair coin after a timeout."""

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
                "Synthetic policy uses its declared seeded retry coin after an ambiguous timeout.",
            )
        else:
            decision = super().decide(request, seed=seed).decision
        return PolicyReply(decision, {**self.metadata, "seed": seed})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-commit", help="Caller-declared installed source revision")
    args = parser.parse_args(argv)
    root = Path(args.output)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Use a new or empty output directory; prior evidence is preserved")
    root.mkdir(parents=True, exist_ok=True)
    artifacts = []

    def save(relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(to_dict(value), indent=2, sort_keys=True,
                                   allow_nan=False) + "\n", encoding="utf-8")
        artifacts.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest(),
                          "size_bytes": path.stat().st_size})

    config = ScenarioConfig(
        name="seeded-retry-pivot", fault=Fault.TIMEOUT_AFTER_COMMIT,
        context=RefundContext(retry_instruction=True), use_idempotency=False,
    )
    # Settings and analytic mechanism truth are saved before drawing any policy
    # decision. The truth file is not an input to the policy or estimator.
    save("protocol.json", {
        "source_commit": args.source_commit, "package_version": __version__,
        "declared_at_utc": datetime.now(timezone.utc).isoformat(),
        "recipe_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "provider": "synthetic", "model_calls": 0,
        "world_seed": 0, "factual_policy_seed": 0,
        "continuation_seed": 100, "samples_per_decision": 16,
        "max_calls_shared": 400, "max_attempts": 2,
        "targets": ["action", "consequence", "action_linked_consequence"],
        "confidence": 0.95, "bootstrap_samples": 2000, "bootstrap_seed": 0,
        "scope": "Fixed synthetic mechanism; no redraw, tuning, or model inference.",
    })
    save("fixture-truth.json", {
        "declared_before_sampling": True,
        "mechanism": "A timeout follows one committed refund. A non-idempotent retry "
                     "commits a duplicate; stopping after the timeout preserves exactly one refund.",
        "population_retry_probability": 0.5,
        "intended_latest_population_rescue_position": 1,
        "decision_roles": ["initial selection", "timeout retry/stop", "terminal stop"],
        "population_changed_bad_rates": {
            "action": [0.0, 0.0, 0.0], "consequence": [0.5, 0.5, 1.0],
            "action_linked_consequence": [0.5, 0.5, 1.0],
        },
        "reference_limit": "Analytic Bernoulli idealization of a seeded pseudorandom coin; "
                           "not a guarantee for the finite declared seed schedule. The observed "
                           "factual seed is fixed and is not a population baseline estimate.",
    })
    bounded = BudgetedPolicy(SeededRetryPolicy(), 400)
    started = time.perf_counter()
    factual = run_policy_scenario(config, bounded, seed=0, max_attempts=2)
    factual_seconds = time.perf_counter() - started
    factual_calls = bounded.calls
    save("traces/factual.json", factual.trace)
    started = time.perf_counter()
    result = contrastive_decisions(
        factual, bounded, samples=16, seed=100,
        targets=("action", "consequence", "action_linked_consequence"),
        confidence=0.95, bootstrap_samples=2000, bootstrap_seed=0,
    )
    continuation_seconds = time.perf_counter() - started
    branches = []
    for branch in result.branches:
        receipt = {"index": branch.index, "decision_index": branch.decision_index,
                   "continuation_seed": branch.continuation_seed,
                   **branch.replay.summary()}
        if branch.replay.episode is not None:
            path = f"traces/branch_{branch.index:05d}.json"
            save(path, branch.replay.episode.trace)
            receipt.update(trace=path, outcome=to_dict(episode_outcome(branch.replay.episode)))
        else:
            receipt["decisions"] = to_dict(branch.replay.decisions)
        branches.append(receipt)
    save("results.json", {
        "source_commit": args.source_commit, "policy": result.policy_metadata,
        "factual": {"trace": "traces/factual.json", "policy_calls": factual_calls,
                    "outcome": to_dict(episode_outcome(factual))},
        "branches": branches, "planned_seeds": result.planned_seeds,
        "summary": result.summary(), "method": result.method_record(),
        "estimates": [estimate.to_dict() for estimate in result.results],
        "loci": result.loci,
        "cost": {"factual_policy_calls": factual_calls,
                 "continuation_policy_calls": result.calls, "total_policy_calls": bounded.calls,
                 "factual_seconds": factual_seconds,
                 "continuation_validation_and_estimation_seconds": continuation_seconds},
        "scope": "Synthetic mechanism integrity and localization example, not model performance "
                 "or calibrated statistical coverage. No match to upstream numerical RNG is claimed.",
    })
    save("trace-schema.json", get_trace_schema())
    # Deliberately no evaluator labels in the traces. The separate analytic
    # truth is retained only for external scoring; explanations are recomputable.
    (root / "manifest.json").write_text(json.dumps({"artifacts": artifacts}, indent=2)
                                       + "\n", encoding="utf-8")
    print(json.dumps({"completed_branches": result.summary()["completed_branches"],
                      "loci": to_dict(result.loci), "policy_calls": bounded.calls}, sort_keys=True))


if __name__ == "__main__":
    main()
