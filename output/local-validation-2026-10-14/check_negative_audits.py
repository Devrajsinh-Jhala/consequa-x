"""Reject targeted corrupted smoke copies without modifying retained evidence."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from consequa_x.explanation import explain
from consequa_x.models import Trace

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--report", type=Path, help="Optional fresh receipt; defaults to read-only.")
args = parser.parse_args()

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write(path, value):
    path.write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")

def reseal(folder):
    path = folder / "manifest.json"
    manifest = read(path)
    for record in manifest["artifacts"]:
        record["sha256"] = sha256((folder/record["path"]).read_bytes()).hexdigest()
    write(path, manifest)

probes = [
    ("missing_completed_receipt", "complete episode inventory"),
    ("duplicate_trial_index", "trial index/seed"),
    ("incorrect_aggregate", "all independent assessment metrics"),
    ("phase_seed_corruption", "phase key"),
    ("verification_corruption", "fresh installed verifier"),
    ("incomplete_manifest", "complete manifest inventory"),
    ("checkpoint_wheel_corruption", "candidate wheel retained"),
]
receipts = []
for name, expected_error in probes:
    with tempfile.TemporaryDirectory(prefix="validation-audit-", dir=WORKSPACE / "tmp") as temporary:
        target = Path(temporary).resolve() / "evidence"
        assert target.is_relative_to((WORKSPACE / "tmp").resolve())
        shutil.copytree(ROOT, target)
        folder = target / "v1"
        if name in ("missing_completed_receipt", "duplicate_trial_index", "incorrect_aggregate"):
            path = folder / "results.json"
            data = read(path)
            if name == "missing_completed_receipt":
                data["samples"].pop()
            elif name == "duplicate_trial_index":
                data["samples"][1]["index"] = 0
            else:
                data["summary"]["assessment_metrics"]["contradicted_claims"] = 5
            write(path, data)
            reseal(folder)
        elif name in ("phase_seed_corruption", "verification_corruption"):
            path = folder / "traces/episode_0000.json"
            data = read(path)
            if name == "phase_seed_corruption":
                event = next(event for event in data["events"] if event["type"] == "agent_decision")
                event["data"]["policy_reply"]["metadata"]["seed"] += 1
            else:
                data["verifications"][-1]["status"] = "violated"
            write(path, data)
            if name == "phase_seed_corruption":
                write(folder / "explanations/episode_0000.json", explain(Trace.from_dict(data)).to_dict())
            reseal(folder)
        elif name == "incomplete_manifest":
            path = folder / "manifest.json"
            data = read(path)
            data["artifacts"].pop()
            write(path, data)
        else:
            path = target / "candidate-checkpoint.whl"
            path.write_bytes(path.read_bytes()+b"smoke corruption")
        completed = subprocess.run([sys.executable, "-I", str(ROOT / "audit_validation.py"),
                                    "--root", str(target)], capture_output=True, text=True, check=False)
        assert completed.returncode != 0 and expected_error in completed.stderr, (name, completed.stderr)
        receipts.append({"probe": name, "status": "rejected", "expected_error": expected_error,
                         "return_code": completed.returncode,
                         "rehash_before_semantic_check": name not in ("incomplete_manifest", "checkpoint_wheel_corruption")})
report = {"status": "passed", "generation_calls": 0, "negative_cases": len(receipts),
          "audit_script_sha256": sha256((ROOT / "audit_validation.py").read_bytes()).hexdigest(),
          "scope": "Targeted corrupted temporary smoke copies, not an exhaustive security proof. Frozen evidence unchanged.",
          "cases": receipts}
if args.report is not None:
    target_report = args.report.resolve()
    if (ROOT / "manifest.json").exists() and target_report.is_relative_to(ROOT):
        raise ValueError("closed evidence is read-only; choose an external report path")
    write(target_report, report)
print(json.dumps({"status": "passed", "negative_cases": len(receipts)}))
