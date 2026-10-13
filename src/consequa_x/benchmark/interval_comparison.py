"""Frozen, same-draw interval comparisons and finite binomial calculations."""

from contextlib import ExitStack
from dataclasses import replace
from fractions import Fraction
import gzip
from hashlib import sha256
import math
from pathlib import Path

from .. import __version__
from ..models import to_dict
from .calibration import (
    CalibrationPlan, CalibrationResult, INTERVAL_COMPARISON_CASES,
    analyze_calibration, calibration_protocol, compact_calibration_trial,
)
from .calibration_export import _json, _write_json, export_calibration
from .decision_contrastive import with_contrastive_interval
from .decision_shapley import with_shapley_intervals
from .intervals import binomial_interval


CONTRASTIVE_VARIANTS = ("percentile_bootstrap", "wilson", "clopper_pearson")
SHAPLEY_VARIANTS = ("normal", "hoeffding_exact_endpoints")
PROBABILITY_GRID = tuple(Fraction(value) for value in (
    "0", ".01", ".05", ".1", ".25", ".5", ".75", ".9", ".95", ".99", "1"))
SAMPLE_GRID = (8, 16, 32, 64)


def comparison_plan(*, repeats=32, seed=2_000_000, **settings):
    """Fresh integration defaults; the legacy replay methods supply shared draws."""
    return CalibrationPlan(repeats=repeats, seed=seed, mechanisms=INTERVAL_COMPARISON_CASES,
                           **settings)


def _bootstrap_limit_interval(successes, total, confidence):
    """Infinite-resample percentile limits for the empirical binomial law.

    This is NOT exact coverage of a particular finite seeded bootstrap run.
    Finite bootstrap intervals are separately compared on fresh actual traces.
    """
    p = Fraction(successes, total)
    tail = Fraction.from_float((1-confidence)/2)
    cumulative = Fraction(0)
    lower = upper = None
    for count in range(total+1):
        cumulative += math.comb(total, count) * p**count * (1-p)**(total-count)
        if lower is None and cumulative >= tail:
            lower = count / total
        if upper is None and cumulative >= 1-tail:
            upper = count / total
    return lower, upper


def finite_binomial_comparison(*, confidence=.95):
    """Enumerate every success count using exact rational binomial weights."""
    # Reuse public input validation before any artifact is created.
    binomial_interval(0, 1, confidence=confidence)
    rows = []
    count_intervals = []
    for total in SAMPLE_GRID:
        methods = {
            "percentile_bootstrap_limit": [_bootstrap_limit_interval(k, total, confidence)
                                           for k in range(total+1)],
            "wilson": [binomial_interval(k, total, confidence=confidence, method="wilson")
                       for k in range(total+1)],
            "clopper_pearson": [binomial_interval(k, total, confidence=confidence)
                                for k in range(total+1)],
        }
        for method, intervals in methods.items():
            count_intervals.append({"samples": total, "method": method,
                                    "intervals_by_success_count": intervals})
            for q in PROBABILITY_GRID:
                weights = [math.comb(total, k)*q**k*(1-q)**(total-k) for k in range(total+1)]
                assert sum(weights) == 1
                covered = sum(weight for weight, (low, high) in zip(weights, intervals)
                              if low <= float(q) <= high)
                degenerate = sum(weight for weight, (low, high) in zip(weights, intervals)
                                 if low == high)
                rows.append({"samples": total, "probability": float(q), "method": method,
                             "coverage": float(covered),
                             "coverage_fraction": [covered.numerator, covered.denominator],
                             "expected_width": math.fsum(float(weight)*(high-low)
                                                          for weight, (low, high) in zip(weights, intervals)),
                             "zero_width_probability": float(degenerate),
                             "zero_count_interval": intervals[0], "full_count_interval": intervals[-1],
                             "probability_mass": 1})
    return {"kind": "finite_binomial_interval_comparison_v1", "confidence": confidence,
            "sample_grid": SAMPLE_GRID, "probability_grid": [float(q) for q in PROBABILITY_GRID],
            "rows": rows, "count_intervals": count_intervals,
            "arithmetic": "exact rational probability weights; floating-point interval boundaries",
            "bootstrap_scope": "limiting empirical bootstrap; finite seeded bootstrap is tested in integration",
            "scope": "independent known Bernoulli draws, constant observed factual baseline",
            "limits": ["No multiplicity correction, unknown evidence, model generalization or seed independence established.",
                       "Clopper-Pearson classification relies on numerically validated binomial inversion."]}


def _contrastive_record(result):
    return {"summary": result.summary(), "method": result.method_record(),
            "results": [item.to_dict() for item in result.results], "loci": to_dict(result.loci)}


def _shapley_record(result):
    return {"summary": result.summary(), "method": result.method_record(),
            "results": [item.to_dict() for item in result.results],
            "endpoint_checks": to_dict(result.endpoint_checks)}


