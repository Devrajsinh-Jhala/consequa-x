"""Freeze a separately identified follow-up without changing the registered cases.

Run once before follow-up generation and publish the resulting exact bytes.
The original protocol and its interrupted denominator are retained separately.
No model request or native task trajectory is executed here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.limbo_agent.audit import require, verify_manifest  # noqa: E402
from research.limbo_agent.harness import manifest  # noqa: E402
from research.limbo_agent.protocol import (  # noqa: E402
    canonical, file_binding, freeze, utc, write_new,
)

ORIGINAL_COMMIT = "267cd1a3e846c46c009f20accbf302746e064875"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bound(path):
    return {"path": str(Path(path).resolve()), **file_binding(path)}


def compare_design(original, followup):
    for key in ("schema", "seed", "native", "sources", "metadata", "arms", "limits", "claims", "endpoints"):
        require(canonical(original[key]) == canonical(followup[key]), "Original design changed: " + key)
    require(canonical({key: original["wheel"][key] for key in ("sha256", "bytes")})
            == canonical({key: followup["wheel"][key] for key in ("sha256", "bytes")}),
            "Original SDK wheel changed")
    for key in ("python_version", "implementation", "distributions"):
        require(canonical(original["environment"][key]) == canonical(followup["environment"][key]),
                "Original interpreter/dependency versions changed: " + key)
    for key in ("executable", "base_executable"):
        require(canonical({field: original["environment"][key][field] for field in ("sha256", "bytes")})
                == canonical({field: followup["environment"][key][field] for field in ("sha256", "bytes")}),
                "Original interpreter bytes changed: " + key)
    require(len(original["schedule"]) == len(followup["schedule"]) == 96,
            "Both conditions must retain 96 planned slots")
    for old, new in zip(original["schedule"], followup["schedule"]):
        require(old["spec"]["model"] == original["runtime_binding"]["model"]
                and new["spec"]["model"] == followup["runtime_binding"]["model"],
                "A slot model differs from its declared runtime alias")
        left, right = dict(old), dict(new)
        left["spec"], right["spec"] = dict(old["spec"]), dict(new["spec"])
        left["spec"].pop("model")
        right["spec"].pop("model")
        require(canonical(left) == canonical(right), "Follow-up cases, arms or limits changed")
    for key in ("model_blob_sha256", "model_digest", "context_tokens", "parallel_slots"):
        require(canonical(original["runtime_binding"][key]) == canonical(followup["runtime_binding"][key]),
                "Original model weights/configuration changed: " + key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native-root", "wheel", "runtime-binding", "readiness", "original-protocol",
                 "interrupted-analysis", "runtime-launch-receipt", "private-runtime-manifest",
                 "durability-proof", "amendment", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    original = load(args.original_protocol)
    ready = load(args.readiness)
    require(ready.get("schema") == "conseqax-limbo-relocated-readiness-v1" and ready.get("passed") is True,
            "Follow-up needs its passed relocated readiness")
    verify_manifest(args.readiness.parent)
    verify_manifest(args.interrupted_analysis)
    earlier = load(args.interrupted_analysis / "results.json")
    require(earlier["inputs"]["protocol_commit"] == ORIGINAL_COMMIT
            and {key: earlier["inputs"]["protocol"][key] for key in ("sha256", "bytes")}
                == file_binding(args.original_protocol), "Interrupted analysis identity differs")
    original_audit = load(args.interrupted_analysis / "inputs/audit-result.json")
    require(original_audit.get("passed") is True and bool(original_audit.get("interrupted_collection")),
            "Original condition must have passed replay and explicit interruption provenance")
    launch = load(args.runtime_launch_receipt)
    inventory = load(args.private_runtime_manifest)
    require(launch["version_response"]["version"] == launch["declared_runtime_version"]
            == inventory["declared_version"] == "0.40.10", "Private runtime version differs")
    require(launch["model_generation_attempts"] == launch["model_downloads"] == 0
            and launch["normal_service_modified"] is False,
            "Runtime setup must retain zero completions/downloads and no normal-service mutation")
    require({key: launch["private_runtime_manifest"][key] for key in ("sha256", "bytes")}
            == file_binding(args.private_runtime_manifest), "Private runtime inventory differs")
    require(ready["runtime_binding"] == launch["runtime_binding"] == load(args.runtime_binding),
            "Readiness/runtime setup differs")
    require(ready["prospective_amendment"] == bound(args.amendment)
            and ready["durability_proof"] == bound(args.durability_proof),
            "Readiness does not bind the selected amendment/durability proof")
    # The unchanged freezer writes only to an owned temporary directory. The
    # final extended protocol is created once, then committed before generation.
    with tempfile.TemporaryDirectory(prefix="conseqax-followup-freeze-") as temporary:
        value = freeze(ROOT, args.native_root, args.wheel, args.runtime_binding,
            Path(temporary) / "base-freeze", world_count=24, index=1022,
            max_tool_calls=16, max_requests=16, max_output_tokens=512,
            request_timeout_s=1200.0, episode_timeout_s=7200.0, seed=1701,
            readiness_path=args.readiness)
    compare_design(original, value)
    value["execution_condition"] = {
        "id": "relocated-isolated-runtime-2026-10-24", "ollama_version": "0.40.10",
        "runtime_launch_receipt": bound(args.runtime_launch_receipt),
        "private_runtime_manifest": bound(args.private_runtime_manifest),
        "launcher": bound(ROOT / "scripts/launch_durable_research.py"),
        "durability_proof": bound(args.durability_proof), "amendment": bound(args.amendment),
        "declaration_source": bound(__file__),
        "scope": "One separately declared full execution condition; same cases/weights/design, relocated paths and private runtime; no retry/resume/replacement of the interrupted original",
    }
    value["prior_condition"] = {
        "protocol_commit": ORIGINAL_COMMIT, "protocol": bound(args.original_protocol),
        "interrupted_analysis": bound(args.interrupted_analysis / "results.json"),
        "interrupted_analysis_manifest": bound(args.interrupted_analysis / "manifest.json"),
        "partial_data_exposed_before_followup_freeze": True, "cohorts_pooled": False,
        "same_base_instances": True, "independent_task_count_across_conditions": 12,
        "unseen_holdout_claim": False, "causal_runtime_version_comparison": False,
    }
    out = args.output.resolve()
    require(ROOT / "output" in out.parents, "Follow-up protocol must be under the research output directory")
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / "protocol.json", value)
    write_new(out / "protocol-receipt.json", {
        "protocol": file_binding(out / "protocol.json"), "created_utc": utc(),
        "separate_followup_condition": True, "original_design_comparison_passed": True,
        "original_protocol": bound(args.original_protocol), "model_generations": 0,
        "publication_before_generation_required": True,
    })
    (out / "declaration-source.py").write_bytes(Path(__file__).read_bytes())
    write_new(out / "manifest.json", manifest(out))
    print(json.dumps({"passed": True, "planned_slots": 96, "output": str(out)}))


if __name__ == "__main__":
    main()
