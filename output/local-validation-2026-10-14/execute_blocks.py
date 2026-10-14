"""Run the frozen two-block validation without any redraw or prompt changes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

from consequa_x.adapters.ollama import OllamaPolicy

ROOT = Path(__file__).resolve().parent
def now():
    return datetime.now(timezone.utc).isoformat()
def write(value):
    (ROOT / "execution.json").write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

if (ROOT / "execution.json").exists() or any((ROOT / name).exists() for name in ("v1", "v2")):
    raise RuntimeError("Refusing to rerun started study")
protocol_bytes = (ROOT / "protocol.json").read_bytes()
protocol = json.loads(protocol_bytes)
assert protocol["local_model_preflight"] == "passed"
assert protocol["wheel_sha256"] == "9250ad76c02075248aa6a12fd6e20b9be363bbf626093e13d893dfd1edd25d0e"
assert Path(protocol["blocks"][0]["argv"][0]).resolve() == Path(sys.executable).resolve()
record = {"started_utc": now(), "client_date": "2026-10-14", "client_timezone": "Asia/Calcutta",
          "protocol_sha256": sha256(protocol_bytes).hexdigest(), "blocks": [], "status": "running"}
write(record)
start = time.monotonic()
for item in protocol["blocks"]:
    assert (ROOT / "protocol.json").read_bytes() == protocol_bytes
    assert sha256((ROOT / "study-plan.source.json").read_bytes()).hexdigest() == protocol["manifest_sha256"]
    entry = {"block": item["block"], "prompt_version": item["prompt_version"],
             "argv": item["argv"], "started_utc": now(), "status": "running"}
    record["blocks"].append(entry)
    write(record)
    print(f"Starting {item['block']} with 12 planned episodes and 36-call cap", flush=True)
    block_start = time.monotonic()
    with (ROOT / f"{item['block']}-stdout.log").open("w", encoding="utf-8") as stdout, (ROOT / f"{item['block']}-stderr.log").open("w", encoding="utf-8") as stderr:
        result = subprocess.run(item["argv"], cwd=ROOT.parent.parent, stdout=stdout, stderr=stderr, check=False)
    entry.update(status="finished", exit_code=result.returncode, finished_utc=now(), elapsed_seconds=time.monotonic()-block_start)
    results_path = ROOT / item["block"] / "results.json"
    if results_path.exists():
        data = json.loads(results_path.read_text(encoding="utf-8"))
        entry["summary"] = data["summary"]
        print(json.dumps({"block": item["block"], "exit_code": result.returncode, "summary": data["summary"]}), flush=True)
    else:
        entry["status"] = "preflight_or_export_failure"
        record["status"] = "stopped_without_redraw"
        record["remaining_blocks_not_started"] = [other["block"] for other in protocol["blocks"][len(record["blocks"]):]]
        write(record)
        print(f"Stopped: {item['block']} produced no results; remaining blocks not started", flush=True)
        break
    write(record)
else:
    record["status"] = "finished"
record.update(finished_utc=now(), elapsed_seconds=time.monotonic()-start)
write(record)
policy = OllamaPolicy(protocol["requested_model"], temperature=0, timeout=180, num_predict=512)
runtime = {"inspected_utc": now(), "generation_calls": 0}
try:
    runtime.update(version=policy._request("/api/version"), tags=policy._request("/api/tags"), running_models=policy._request("/api/ps"))
except Exception as error:
    runtime.update(error_type=type(error).__name__, error=str(error))
(ROOT / "runtime-after.json").write_text(json.dumps(runtime, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"study_status": record["status"], "elapsed_seconds": record["elapsed_seconds"]}), flush=True)
if record["status"] != "finished":
    raise SystemExit(2)
