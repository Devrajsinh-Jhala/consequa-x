"""Freeze evaluator-owned validation metadata using read-only local inspection."""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import zipfile

from consequa_x.adapters.ollama import OllamaPolicy, PROMPT_PROFILES
from consequa_x.benchmark.study import study_plan_from_json, template_wording_sha256
from consequa_x.models import to_dict
import consequa_x

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
SOURCE = "2c4adfeb2a364a8116d6edbccbbdac64b413fc9c"
WHEEL_SHA = "9250ad76c02075248aa6a12fd6e20b9be363bbf626093e13d893dfd1edd25d0e"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
SEED = 12000000
ORDER_SEED = 12000099

def now():
    return datetime.now(timezone.utc).isoformat()

def write(name, value):
    path = ROOT / name
    if path.exists():
        raise RuntimeError(f"Refusing to replace {name}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

if (ROOT / "protocol.json").exists() or any((ROOT / name).exists() for name in ("v1", "v2")):
    raise RuntimeError("Study already frozen or started")
manifest = WORKSPACE / "docs/studies/refund-family-candidates-v1.json"
manifest_bytes = manifest.read_bytes()
plan = study_plan_from_json(manifest_bytes.decode("utf-8"))
selected = plan.select("validation", order_seed=ORDER_SEED)
expected_cases = {
    "validation.standard-boundary", "validation.vip-boundary", "validation.expired",
    "validation.other-actor", "validation.delayed-readback", "validation.unsafe-retry",
}
assert {case.case_id for case in selected} == expected_cases
assert {case.template.family_id for case in selected} == {"refund-case-note"}
assert {case.template.template_id for case in selected} == {"refund-case-note-v1"}
assert importlib.metadata.version("consequa-x") == "0.1.0a2"
package = Path(consequa_x.__file__).resolve().parent
assert "alpha2-wheel-env" in str(package)
source_hashes = {
    path.relative_to(package).as_posix(): sha256(path.read_bytes()).hexdigest()
    for path in sorted(package.rglob("*"))
    if path.is_file() and (path.suffix in (".py", ".json") or path.name == "py.typed")
}
wheel = WORKSPACE / "dist/consequa_x-0.1.0a2-py3-none-any.whl"
assert sha256(wheel.read_bytes()).hexdigest() == WHEEL_SHA, "candidate wheel changed"
with zipfile.ZipFile(wheel) as archive:
    for relative, digest in source_hashes.items():
        assert sha256(archive.read("consequa_x/" + relative)).hexdigest() == digest, relative
shutil.copyfile(wheel, ROOT / "candidate-checkpoint.whl")
(ROOT / "study-plan.source.json").write_bytes(manifest_bytes)
schedule = []
for case in selected:
    for repetition in range(2):
        index = len(schedule)
        trial = SEED + index
        schedule.append({
            "index": index, "case_id": case.case_id, "repetition": repetition,
            "template_id": case.template.template_id, "family_id": case.template.family_id,
            "split": case.split, "world_seed": trial, "trial_seed": trial,
            "reserved_phase_keys": list(range(trial * 6, trial * 6 + 6)),
            "wording_sha256": template_wording_sha256(case.template),
            "scenario": to_dict(case.config),
        })
hardware = {"platform": platform.platform(), "python": sys.version,
            "executable": str(Path(sys.executable).resolve())}
for label, command in {
    "processor": "Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Depth 4",
    "operating_system": "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Depth 4",
}.items():
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, check=True)
    hardware[label] = json.loads(result.stdout)
write("hardware.json", hardware)
inspection = {"started_utc": now(), "generation_calls": 0}
policy = OllamaPolicy(MODEL, temperature=0, timeout=180, num_predict=512)
try:
    inspection["version"] = policy._request("/api/version")
    inspection["tags"] = policy._request("/api/tags")
    matching = [entry for entry in inspection["tags"].get("models", []) if entry.get("name") == MODEL]
    if len(matching) != 1:
        raise RuntimeError("The exact installed model tag was not found")
    inspection["selected_model"] = matching[0]
    inspection["show"] = policy._request("/api/show", {"model": MODEL, "verbose": False})
    inspection["adapter_inspection"] = policy.validate_local_model()
    inspection["running_models"] = policy._request("/api/ps")
    inspection["status"] = "passed"
except Exception as error:
    inspection.update(status="failed", error_type=type(error).__name__, error=str(error))
