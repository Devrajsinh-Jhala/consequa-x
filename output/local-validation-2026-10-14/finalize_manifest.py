"""Seal the complete local validation snapshot once; no generation calls."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
destination = ROOT / "manifest.json"
if destination.exists():
    raise SystemExit("Snapshot already closed; review changes before replacing its manifest.")
protocol = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
audit = json.loads((ROOT / "audit.json").read_text(encoding="utf-8"))
rationale = json.loads((ROOT / "rationale-audit.json").read_text(encoding="utf-8"))
negative = json.loads((ROOT / "negative-checks.json").read_text(encoding="utf-8"))
assert audit["status"] == negative["status"] == "passed"
assert rationale["input_audit_sha256"] == sha256((ROOT / "audit.json").read_bytes()).hexdigest()
assert audit["audit_script_sha256"] == negative["audit_script_sha256"] == sha256((ROOT / "audit_validation.py").read_bytes()).hexdigest()
artifacts = []
for path in sorted(ROOT.rglob("*")):
    if path.is_file() and path != destination:
        assert path.resolve().is_relative_to(ROOT.resolve())
        artifacts.append({"path": path.relative_to(ROOT).as_posix(),
                          "bytes": path.stat().st_size,
                          "sha256": sha256(path.read_bytes()).hexdigest()})
manifest = {"schema_version": "consequa-local-validation-artifacts-v1",
            "completed": True, "status": "completed",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_revision": protocol["source_revision"],
            "checkpoint_wheel_sha256": protocol["wheel_sha256"],
            "generation_calls": audit["actual_calls"],
            "planned_episodes": 24, "completed_episodes": 24,
            "audit_assertions": audit["assertions"],
            "negative_cases": negative["negative_cases"],
            "artifacts": artifacts}
destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
print(json.dumps({"status": "completed", "artifacts": len(artifacts)}))
