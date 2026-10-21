"""Explicit process-only research server; no model load/generation/download."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

OUT = Path(__file__).resolve().parent
EXE = Path("C:/Users/DELL/AppData/Local/Programs/Ollama/ollama.exe")
MODELS = Path("C:/Users/DELL/.ollama/models")
TAG = MODELS / "manifests-v2/ollama.com/library/conseqax-native-probe-20261020/ctx16k"
BASE = MODELS / "manifests-v2/ollama.com/library/qwen3/4b-instruct-2507-q4_K_M"
PORT = 11436


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


config = {"OLLAMA_HOST": "127.0.0.1:11436", "OLLAMA_MODELS": str(MODELS),
          "OLLAMA_NO_CLOUD": "1", "OLLAMA_NUM_PARALLEL": "2",
          "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0",
          "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_CONTEXT_LENGTH": "16384",
          "OLLAMA_KEEP_ALIVE": "-1", "OLLAMA_NOPRUNE": "1", "OLLAMA_DEBUG": "1"}
with socket.socket() as check:
    check.bind(("127.0.0.1", PORT))
env = dict(os.environ)
removed = []
for key in tuple(env):
    upper = key.upper()
    if (upper.endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN"))
            or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                         "GOOGLE_APPLICATION_CREDENTIALS", "AWS_SHARED_CREDENTIALS_FILE"}):
        env.pop(key, None)
        removed.append(key)
env.update(config)
record = {"started_utc": datetime.now(timezone.utc).isoformat(),
          "scope": "separate empty process-only two-slot q8_0 cache/FlashAttention research server;16384tokens per slot",
          "server_executable": str(EXE), "server_executable_sha256": sha(EXE),
          "command": [str(EXE), "serve"], "process_only_environment": config,
          "removed_environment_names": sorted(removed), "normal_service_modified": False,
          "original_tag_manifest_sha256_before": sha(BASE),
          "research_tag_manifest_sha256_before": sha(TAG),
          "model_generation_attempts": 0, "model_load_requests": 0, "model_downloads": 0,
          "cloud_disabled_requested": True}
stdout = (OUT / "isolated-q8-server.stdout.log").open("xb")
stderr = (OUT / "isolated-q8-server.stderr.log").open("xb")
try:
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    process = subprocess.Popen([str(EXE), "serve"], env=env, stdout=stdout, stderr=stderr,
                               startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    record["server_pid"] = process.pid
finally:
    stdout.close()
    stderr.close()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
record["poll_failures"] = []
for _ in range(30):
    try:
        with opener.open("http://127.0.0.1:11436/api/version", timeout=2) as response:
            record["version_response"] = json.load(response)
        break
    except Exception as error:
        record["poll_failures"].append(type(error).__name__)
        time.sleep(.5)
else:
    record["error"] = "Separate server did not become ready"
record["server_alive"] = process.poll() is None
record["original_tag_manifest_sha256_after"] = sha(BASE)
record["research_tag_manifest_sha256_after"] = sha(TAG)
record["finished_utc"] = datetime.now(timezone.utc).isoformat()
(OUT / "isolated-q8-server-launch.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
