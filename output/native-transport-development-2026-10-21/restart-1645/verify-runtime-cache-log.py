"""Bind the research server's append-only log prefix; no server request."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
source = out / "isolated-q8-server.stderr.log"
prefix = source.read_bytes()
lines = prefix.decode("utf-8", errors="replace").splitlines()
observations = [{"line": number, "text": line} for number, line in enumerate(lines, 1)
                if any(needle in line for needle in ("starting llama-server", "n_seq_max", "n_ctx ", "n_ctx_seq", "flash_attn ", "CPU KV buffer size", "K (q8_0)", "n_ctx_slot"))]
text = "\n".join(item["text"] for item in observations)
checks = {
    "parallel_2_actual": "-np 2" in text and "n_seq_max             = 2" in text,
    "total_context_32768_actual": "-c 32768" in text and "n_ctx                 = 32768" in text,
    "per_slot_context_16384_actual": "n_ctx_seq             = 16384" in text and "n_ctx_slot = 16384" in text,
    "q8_0_keys_and_values_actual": "--cache-type-k q8_0 --cache-type-v q8_0" in text and "K (q8_0): 1224.00 MiB, V (q8_0): 1224.00 MiB" in text,
    "flash_attention_actual_enabled": "--flash-attn on" in text and "flash_attn            = enabled" in text,
    "KV_total_2448MiB_actual": "CPU KV buffer size =  2448.00 MiB" in text,
}
record = {"schema": "native-parallel2-cache-log-prefix-check-v1", "created_utc": datetime.now(timezone.utc).isoformat(), "source_log": str(source), "source_prefix_bytes": len(prefix), "source_prefix_sha256": hashlib.sha256(prefix).hexdigest(), "scope": "Fresh restart-1645 research server log prefix binding at observation time; no normal user service evidence used.", "actual_generation_requests_by_this_check": 0, "observations": observations, "checks": checks, "passed": all(checks.values())}
with (out / "runtime-parallel2-q8-cache-check.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
print(json.dumps({"passed": record["passed"], "checks": checks}))
raise SystemExit(0 if record["passed"] else 1)
