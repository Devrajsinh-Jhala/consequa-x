"""Check installed stable bytes and real offline workflows, without dependencies."""
import argparse
from hashlib import sha256
from importlib import metadata, resources
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import platform
import sys

import consequa_x
from consequa_x import Trace, VerificationStatus, explain
from consequa_x.benchmark.runner import demo_scenarios, run_scenario
from consequa_x.schema import get_trace_schema, validate_trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--expected-example-sha", required=True)
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Keep prior installation receipts")
    package = Path(consequa_x.__file__).resolve()
    assert package.is_relative_to(args.installed_root.resolve()), package
    assert consequa_x.__version__ == metadata.version("consequa-x") == "1.0.0"
    required = metadata.metadata("consequa-x").get_all("Requires-Dist", [])
    assert all(item.rpartition(';')[2].strip() == 'extra == "dev"' for item in required), required
    assert metadata.metadata("consequa-x")["License-Expression"] == "MIT"
    assert get_trace_schema() == json.loads(resources.files("consequa_x").joinpath(
        "schemas/trace-v0.1.json").read_text(encoding="utf-8"))
    payloads = json.loads(args.checkpoint.read_text(encoding="utf-8"))["payload_sha256"]
    for name, digest in payloads.items():
        assert sha256((package.parent.parent / name).read_bytes()).hexdigest() == digest, name
    scenarios = demo_scenarios()
    assert len(scenarios) == 12
    statuses = set()
    for scenario in scenarios:
        trace = run_scenario(scenario, seed=0).trace
        assert Trace.from_json(trace.to_json()) == validate_trace(trace.to_json()) == trace
        explanation = explain(trace)
        statuses.add(explanation.consequence.status.value)
        assert explanation.graph.nodes
    assert statuses == {"satisfied", "violated", "unknown"}, statuses
    assert sha256(args.example.read_bytes()).hexdigest() == args.expected_example_sha
    spec = spec_from_file_location("artifact_delivery", args.example.resolve())
    example = module_from_spec(spec)
    spec.loader.exec_module(example)
    trace = Trace.from_json(example.build_trace().to_json())
    neutral = explain(trace)
    assert neutral.assessment_alignment == "unassessable"
    qualified = explain(trace, target_matcher=example.ArtifactTargetMatcher())
    assert qualified.consequence.status is VerificationStatus.SATISFIED
    assert qualified.assessment_alignment == "contradicted"
    unknown = example.build_trace(example.captured_readback(available=False))
    assert explain(unknown, target_matcher=example.ArtifactTargetMatcher()).consequence.status \
        is VerificationStatus.UNKNOWN
    wrong = example.build_trace(example.captured_readback(b"different captured bytes"))
    assert explain(wrong, target_matcher=example.ArtifactTargetMatcher()).consequence.status \
        is VerificationStatus.VIOLATED
    report = {"passed": True, "python": platform.python_version(),
        "platform": platform.platform(), "executable": sys.executable,
        "module_file": str(package), "version": metadata.version("consequa-x"),
        "runtime_dependencies": 0, "runtime_files_matching_study_checkpoint": len(payloads),
        "trace_roundtrips": len(scenarios), "observed_statuses": sorted(statuses),
        "artifact_example_checks": ["neutral_without_matcher", "contradicted_failure",
            "unavailable_readback_unknown", "captured_wrong_bytes_violated"],
        "provider_calls": 0, "example_sha256": sha256(args.example.read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
