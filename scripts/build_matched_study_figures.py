"""Build descriptive scientific figures from a sealed matched-study analysis.

No model, analyzer, or frozen runtime is imported or executed. A hash-bound final
collection disposition is mandatory: ongoing partial data are refused. Outputs
are created in a fresh directory and include every plotted fraction in CSV/JSON.
This is postcollection presentation tooling, not a change to frozen estimands.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import csv
import json
import math
from pathlib import Path
import sys
from textwrap import fill


METHODS = ("response_only", "agent_self_report", "readback_state_only",
           "independent_public_reference", "consequa_state_origin")
LABELS = ("Public response", "Agent assessment", "Readback only",
          "Independent ref.", "Consequa-X")
TARGETS = ("state", "action_linked")
STATUSES = ("completed", "failed", "interrupted_partial", "unstarted")
METRICS = ("coverage", "claim_error", "correct_yield", "full_planned_correct_yield")
COLORS = ("#65738A", "#B16C28", "#217A91", "#8062A6", "#176B54")


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def reject_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def check_rate(rate, numerator, denominator, where):
    require(integer(numerator) and integer(denominator) and numerator <= denominator,
            f"Invalid fraction at {where}")
    require(integer(rate["numerator"]) and integer(rate["denominator"]) and
            rate["numerator"] == numerator and rate["denominator"] == denominator,
            f"Fraction counts differ from episode rows at {where}")
    expected = numerator / denominator if denominator else None
    value = rate["value"]
    require((value is None and expected is None) or
            (type(value) in (int, float) and expected is not None and
             math.isfinite(value) and math.isclose(value, expected, abs_tol=1e-12)),
            f"Fraction value differs from counts at {where}")


def key_for(slot):
    return json.dumps({axis: slot[axis] for axis in ("model", "prompt_version")}, sort_keys=True)


def validate_summary(summary, rows, planned, where):
    require(set(summary) == set(METHODS), f"Auditor set differs at {where}")
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        for target in TARGETS:
            eligible = [row for row in selected if row["gold"][target] is not None]
            claims = [row for row in eligible if row["prediction"][target] is not None]
            correct = sum(row["prediction"][target] == row["gold"][target] for row in claims)
            value = summary[method][target]
            expected = {"completed": len(selected), "gold_assessable": len(eligible),
                        "claims": len(claims), "correct_claims": correct,
                        "wrong_claims": len(claims) - correct,
                        "abstentions": len(eligible) - len(claims), "planned_episodes": planned}
            require(all(value[name] == count for name, count in expected.items()),
                    f"Summary counts differ from episode rows at {where}/{method}/{target}")
            fractions = {"coverage": (len(claims), len(eligible)),
                         "claim_error": (len(claims) - correct, len(claims)),
                         "correct_yield": (correct, len(eligible)),
                         "full_planned_correct_yield": (correct, planned)}
            for metric, (numerator, denominator) in fractions.items():
                check_rate(value[metric], numerator, denominator,
                           f"{where}/{method}/{target}/{metric}")


def validate_inputs(analysis_path, protocol_path, disposition_path, diagnostics_path=None):
    """Verify finality, hashes, every frozen slot, and all plotted denominators."""
    paths = {"analysis": Path(analysis_path).resolve(), "protocol": Path(protocol_path).resolve(),
             "disposition": Path(disposition_path).resolve()}
    if diagnostics_path:
        paths["execution_diagnostics"] = Path(diagnostics_path).resolve()
    inputs = {name: read_json(path) for name, path in paths.items()}
    hashes = {name: file_hash(path) for name, path in paths.items()}
    analysis, protocol, disposition = (inputs[name] for name in ("analysis", "protocol", "disposition"))
    require(analysis["schema_version"] == "consequa-matched-audit-analysis-v1", "Unknown analysis schema")
    require(protocol["schema_version"] == "consequa-matched-local-study-v1", "Unknown frozen protocol schema")
    require(disposition["schema_version"] == "consequa-matched-study-disposition-v1", "Unknown disposition schema")
    require(disposition.get("final") is True and disposition.get("no_active_runner") is True,
            "Final collection disposition must declare final=true and no_active_runner=true")
    require(not (paths["protocol"].parent / "runner.lock").exists(), "Study has a runner lock; refuse active data")
    require(disposition["analysis_sha256"] == hashes["analysis"], "Analysis differs from final disposition hash")
    require(analysis["protocol_sha256"] == hashes["protocol"] == disposition["protocol_sha256"],
            "Frozen protocol hashes disagree")
    journal_path = paths["protocol"].parent / "request-journal.jsonl"
    hashes["journal"] = file_hash(journal_path)
    paths["journal"] = journal_path
    require(hashes["journal"] == analysis["journal_sha256"] == disposition["journal_sha256"],
            "Captured journal differs from final analysis/disposition")
    planned = protocol["planned_episodes"]
    require(integer(planned) and planned > 0 and planned == analysis["planned_episodes"],
            "Planned episode counts disagree")
    schedule = {slot["slot_id"]: slot for slot in protocol["schedule"]}
    require(len(schedule) == len(protocol["schedule"]) == planned, "Duplicate or missing frozen schedule slots")
    receipts = analysis["episodes"]
    require(len(receipts) == planned, "Analysis lacks full frozen-slot accounting")
    received_ids = [receipt["slot"]["slot_id"] for receipt in receipts]
    require(set(received_ids) == set(schedule) and len(set(received_ids)) == planned,
            "Analysis episode slots differ from frozen schedule")
    for receipt in receipts:
        require(receipt["slot"] == schedule[receipt["slot"]["slot_id"]], "Episode slot metadata changed")
        require(receipt["status"] in STATUSES, "Unknown episode disposition")
    counts = Counter(receipt["status"] for receipt in receipts)
    status = {name: counts[name] for name in STATUSES}
    require(analysis["episode_status"] == status, "Analysis disposition totals differ from slot receipts")
    if "episode_status" in disposition:
        require(disposition["episode_status"] == status, "Final disposition counts disagree")
    state = disposition["collection_state"]
    require(state in {"completed", "stopped"}, "Final state must be completed or explicitly stopped")
    if state == "completed":
        require(not counts["interrupted_partial"] and not counts["unstarted"],
                "Completed disposition contains unfinished slots; disclose stopped instead")
        tail = journal_path.read_text(encoding="utf-8").splitlines()
        require(bool(tail) and json.loads(tail[-1])["event"] == "run_stopped",
                "Completed collection lacks a terminal runner stop")
    else:
        require(type(disposition.get("stopped_reason")) is str and disposition["stopped_reason"].strip(),
                "Stopped collection needs an explicit reason; partial data cannot appear complete")
    rows = analysis["rows"]
    completed = {receipt["slot"]["slot_id"] for receipt in receipts if receipt["status"] == "completed"}
    observed = Counter()
    gold_by_slot = {}
    for row in rows:
        slot_id = row["slot"]["slot_id"]
        require(slot_id in completed and row["slot"] == schedule[slot_id], "Semantic row outside completed slots")
        require(row["method"] in METHODS, "Unknown auditor in semantic row")
        observed[slot_id, row["method"]] += 1
        if slot_id in gold_by_slot:
            require(row["gold"] == gold_by_slot[slot_id], "Auditors were scored against different episode gold")
        gold_by_slot[slot_id] = row["gold"]
        for target in TARGETS:
            require(row["gold"][target] is None or type(row["gold"][target]) is bool, "Invalid gold target")
            require(row["prediction"][target] is None or type(row["prediction"][target]) is bool,
                    "Invalid predicted target")
    require(observed == Counter({(slot, method): 1 for slot in completed for method in METHODS}),
            "Completed episodes need exactly one row per auditor")
    validate_summary(analysis["summary"], rows, planned, "overall")
    groups = defaultdict(list)
    for receipt in receipts:
        groups[key_for(receipt["slot"])].append(receipt)
    strata = analysis["strata"]["model/prompt_version"]
    require(set(strata) == set(groups), "Model/profile strata omit planned groups")
    for key, selected in groups.items():
        stratum = strata[key]
        group_counts = Counter(item["status"] for item in selected)
        require(stratum["planned_episodes"] == len(selected) and
                stratum["episode_status"] == {name: group_counts[name] for name in STATUSES},
                f"Stratum disposition counts disagree: {key}")
        validate_summary(stratum["summary"], [row for row in rows if key_for(row["slot"]) == key],
                         len(selected), key)
    if diagnostics_path:
        diagnostic = inputs["execution_diagnostics"]
        require(diagnostic["schema_version"] == "consequa-matched-execution-summary-v1", "Unknown diagnostic schema")
        require(diagnostic["protocol_sha256"] == hashes["protocol"] and
                diagnostic["journal_sha256"] == hashes["journal"] and
                diagnostic["analysis_sha256"] == hashes["analysis"], "Execution diagnostics bind different source data")
        inventory_path = paths["execution_diagnostics"].parent / "input-inventory.json"
        require(file_hash(inventory_path) == diagnostic["input_inventory_sha256"],
                "Execution diagnostic input inventory changed")
        paths["execution_diagnostic_inventory"] = inventory_path
        hashes["execution_diagnostic_inventory"] = file_hash(inventory_path)
        require(diagnostic["episode_status"] == status, "Execution diagnostic dispositions differ")
        require(set(diagnostic["strata"]["model/prompt_version"]) == set(groups), "Diagnostic strata differ")
        for key, selected in groups.items():
            value = diagnostic["strata"]["model/prompt_version"][key]
            group_counts = Counter(item["status"] for item in selected)
            require(value["planned_episodes"] == len(selected) and
                    value["completed_episodes"] == group_counts["completed"], "Diagnostic denominators differ")
            picked, dispatched = value["action_selected_episodes"], value["dispatched_episodes"]
            selected_from_rows = sum(row["action_selected"] is True for row in rows
                                     if key_for(row["slot"]) == key and row["method"] == METHODS[0])
            require(integer(picked) and integer(dispatched) and
                    dispatched <= picked <= group_counts["completed"] and picked == selected_from_rows,
                    "Invalid selection/dispatch counts or disagreement with retained analysis")
            for name, numerator in (("action_selected", picked), ("dispatched", dispatched)):
                for basis, denominator in (("completed", group_counts["completed"]), ("planned", len(selected))):
                    check_rate(value["rates"][f"{name}_per_{basis}"], numerator, denominator,
                               f"diagnostics/{key}/{name}_per_{basis}")
    return inputs, paths, hashes


def plotted_rows(inputs):
    analysis = inputs["analysis"]
    table = []
    for group, summary in [("overall", analysis["summary"]), *[
            (key, value["summary"]) for key, value in sorted(analysis["strata"]["model/prompt_version"].items())]]:
        for method in METHODS:
            for target in TARGETS:
                for metric in METRICS:
                    table.append({"group": group, "method": method, "target": target,
                                  "metric": metric, **summary[method][target][metric],
                                  "postcollection_diagnostic": False})
    for group, value in sorted(analysis["strata"]["model/prompt_version"].items()):
        planned = value["planned_episodes"]
        for status, count in value["episode_status"].items():
            table.append({"group": group, "method": "collection", "target": "episode_disposition",
                          "metric": status, "numerator": count, "denominator": planned,
                          "value": count / planned if planned else None,
                          "postcollection_diagnostic": False})
    if "execution_diagnostics" in inputs:
        for group, value in sorted(inputs["execution_diagnostics"]["strata"]["model/prompt_version"].items()):
            for name, rate in value["rates"].items():
                if name in {"action_selected_per_completed", "action_selected_per_planned",
                            "dispatched_per_completed", "dispatched_per_planned"}:
                    table.append({"group": group, "method": "agent_execution", "target": "operation",
                                  "metric": name, **rate, "postcollection_diagnostic": True})
    return table


def point(ax, value, y, color, *, marker="o", prefix=""):
    if value["denominator"] == 0:
        ax.text(0.035, y, prefix + "N/A (0 denom.)", ha="left", va="center", fontsize=7.0,
                color="#636B77")
        return
    x = value["value"]
    ax.plot(x, y, marker=marker, color=color, markersize=5, clip_on=False)
    label = f"{value['numerator']}/{value['denominator']}"
    ax.annotate(prefix + label, (x, y), xytext=(-7 if x > 0.52 else 7, 0),
                textcoords="offset points", va="center", ha="right" if x > 0.52 else "left",
                fontsize=7.0, color="#202936")


def style_axis(ax):
    ax.set_xlim(-0.025, 1.04)
    ax.set_xticks([0, .25, .5, .75, 1], ["0", "25", "50", "75", "100"])
    ax.grid(axis="x", color="#DEE3E8", linewidth=.6, zorder=-10)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#A8AFB8")
    ax.tick_params(axis="y", length=0, pad=9)
    ax.tick_params(axis="x", labelsize=7.5, colors="#56606D")


def save_figure(fig, out, stem):
    fig.savefig(out / f"{stem}.svg", format="svg", metadata={"Date": None})
    fig.savefig(out / f"{stem}.pdf", format="pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / f"{stem}.png", format="png", dpi=180)


def fixture_watermark(fig, inputs):
    if inputs["analysis"].get("synthetic_fixture") is True:
        fig.text(.5, .5, "SYNTHETIC LAYOUT FIXTURE\nNOT STUDY RESULTS", ha="center", va="center",
                 fontsize=19, rotation=22, color="#7C3B32", alpha=.22, zorder=100)


def metric_figure(inputs, out, plt):
    analysis, disposition = inputs["analysis"], inputs["disposition"]
    fig, axes = plt.subplots(2, 3, figsize=(7.16, 5.6))
    titles = ("Definite coverage", "Error among definite outputs", "Correct definite yield")
    for row, target in enumerate(TARGETS):
        for col, metric in enumerate(METRICS[:3]):
            ax = axes[row, col]
            style_axis(ax)
            for index, (method, color) in enumerate(zip(METHODS, COLORS, strict=True)):
                point(ax, analysis["summary"][method][target][metric], index, color)
            ax.set_ylim(len(METHODS)-.5, -.5)
            ax.set_yticks(range(len(METHODS)), LABELS if col == 0 else [""]*len(METHODS), fontsize=7.2)
            target_name = "Global state" if target == "state" else "Action-linked outcome"
            ax.set_title(f"{chr(97 + row*3 + col)}) {target_name}\n{titles[col]}", fontsize=8.0, pad=10)
            if row == 1:
                ax.set_xlabel("Percent", fontsize=8)
    counts = analysis["episode_status"]
    fig.suptitle("Matched factual auditors on shared completed episodes", fontsize=11, y=.985)
    fig.text(.5, .93, fill(f"{counts['completed']} completed / {analysis['planned_episodes']} planned; "
             f"collection {disposition['collection_state']}. Different information budgets; fixed simulator cases.",
             width=113), ha="center", fontsize=7.0, color="#4A5564")
    fig.text(.02, .025, fill("Fractions use completed episodes with assessable ledger gold. "
             "Abstention is unclaimed, not correct. N/A means a zero denominator; it is not zero error. "
             "Point estimates are descriptive. These episodes are not independent task samples; no confidence intervals are implied.",
             width=122), fontsize=7.0, color="#46505F")
    fig.subplots_adjust(left=.16, right=.985, bottom=.19, top=.82, hspace=.60, wspace=.16)
    fixture_watermark(fig, inputs)
    save_figure(fig, out, "matched-baseline-metrics")
    plt.close(fig)


def group_label(key):
    axes = json.loads(key)
    model = axes["model"].split(":", 1)[0]
    profile = axes["prompt_version"].removeprefix("refund-policy-")
    return f"{model} / {profile}"


def disposition_figure(inputs, out, plt):
    analysis = inputs["analysis"]
    strata = analysis["strata"]["model/prompt_version"]
    keys = sorted(strata)
    has_diagnostics = "execution_diagnostics" in inputs
    fig, axes = plt.subplots(1, 3 if has_diagnostics else 2, figsize=(7.16, 4.8))
    ax = axes[0]
    disposition_colors = ("#39846D", "#C36A63", "#D6A23E", "#CCD1D7")
    for index, key in enumerate(keys):
        left = 0
        planned = strata[key]["planned_episodes"]
        for status, color in zip(STATUSES, disposition_colors, strict=True):
            count = strata[key]["episode_status"][status]
            if count:
                ax.barh(index, count, left=left, height=.58, color=color, edgecolor="white", linewidth=.5)
                if count >= planned * .08:
                    ax.text(left + count/2, index, str(count), ha="center", va="center", fontsize=8,
                            color="white" if status in {"completed", "failed"} else "#202936")
            left += count
        ax.text(left + max(.03, left*.018), index, f"N={left}", va="center", fontsize=7.5)
    ax.set_xlim(0, max(value["planned_episodes"] for value in strata.values()) * 1.23)
    ax.set_yticks(range(len(keys)), [group_label(key) for key in keys], fontsize=7.2)
    ax.set_ylim(len(keys)-.5, -.5)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", labelsize=8)
    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Frozen episode slots", fontsize=8)
    ax.set_title("a) Collection disposition", fontsize=8.5, pad=14)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    ax.legend([Patch(facecolor=color) for color in disposition_colors],
              ["Completed", "Failed", "Interrupted", "Unstarted"], loc="upper center",
              bbox_to_anchor=(.5, -.16), frameon=False, ncol=2, fontsize=7)
    ax = axes[1]
    style_axis(ax)
    for index, key in enumerate(keys):
        for target, offset, color, marker in (("state", -.13, "#217A91", "o"),
                                             ("action_linked", .13, "#8062A6", "s")):
            point(ax, strata[key]["summary"]["consequa_state_origin"][target]["full_planned_correct_yield"],
                  index + offset, color, marker=marker)
    ax.set_yticks([])
    ax.set_ylim(len(keys)-.5, -.5)
    ax.set_title("b) Consequa-X operational yield\nCorrect definite / planned", fontsize=8.0, pad=14)
    ax.set_xlabel("Percent", fontsize=8)
    ax.legend([Line2D([], [], color="#217A91", marker="o", linestyle=""),
               Line2D([], [], color="#8062A6", marker="s", linestyle="")],
              ["Global state", "Action-linked"], frameon=False, loc="upper center",
              bbox_to_anchor=(.5, -.16), ncol=1, fontsize=7)
    if has_diagnostics:
        ax = axes[2]
        style_axis(ax)
        for index, key in enumerate(keys):
            rates = inputs["execution_diagnostics"]["strata"]["model/prompt_version"][key]["rates"]
            for name, offset, color, marker in (("action_selected", -.13, "#B16C28", "o"),
                                                ("dispatched", .13, "#202936", "D")):
                point(ax, rates[f"{name}_per_completed"], index + offset, color, marker=marker)
        ax.set_yticks([])
        ax.set_ylim(len(keys)-.5, -.5)
        ax.set_title("c) Agent execution\nSelected or dispatched / completed\nPostcollection diagnostic", fontsize=7.5, pad=14)
        ax.set_xlabel("Percent", fontsize=8)
        ax.legend([Line2D([], [], color="#B16C28", marker="o", linestyle=""),
                   Line2D([], [], color="#202936", marker="D", linestyle="")],
                  ["Action selected", "Agent dispatched"], frameon=False, loc="upper center",
                  bbox_to_anchor=(.5, -.16), ncol=1, fontsize=7)
    fig.suptitle("Model/profile accounting and operational yield", fontsize=11, y=.97)
    fig.text(.02, .025, fill("Operational yield retains failed, interrupted, unstarted, and gold-unassessable slots in the planned denominator. "
             + ("Selection/dispatch rates are postcollection descriptive diagnostics. A no-action outcome is not a dispatched fault test."
                if has_diagnostics else "No selection/dispatch diagnostics were supplied; do not infer that every episode exercised a fault."),
             width=120), fontsize=7.0, color="#46505F")
    fig.subplots_adjust(left=.19, right=.985, bottom=.28,
                        top=.80, wspace=.22)
    fixture_watermark(fig, inputs)
    save_figure(fig, out, "matched-model-disposition")
    plt.close(fig)


def build(analysis, protocol, disposition, output, diagnostics=None):
    script_sha = file_hash(__file__)
    inputs, paths, hashes = validate_inputs(analysis, protocol, disposition, diagnostics)
    # Plot only after all source accounting and finality checks have succeeded.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                                "pdf.fonttype": 42, "ps.fonttype": 42,
                                "svg.fonttype": "none", "axes.axisbelow": True})
    out = Path(output).resolve()
    require(not out.is_relative_to(paths["protocol"].parent), "Figure output must be outside the frozen study directory")
    out.mkdir(parents=True, exist_ok=False)
    source_dir = out / "source-inputs"
    source_dir.mkdir()
    for name, path in paths.items():
        (source_dir / f"{name}{'.jsonl' if name == 'journal' else '.json'}").write_bytes(path.read_bytes())
    table = plotted_rows(inputs)
    with (out / "figure-fractions.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["group", "method", "target", "metric", "numerator",
                                                   "denominator", "value", "postcollection_diagnostic"])
        writer.writeheader()
        writer.writerows(table)
    (out / "figure-fractions.json").write_text(json.dumps(table, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    metric_figure(inputs, out, plt)
    disposition_figure(inputs, out, plt)
    counts = inputs["analysis"]["episode_status"]
    notes = ("# Matched-study figures\n\n"
             + ("**SYNTHETIC LAYOUT FIXTURE - NOT STUDY RESULTS.**\n\n"
                if inputs["analysis"].get("synthetic_fixture") is True else "")
             +
             "These are descriptive figures from one explicitly closed collection. They do not establish "
             "causal attribution, model superiority, population generalization, or conference readiness.\n\n"
             f"Collection disposition: **{inputs['disposition']['collection_state']}**; "
             f"planned {inputs['analysis']['planned_episodes']}; dispositions `{json.dumps(counts, sort_keys=True)}`.\n\n"
             + (f"Stopped reason: {inputs['disposition']['stopped_reason']}\n\n"
                if inputs["disposition"]["collection_state"] == "stopped" else "")
             + "`matched-baseline-metrics` uses completed episodes with assessable ledger gold. "
             "Coverage is definite/assessable; error is wrong/definite; yield is correct/assessable. "
             "Zero denominators are null and displayed N/A. Abstaining on every target gives zero coverage "
             "and yield, with undefined claim error. Different auditor information budgets are declared in the protocol.\n\n"
             "`matched-model-disposition` retains all planned slots in operational yield. Its action-selection "
             "and dispatch panel, when present, is a postcollection descriptive addition and uses completed "
             "episodes for its displayed denominator. A no-action episode does not exercise a dispatched fault. "
             "Full model tags and all fraction numerators/denominators are in `figure-fractions.csv` and `.json`.\n\n"
             "SVG/PDF are vector exports; PNGs are layout previews. Exact input copies and their hashes "
             "are retained. Final inventory binds every generated file. No live model or analyzer was run.\n")
    (out / "README.md").write_text(notes, encoding="utf-8")
    # Do not silently plot an input changed between validation and artifact copy.
    require(all(file_hash(path) == hashes[name] for name, path in paths.items()),
            "Source input changed during plotting; preserve this directory as an invalid build")
    require(file_hash(__file__) == script_sha,
            "Figure builder changed during plotting; preserve this directory as an invalid build")
    inventory = {"schema_version": "consequa-matched-figure-inventory-v1",
                 "created_utc": datetime.now(timezone.utc).isoformat(),
                 "postcollection_presentation": True,
                 "synthetic_fixture": inputs["analysis"].get("synthetic_fixture") is True,
                 "script_sha256": script_sha, "python": sys.version,
                 "matplotlib": matplotlib.__version__,
                 "inputs": {name: {"path": str(path), "sha256": hashes[name]} for name, path in paths.items()},
                 "files": {path.relative_to(out).as_posix(): file_hash(path)
                           for path in sorted(out.rglob("*")) if path.is_file()}}
    (out / "figure-inventory.json").write_text(json.dumps(inventory, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"output": str(out), "collection_state": inputs["disposition"]["collection_state"],
            "planned_episodes": inputs["analysis"]["planned_episodes"], "episode_status": counts,
            "figures": ["matched-baseline-metrics", "matched-model-disposition"],
            "inventory_sha256": file_hash(out / "figure-inventory.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--disposition", required=True)
    parser.add_argument("--execution-diagnostics")
    parser.add_argument("--output", required=True, help="New directory; no existing path is overwritten")
    args = parser.parse_args()
    result = build(args.analysis, args.protocol, args.disposition, args.output, args.execution_diagnostics)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
