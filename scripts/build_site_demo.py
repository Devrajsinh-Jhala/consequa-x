"""Generate the homepage demo data from real Consequa-X package runs.

The homepage inspector and live terminal must not carry hand-written outcomes.
This script runs the package CLI in a new temporary directory, records each
command's exact standard output (printed paths are shown relative to that
directory), confirms that the rendered report is byte-identical to the published
sample report, and extracts four real demo traces with fresh ``explain`` results
and evidence-graph subsets. It writes one generated JavaScript data file. It
never edits page markup, deploys anything or calls a model.
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from consequa_x import Trace, __version__, build_graph, explain


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "website/dist"
OUTPUT = DIST / "assets/demo-data.js"
SAMPLE_REPORT = DIST / "assets/sample-report.html"
INSTALL = f"python -m pip install consequa-x=={__version__}"
REPORT_TRACE = "my-demo/traces/episode_01.json"
COMMANDS = (
    ("consequa-x --version", ("--version",)),
    ("consequa-x demo --output my-demo", ("demo", "--output", "my-demo")),
    (f"consequa-x report {REPORT_TRACE} --output my-report.html",
     ("report", REPORT_TRACE, "--output", "my-report.html")),
)
SCENARIOS = (
    ("episode_01", "Timeout after commit"),
    ("episode_05", "Stale readback"),
    ("episode_09", "Another actor"),
    ("episode_06", "Later readback"),
)
CONTEXT_LABELS = {"user_input": "user input", "memory_read": "memory read",
                  "retrieval": "retrieval", "system_instruction": "system instruction"}
GRAPH_LANES = {"action_dispatch": 0, "tool_response": 0, "agent_assessment": 0,
               "external_effect_identity": 1, "observed_external_effect": 1,
               "external_observation": 2, "postcondition": 3, "verification": 3}
EDGE_LABELS = {"DEPENDENCY": "Declared dependency", "RESPONSE": "Response to attempt",
               "EFFECT": "Provider origin metadata", "OBSERVATION": "Readback witness",
               "IDENTITY": "Shared effect identifier", "CONTRACT": "Declared contract",
               "VERIFICATION": "Verification evidence"}


def run_cli(workdir, args):
    """Run the real CLI and return stdout lines with the work directory removed."""
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "consequa_x", *args], cwd=workdir,
        capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    prefix = str(Path(workdir).resolve()) + os.sep
    text = completed.stdout.replace(prefix, "").replace(os.sep, "/")
    if str(Path(workdir).resolve()).replace(os.sep, "/") in text:
        raise ValueError("A printed path still exposes the temporary directory")
    return text.rstrip("\n").splitlines()


def money(expected):
    amount = expected["amount_minor"]
    return f"{expected['currency']} {amount // 100:,}" + (f".{amount % 100:02d}" if amount % 100 else "")


def plural(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


def timeline(trace):
    """Readable entries derived only from captured records, in recorded order."""
    action, contract = trace.action, trace.action.contract
    entries = []
    context = [event for event in trace.events if event.type.value in CONTEXT_LABELS]
    if context:
        kinds = {}
        for event in context:
            label = CONTEXT_LABELS[event.type.value]
            kinds[label] = kinds.get(label, 0) + 1
        entries.append({
            "t": min(event.time_ms for event in context),
            "t_end": max(event.time_ms for event in context),
            "kind": "context", "label": "Context captured",
            "detail": ", ".join(plural(count, label) if count > 1 else label
                                for label, count in kinds.items()),
        })
    count = "At least one" if contract.exact_count is None else f"Exactly {contract.exact_count}"
    horizon = (f"; persists to {contract.horizon_ms} ms" if contract.stability_ms else "")
    entries.append({"t": action.registered_at_ms, "kind": "contract",
                    "label": "Outcome contract registered",
                    "detail": f"{count} refund of {money(contract.expected)} by "
                              f"{contract.deadline_ms} ms{horizon}"})
    attempts = 0
    for event in trace.events:
        kind = event.type.value
        if kind == "agent_decision":
            entries.append({"t": event.time_ms, "kind": "decision",
                            "label": "Agent decides to refund", "detail": "Policy decision"})
        elif kind == "action_dispatch":
            attempts += 1
            entries.append({"t": event.time_ms, "kind": "dispatch", "label": "Refund dispatched",
                            "detail": f"Attempt {attempts}"})
        elif kind == "tool_response":
            status = event.data.get("status", "recorded")
            entries.append({"t": event.time_ms, "kind": "response",
                            "label": f"Tool response: {status}", "tone": status,
                            "detail": "A response describes the call, not the outcome"})
        elif kind == "agent_assessment":
            entries.append({"t": event.time_ms, "kind": "assessment",
                            "label": f"Agent reports {trace.assessment.status.value}",
                            "detail": "Reported assessment, not verification"})
    for index, observation in enumerate(trace.observations, 1):
        coverage = ("complete" if observation.complete else "incomplete") + (
            "" if observation.available else ", unavailable")
        entries.append({"t": observation.observed_at_ms, "kind": "readback",
                        "label": f"Independent readback {index}",
                        "detail": f"Watermark {observation.as_of_ms} ms; {coverage}; "
                                  f"{plural(len(observation.records), 'effect record')}"})
    for index, verification in enumerate(trace.verifications, 1):
        entries.append({"t": verification.observed_at_ms, "kind": "verification",
                        "label": f"Verification {index}: {verification.status.value}",
                        "tone": verification.status.value,
                        "detail": f"Origin {verification.origin.value}. {verification.reason}"})
    order = {"context": 0, "contract": 1, "decision": 2, "dispatch": 3, "response": 4,
             "assessment": 5, "readback": 6, "verification": 7}
    return sorted(entries, key=lambda entry: (entry["t"], order[entry["kind"]]))


def ribbon(trace):
    action, contract = trace.action, trace.action.contract
    observations = []
    for observation in trace.observations:
        effects = []
        for record in observation.records:
            actor = record.get("actor")
            effects.append({
                "committed_ms": record.get("committed_at_ms"),
                "actor": "agent" if actor == action.actor else ("other" if actor else "unknown"),
                "linked": record.get("action_id") == action.action_id,
            })
        observations.append({
            "observed_ms": observation.observed_at_ms, "watermark_ms": observation.as_of_ms,
            "complete": observation.complete, "available": observation.available,
            "covers_horizon": observation.as_of_ms >= contract.horizon_ms, "effects": effects,
        })
    return {"registered_ms": action.registered_at_ms, "deadline_ms": contract.deadline_ms,
            "stability_ms": contract.stability_ms, "horizon_ms": contract.horizon_ms,
            "exact_count": contract.exact_count, "observations": observations}


def graph_subset(trace):
    """Real evidence-graph nodes and non-temporal links, with report-style aliases."""
    graph = build_graph(trace)
    observed = {f"observation:{item.observation_id}": item.observed_at_ms
                for item in trace.observations}
    counters, aliases, reveal = {}, {}, {}
    names = {"action_dispatch": "Dispatch", "tool_response": "Response",
             "agent_assessment": "Assessment", "observed_external_effect": "Witness",
             "external_effect_identity": "Effect identity", "external_observation": "Readback",
             "postcondition": "Contract", "verification": "Verification"}
    nodes = []
    for node in graph.nodes:
        if node.kind not in GRAPH_LANES:
            continue
        counters[node.kind] = counters.get(node.kind, 0) + 1
        aliases[node.id] = f"{names[node.kind]} {counters[node.kind]}"
        if node.kind == "observed_external_effect":
            reveal[node.id] = observed[f"observation:{node.data['witness_observation_id']}"]
        else:
            reveal[node.id] = node.time_ms
    for node in graph.nodes:
        if node.kind == "external_effect_identity":
            reveal[node.id] = min(reveal[f] for f in
                                  (e.source for e in graph.edges
                                   if e.kind == "IDENTITY" and e.target == node.id))
    for node in graph.nodes:
        if node.id in aliases:
            status = node.data.get("status") if node.kind in {"tool_response", "agent_assessment",
                                                              "verification"} else None
            nodes.append({"id": aliases[node.id], "kind": node.kind,
                          "lane": GRAPH_LANES[node.kind], "time_ms": node.time_ms,
                          "reveal_ms": reveal[node.id], "status": status,
                          "origin": node.data.get("origin") if node.kind == "verification" else None,
                          "actor": ("agent" if node.data.get("actor") == trace.action.actor else
                                    "other" if node.data.get("actor") else "unknown")
                          if node.kind == "observed_external_effect" else None})
    edges = [{"source": aliases[edge.source], "target": aliases[edge.target],
              "kind": edge.kind, "label": EDGE_LABELS[edge.kind]}
             for edge in graph.edges
             if edge.kind != "TEMPORAL" and edge.source in aliases and edge.target in aliases]
    return {"nodes": nodes, "edges": edges,
            "full_counts": {"nodes": len(graph.nodes), "edges": len(graph.edges)}}


def printed_cases(demo_output):
    """Scenario names and diagnoses in episode order, as the demo command printed them."""
    cases = []
    for line in demo_output[1:]:
        name, diagnosis = line.strip().split(": ", 1)
        cases.append((name, diagnosis))
    return cases


def scenario(demo, cases, stem, label):
    trace = Trace.from_json((demo / "traces" / f"{stem}.json").read_text(encoding="utf-8"))
    result = explain(trace)
    exported = json.loads((demo / "explanations" / f"{stem}.json").read_text(encoding="utf-8"))
    if result.to_dict() != exported:
        raise ValueError(f"Fresh explain() differs from the CLI export for {stem}")
    name, printed = cases[int(stem.split("_")[1])]
    if printed != result.diagnosis:
        raise ValueError(f"Printed demo diagnosis differs from explain() for {stem}")
    latest = trace.verifications[-1]
    return {
        "id": stem, "label": label, "scenario": name, "file": f"traces/{stem}.json",
        "response": [item.status.value for item in trace.responses],
        "assessment": trace.assessment.status.value,
        "timeline": timeline(trace), "ribbon": ribbon(trace), "graph": graph_subset(trace),
        "explanation": {"state": latest.status.value, "origin": latest.origin.value,
                        "alignment": result.assessment_alignment,
                        "diagnoses": list(result.diagnoses), "diagnosis": result.diagnosis,
                        "summary": result.summary, "reason": latest.reason},
    }


def build():
    with tempfile.TemporaryDirectory(prefix="consequa-site-demo-") as workdir:
        terminal = [{"command": command, "output": run_cli(workdir, args)}
                    for command, args in COMMANDS]
        report = (Path(workdir) / "my-report.html").read_bytes()
        if report != SAMPLE_REPORT.read_bytes():
            raise ValueError("Rendered report differs from website/dist/assets/sample-report.html")
        demo = Path(workdir) / "my-demo"
        cases = printed_cases(terminal[1]["output"])
        data = {
            "generator": "scripts/build_site_demo.py",
            "package_version": __version__, "seed": 0,
            "install": INSTALL, "terminal": terminal,
            "report": {"path": "assets/sample-report.html", "sha256": sha256(report).hexdigest(),
                       "trace": REPORT_TRACE},
            "scenarios": [scenario(demo, cases, stem, label) for stem, label in SCENARIOS],
        }
    return ("// Generated by scripts/build_site_demo.py from real consequa-x "
            f"{__version__} runs. Do not edit by hand.\n"
            "window.CONSEQUA_DEMO = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Fail if the committed data differs from a fresh build")
    args = parser.parse_args()
    content = build()
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != content:
            raise SystemExit("website/dist/assets/demo-data.js is stale; rebuild it")
        print("Demo data matches a fresh package run.")
        return
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