inspection["finished_utc"] = now()
write("runtime-before.json", inspection)
commands = []
for short, profile in (("v1", "refund-policy-v1"), ("v2", "refund-policy-v2")):
    commands.append({
        "block": short, "prompt_version": profile,
        "argv": [sys.executable, "-I", "-m", "consequa_x", "model-eval",
            "--provider", "ollama", "--model", MODEL,
            "--base-url", "http://127.0.0.1:11434", "--study", str(ROOT / "study-plan.source.json"),
            "--split", "validation", "--samples", "2", "--seed", str(SEED),
            "--order-seed", str(ORDER_SEED), "--max-calls", "36", "--max-attempts", "2",
            "--temperature", "0", "--num-predict", "512", "--timeout", "180",
            "--prompt-version", profile, "--output", str(ROOT / short)],
    })
protocol = {
    "study_id": "local-validation-2026-10-14", "schema_version": "consequa-local-validation-v1",
    "client_date": "2026-10-14", "client_timezone": "Asia/Calcutta", "frozen_utc": now(),
    "source_revision": SOURCE, "package_version": "0.1.0a2", "wheel_sha256": WHEEL_SHA,
    "checkpoint_status": "Frozen research checkpoint, not the published final release artifact",
    "known_unrelated_issue": "Candidate source has an interaction-export manifest-format issue under repair; model-eval adapter unchanged. No regeneration after that package repair.",
    "package_module_sha256": source_hashes,
    "installed_package_path": str(package),
    "manifest_sha256": sha256(manifest_bytes).hexdigest(),
    "manifest_source": "docs/studies/refund-family-candidates-v1.json",
    "proposal_source": "paper/protocol-next-validation.md",
    "proposal_sha256": sha256((WORKSPACE / "paper/protocol-next-validation.md").read_bytes()).hexdigest(),
    "prompt_sha256": {version: sha256(text.encode("utf-8")).hexdigest() for version, text in PROMPT_PROFILES.items()},
    "provider": "ollama", "base_url": "http://127.0.0.1:11434", "requested_model": MODEL,
    "model_digest": inspection.get("selected_model", {}).get("digest"),
    "local_model_preflight": inspection["status"],
    "settings": {"split": "validation", "samples_per_case_per_profile": 2, "max_attempts": 2,
        "max_calls_per_profile": 36, "max_calls_total": 72, "temperature": 0,
        "num_predict": 512, "timeout_seconds": 180, "seed": SEED, "order_seed": ORDER_SEED},
    "case_order": [case.case_id for case in selected], "schedule_per_profile": schedule,
    "planned_profiles": [command["prompt_version"] for command in commands],
    "planned_episodes": 24, "blocks": commands,
    "exposure": {"generated_family": "refund-case-note", "generated_split": "validation",
        "held_out_generation": False, "held_out_family_reserve": "refund-operations-ticket",
        "post_run_status": "Validation family exposed to this model/protocol; reserve held-out generation for a separate study",
        "limitations": "Candidate fault conditions overlap across splits; this is not held-out fault-composition validation."},
    "analysis": {"primary": "Complete case/profile/repetition receipt table; descriptive integration validation",
        "metrics": ["planned/completed/failed/unstarted episodes", "actual attempted calls/budget",
            "selection/retry/stop and committed effects", "state/origin/action-linked outcomes",
            "structured status claim/assessable coverage and contradiction denominators",
            "separate manual rationale-claim audit", "hashes/model identity/tokens/timing"],
        "null_denominator": "JSON null, not zero-percent error", "hypothesis_tests": False,
        "rationale_categories": ["affirmative_outcome", "negative_outcome", "explicit_uncertainty", "operation_or_eligibility_only", "ambiguous"],
        "rationale_alignment": ["supported", "contradicted", "unassessable", "not_an_outcome_claim"]},
    "pairing": "Same world/trial/phase keys across profile blocks, best-effort control, not proof of independence/determinism",
    "order_limit": "Fixed v1 then v2 blocks, server/order confounding; no randomized treatment estimate",
    "failure_policy": "Retain failures and unstarted receipts, no sample replacement, redraw, prompt changes or increased cap; stop on initial server/model preflight failure",
    "scope": "Existing local model and synthetic payments only; no downloads, paid calls, Actions or held-out inference",
}
write("protocol.json", protocol)
print(json.dumps({"preflight": inspection["status"], "model_digest": protocol["model_digest"],
                  "case_order": protocol["case_order"], "planned_episodes": 24,
                  "max_calls": 72, "wheel_sha256": WHEEL_SHA}))
if inspection["status"] != "passed":
    raise SystemExit(2)
