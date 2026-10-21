"""Stream file identity only; no generation, load, model imports, or network."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
files = {
    "server_executable": ("C:/Users/DELL/AppData/Local/Programs/Ollama/ollama.exe", "71d2002d3ae572d5fa8c1d368ce9d1b9a39c7187cf169e8b330c55410bf6c58e"),
    "runner_executable": ("C:/Users/DELL/AppData/Local/Programs/Ollama/lib/ollama/llama-server.exe", "bb3d2f86e3d8907c4febc3d7a299a8d13d95ddc281c5f81fe496e0d32b12dca3"),
    "model_blob": ("C:/Users/DELL/.ollama/models/blobs/sha256-85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9", "85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9"),
    "research_tag": ("C:/Users/DELL/.ollama/models/manifests-v2/ollama.com/library/conseqax-native-probe-20261020/ctx16k", "7f091551b95c30f4ff31a067faa273f56a3563b556cfd3d9f80d47c9b5d20ffc"),
}
receipt = {"schema": "native-restart-file-identity-v1", "started_utc": datetime.now(timezone.utc).isoformat(), "actual_generation_requests": 0, "model_load_requests": 0, "files": {}}
for name, (filename, expected) in files.items():
    path = Path(filename)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    receipt["files"][name] = {"path": str(path), "size": path.stat().st_size, "sha256": actual, "expected_sha256": expected, "passed": actual == expected}
receipt["passed"] = all(item["passed"] for item in receipt["files"].values())
receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
with (out / "binary-model-identity.json").open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps({"passed": receipt["passed"], "files": {name: item["sha256"] for name, item in receipt["files"].items()}}))