def _manifest(output):
    artifacts = [{"path": path.relative_to(output).as_posix(),
                  "sha256": sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
                 for path in sorted(output.rglob("*")) if path.is_file() and path != output/"manifest.json"]
    _write_json(output/"manifest.json", {"package_version": __version__, "status": "completed",
                                        "artifacts": artifacts})


def export_interval_comparison(plan: CalibrationPlan, output, *, source_revision=None, theory_only=False):
    """Declare first, collect one unchanged replay dataset, then compare intervals.

    Full policy/world evidence is retained once under raw/. Every interval uses
    exactly that dataset. Compact comparison receipts identify its trial and
    cannot spend a second policy-call allowance or turn a refusal into a point.
    """
    protocol = calibration_protocol(plan)
    if (plan.contrastive_interval_method != "percentile_bootstrap"
            or plan.shapley_interval_method != "normal" or plan.endpoint_interval_method != "normal"):
        raise ValueError("comparison collection must preserve the original bootstrap/normal methods")
    if source_revision is not None and (type(source_revision) is not str or not source_revision.strip()):
        raise ValueError("source_revision must be a nonempty identifier or None")
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("compare-intervals requires a new or empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output/"protocol.json", {"package_version": __version__, **protocol,
        "study_kind": "same_draw_interval_comparison_v1", "source_revision": source_revision,
        "theory_only": theory_only, "contrastive_variants": CONTRASTIVE_VARIANTS,
        "shapley_variants": SHAPLEY_VARIANTS, "additional_policy_calls_for_comparison": 0,
        "finite_sample_grid": SAMPLE_GRID, "finite_probability_grid": [float(q) for q in PROBABILITY_GRID],
        "retention": "all raw trials plus all numerical variants; full raw evidence preselected at replicate 0"})
    finite = finite_binomial_comparison(confidence=plan.confidence)
    _write_json(output/"finite-binomial.json", finite)
    if theory_only:
        (output/"README.md").write_text(
            "# Finite binomial interval comparison\n\n"
            "Every binomial count was enumerated on the predeclared sample/probability grid. "
            "Probability weights are exact rational values; interval boundaries use floating-point arithmetic. "
            "The bootstrap column is its infinite-resample limit, not a finite seeded bootstrap guarantee. "
            "No payment replay or model was run.\n", encoding="utf-8", newline="\n")
        _manifest(output)
        return {"finite_binomial": finite, "actual_policy_calls": 0}

    compact_variants = {name: [] for name in CONTRASTIVE_VARIANTS + SHAPLEY_VARIANTS[1:]}
    with ExitStack() as stack:
        streams = {}
        for name in plan.mechanisms:
            path = output/"comparisons"/f"{name}.jsonl.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = stack.enter_context(path.open("wb"))
            streams[name] = stack.enter_context(gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0))

        def compare(trial):
            base = compact_calibration_trial(trial)
            c_records = {}
            s_records = {}
            for name in CONTRASTIVE_VARIANTS:
                if trial.contrastive is None:
                    compact_variants[name].append(base)
                    c_records[name] = None
                    continue
                result = with_contrastive_interval(trial.contrastive, interval_method=name)
                fields = _contrastive_record(result)
                c_records[name] = fields
                compact_variants[name].append(replace(base, contrastive={**base.contrastive, **fields}))
            if trial.shapley is not None:
                result = with_shapley_intervals(trial.shapley, interval_method="hoeffding",
                                                endpoint_interval_method="clopper_pearson_difference")
                fields = _shapley_record(result)
                s_records["normal"] = _shapley_record(trial.shapley)
                s_records["hoeffding_exact_endpoints"] = fields
                compact_variants["hoeffding_exact_endpoints"].append(
                    replace(base, shapley={**base.shapley, **fields}))
            else:
                s_records = dict.fromkeys(SHAPLEY_VARIANTS)
                compact_variants["hoeffding_exact_endpoints"].append(base)
            record = {"seed_plan": to_dict(trial.seed_plan),
                      "raw_evidence": f"raw/trials/{trial.seed_plan.mechanism}.jsonl.gz",
                      "replicate": trial.seed_plan.replicate, "contrastive": c_records,
                      "shapley": s_records, "calls": base.to_dict()["calls"],
                      "additional_policy_calls": 0}
            streams[trial.seed_plan.mechanism].write((_json(record)+"\n").encode("utf-8"))

        raw_result = export_calibration(plan, output/"raw", source_revision=source_revision, on_trial=compare)

    original = raw_result.summary()
    summaries = {name: analyze_calibration(CalibrationResult(plan, tuple(trials)))
                 for name, trials in compact_variants.items()}
    summary = {"package_version": __version__, "kind": "same_draw_interval_comparison_v1",
               "source_revision": source_revision, "planned_trials": original["planned_trials"],
               "actual_policy_calls": original["actual_policy_calls"],
               "additional_policy_calls_for_comparison": 0,
               "contrastive": {name: {"estimates": [row for row in summaries[name]["estimates"]
                                                      if row["method"] == "contrastive"],
                                       "loci": summaries[name]["loci"]} for name in CONTRASTIVE_VARIANTS},
               "shapley": {"normal": {"estimates": [row for row in original["estimates"]
                                                       if row["method"] == "shapley"],
                                         "endpoints": original["endpoints"]},
                            "hoeffding_exact_endpoints": {
                                "estimates": [row for row in summaries["hoeffding_exact_endpoints"]["estimates"]
                                              if row["method"] == "shapley"],
                                "endpoints": summaries["hoeffding_exact_endpoints"]["endpoints"]}},
               "raw_summary": "raw/summary.json",
               "limits": ["Every variant shares points, target labels, seeds, actual calls and all refusals.",
                          "Coverage requires analytic eligibility; a completed invalid-population game remains unscored.",
                          "Conservative intervals can be substantially wider; no model or task-generalization claim.",
                          "Within-method independence is an assumption; requested RNG keys do not prove it."]}
    _write_json(output/"summary.json", summary)
    _write_report(output, plan, summary, finite)
    _manifest(output)
    print(f"Saved same-draw interval comparison in {output.resolve()}")
    return summary


