"""Plot sealed local-judge and native task-state transfer results, without inference."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(judge_path, tau_path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(output).resolve()
    if out.exists():
        raise ValueError("Use a fresh figure directory")
    judge, tau = load(judge_path), load(tau_path)
    if judge.get("final") is not True or tau.get("dispositions", {}).get("unstarted") != 0:
        raise ValueError("Only explicitly closed studies can be plotted")
    selected = judge["summary"]["selected_planned"]
    if selected != 84 or tau["planned"] != 656:
        raise ValueError("Unexpected prospective study size")
    out.mkdir(parents=True)
    (out / "source-inputs").mkdir()
    for name, source in (("judge-analysis.json", judge_path), ("tau-summary.json", tau_path)):
        (out / "source-inputs" / name).write_bytes(Path(source).read_bytes())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "pdf.fonttype": 42, "ps.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False})
    fractions = []

    def export(fig, stem):
        for suffix in ("pdf", "svg", "png"):
            options = {"dpi": 160} if suffix == "png" else {}
            fig.savefig(out / f"{stem}.{suffix}", **options)
        plt.close(fig)

    methods = (("local_trace_judge", "Local model judge", "#b76922"),
               ("independent_public_reference", "Independent reference", "#7860a5"),
               ("consequa_state_origin", "Consequa-X", "#19765d"))
    targets = (("state", "Global state"), ("action_linked", "Action-linked outcome"),
               ("origin", "Effect origin"))
    metrics = (("coverage", "Definite coverage", "claims", "gold_assessable_outputs"),
               ("claim_error", "Error among definite claims", "wrong_claims", "claims"),
               ("planned_yield", "Correct definite / all planned", "correct_claims", None))
    fig, axes = plt.subplots(3, 3, figsize=(9.5, 7.6))
    fig.subplots_adjust(left=.22, right=.97, top=.84, bottom=.24, hspace=.9, wspace=.25)
    fig.suptitle("Same-evidence local model judge", fontsize=18, y=.98)
    status = judge["summary"]["judge_status"]
    fig.text(.5, .935, f"84 selected traces; {status.get('completed', 0)}/84 judge outputs completed. 17 distinct evidence patterns.",
             ha="center", fontsize=10, color="#475569")
    for row, (target, title) in enumerate(targets):
        for col, (metric, label, numkey, denkey) in enumerate(metrics):
            ax = axes[row, col]
            ax.set_title(f"{title}\n{label}", fontsize=11, pad=12)
            for idx, (method, _, color) in enumerate(methods):
                d = judge["summary"]["methods"][method][target]
                n, den = d[numkey], selected if denkey is None else d[denkey]
                if n < 0 or den < 0 or n > den or d["claims"] != d["correct_claims"] + d["wrong_claims"]:
                    raise ValueError("Invalid judge fraction")
                value = n / den if den else None
                fractions.append({"study": "judge", "group": method, "target": target,
                                  "metric": metric, "numerator": n, "denominator": den,
                                  "value": value})
                y = 2 - idx
                if value is None:
                    ax.text(3, y, "N/A (0 denominator)", va="center", fontsize=9, color="#64748b")
                else:
                    x = 100 * value
                    ax.scatter(x, y, s=50, color=color, zorder=3)
                    ax.annotate(f"{n}/{den}", (x, y), xytext=(-9 if x > 65 else 9, 0),
                                textcoords="offset points", ha="right" if x > 65 else "left",
                                va="center", fontsize=10)
            ax.set(xlim=(-3, 103), ylim=(-.4, 2.4), xticks=(0, 25, 50, 75, 100),
                   yticks=(2, 1, 0), yticklabels=[m[1] for m in methods] if col == 0 else [])
            ax.grid(axis="x", color="#e2e8f0")
            ax.spines["left"].set_visible(False)
            ax.spines["bottom"].set_color("#94a3b8")
            ax.tick_params(axis="y", length=0)
            if row == 2:
                ax.set_xlabel("Percent")
    unassessable = judge["summary"]["methods"]["local_trace_judge"]["origin"]["claims_with_unassessable_gold"]
    fig.text(.02, .025, "One frozen Qwen3 4B judge on a fixed repetition-zero subset. Gold-unassessable origin is excluded only\n"
             "from semantic coverage/error denominators. Failures and abstentions remain in all-planned yield.\n"
             f"The judge additionally made {unassessable} origin claims with unknown gold; these are not scored as correct or wrong.\n"
             "N/A is undefined, not zero error. Descriptive fractions; no independent-task confidence intervals.",
             fontsize=10, color="#475569", linespacing=1.4)
    export(fig, "same-evidence-trace-judge")

    domains = (("retail", 114, "Retail"), ("airline", 50, "Airline"))
    variants = (("reference", "Reference replay"), ("omit_writes", "Omit writes"),
                ("false_acknowledgement", "False success response"),
                ("altered_first_write", "Alter first write"))
    native = Counter()
    for d in tau["native_db_component_counts"]:
        native[d["domain"], d["variant"], d["db_match"]] += d["count"]
    fields = Counter()
    for d in tau["action_field_counts"]:
        fields[d["domain"], d["variant"], d["status"]] += d["count"]
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 6.5))
    fig.subplots_adjust(left=.22, right=.97, top=.81, bottom=.29, hspace=.8, wspace=.40)
    fig.suptitle("Maintained benchmark task/tool state transfer", fontsize=17, y=.98)
    fig.text(.5, .93, "164 canonical tasks × four controls = 656 planned cells; native tools and DB evaluator unchanged.",
             ha="center", fontsize=10, color="#475569")
    colors = {"satisfied": "#1b7a60", "violated": "#bd6637", "unknown": "#8795a5"}
    for row, (domain, planned, title) in enumerate(domains):
        ax, bx = axes[row]
        ax.set_title(f"{title}: native task DB matches\nMatches / planned source tasks", fontsize=11)
        bx.set_title(f"{title}: intended-operation field checks\nCounts; right label = satisfied / N", fontsize=11)
        for idx, (variant, label) in enumerate(variants):
            y, n = 3 - idx, native[domain, variant, True]
            if n > planned:
                raise ValueError("Invalid native task fraction")
            fractions.append({"study": "tau3_native_db", "group": domain, "target": variant,
                              "metric": "db_match_per_planned", "numerator": n,
                              "denominator": planned, "value": n / planned})
            x = 100 * n / planned
            ax.scatter(x, y, color="#306b8d", s=50, zorder=3)
            ax.annotate(f"{n}/{planned}", (x, y), xytext=(-8 if x > 65 else 8, 0),
                        textcoords="offset points", va="center", ha="right" if x > 65 else "left")
            left = 0
            statuses = sorted({s for d, v, s in fields if d == domain and v == variant})
            for s in ("satisfied", "violated", "unknown", *[s for s in statuses if s not in colors]):
                count = fields[domain, variant, s]
                if not count:
                    continue
                bx.barh(y, count, left=left, height=.55, color=colors.get(s, "#c5b57e"))
                if count >= 8:
                    bx.text(left + count / 2, y, str(count), ha="center", va="center", color="white", fontsize=10.5)
                left += count
                fractions.append({"study": "tau3_action_fields", "group": domain, "target": variant,
                                  "metric": s, "numerator": count, "denominator": None, "value": None})
            bx.text(left + 2, y, f"{fields[domain, variant, 'satisfied']}/{left}", va="center", fontsize=10)
        ax.set(xlim=(-3, 103), ylim=(-.4, 3.4), xticks=(0, 25, 50, 75, 100),
               yticks=(3, 2, 1, 0), yticklabels=[v[1] for v in variants], xlabel="Percent")
        bx.set(ylim=(-.4, 3.4), yticks=(), xlabel="Intended-operation audits")
        ax.grid(axis="x", color="#e2e8f0")
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        bx.spines["left"].set_visible(False)
        bx.margins(x=.30)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=c, label=s.capitalize()) for s, c in colors.items()] +
               [Patch(color="#c5b57e", label="Capture unavailable")],
               loc="lower center", bbox_to_anchor=(.55, .11), ncol=4, frameon=False)
    fig.text(.02, .025, "Model-free reference/control replay, not autonomous-agent benchmark performance.\n"
             "DB targets and immediate field contracts differ; these counts are not predicate accuracy.\n"
             "Missing readback and origin remain unknown.",
             color="#475569", fontsize=10, linespacing=1.4)
    export(fig, "benchmark-state-transfer")
    (out / "fractions.json").write_text(json.dumps(fractions, indent=2) + "\n", encoding="utf-8")
    with (out / "fractions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fractions[0]))
        writer.writeheader()
        writer.writerows(fractions)
    manifest = {"script_sha256": digest(__file__), "matplotlib": matplotlib.__version__,
                "inputs": {str(Path(p).resolve()): digest(p) for p in (judge_path, tau_path)},
                "files": {p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob("*")) if p.is_file()},
                "model_calls": 0, "postcollection_presentation": True}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "figures": 2, "fractions": len(fractions)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-analysis", required=True)
    parser.add_argument("--tau-summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(args.judge_analysis, args.tau_summary, args.output)
