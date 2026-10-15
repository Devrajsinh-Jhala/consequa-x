"""Installed CLI creates portable evidence, then refuses to replace it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


def run(*args, code=0):
    result = subprocess.run([sys.executable, "-I", "-m", "consequa_x", *map(str, args)],
                            capture_output=True, text=True)
    assert result.returncode == code, (result.returncode, result.stderr)


def inventory(root):
    return {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    demo = args.output / "demo"
    run("demo", "--output", demo)
    before = inventory(demo)
    run("demo", "--output", demo, code=2)
    assert before == inventory(demo)
    trace = demo / "traces/episode_01.json"
    explanation = args.output / "explanation.json"
    run("explain", trace, "--output", explanation)
    saved = explanation.read_bytes()
    run("explain", trace, "--output", explanation, code=2)
    run("explain", trace, "--output", trace, code=2)
    assert explanation.read_bytes() == saved and inventory(demo) == before
    study = args.output / "parallel-engineering-smoke"
    run("calibrate-interactions", "--source-revision", args.source_revision,
        "--repeats", 1, "--pairs", 2, "--samples", 1, "--endpoint-samples", 2,
        "--seed", 36_000_000, "--workers", 2, "--output", study)
    summary = json.loads((study / "summary.json").read_text(encoding="utf-8"))
    protocol = json.loads((study / "protocol.json").read_text(encoding="utf-8"))
    assert summary["planned_trials"] == 16 and summary["planned_branches"] == 320
    assert protocol["execution"]["workers"] == 2
    record = {"passed": True, "source_revision": args.source_revision,
        "demo_traces": 12, "demo_file_count": len(before), "existing_evidence_preserved": True,
        "explanation_cannot_overwrite_source": True, "installed_parallel_workers": 2,
        "parallel_trials": 16, "parallel_planned_branches": 320,
        "scope": "Engineering smoke only; excluded from retained study.", "model_calls": 0}
    (args.output / "checks.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
