"""Export the complete controlled availability grid after completed, bound audit.

This exporter imports no world, controller, collection runner, auditor or
framework, and never executes a study. It reads every retained artifact only to
verify its bound bytes; plotted values come from independently recomputed case
summaries and the auditor's coverage analysis, not analytical hypotheses.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import subprocess


SCHEMA = "conseqa-availability-publication-exports-v1"
STUDY_SCHEMA = "conseqa-recovery-availability-sweep-v1"
AUDIT_SCHEMA = "conseqa-availability-postcollection-audit-v1"
EXPECTED_PROTOCOL_SHA256 = "e874c6781aa0dbc8ef682ea0a8d37c25d73cc861dada05fd0379116d4a7f6584"
ENGINE_COMMIT = "22e88498cff0e2afd1549803fb4d9645902e74b9"
SEMANTIC_AUDITOR = "scripts/audit_recovery_controller_study.py"
SEMANTIC_AUDITOR_SHA256 = "6a5a02d654a9d56d50ac10920b47b5543addb116eae123d119c8bcaf70ecaf91"
SWEEP_AUDITOR = "scripts/audit_recovery_availability_sweep.py"
METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
DOMAINS = ("inventory_reservation", "support_transition", "delivery_registration")
FACTORS = {"lag_ms": [0, 40, 80, 95], "unavailable_until_ms": [0, 170, 210, 250],
           "incomplete_until_ms": [0, 170, 210, 250]}
POLL, SINGLE = "consequax_poll", "consequax_one_read"
SPEC = {"figure_inches": [7.1, 7.35], "minimum_font_points": 10.5, "annotation_font_points": 11,
        "png_dpi": 300, "factor_order": FACTORS, "method_order": list(METHODS),
        "facets": "incomplete_until_ms ascending; rows lag_ms; columns unavailable_until_ms",
        "cell_counts": "Observed correct definite global-state reports: polling | one-final-read, each /3 planned domains",
        "cell_reads": "Mean charged reads among observed completed slots: polling | one-final-read",
        "color": "polling minus one-final-read correct definite counts; fixed limits [-3,3]",
        "uncertainty_intervals": False, "population_inference": False,
        "selection": "Every one of the 64 prospective controlled profiles; no outcome-dependent selection",
        "layout_revision": 2}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def strict_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def invalid(value):
        raise ValueError(f"nonfinite JSON token: {value}")

    value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=invalid)
    require(type(value) is dict, "JSON artifact must be an object")
    return value


def safe_path(root, name):
    require(type(name) is str and name and "\\" not in name and ":" not in name, "unsafe manifest path")
    part = PurePosixPath(name)
    require(not part.is_absolute() and part.as_posix() == name and all(x not in {".", ".."} for x in part.parts),
            "noncanonical manifest path")
    target = root.joinpath(*part.parts)
    require(target.resolve().is_relative_to(root.resolve()), "manifest path escapes root")
    return target


def verify_inventory(root, expected_schema, *, terminal=False):
    manifest = strict_json(root / "manifest.json")
    require(manifest.get("complete") is True and manifest.get("schema") == expected_schema,
            "artifact inventory is incomplete or has another schema")
    files = manifest.get("files")
    require(type(files) is dict and files, "manifest has no file bindings")
    for name, digest in files.items():
        require(type(digest) is str and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
                "malformed artifact digest")
        path = safe_path(root, name)
        require(path.is_file() and sha(path) == digest, f"artifact hash differs: {name}")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    expected = set(files) | {"manifest.json"}
    if terminal:
        expected.add("completion-receipt.json")
    require(actual == expected, "missing or unmanifested artifacts")
    return manifest


def git_blob(root, commit, name):
    require(type(commit) is str and len(commit) == 40 and all(c in "0123456789abcdef" for c in commit),
            "invalid source commit")
    safe_path(root, name)
    return subprocess.check_output(["git", "-C", str(root), "show", f"{commit}:{name}"])


def bound_bytes(data, expected, label):
    require(expected == {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)},
            f"source byte binding differs: {label}")


def same_summary(left, right, path="summary"):
    require(type(left) is type(right), f"summary type differs at {path}")
    if type(left) is dict:
        require(set(left) == set(right), f"summary keys differ at {path}")
        for key in left:
            same_summary(left[key], right[key], f"{path}.{key}")
    elif type(left) is list:
        require(len(left) == len(right), f"summary length differs at {path}")
        for index, (a, b) in enumerate(zip(left, right)):
            same_summary(a, b, f"{path}[{index}]")
    elif type(left) is float:
        require(math.isfinite(left) and math.isfinite(right)
                and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12), f"summary number differs at {path}")
    else:
        require(left == right, f"summary value differs at {path}")


def validate_plan(protocol):
    require(protocol.get("schema") == STUDY_SCHEMA and tuple(protocol["methods"]) == METHODS,
            "study schema or method set differs")
    require((protocol["case_count"], protocol["profile_count"], protocol["domain_count"], protocol["seed_count"])
            == (192, 64, 3, 1), "controlled dimensions differ")
    require(protocol["design"]["factors"] == FACTORS, "factor grid differs")
    cases, observed, ids, families = {}, set(), set(), {}
    expected_schedule = []
    for index, case in enumerate(protocol["cases"]):
        profile = case["_availability_profile"]
        require(set(profile) == {"profile_id", *FACTORS}, "profile keys differ")
        values = tuple(profile[key] for key in FACTORS)
        require(all(type(profile[key]) is int and profile[key] in levels for key, levels in FACTORS.items()),
                "undeclared factor value")
        require(case["domain"] in DOMAINS and case["case_id"] not in ids, "case identity differs")
        ids.add(case["case_id"])
        identity = (case["domain"], *values)
        require(identity not in observed, "duplicate factor/domain cell")
        observed.add(identity)
        require(case["family_id"] == profile["profile_id"] and
                (profile["profile_id"] not in families or families[profile["profile_id"]] == values),
                "profile aliases different conditions")
        families[profile["profile_id"]] = values
        cases[case["case_id"]] = case
        offset = index % len(METHODS)
        for method in METHODS[offset:] + METHODS[:offset]:
            expected_schedule.append({"trial_id": f"trial_{len(expected_schedule):06d}",
                "case_id": case["case_id"], "family_id": case["family_id"], "domain": case["domain"],
                "seed": 0, "method": method, **profile})
    require(observed == set(itertools.product(DOMAINS, *FACTORS.values())) and len(cases) == 192
            and len(families) == 64, "factor/domain coverage is incomplete")
    require(protocol["schedule"] == expected_schedule, "full schedule or rotation differs")
    return cases


def load_bundle(study_dir, audit_dir, git_root, expected_protocol):
    study, audit_root, git_root = (Path(path).resolve() for path in (study_dir, audit_dir, git_root))
    manifest = verify_inventory(study, STUDY_SCHEMA, terminal=True)
    receipt = strict_json(study / "completion-receipt.json")
    require(receipt.get("complete") is True and receipt.get("schema") == STUDY_SCHEMA,
            "collection has not completed")
    require(receipt["manifest_sha256"] == sha(study / "manifest.json"), "completion manifest hash differs")
    require(receipt.get("no_retries_or_replacements") is True and receipt.get("source_and_runtime_final_recheck") is True
            and receipt["new_model_calls"] == receipt["external_application_calls"] == 0,
            "collection invariant differs")
    protocol_sha = sha(study / "protocol.json")
    require(protocol_sha == expected_protocol == receipt["protocol_sha256"], "protocol binding differs")
    protocol = strict_json(study / "protocol.json")
    cases = validate_plan(protocol)
    require({f"trials/{slot['trial_id']}.json.gz" for slot in protocol["schedule"]}
            == {name for name in manifest["files"] if name.startswith("trials/")}, "raw slot coverage differs")
    case_data = (study / "cases.json").read_bytes()
    bound_bytes(case_data, {key: protocol["cases_json"][key] for key in ("sha256", "bytes")}, "cases.json")
    require(strict_json(study / "cases.json") == {"schema": STUDY_SCHEMA, "cases": protocol["cases"]},
            "bound case payload differs")
    audit_manifest = verify_inventory(audit_root, AUDIT_SCHEMA)
    audit = strict_json(audit_root / "audit-receipt.json")
    require(audit.get("schema") == AUDIT_SCHEMA and audit.get("passed") is True,
            "completed passed audit is required")
    require(audit["protocol_sha256"] == protocol_sha and audit["manifest_sha256"] == receipt["manifest_sha256"],
            "audit refers to another collection")
    for source, target in (("protocol.json", "protocol.source.json"), ("manifest.json", "study-manifest.source.json"),
                           ("completion-receipt.json", "completion-receipt.source.json"),
                           ("cases.json", "cases.source.json"), ("started.json", "started.source.json")):
        require((study / source).read_bytes() == (audit_root / target).read_bytes(), f"audit source copy differs: {source}")
    require(sha(audit_root / "audit-code.source.py") == audit["audit_script_sha256"]
            == protocol["source"]["files"][SWEEP_AUDITOR]["sha256"], "executed auditor bytes differ")
    require(protocol["engine"]["commit"] == ENGINE_COMMIT and
            protocol["engine"]["files"][SEMANTIC_AUDITOR]["sha256"]
            == audit["semantic_auditor_sha256"] == SEMANTIC_AUDITOR_SHA256, "semantic auditor binding differs")
    for declaration in (protocol["source"], protocol["engine"]):
        for name, expected in declaration["files"].items():
            bound_bytes(git_blob(git_root, declaration["commit"], name), expected, name)
    started = strict_json(study / "started.json")
    require(audit["source_commit"] == protocol["source"]["commit"] == started["source_commit"]
            and audit["engine_commit"] == ENGINE_COMMIT == started["original_engine_commit"]
            and audit["protocol_commit"] == started["protocol_commit"], "source receipt commits differ")
    require(git_blob(git_root, started["protocol_commit"], protocol["protocol_git_path"])
            == (study / "protocol.json").read_bytes(), "committed protocol bytes differ")
    require(git_blob(git_root, started["protocol_commit"], protocol["cases_json"]["git_path"])
            == case_data, "committed case bytes differ")
    summary, computed = strict_json(study / "summary.json"), strict_json(audit_root / "recomputed-summary.json")
    same_summary({key: value for key, value in summary.items() if key not in
                  {"protocol_sha256", "collection_seconds", "controlled_profile_count", "domain_count"}}, computed)
    for key in ("planned_trials", "completed_trials", "failed_trials"):
        require(computed[key] == receipt[key] == audit[key], f"receipt denominator differs: {key}")
    require(computed["planned_trials"] == 960 and computed["completed_trials"] + computed["failed_trials"] == 960,
            "planned denominator differs")
    require(summary["protocol_sha256"] == protocol_sha and summary["controlled_profile_count"] == 64
            and summary["domain_count"] == 3, "summary metadata differs")
    analysis = strict_json(audit_root / "coverage-analysis.json")
    return {"study": study, "audit_root": audit_root, "manifest": manifest, "audit_manifest": audit_manifest,
            "protocol": protocol, "cases": cases, "receipt": receipt, "audit": audit,
            "computed": computed, "analysis": analysis, "protocol_sha256": protocol_sha}


def count(value, label):
    require(type(value) is int and value >= 0, f"invalid count: {label}")
    return value


def metric(row, name):
    value = row["metrics"][name]
    total, observed, unavailable = (count(value[key], name + " " + key) for key in ("sum", "observed", "unavailable"))
    require(observed + unavailable == 1, "case metric denominator differs")
    mean = total / observed if observed else None
    require((mean is None and value["mean"] is None) or (type(value["mean"]) in (int, float)
            and math.isfinite(value["mean"]) and math.isclose(value["mean"], mean, abs_tol=1e-12)),
            "case metric mean differs")
    require(observed > 0 or total == 0, "unobserved metric has a nonzero sum")
    return total, observed, unavailable


def fraction(numerator, denominator):
    return None if not denominator else str(Fraction(numerator, denominator))


def data_tables(bundle):
    protocol, computed, cases, analysis = (bundle[key] for key in ("protocol", "computed", "cases", "analysis"))
    endpoints = protocol["design"]["endpoints"]
    expected_keys = {(slot["case_id"], slot["method"]) for slot in protocol["schedule"]}
    coverage = {}
    for row in analysis["coverage_rows"]:
        key = (row["case_id"], row["method"])
        require(key not in coverage, "duplicate audited coverage row")
        coverage[key] = row
    require(set(coverage) == expected_keys, "audited coverage row denominator differs")
    summaries = {}
    for row in computed["cases"]:
        key = (row["case_id"], row["method"])
        require(key not in summaries, "duplicate audited case summary")
        summaries[key] = row
    require(set(summaries) == expected_keys, "audited case summary denominator differs")
    case_rows, grouped = [], defaultdict(list)
    for slot in protocol["schedule"]:
        key = (slot["case_id"], slot["method"])
        case, row, observed = cases[key[0]], summaries[key], coverage[key]
        require((row["planned"], row["completed"], row["failed"]) in ((1, 1, 0), (1, 0, 1)),
                "case completion counts differ")
        require(type(observed["completed"]) is bool and observed["completed"] == bool(row["completed"]),
                "coverage disposition differs")
        require(observed["trial_id"] == slot["trial_id"], "coverage trial identity differs")
        require(set(row["metrics"]) == set(endpoints), "case endpoint set differs")
        values = {name: metric(row, name) for name in endpoints}
        definite, wrong = values["state_definite"], values["state_wrong_definite"]
        require(definite[1:] == wrong[1:] and 0 <= wrong[0] <= definite[0] <= definite[1],
                "correct-definite decomposition differs")
        correct = definite[0] - wrong[0]
        item = {**slot, "completed": row["completed"], "failed": row["failed"],
                "correct_definite_state": correct, "state_unavailable": definite[2],
                "reported_state": observed.get("reported_state"),
                "evidence_ready": observed.get("evidence_ready")}
        for name, (total, n, unavailable) in values.items():
            item.update({name + "_sum": total, name + "_observed": n, name + "_unavailable": unavailable})
        if observed["completed"]:
            require(all(observed[name] == case["_availability_profile"][name]
                        for name in case["_availability_profile"]), "coverage profile differs")
            require(values["reads"][0] == observed["reads"] and values["dispatches"][0] == observed["dispatches"],
                    "coverage resources differ")
            claim = observed["reported_state"]
            require(type(claim) is bool or claim is None, "invalid reported state")
            require(definite[0] == int(claim is not None), "coverage definite claim differs")
            truth = bool(values["original_completion"][0])
            require(wrong[0] == int(claim is not None and claim != truth), "coverage correct claim differs")
        case_rows.append(item)
        grouped[(slot["profile_id"], slot["method"])].append(item)
    profiles = []
    for (profile_id, method), rows in sorted(grouped.items()):
        require(len(rows) == 3 and {row["domain"] for row in rows} == set(DOMAINS), "profile/domain denominator differs")
        record = {"profile_id": profile_id, "method": method,
                  **{name: rows[0][name] for name in FACTORS}, "planned": 3,
                  "completed": sum(row["completed"] for row in rows), "failed": sum(row["failed"] for row in rows),
                  "correct_definite_state": sum(row["correct_definite_state"] for row in rows),
                  "state_unavailable": sum(row["state_unavailable"] for row in rows)}
        record["correct_definite_state_yield_fraction"] = fraction(record["correct_definite_state"], 3)
        for name in endpoints:
            for suffix in ("sum", "observed", "unavailable"):
                record[name + "_" + suffix] = sum(row[name + "_" + suffix] for row in rows)
            record[name + "_mean_fraction"] = fraction(record[name + "_sum"], record[name + "_observed"])
        profiles.append(record)
    require(len(profiles) == 320, "profile/method table is incomplete")
    return {"cases": case_rows, "profiles": profiles, "methods": computed["methods"],
            "paired_contrasts": computed["paired_contrasts"],
            "audited_method_comparisons": analysis["paired_comparisons"],
            "hypotheses_are_not_forced": True}


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, rows):
    fields = list(rows[0])
    require(all(set(row) == set(fields) for row in rows), "CSV row keys differ")
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def mean_reads(row):
    n = row["reads_observed"]
    return None if not n else Fraction(row["reads_sum"], n)


def short_fraction(value):
    if value is None:
        return "NA"
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.2f}"


def plot_grid(tables, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.titlesize": 11,
                         "axes.labelsize": 10.5, "xtick.labelsize": 10.5, "ytick.labelsize": 10.5,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"})
    by_cell = {(row["lag_ms"], row["unavailable_until_ms"], row["incomplete_until_ms"], row["method"]): row
               for row in tables["profiles"]}
    figure, axes = plt.subplots(2, 2, figsize=SPEC["figure_inches"])
    figure.subplots_adjust(left=0.10, right=0.96, bottom=0.33, top=0.865, wspace=0.24, hspace=0.48)
    for axis, incomplete in zip(axes.flat, FACTORS["incomplete_until_ms"]):
        image_values = np.zeros((4, 4))
        for yi, lag in enumerate(FACTORS["lag_ms"]):
            for xi, unavailable in enumerate(FACTORS["unavailable_until_ms"]):
                poll, single = (by_cell[(lag, unavailable, incomplete, method)] for method in (POLL, SINGLE))
                image_values[yi, xi] = poll["correct_definite_state"] - single["correct_definite_state"]
        image = axis.imshow(image_values, cmap="RdBu", vmin=-3, vmax=3, aspect="auto")
        for yi, lag in enumerate(FACTORS["lag_ms"]):
            for xi, unavailable in enumerate(FACTORS["unavailable_until_ms"]):
                poll, single = (by_cell[(lag, unavailable, incomplete, method)] for method in (POLL, SINGLE))
                color = "white" if abs(image_values[yi, xi]) >= 2 else "#202020"
                labels = [f"{poll['correct_definite_state']} | {single['correct_definite_state']}",
                          f"{short_fraction(mean_reads(poll))} | {short_fraction(mean_reads(single))}"]
                if poll["state_unavailable"] or single["state_unavailable"]:
                    labels.append(f"u{poll['state_unavailable']} | {single['state_unavailable']}")
                axis.text(xi, yi, "\n".join(labels), ha="center", va="center", color=color,
                          fontsize=10.5 if len(labels) == 3 else SPEC["annotation_font_points"],
                          linespacing=1.0 if len(labels) == 3 else 1.35)
        axis.set_title(f"Incomplete until {incomplete} ms", pad=8)
        axis.set_xticks(range(4), FACTORS["unavailable_until_ms"])
        axis.set_yticks(range(4), FACTORS["lag_ms"])
        axis.set_xlabel("Unavailable until (ms)", labelpad=4)
        axis.set_ylabel("Readback lag (ms)", labelpad=4)
        axis.set_xticks(np.arange(-0.5, 4, 1), minor=True)
        axis.set_yticks(np.arange(-0.5, 4, 1), minor=True)
        axis.grid(which="minor", color="white", linewidth=1)
        axis.tick_params(which="minor", bottom=False, left=False)
        for spine in axis.spines.values():
            spine.set_visible(False)
    figure.suptitle("Evidence availability: coverage and read cost", fontsize=13.5, x=0.53, y=0.97)
    figure.text(0.53, 0.925, "All 64 controlled profiles, each repeated in three application domains", ha="center", fontsize=10.5)
    color_axis = figure.add_axes([0.24, 0.155, 0.59, 0.018])
    colorbar = figure.colorbar(image, cax=color_axis, orientation="horizontal", ticks=[-3, 0, 3])
    colorbar.set_label("Polling minus one-final-read correct reports (counts out of 3)", fontsize=10.5, labelpad=5)
    figure.text(0.05, 0.225, "Each cell: correct definite reports (top), mean charged reads (bottom).", fontsize=10.5)
    figure.text(0.05, 0.197, "Both rows: polling | one-final-read; counts use three planned domains.", fontsize=10.5)
    figure.text(0.05, 0.067, "Domains repeat one mechanism; they are not independent task samples.", fontsize=10.5)
    figure.text(0.05, 0.041, "Reads use observed slots; u marks unavailable outcomes.", fontsize=10.5)
    figure.text(0.05, 0.015, "All five policies and exact endpoint counts remain in the tables.", fontsize=10.5)
    for extension in ("pdf", "svg", "png"):
        figure.savefig(output / f"recovery-availability-grid.{extension}", dpi=SPEC["png_dpi"],
                       metadata={"Creator": "ConseqaX controlled availability exporter"} if extension == "pdf" else None)
    plt.close(figure)


def export(args):
    output = args.output.resolve()
    require(not output.exists(), "export directory must be new")
    bundle = load_bundle(args.study_dir, args.audit_dir, args.git_root, args.expected_protocol_sha256)
    require(not output.is_relative_to(bundle["study"]) and not output.is_relative_to(bundle["audit_root"]),
            "export directory must be separate from measured/audit artifacts")
    tables = data_tables(bundle)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plot-specification.json", SPEC)
    write_json(output / "availability-results.json", {"schema": SCHEMA, "protocol_sha256": bundle["protocol_sha256"], **tables})
    write_csv(output / "case-method-results.csv", tables["cases"])
    write_csv(output / "profile-method-results.csv", tables["profiles"])
    sources = output / "source-inputs"
    sources.mkdir()
    for root, name, target in ((bundle["study"], "protocol.json", "protocol.source.json"),
        (bundle["study"], "cases.json", "cases.source.json"),
        (bundle["study"], "summary.json", "collection-summary.source.json"),
        (bundle["study"], "manifest.json", "study-manifest.source.json"),
        (bundle["study"], "completion-receipt.json", "completion-receipt.source.json"),
        (bundle["study"], "started.json", "started.source.json"),
        (bundle["audit_root"], "manifest.json", "audit-manifest.source.json"),
        (bundle["audit_root"], "audit-receipt.json", "audit-receipt.source.json"),
        (bundle["audit_root"], "recomputed-summary.json", "recomputed-summary.source.json"),
        (bundle["audit_root"], "coverage-analysis.json", "coverage-analysis.source.json"),
        (bundle["audit_root"], "audit-code.source.py", "audit-code.source.py")):
        shutil.copyfile(root / name, sources / target)
    shutil.copyfile(Path(__file__), sources / "plotting-code.source.py")
    plot_grid(tables, output)
    (output / "README.md").write_text(
        "# Controlled availability publication export\n\n"
        "Every retained study/audit artifact hash and exact inventory passed before these exports. "
        "The passed audit, copied auditor bytes, original semantic auditor and immutable source/protocol/case Git blobs were checked. "
        "Values derive from audited per-case summaries and coverage rows; analytical predictions do not set displayed outcomes.\n\n"
        "The figure shows all 64 controlled profiles and both correct-definite state-report counts (/3 planned domains) and charged mean reads. "
        "Unavailable outcomes remain explicit; read means use observed slots. Complete exact data for all five methods, all cases/profiles, "
        "all original endpoints and paired contrasts are in JSON/CSV. No confidence intervals or task-population claims are made. "
        "The three domains repeat the same controlled mechanism. This post hoc motivated follow-up supplements the original negative finding, "
        "and cannot establish better recovery actions or framework superiority over the matched strong reference.\n\n"
        "Manifest completion attests export completion, not visual review.\n", encoding="utf-8")
    inventory = {path.relative_to(output).as_posix(): sha(path) for path in sorted(output.rglob("*")) if path.is_file()}
    write_json(output / "manifest.json", {"schema": SCHEMA, "complete": True,
        "protocol_sha256": bundle["protocol_sha256"], "study_manifest_sha256": sha(bundle["study"] / "manifest.json"),
        "audit_manifest_sha256": sha(bundle["audit_root"] / "manifest.json"),
        "audit_receipt_sha256": sha(bundle["audit_root"] / "audit-receipt.json"), "files": inventory})
    print(json.dumps({"complete": True, "profiles": 64, "case_method_rows": len(tables["cases"]),
                      "manifest_sha256": sha(output / "manifest.json")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--git-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-protocol-sha256", default=EXPECTED_PROTOCOL_SHA256)
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args())


if __name__ == "__main__":
    main()
