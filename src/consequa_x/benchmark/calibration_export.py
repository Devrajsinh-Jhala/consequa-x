"""Portable, deterministic evidence exports for the offline calibration probe."""

from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path

from .. import __version__
from ..models import to_dict
from ..schema import get_trace_schema
from .calibration import (
    calibration_protocol, compact_calibration_trial, run_calibration,
)


def _json(value):
    return json.dumps(to_dict(value), sort_keys=True, allow_nan=False, separators=(",", ":"))


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def export_calibration(plan, output, *, source_revision=None, on_trial=None):
    """Save the frozen protocol first; retain every compact trial and replicate 0.

    An existing nonempty directory is rejected. Partial exports survive an
    execution or export error and lack the final completion manifest.
    """
    output = Path(output)
    protocol = calibration_protocol(plan)
    if on_trial is not None and not callable(on_trial):
        raise TypeError("on_trial must be callable or None")
    if source_revision is not None and (not isinstance(source_revision, str)
                                        or not source_revision.strip()):
        raise ValueError("source_revision must be a nonempty identifier or None")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("calibrate-attribution requires a new or empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "protocol.json", {"package_version": __version__, **protocol,
        "source_revision": source_revision,
        "source_revision_trust": "caller supplied; the exporter does not inspect Git",
        "retention": {"all_trials": "trials/<mechanism>.jsonl.gz",
                      "full_evidence_replicates": [0],
                      "selection": "replicate 0, every attempted branch, including failures",
                      "gzip_mtime": 0}})
    _write_json(output / "trace-schema.json", get_trace_schema())

    def gz_write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write((_json(value) + "\n").encode("utf-8"))

    def evidence(trial):
        public = {"seed_plan": to_dict(trial.seed_plan), "methods": {}}
        gold = {"seed_plan": to_dict(trial.seed_plan), "methods": {}}
        for method, factual, decisions, experiment in (
            ("contrastive", trial.factual, trial.factual_decisions, trial.contrastive),
            ("shapley", trial.shapley_factual, trial.shapley_factual_decisions, trial.shapley),
        ):
            episodes = [("factual", factual, decisions)]
            if experiment is not None:
                for branch in experiment.branches:
                    index = branch.index if method == "contrastive" else branch.slot.index
                    episodes.append((f"branch_{index}", branch.replay.episode,
                                     branch.replay.decisions))
            public["methods"][method] = {}
            gold["methods"][method] = {}
            for key, episode, receipts in episodes:
                record = {"decisions": to_dict(receipts)}
                if episode is not None:
                    record.update(trace=to_dict(episode.trace),
                                  explanation=episode.explanation.to_dict())
                    gold["methods"][method][key] = {
                        "config": to_dict(episode.config), "seed": episode.seed,
                        "records": to_dict(episode.ground_truth)}
                public["methods"][method][key] = record
        gz_write(output / "evidence" / f"{trial.seed_plan.mechanism}.json.gz", public)
        gz_write(output / "evaluator_truth" / f"{trial.seed_plan.mechanism}.json.gz", gold)

    with ExitStack() as stack:
        streams = {}
        for name in plan.mechanisms:
            path = output / "trials" / f"{name}.jsonl.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = stack.enter_context(path.open("wb"))
            streams[name] = stack.enter_context(gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", mtime=0))

        def retain(trial):
            record = compact_calibration_trial(trial).to_dict()
            streams[trial.seed_plan.mechanism].write((_json(record) + "\n").encode("utf-8"))
            if trial.seed_plan.replicate == 0:
                evidence(trial)
            if on_trial is not None:
                on_trial(trial)
            if trial.seed_plan.replicate == plan.repeats - 1:
                print(f"Completed {trial.seed_plan.mechanism}: {plan.repeats} planned trials",
                      flush=True)

        result = run_calibration(plan, on_trial=retain)

    summary = result.summary()
    _write_json(output / "summary.json", {"package_version": __version__, **summary})
    report = (
        "# Synthetic attribution calibration probe\n\n"
        f"{len(result.trials)} predeclared trials across {len(plan.mechanisms)} mechanisms; "
        f"{plan.repeats} repetitions each. No language model was called.\n\n"
        "`protocol.json` was saved before policy calls. `summary.json` reports "
        "availability, reference eligibility, error and interval coverage with explicit "
        "denominators. All planned draws and refusal receipts are in compressed JSONL "
        "files under `trials/`. Full public traces, explanations and decision receipts "
        "for replicate 0 are in `evidence/`; its gold records stay separately in "
        "`evaluator_truth/`. Python's standard `gzip` module can read these files.\n\n"
        "The policy has a declared fixed factual timeout intervention and stochastic "
        "fresh continuations. Analytic references describe its ideal Bernoulli law, "
        "not the observed replay sample. The three-position retry game has undefined "
        "population Shapley values when some held positions are unreachable. Available "
        "finite estimates there are not scored against fabricated truth.\n\n"
        "Missing provenance, stale readback and the three-call budget control are "
        "intentional refusal strata. Refusals remain in planned denominators. "
        "State and linked targets reuse outcomes and are not independent replications. "
        "This exploratory synthetic probe does not establish calibrated coverage, "
        "model accuracy, interaction recovery or method superiority.\n\n"
        "The file manifest detects changed bytes, not authenticity. The detailed "
        "design and metric definitions are in `docs/attribution-calibration.md`.\n"
    )
    (output / "README.md").write_text(report, encoding="utf-8", newline="\n")
    artifacts = [{"path": path.relative_to(output).as_posix(),
                  "sha256": sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
                 for path in sorted(output.rglob("*")) if path.is_file()]
    _write_json(output / "manifest.json", {"package_version": __version__,
                                          "status": "completed", "artifacts": artifacts})
    print(f"Saved calibration probe in {output.resolve()}")
    return result
