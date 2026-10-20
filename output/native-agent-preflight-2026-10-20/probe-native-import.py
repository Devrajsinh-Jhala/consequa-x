"""Import-only preflight; no tasks, models, provider calls or source changes."""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import traceback

OUT = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit")
EXPECTED = "96a3ef92329baf908ffe9dfe188cea34e8701d2a"


def git(*args):
    return subprocess.check_output(["git", "-C", str(SOURCE), *args], text=True).strip()


def source_hashes():
    paths = sorted((SOURCE / "src/tau2").rglob("*.py"))
    paths += [SOURCE / "pyproject.toml"]
    return {p.relative_to(SOURCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


if git("rev-parse", "HEAD") != EXPECTED or git("status", "--porcelain", "--untracked-files=no"):
    raise RuntimeError("Pinned upstream identity/cleanliness check failed")
before = source_hashes()
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["TAU2_DATA_DIR"] = str(SOURCE / "data")
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["DO_NOT_TRACK"] = "1"
for name in tuple(os.environ):
    upper = name.upper()
    if (upper.endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN"))
            or upper in {"GOOGLE_APPLICATION_CREDENTIALS", "AWS_SHARED_CREDENTIALS_FILE"}):
        os.environ.pop(name, None)

network_attempts = []
source_write_attempts = []
subprocess_attempts = []
imports_active = False


def blocked_socket(event, *args, **kwargs):
    network_attempts.append({"event": event})
    raise RuntimeError("Python socket networking, including loopback, is disabled during import-only preflight")


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        blocked_socket(event)
    if event == "subprocess.Popen" and imports_active:
        subprocess_attempts.append({"event": event})
        raise RuntimeError("Subprocesses are disabled during native imports")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path, mode, flags = args
        writing = ((mode and any(c in mode for c in "wax+"))
                   or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and Path(path).resolve().is_relative_to(SOURCE):
            source_write_attempts.append({"event": event, "path": str(path)})
            raise RuntimeError("Writing to pinned upstream source is disabled")


sys.addaudithook(audit)
socket.socket.connect = lambda *args, **kwargs: blocked_socket("socket.connect")
socket.socket.connect_ex = lambda *args, **kwargs: blocked_socket("socket.connect_ex")
socket.create_connection = lambda *args, **kwargs: blocked_socket("socket.create_connection")
socket.getaddrinfo = lambda *args, **kwargs: blocked_socket("socket.getaddrinfo")
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "src"))

result = {
    "scope": "normal native module imports only; no evaluation tasks requested or run, no models generated",
    "python": sys.version,
    "executable": sys.executable,
    "source": str(SOURCE),
    "upstream_commit": EXPECTED,
    "namespace_bypass": False,
    "network_policy": "Python socket connections/DNS blocked including loopback; subprocesses blocked during imports; not an OS-level native-code firewall",
    "dotenv_loading_disabled": True,
    "imported": [],
    "status": "incomplete",
}
exit_code = 0
try:
    imports_active = True
    for name in ["tau2", "tau2.cli", "tau2.runner.build", "tau2.runner.simulation",
                 "tau2.agent.llm_agent", "tau2.user.user_simulator",
                 "tau2.evaluator.evaluator", "tau2.evaluator.evaluator_env",
                 "tau2.evaluator.evaluator_communicate"]:
        importlib.import_module(name)
        result["imported"].append(name)
    result["status"] = "passed"
except Exception as error:
    exit_code = 1
    result["status"] = "failed"
    result["error_type"] = type(error).__name__
    result["error"] = str(error)
    result["traceback"] = traceback.format_exc()
    print(result["traceback"], file=sys.stderr)
finally:
    imports_active = False
    result["network_attempts"] = network_attempts
    result["source_write_attempts"] = source_write_attempts
    result["subprocess_attempts"] = subprocess_attempts
    result["source_hashes_before"] = before
    result["source_hashes_after"] = source_hashes()
    result["tracked_source_clean_after"] = not git("status", "--porcelain", "--untracked-files=no")
    result["source_unchanged"] = before == result["source_hashes_after"]
    if not result["source_unchanged"] or not result["tracked_source_clean_after"]:
        result["status"] = "failed"
        exit_code = 1
    if network_attempts or source_write_attempts or subprocess_attempts:
        result["status"] = "failed"
        exit_code = 1
    (OUT / "native-import-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["status", "imported", "network_attempts", "source_unchanged"]}))
sys.exit(exit_code)
