"""Read-only postcollection analysis of an interrupted resource observer.

This script never imports psutil, contacts a server, inspects a current process,
or changes any input. It creates a new finalization bundle, not an observer seal.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("A timestamp is missing its timezone")
    return result


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed in observer inventory")
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {
                "bytes": len(data), "sha256": sha(data),
            }
    return result


def finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def summarize(samples):
    if not samples:
        return {"samples": 0, "observed_interval": None}
    first, last = samples[0], samples[-1]
    span = last["elapsed_seconds"] - first["elapsed_seconds"]
    result = {
        "samples": len(samples),
        "observed_interval": {
            "first_sample_utc": first["recorded_utc"],
            "last_sample_utc": last["recorded_utc"],
            "first_sample_index": first["sample_index"],
            "last_sample_index": last["sample_index"],
            "monotonic_seconds_between_first_and_last_sample": span,
        },
        "sampled_available_ram_bytes": {
            "minimum": min(s["system_ram"]["available_bytes"] for s in samples),
            "maximum": max(s["system_ram"]["available_bytes"] for s in samples),
        },
        "processes": {},
    }
    for name in sorted(first["processes"]):
        def cpu(row):
            item = row["processes"][name]
            return item["cpu_user_seconds"] + item["cpu_system_seconds"]
        delta = cpu(last) - cpu(first)
        if delta < 0:
            raise ValueError("CPU clock decreased")
        result["processes"][name] = {
            "cpu_seconds_delta_between_first_and_last_sample": delta,
            "cpu_percent_between_first_and_last_sample": (
                100 * delta / span if span > 0 else None
            ),
            "sampled_rss_bytes": {
                "minimum": min(s["processes"][name]["rss_bytes"] for s in samples),
                "maximum": max(s["processes"][name]["rss_bytes"] for s in samples),
            },
            "sampled_vms_bytes": {
                "minimum": min(s["processes"][name]["vms_bytes"] for s in samples),
                "maximum": max(s["processes"][name]["vms_bytes"] for s in samples),
            },
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observer, episode, output = (
        path.resolve() for path in (args.observer, args.episode, args.output)
    )
    if observer == output or observer in output.parents or output in observer.parents:
        raise ValueError("The finalization must be separate from the original observer")
    output.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    if any(p.resolve() != script for p in output.iterdir()):
        raise ValueError("Refuse to overwrite an existing finalization")
    before = inventory(observer)
    required = {"launch.source.json", "observer-binding.json", "observer.source.py",
                "render.source.json", "resources.jsonl"}
    if set(before) != required:
        raise ValueError("Unexpected observer contents; this analysis expects an unsealed journal")
    binding = json.loads((observer / "observer-binding.json").read_bytes())
    raw = (observer / "resources.jsonl").read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("Journal does not end in a complete newline-terminated record")
    samples = [json.loads(line) for line in raw.splitlines()]
    if not samples:
        raise ValueError("Empty resource journal")
    for index, row in enumerate(samples):
        if row["schema"] != "native-resource-sample-v1" or row["sample_index"] != index:
            raise ValueError("Sample schema or sequential index mismatch")
        stamp(row["recorded_utc"])
        if index and (row["elapsed_seconds"] <= samples[index - 1]["elapsed_seconds"]
                      or stamp(row["recorded_utc"]) <= stamp(samples[index - 1]["recorded_utc"])):
            raise ValueError("Sample timestamps do not increase")
        for name, identity in binding["processes"].items():
            process = row["processes"][name]
            for key in ("pid", "create_time_epoch_seconds"):
                if process[key] != identity[key]:
                    raise ValueError("Historical process lease mismatch")
            for key in ("cpu_user_seconds", "cpu_system_seconds", "rss_bytes", "vms_bytes"):
                if not finite_number(process[key]) or process[key] < 0:
                    raise ValueError("Invalid process metric")
    linked_paths = [episode / "model-calls.jsonl", episode / "execution-receipt.json"]
    linked = {}
    linked_bytes = {}
    for path in linked_paths:
        data = path.read_bytes()
        linked_bytes[path.name] = data
        linked[str(path)] = {"bytes": len(data), "sha256": sha(data)}
    journal = [json.loads(line) for line in linked_bytes["model-calls.jsonl"].splitlines()]
    calls = {}
    for event in journal:
        index = event["call_index"]
        record = calls.setdefault(index, {})
        key = "start" if event["kind"] == "request_start" else "terminal"
        if key in record:
            raise ValueError("Duplicate call event")
        record[key] = event
    requests = []
    for index in sorted(calls):
        start, terminal = calls[index].get("start"), calls[index].get("terminal")
        if start is None or terminal is None:
            raise ValueError("This finalization requires complete terminal request records")
        lo, hi = stamp(start["recorded_utc"]), stamp(terminal["recorded_utc"])
        if hi < lo:
            raise ValueError("Request terminal precedes start")
        interior = [row for row in samples if lo <= stamp(row["recorded_utc"]) <= hi]
        request = {
            "call_index": index,
            "request_start_utc": start["recorded_utc"],
            "request_terminal_utc": terminal["recorded_utc"],
            "terminal_kind": terminal["kind"],
            "terminal_error_type": terminal.get("error_type"),
            "recorded_wall_seconds": terminal.get("wall_seconds"),
            "resource_samples_recorded_inside_request_window": summarize(interior),
        }
        requests.append(request)
    intervals = [samples[i]["elapsed_seconds"] - samples[i - 1]["elapsed_seconds"]
                 for i in range(1, len(samples))]
    after = inventory(observer)
    if before != after:
        raise ValueError("Observer inputs changed during analysis")
    for path in linked_paths:
        if path.read_bytes() != linked_bytes[path.name]:
            raise ValueError("Linked G1 input changed during analysis")
    result = {
        "schema": "native-resource-observer-posthoc-finalization-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "observer_directory": str(observer),
        "observer_termination": {
            "original_summary_present": False,
            "original_manifest_present": False,
            "termination_classification": "unclean_or_unsealed_observer_termination",
            "cause": "unknown_from_retained_observer_artifacts",
            "closing_status": None,
            "coverage_after_last_recorded_sample": "unavailable",
            "retrospective_observer_seal_created": False,
        },
        "original_inputs_unchanged": before == after,
        "original_inventory_before": before,
        "original_inventory_after": after,
        "linked_G1_inputs": linked,
        "historical_process_binding": binding["processes"],
        "process_identity_interpretation": (
            "All retained samples match the original PID and creation-time lease. "
            "The original observer additionally bound executable identity and parent PID. "
            "A historical PID alone never authorizes inspecting or controlling a current process. "
            "This analysis did not inspect or act on any current process."
        ),
        "full_recorded_interval": summarize(samples),
        "monotonic_sample_interval_seconds": {
            "minimum": min(intervals), "maximum": max(intervals),
            "median": statistics.median(intervals),
        },
        "G1_request_windows": requests,
        "G1_execution_receipt": json.loads(linked_bytes["execution-receipt.json"]),
        "interpretation": (
            "The timed-out G1 request overlaps sustained runner CPU activity and available "
            "system RAM in the retained samples. These measurements describe resource "
            "use, not the causal reason for the timeout. They cannot exclude paging, "
            "memory pressure between samples, scheduler effects, or other bottlenecks."
        ),
        "limitations": [
            "No new measurements were taken; there is no coverage beyond the final sample.",
            "Samples are approximately 30 seconds apart and do not establish true resource peaks.",
            "Per-request CPU is computed from the first and last samples fully inside that request, "
            "not extrapolated to its unsampled edges; each interval is reported explicitly.",
            "CPU percent is 100 times process user+system CPU seconds delta divided by monotonic "
            "wall seconds delta; it may exceed 100 across cores.",
            "RSS is working-set memory, and VMS is virtual allocation; neither establishes physical "
            "resident model cache size or memory bandwidth.",
            "System available RAM reflects unobserved applications. No paging, GPU utilization, "
            "or per-request generation-versus-prefill timing was measured by this observer.",
            "The linked G1 task is development data and has no fabricated native reward.",
            "This new bundle is a postcollection inventory and analysis, not the missing original "
            "observer terminal receipt or manifest.",
        ],
    }
    def write(name, content):
        with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    write("result.json", json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    failed = [r for r in requests if r["terminal_kind"] == "request_error"]
    lines = [
        "# Resource observer postcollection finalization", "",
        "The original observer ended without its summary or manifest. Its retained artifacts "
        "do not establish why it stopped. This new bundle preserves and inventories all five "
        "original files; their byte lengths and SHA-256 hashes match before and after analysis.", "",
        f"The journal contains {len(samples)} complete sequential samples, from "
        f"{samples[0]['recorded_utc']} through {samples[-1]['recorded_utc']}. "
        "There is no resource evidence after that final sample and no inferred closing status.", "",
        "The original process lease binds PID, creation time, executable identity, and parent PID. "
        "Every retained sample matches the recorded PID and creation time. Historical PIDs must "
        "not be treated as current process identities. This analysis performed no process lookup "
        "or process control, network request, or model invocation.", "",
        "## G1 development request alignment", "",
        "| Call | Terminal | Recorded request seconds | Interior samples | Runner CPU % | Minimum available RAM (GiB) | Maximum runner RSS (GiB) |",
        "|---:|:---|---:|---:|---:|---:|---:|",
    ]
    for r in requests:
        s = r["resource_samples_recorded_inside_request_window"]
        cpu = s["processes"]["runner"]["cpu_percent_between_first_and_last_sample"]
        cpu_text = f"{cpu:.2f}" if cpu is not None else "unavailable"
        lines.append(f"| {r['call_index']} | {r['terminal_kind']} | {r['recorded_wall_seconds']:.3f} "
                     f"| {s['samples']} | {cpu_text} | "
                     f"{s['sampled_available_ram_bytes']['minimum'] / 2**30:.3f} | "
                     f"{s['processes']['runner']['sampled_rss_bytes']['maximum'] / 2**30:.3f} |")
    lines += ["", "CPU is calculated between the first and last recorded samples strictly inside "
              "each request's inclusive timestamp window, using cumulative user+system CPU delta "
              "and monotonic elapsed time. Exact covered bounds appear in result.json. "
              "100% represents one CPU core equivalent; values above 100% are valid.", ""]
    for r in failed:
        s = r["resource_samples_recorded_inside_request_window"]
        lines += [f"Call {r['call_index']} ended with `{r['terminal_error_type']}` at "
                  f"{r['request_terminal_utc']}. Its {s['samples']} interior samples cover "
                  f"{s['observed_interval']['first_sample_utc']} to "
                  f"{s['observed_interval']['last_sample_utc']}. Sustained CPU activity is "
                  "consistent with ongoing computation while the client waited. These sampled "
                  "data cannot establish whether compute, paging, memory pressure, scheduler "
                  "effects, or another factor caused the timeout.", ""]
    lines += ["The original G1 execution receipt records 9 attempted model calls, 8 completions, "
              "one timeout, and five completed native tool dispatches. It marks the native "
              "reward as not fabricated. This is a failed development run, not an official "
              "benchmark score.", "", "## Limits", ""]
    lines.extend(f"- {item}" for item in result["limitations"])
    write("README.md", "\n".join(lines) + "\n")
    final_inventory = inventory(output)
    write("manifest.json", json.dumps({
        "schema": "native-resource-observer-posthoc-finalization-manifest-v1",
        "files": final_inventory,
        "original_observer_manifest_reconstructed": False,
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "samples": len(samples),
                      "original_inputs_unchanged": True,
                      "manifest_sha256": sha((output / "manifest.json").read_bytes())}))


if __name__ == "__main__":
    main()
