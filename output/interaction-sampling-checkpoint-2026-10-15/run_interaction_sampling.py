"""Standalone frozen physical interaction study runner; no model or CI calls.

Example: python scripts/run_interaction_sampling.py --source-revision COMMIT
--output output/my-interaction-sampling
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
import time

from consequa_x.benchmark.interaction_sampling import (
    GAMES,
    InteractionSamplingPlan,
    export_interaction_sampling,
)
from consequa_x.benchmark.interaction_mechanisms import INTERACTION_MECHANISMS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--repeats", type=int, default=128)
    parser.add_argument("--pairs", type=int, default=32)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--endpoint-samples", type=int, default=32)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=20_000_000)
    parser.add_argument("--max-calls", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--mechanism", action="append", choices=tuple(INTERACTION_MECHANISMS))
    parser.add_argument("--game", action="append", choices=GAMES)
    args = parser.parse_args(argv)
    plan = InteractionSamplingPlan(
        repeats=args.repeats,
        pairs=args.pairs,
        samples_per_eval=args.samples,
        endpoint_samples=args.endpoint_samples,
        confidence=args.confidence,
        seed=args.seed,
        max_calls=args.max_calls,
        mechanisms=tuple(args.mechanism or INTERACTION_MECHANISMS),
        games=tuple(args.game or GAMES),
    )
    root = Path(args.output)
    execution_path = root.parent / f"{root.name}-execution.json"
    if execution_path.exists():
        raise ValueError("Execution receipt already exists; preserve previous study records")
    started = datetime.now(timezone.utc).isoformat()
    tick = time.perf_counter()
    completed = 0
    def progress(trial, record):
        nonlocal completed
        completed += 1
        if completed % 16 == 0:
            print(f"Collected {completed}/{plan.trial_count} trials", flush=True)
    summary = export_interaction_sampling(plan, args.output, source_revision=args.source_revision,
                                         workers=args.workers, on_trial=progress)
    # Receipt stays outside the artifact's sealed inventory, avoiding self-reference
    # or mutation of the completed export. Preserve this alongside the study.
    execution = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - tick,
        "source_revision": args.source_revision,
        "python": sys.version,
        "platform": platform.platform(),
        "argv": list(sys.argv if argv is None else argv),
        "module_file": __import__(
            "consequa_x.benchmark.interaction_sampling", fromlist=[""]
        ).__file__,
        "planned_trials": summary["planned_trials"],
        "planned_branches": summary["planned_branches"],
        "actual_policy_calls": summary["actual_policy_calls"],
        "artifact_manifest_sha256": sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "generation_provider": "synthetic",
        "model_calls": 0,
        "workers": args.workers,
    }
    execution_path.write_text(
        json.dumps(execution, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(root.resolve()),
                "execution_receipt": str(execution_path.resolve()),
                "elapsed_seconds": execution["elapsed_seconds"],
                "actual_policy_calls": summary["actual_policy_calls"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