def _write_report(output, plan, summary, finite):
    def coverage(row):
        value = row["interval_coverage"]
        n, d = value["numerator"], value["denominator"]
        return f"{n}/{d}" if d else "unavailable"

    lines = ["# Same-draw interval comparison\n",
             f"{summary['planned_trials']} predeclared synthetic trials, {plan.repeats} repetitions per case. "
             "No language model was called. All variants reuse the same real refund-world evidence; "
             "interval comparisons spent zero additional policy calls.\n",
             "## Consequence coverage at the timeout position\n",
             "| Mechanism | Bootstrap | Wilson | Exact binomial | Normal Shapley | Hoeffding Shapley |",
             "| --- | --- | --- | --- | --- | --- |"]
    for mechanism in plan.mechanisms:
        row_values = []
        for name in CONTRASTIVE_VARIANTS:
            rows = summary["contrastive"][name]["estimates"]
            row_values.append(coverage(next(r for r in rows if r["mechanism"] == mechanism
                                            and r["target"] == "consequence" and r["decision_index"] == 1)))
        for name in SHAPLEY_VARIANTS:
            rows = summary["shapley"][name]["estimates"]
            row_values.append(coverage(next(r for r in rows if r["mechanism"] == mechanism
                                            and r["target"] == "consequence" and r["decision_index"] == 1)))
        lines.append("| " + " | ".join([mechanism, *row_values]) + " |")
    minima = {name: min(r["coverage"] for r in finite["rows"] if r["method"] == name)
              for name in ("percentile_bootstrap_limit", "wilson", "clopper_pearson")}
    lines += ["", "Coverage denominators include available eligible intervals only. Availability and "
              "covered/planned eligible composites remain separate in `summary.json`. The state and "
              "linked targets share evidence and are not pooled as independent observations.\n",
              "## Finite distribution calculation\n",
              "The predeclared grid uses n=8,16,32,64 and eleven probabilities including zero and one. "
              "Minimum coverage over that grid: " + ", ".join(f"{name} {100*value:.2f}%" for name, value in minima.items()) + ". "
              "The bootstrap entry is its infinite-resample limit; actual seeded bootstrap intervals "
              "are separately measured above. Exact probability weights do not make a finite "
              "observed coverage proportion a population guarantee.\n",
              "## Width, refusals and interpretation\n",
              "Exact binomial and Hoeffding options retain uncertainty at homogeneous samples and "
              "can be much wider than bootstrap/normal intervals. Every row retains mean interval "
              "width, point bias/RMSE, zero-width frequency and explicit refusal counts. "
              "No point, draw, locus rule or budget was changed. Different interval bounds can "
              "change nominal locus selections; all such selections are retained.\n",
              "The strict three-position retry game can be population-undefined. Available vectors "
              "there remain ineligible for numerical scoring. Unknown readback/provenance and "
              "budget failures remain refusals under every method. Conservative bounds do not "
              "repair undefined interventions or missing evidence.\n",
              "Binomial bounds require independent known binary draws; Hoeffding requires "
              "independent bounded pair observations from a defined game. Requested seeds do not "
              "establish these assumptions for live models. Intervals remain individual, with "
              "no multiplicity correction across decisions or targets.\n",
              "Raw public traces and explanations for replicate 0 are under `raw/evidence/`; "
              "simulator gold is separate. All planned raw draws and numerical variants are "
              "compressed JSONL. Both protocols were saved before policy calls. Byte manifests "
              "detect changes, not authenticity.\n"]
    (output/"README.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
