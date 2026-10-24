"""Present already frozen results in a new, review-pending manuscript bundle.

Validates both cohorts and the immutable proposed manuscript, then applies the
finite editorial checklist. No inference, new analysis, PDF, Git mutation or
working-paper edit occurs. Git is read only for existing provenance checks.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
EDITOR = "scripts/finalize_limbo_editorial_sources.py"
BUILDER = "scripts/build_final_limbo_paper.py"
PREPARER = "scripts/prepare_final_limbo_manuscript.py"
ANALYZER = "scripts/analyze_limbo_external_benchmark.py"
LEDGER = "paper/limbo-evidence-ledger-addendum-2026-10-24.md"
DISPOSITION = "paper/limbo-review-disposition-2026-10-24.md"
ARMS = ("vanilla", "sdk_retry3", "guard", "conseqax_guard")
LABELS = ("Vanilla", "SDK retry", "Native guard", "ConseqaX guard")


def module(root, name, label):
    path = root / name
    spec = importlib.util.spec_from_file_location(label, path)
    value = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), value.__dict__)
    return value


def once(text, old, new):
    if not old or text.count(old) != 1:
        raise ValueError("Expected exactly one reviewed editorial anchor: " + old[:90])
    return text.replace(old, new, 1)


def abstract(result, earlier):
    values = result["arms"]
    graded = sum(values[arm]["audited_grade_available"] for arm in ARMS)
    errors = sum(values[arm]["audited_native_error_returns"] for arm in ARMS)
    previous = sum(earlier["result"]["arms"][arm]["audited_grade_available"] for arm in ARMS)
    endpoints = "; ".join(f"{label}: TS {values[arm]['endpoints']['TS']['true_audited']}/24, "
        f"EOS {values[arm]['endpoints']['EOS']['true_audited']}/24" for arm, label in zip(ARMS, LABELS))
    package = values["conseqax_guard"]
    receipts = package["costs"]["receipt_count"]["observed_total"]
    activation = ("No measured receipt activated; receipt-path qualification remains a separate scripted fixture. "
                  if receipts == 0 else "Receipt activation demonstrates integration rather than a new recovery algorithm. ")
    return ("A timed-out tool call can leave an agent uncertain whether an operation failed or will commit later. "
        "ConseqaX separates state, action-origin and unknown conclusions through explicit contracts and readback witnesses. "
        "Study A retains 15,360 SQLite worlds from 24 authored cases: readback safely recovers 14/24 versus "
        "8/24 for response-driven retry, matching a strong reference. Repeated seeds add no recorded-metric diversity; "
        "polling adds no coverage and detection does not repair all harmful effects. Study B retains 960 worlds: "
        "polling raises correct-state yield from 3/192 to 81/192 at 741 versus 192 reads, with identical physical outcomes. "
        "The externally authored LIMBO study covers 12 base instances, 24 task/fault conditions and four arms. "
        f"The interrupted original retains {previous}/96 audited grades. A separately declared follow-up, after partial-data "
        f"exposure, retains another 96 planned slots on the same instances; cohorts are not pooled. Replay establishes "
        f"{graded}/96 follow-up grades, including {errors} native error returns after settlement. All-planned results are "
        f"{endpoints}. The package emits {receipts} audited receipts in "
        f"{package['receipt_episodes_with_at_least_one']}/24 episodes, with complete accounting in "
        f"{package['audited_grade_available']}/24. " + activation +
        "Missing grades remain unavailable. Native EOS has domain-specific accounting, not a universal exactly-once "
        "guarantee. Study A's packaging deviation remains disclosed. These finite simulator results establish neither "
        "task-population superiority nor independent service validation.")


def baseline_contrasts(result):
    parts = []
    for baseline, label in (("vanilla", "Vanilla"), ("sdk_retry3", "SDK retry")):
        pair = result["matched_contrasts"][baseline + "__vs__guard"]
        if pair["left"] != baseline or pair["right"] != "guard" or pair["planned_worlds"] != 24:
            raise ValueError("Unexpected frozen matched-contrast orientation")
        endpoints = pair["endpoints"]
        values = []
        for metric in ("TS", "EOS"):
            cell = endpoints[metric]
            difference = -cell["all_planned_numerator_difference_left_minus_right"]
            if difference != cell["right_all_planned_true"] - cell["left_all_planned_true"]:
                raise ValueError("Frozen matched-contrast numerator differs")
            if cell["both_grades_available"] + cell["at_least_one_grade_unavailable"] != 24:
                raise ValueError("Frozen matched-contrast availability differs")
            values.append(f"{metric} numerator difference {difference:+d}/24, "
                f"both grades available {cell['both_grades_available']}/24 and "
                f"at least one grade unavailable {cell['at_least_one_grade_unavailable']}/24")
        parts.append("Native guard minus " + label + ": " + "; ".join(values))
    return ("Follow-up matched baseline contrasts over all 24 planned native worlds were "
        + ". ".join(parts) + ". These finite paired counts retain every unavailable pair; they are "
        "not population significance, equivalence or an independent recovery-algorithm claim.")


def readiness_text(result):
    package = result["arms"]["conseqax_guard"]
    receipts = package["costs"]["receipt_count"]["observed_total"]
    activation = ("No autonomous follow-up receipt activated; the scripted fixture is the receipt-path evidence."
        if receipts == 0 else f"Measured follow-up activation comprised {receipts} audited receipts in "
        f"{package['receipt_episodes_with_at_least_one']}/24 planned SDK episodes; "
        f"{package['audited_grade_available']}/24 had complete audited accounting.")
    return ("Qualification evidence is separated from measurement. Preserved excluded autonomous native executions "
        "validated normal baseline/guard returns under the historical runtime; a separately scripted repeated-proposal "
        "fixture exercised the actual SDK receipt path without model generations or a native task grade. Relocated "
        "readiness retained those historical executions and added current-runtime full-schema render/token parity "
        "and a two-call task-independent structured-tool roundtrip. Historical executions are not relabeled as "
        "current-runtime trajectories, and fixture receipts do not enter measured counts. " + activation +
        " The auditor checks saved receipt mappings and native behavior; it does not independently re-execute the "
        "SDK or authenticate a production service.")


def edit_texts(p, result, earlier, analysis, tex, readable, methods, native):
    old_abstract, new_abstract = p.abstract(result, earlier), abstract(result, earlier)
    tex = once(tex, p.escape(old_abstract), p.escape(new_abstract))
    readable = once(readable, old_abstract, new_abstract)
    old_pin = "All three experiments retain the 2.1.1 package pin"
    new_pin = "Studies A/B and both native runtime conditions retain the 2.1.1 package pin"
    tex, readable = once(tex, old_pin, new_pin), once(readable, old_pin, new_pin)
    if result["arms"]["conseqax_guard"]["costs"]["receipt_count"]["observed_total"] == 0:
        no_activation = "No autonomous follow-up receipt activated; the separate scripted fixture remains receipt-path evidence."
        tex = once(tex, r"\section{Conclusion and Artifact Availability}",
            r"\section{Conclusion and Artifact Availability}" + "\n\n" + p.escape(no_activation))
        readable = once(readable, "## 10. Conclusion and Artifact Availability",
            "## 10. Conclusion and Artifact Availability\n\n" + no_activation)
    keys = re.findall(r"\\bibitem\{([^{}]+)\}", tex)
    old_methods = p.methods_markdown(methods, keys)
    methods = once(methods, r"\subsection{Actual SDK path and public-information boundary}",
        r"\subsection{Actual SDK path and public-information boundary}" + "\n\n" + p.escape(readiness_text(result)))
    readable = once(readable, old_methods, p.methods_markdown(methods, keys))
    paragraphs = (analysis / "narrative.md").read_text(encoding="utf-8").strip().split("\n\n")
    if len(paragraphs) != 7 or not paragraphs[4].startswith("Assigned-condition results were "):
        raise ValueError("Frozen assigned-condition narrative shape differs")
    additions = (paragraphs[4], baseline_contrasts(result),
        "The original six graded prefix slots, one interrupted slot and 89 unstarted slots do not support "
        "an efficacy comparison of that condition. Its 90 unavailable grades are not native failures.")
    native = once(native, p.escape(paragraphs[0]),
        p.escape(paragraphs[0]) + "\n\n" + "\n\n".join(p.escape(value) for value in additions))
    readable = once(readable, paragraphs[0], paragraphs[0] + "\n\n" + "\n\n".join(additions))
    readable = once(readable, "| Arm | Planned | Graded | TS true | EOS true | Missing |",
        "**Follow-up runtime condition.**\n\n| Arm | Planned | Graded | TS true | EOS true | Missing |")
    readable = once(readable, p.harm_table(result, False),
        "**Follow-up runtime condition.**\n\n" + p.harm_table(result, False))
    # Every native numeric table/plot caption belongs to the follow-up; the
    # separate two-cohort accounting table is intentionally unchanged.
    native, count = re.subn(r"\\caption\{", lambda _m: r"\caption{Follow-up runtime condition. ", native)
    if count != 5:
        raise ValueError("Expected outcome/effect tables and exactly three native result plots")
    readable = re.sub(r"!\[([^\]]+)\]\(figures/(limbo-(?:outcomes|stratification|costs))\.svg\)",
        lambda match: "![Follow-up runtime condition. " + match[1] + "](figures/" + match[2] + ".svg)", readable)
    for text in (tex, readable, methods, native):
        p.reject_stale(text)
    return tex, readable, methods, native


def prepare(args):
    root, stage, output = args.root.resolve(), args.stage.resolve(), args.output.resolve()
    b, p = module(root, BUILDER, "editorial_builder"), module(root, PREPARER, "editorial_preparer")
    require = b.require
    require(root / "output" in output.parents and not output.exists(), "Need a NEW research output directory")
    for source in (stage, args.analysis.resolve(), args.interrupted_analysis.resolve()):
        require(not output.is_relative_to(source) and not source.is_relative_to(output), "Editorial output overlaps evidence")
    seal = b.check_manifest(stage)
    receipt = b.load(stage / "preparation-receipt.json")
    require(receipt.get("schema") == "conseqax-final-paper-preparation-v1"
            and receipt.get("status") == "REVIEW_PENDING" and receipt.get("visual_review_pending") is True,
            "Need the exact sealed review-pending manuscript stage")
    checked, earlier = b.validate_cohorts(root, args.analysis.resolve(), args.protocol.resolve(), args.protocol_commit,
        args.interrupted_analysis.resolve(), args.interrupted_protocol.resolve(),
        args.interrupted_protocol_commit, args.protocol_commit)
    require(receipt["protocol_commit"] == args.protocol_commit and receipt["protocol"] == b.binding(args.protocol)
            and receipt["analysis_manifest"] == checked["sealed"]["manifest"]
            and receipt["interrupted_cohort"]["protocol_commit"] == args.interrupted_protocol_commit
            and receipt["interrupted_cohort"]["analysis_manifest"] == earlier["sealed"]["manifest"]
            and receipt.get("both_cohorts_retained_separately") is True and receipt.get("cohorts_pooled") is False,
            "Manuscript stage changed cohort provenance")
    for name, expected in receipt["proposed_manuscript_files"].items():
        b.safe_member(name)
        require(b.binding(stage / name) == expected, "Original proposed manuscript changed")
    for name, expected in receipt["source_inputs"].items():
        b.safe_member(name)
        require(name.startswith("paper/"), "Original manuscript source leaves paper directory")
        require(b.binding(root / name) == expected, "Original working-paper base changed")
    sources = {name: b.binding(root / name) for name in (EDITOR, BUILDER, PREPARER, ANALYZER)}
    require(receipt["preparer"] == sources[PREPARER] and receipt["validation_helper"] == sources[BUILDER],
            "Original staging implementation differs from held source")
    result = checked["result"]
    files = ("conseqax-research.tex", "conseqax-research.md", "limbo-native-methods.tex", "limbo-native-results.tex")
    original_texts = [(stage / "paper" / name).read_text(encoding="utf-8") for name in files]
    expected_methods = p.final_methods((root / "paper/limbo-native-methods.tex").read_text(encoding="utf-8"),
        checked["protocol"], args.protocol_commit, b.binding(args.protocol), earlier)
    expected_tex, expected_md = p.assemble((root / "paper/conseqax-research.tex").read_text(encoding="utf-8"),
        (root / "paper/conseqax-research.md").read_text(encoding="utf-8"), expected_methods,
        result, args.analysis.resolve(), earlier)
    require(original_texts == [expected_tex, expected_md, expected_methods,
        p.native_results(result, args.analysis.resolve(), True, earlier)],
        "Original proposed text differs from deterministic preparation over audited data")
    require((stage / "paper/limbo-cohort-accounting.tex").read_text(encoding="utf-8")
            == b.cohort_accounting_tex(checked, earlier), "Original cohort accounting table differs")
    require(b.binding(stage / "paper/limbo-results-table.tex") == b.binding(args.analysis / "results.tex"),
            "Original native numeric table differs")
    for stem in p.NEW_FIGURES:
        for extension in ("pdf", "svg", "png"):
            require(b.binding(stage / "paper/figures" / f"{stem}.{extension}")
                    == b.binding(args.analysis / f"{stem}.{extension}"), "Original native plot differs")
    edited = edit_texts(p, result, earlier, args.analysis.resolve(), *original_texts)
    # All numeric inputs have already been recomputed by the existing checker.
    # Only generated prose/captions change; exact plot/table bytes are retained.
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(stage, output / "inputs/original-staging")
    shutil.copytree(stage / "paper", output / "paper")
    for name, text in zip(files, edited):
        (output / "paper" / name).write_text(text, encoding="utf-8", newline="\n")
    def link(path):
        return "../" + path.resolve().relative_to(root).as_posix()
    available = sum(result["arms"][arm]["audited_grade_available"] for arm in ARMS)
    record = ("## Native evidence closure - " + b.utc() + "\n\n"
        "Status: local audited draft; source review, every-page visual QA and publication remain pending. "
        "Both 96-slot denominators retain the same 12 base instances and are not pooled. The original "
        "has 6 audited grades and 90 unavailable grades; its later preservation archive is not an original "
        "collector seal. The follow-up has " + str(available) + "/96 audited grades.\n\n"
        + "[Original protocol](" + link(args.interrupted_protocol) + "), [original interrupted analysis]("
        + link(args.interrupted_analysis / "results.json") + "), [follow-up protocol](" + link(args.protocol)
        + "), [follow-up audit](" + link(Path(result["inputs"]["audit"]["path"]))
        + "), [follow-up analysis](" + link(args.analysis / "results.json") + ").\n\n"
        "Protocol commit: `" + args.protocol_commit + "`; original: `" + args.interrupted_protocol_commit + "`. "
        "Studies A/B and both native conditions retain SDK 2.1.1 and the declared exact runtime/wheel/source "
        "bindings. Native EOS is domain-qualified; costs and receipt mappings do not establish causal origin, "
        "isolated SDK overhead, independent replication, human validation or production-service safety.\n\n"
        + baseline_contrasts(result) + "\n\n" + readiness_text(result) + "\n")
    (output / LEDGER).write_text("# Native evidence ledger addendum\n\n" + record, encoding="utf-8", newline="\n")
    (output / DISPOSITION).write_text("# Native review disposition\n\n" + record + "\n"
        "T1/T7: all frozen baseline/stratum contrasts are presented without population inference. "
        "T2: externally authored native simulation supplements the controlled SQLite studies; production "
        "validation remains absent. T14/T16: all planned dispositions, error returns, unavailable grades "
        "and unknown usage are retained. T20: exact protocol/runtime/version identities are bound. "
        "These are scoped dispositions, not universal resolution of the criticisms or an acceptance claim.\n",
        encoding="utf-8", newline="\n")
    ledger = (root / "paper/evidence-ledger.md").read_text(encoding="utf-8")
    (output / "paper/evidence-ledger.md").write_text(ledger.rstrip() + "\n\n" + record,
        encoding="utf-8", newline="\n")
    names, _edges = b.discover_sources(output)
    b.validate_paper_assets(output, names, args.analysis.resolve())
    proposed = {path.relative_to(output).as_posix(): b.binding(path)
        for path in sorted((output / "paper").rglob("*")) if path.is_file()}
    base = {name: b.binding(root / name) if (root / name).is_file() else None for name in proposed}
    require(b.check_manifest(stage) == seal and b.check_manifest(output / "inputs/original-staging") == seal,
            "Original staging bundle changed during editorial copying")
    require(all(b.binding(root / name) == identity for name, identity in sources.items()), "Editorial source changed")
    require(b.check_manifest(args.analysis.resolve()) == checked["sealed"]
            and b.check_manifest(args.interrupted_analysis.resolve()) == earlier["sealed"], "Cohort evidence changed")
    b.write_json(output / "editorial-receipt.json", {"schema": "conseqax-limbo-final-editorial-v1",
        "status": "EDITORIAL_REVIEW_PENDING", "utc": b.utc(), "protocol_commit": args.protocol_commit,
        "protocol": b.binding(args.protocol), "analysis_manifest": checked["sealed"]["manifest"],
        "original_stage_manifest": seal["manifest"], "interrupted_cohort": {
            "protocol_commit": args.interrupted_protocol_commit, "protocol": b.binding(args.interrupted_protocol),
            "analysis_manifest": earlier["sealed"]["manifest"]}, "cohorts_pooled": False,
        "proposed_paper_files": proposed, "base_paper_bindings": base, "source_bindings": sources,
        "visual_review_pending": True, "proposed_sources_require_review": True, "new_pdf_created": False,
        "new_model_calls": 0, "new_native_evaluations": 0, "git_mutations": 0,
        "scope": "Presentation only of already frozen statistics after partial follow-up exposure; no new endpoint/filter/selection/analysis; review and publication remain pending"})
    b.write_json(output / "manifest.json", {path.relative_to(output).as_posix(): b.binding(path)
        for path in sorted(output.rglob("*")) if path.is_file()})
    b.check_manifest(output)
    return {"status": "EDITORIAL_REVIEW_PENDING", "output": str(output)}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    for name in ("stage", "analysis", "protocol", "interrupted-analysis", "interrupted-protocol", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--interrupted-protocol-commit", required=True)
    print(json.dumps(prepare(parser.parse_args())))


if __name__ == "__main__":
    main()
