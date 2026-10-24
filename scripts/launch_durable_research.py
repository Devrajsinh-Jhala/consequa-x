"""One-shot Windows research supervisor with explicit Windows job criteria.

This auxiliary launcher does not retry, resume, schedule, stop another process,
or perform inference itself. The default refuses any job membership. The
explicit ambient_non_killing policy permits only the observed non-killing
ambient job after WMI handoff; it promises no reboot/logoff survival. A separate
terminal receipt distinguishes launching from successful completion.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil


DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
STRICT_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
CONFIG_SCHEMA = "conseqax-durable-research-launch-v1"


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_binding(path):
    path = Path(path)
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return {"sha256": value.hexdigest(), "bytes": path.stat().st_size}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def is_process_in_job(pid=None):
    require(os.name == "nt", "This strict launch mechanism is Windows-only")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        member = wintypes.BOOL()
        if not kernel.IsProcessInJob(handle, None, ctypes.byref(member)):
            raise ctypes.WinError(ctypes.get_last_error())
        return bool(member.value)
    finally:
        if pid is not None:
            kernel.CloseHandle(handle)


def current_job_limits():
    """Read innermost current job limits; absence of a job is not an error."""
    require(os.name == "nt", "Job diagnostics are Windows-only")
    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                 wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    info, length = Basic(), wintypes.DWORD()
    ok = kernel.QueryInformationJobObject(None, 2, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(length))
    result = {"query_current_job_succeeded": bool(ok), "winerror": None if ok else ctypes.get_last_error(),
              "scope": "Innermost current job; does not identify every nested outer job"}
    if ok:
        flags = info.LimitFlags
        result.update({"limit_flags": flags, "breakaway_ok": bool(flags & 0x800),
                       "silent_breakaway_ok": bool(flags & 0x1000), "kill_on_job_close": bool(flags & 0x2000)})
        # Fixed generous buffer is diagnostic only, never used to control peers.
        class JobPids(ctypes.Structure):
            _fields_ = [("NumberOfAssignedProcesses", wintypes.DWORD),
                        ("NumberOfProcessIdsInList", wintypes.DWORD),
                        ("ProcessIdList", ctypes.c_size_t * 4096)]
        members = JobPids()
        listed = kernel.QueryInformationJobObject(None, 3, ctypes.byref(members),
                                                  ctypes.sizeof(members), ctypes.byref(length))
        result["process_id_list_complete"] = bool(listed)
        if listed:
            result["assigned_process_count"] = members.NumberOfAssignedProcesses
            result["process_ids"] = list(members.ProcessIdList[:members.NumberOfProcessIdsInList])
    return result


def process_identity(pid):
    process = psutil.Process(pid)
    return {"pid": process.pid, "create_time": process.create_time(),
            "executable": process.exe(), "command_line": process.cmdline(),
            "username": process.username(),
            "in_any_windows_job": is_process_in_job(pid)}


def validate_job_policy(identity, limits, policy):
    require(policy in {"no_any_job", "ambient_non_killing"}, "Unknown explicit job policy")
    if identity["in_any_windows_job"] is False:
        return
    require(policy == "ambient_non_killing" and limits.get("limit_flags") == 6144
            and limits.get("kill_on_job_close") is False and limits.get("silent_breakaway_ok") is True,
            "Refuse job membership that does not meet the explicitly declared job policy")


def sanitized_environment(overrides):
    result, removed = dict(os.environ), []
    for name in tuple(result):
        upper = name.upper()
        if (upper.endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN")) or upper in {
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                "GOOGLE_APPLICATION_CREDENTIALS", "AWS_SHARED_CREDENTIALS_FILE"}):
            removed.append(name)
            result.pop(name, None)
    for name, value in overrides.items():
        upper = name.upper()
        require(not any(word in upper for word in ("TOKEN", "KEY", "SECRET", "PASSWORD")),
                "Credential environment overrides are refused")
        require("=" not in name and name and isinstance(value, str), "Invalid environment override")
        result[name] = value
    return result, sorted(removed)


def supervise(config_path):
    config_path = Path(config_path).resolve()
    output = config_path.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))
    require(config["schema"] == CONFIG_SCHEMA, "Unknown launch schema")
    try:
        own, limits = process_identity(os.getpid()), current_job_limits()
        write_new(output / "supervisor-identity.json", {"observed_utc": utc(), **own,
                                                       "current_job_limits": limits})
        validate_job_policy(own, limits, config.get("job_policy", "no_any_job"))
        require(own["username"] == config["parent"]["username"],
                "Supervisor must run under the same user; no elevation or alternate credentials")
        require(file_binding(config["command"][0]) == config["command_executable_binding"],
                "Target executable changed after launch planning")
        require(file_binding(__file__) == config["launcher_source_binding"],
                "Launcher source changed after planning")
        for item in config["bound_inputs"]:
            require(file_binding(item["path"]) == item["binding"], "Bound input changed: " + item["path"])
        env, removed = sanitized_environment(config["environment_overrides"])
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        with (output / "target.stdout.log").open("xb") as stdout, \
                (output / "target.stderr.log").open("xb") as stderr:
            target = subprocess.Popen(config["command"], cwd=config["cwd"], env=env,
                                      stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                      startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
        identity = process_identity(target.pid)
        if identity["in_any_windows_job"]:
            membership = current_job_limits()
            require(config["job_policy"] == "ambient_non_killing"
                    and membership.get("limit_flags") == 6144 and membership.get("kill_on_job_close") is False
                    and target.pid in membership.get("process_ids", []),
                    "Target is not listed in the explicitly permitted non-killing ambient job")
            identity["listed_in_supervisor_non_killing_ambient_job"] = True
        else:
            identity["listed_in_supervisor_non_killing_ambient_job"] = False
        write_new(output / "launch-receipt.json", {
            "schema": CONFIG_SCHEMA, "status": "launched_not_complete", "launched_utc": utc(),
            "supervisor": own, "target": identity,
            "config_binding": file_binding(config_path), "removed_environment_names": removed,
            "job_policy": config["job_policy"], "supervisor_current_job_limits": limits,
            "no_job_breakaway_fallback": True,
            "scope": "Local launch only; no benchmark success, reboot/logoff survival, or absence of every ambient job claim"})
        code = target.wait()
        write_new(output / "terminal-receipt.json", {
            "schema": CONFIG_SCHEMA, "status": "target_exited", "finished_utc": utc(),
            "target": identity, "return_code": code,
            "stdout": file_binding(output / "target.stdout.log"),
            "stderr": file_binding(output / "target.stderr.log"),
            "scope": "Process exit only; scientific completeness requires the collector/auditor artifacts"})
        return code
    except Exception as exc:
        write_new(output / "launch-failure.json", {"failed_utc": utc(),
            "error_type": type(exc).__name__, "error": str(exc), "no_fallback": True})
        return 1


def wmi_handoff(config_path):
    """Escape only the specifically observed non-killing WMI startup job."""
    config_path = Path(config_path).resolve()
    output = config_path.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        require(config["schema"] == CONFIG_SCHEMA and config["mechanism"] == "wmi_two_stage",
                "Handoff requires an explicit two-stage WMI plan")
        own, limits = process_identity(os.getpid()), current_job_limits()
        write_new(output / "wmi-handoff-identity.json", {"observed_utc": utc(), **own,
                                                        "current_job_limits": limits})
        require(own["username"] == config["parent"]["username"], "WMI handoff must retain the same user")
        require(own["in_any_windows_job"] is True and limits.get("limit_flags") == 6144
                and limits.get("silent_breakaway_ok") is True and limits.get("kill_on_job_close") is False,
                "Refuse unrecognized WMI job; no target or alternate launch is permitted")
        require(file_binding(__file__) == config["launcher_source_binding"], "Handoff source changed")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        env, _ = sanitized_environment({})
        with (output / "supervisor.stdout.log").open("xb") as stdout, \
                (output / "supervisor.stderr.log").open("xb") as stderr:
            child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()),
                "_supervise", str(config_path)], cwd=config["cwd"], env=env,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                startupinfo=startup, creationflags=STRICT_FLAGS, close_fds=True)
        identity = process_identity(child.pid)
        write_new(output / "wmi-handoff-receipt.json", {"handed_off_utc": utc(), "supervisor": identity,
            "scope": "Strict bootstrap only; it must independently verify no job before any target launch"})
        if config.get("job_policy", "no_any_job") == "no_any_job":
            require(identity["in_any_windows_job"] is False, "Final detached bootstrap still belongs to a job")
        else:
            # Final bootstrap independently reads and validates its own limits before the target.
            require(config["job_policy"] == "ambient_non_killing", "Unknown handoff job policy")
        return 0
    except Exception as exc:
        write_new(output / "wmi-handoff-failure.json", {"failed_utc": utc(),
            "error_type": type(exc).__name__, "error": str(exc), "no_fallback": True})
        return 1


def launch(command, cwd, output, overrides, bound_inputs, mechanism="strict_flags", job_policy="no_any_job"):
    require(os.name == "nt", "This strict launch mechanism is Windows-only")
    require(command and Path(command[0]).is_absolute(), "An explicit absolute target executable is required")
    executable = Path(command[0]).resolve(strict=True)
    cwd = Path(cwd).resolve(strict=True)
    output = Path(output).resolve()
    require(cwd.is_dir(), "Command working directory must exist")
    require(mechanism in {"strict_flags", "wmi_service_parent", "wmi_two_stage"}, "Unknown explicit launch mechanism")
    require(job_policy in {"no_any_job", "ambient_non_killing"}, "Unknown explicit job policy")
    require(job_policy != "ambient_non_killing" or mechanism == "wmi_two_stage",
            "Ambient policy requires the explicitly verified two-stage WMI chain")
    require(not output.exists(), "Refuse existing one-shot launch output")
    command = [str(executable), *command[1:]]
    sanitized_environment(overrides)
    inputs = [{"path": str(Path(path).resolve(strict=True)), "binding": file_binding(path)}
              for path in bound_inputs]
    source = Path(__file__).resolve()
    output.mkdir(parents=True, exist_ok=False)
    with source.open("rb") as original, (output / "launcher-source.py").open("xb") as copied:
        copied.write(original.read())
        copied.flush()
        os.fsync(copied.fileno())
    write_new(output / "launch-config.json", {
        "schema": CONFIG_SCHEMA, "planned_utc": utc(), "command": command, "cwd": str(cwd),
        "command_executable_binding": file_binding(executable),
        "launcher_source": str(source), "launcher_source_binding": file_binding(source),
        "bound_inputs": inputs, "environment_overrides": overrides,
        "parent": process_identity(os.getpid()), "parent_current_job_limits": current_job_limits(),
        "mechanism": mechanism, "job_policy": job_policy, "creationflags": STRICT_FLAGS,
        "creationflag_names": ["DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_BREAKAWAY_FROM_JOB"],
        "scope": "One-shot launch; no retries, resumes, scheduling, auto-start or unrelated process control"})
    supervisor_mode = "_wmi_handoff" if mechanism == "wmi_two_stage" else "_supervise"
    supervisor_command = [sys.executable, "-B", str(source), supervisor_mode, str(output / "launch-config.json")]
    try:
        if mechanism in {"wmi_service_parent", "wmi_two_stage"}:
            request = output / "wmi-request.json"
            write_new(request, {"command_line": subprocess.list2cmdline(supervisor_command),
                "cwd": str(cwd), "creationflags": STRICT_FLAGS,
                "result": str(output / "wmi-create-result.json")})
            script = output / "create-wmi-supervisor.ps1"
            # Read an exact structured request rather than interpolating command text into PowerShell.
            script.write_text("param([string]$RequestPath)\n$ErrorActionPreference = 'Stop'\n"
                "$r = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json\n"
                "$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property "
                "@{ShowWindow=[uint16]0; CreateFlags=[uint32]$r.creationflags}\n"
                "$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
                "@{CommandLine=[string]$r.command_line; CurrentDirectory=[string]$r.cwd; "
                "ProcessStartupInformation=$startup}\n"
                "$json = @{ProcessId=$result.ProcessId; ReturnValue=$result.ReturnValue} | ConvertTo-Json\n"
                "[System.IO.File]::WriteAllText([string]$r.result, $json, "
                "[System.Text.UTF8Encoding]::new($false))\n"
                "if ($result.ReturnValue -ne 0) { exit 1 }\n", encoding="utf-8")
            powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-File", str(script),
                "-RequestPath", str(request)], stdin=subprocess.DEVNULL, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, check=False)
            (output / "wmi-call.stdout.log").write_bytes(result.stdout)
            (output / "wmi-call.stderr.log").write_bytes(result.stderr)
            require(result.returncode == 0, "One-shot WMI create failed; no fallback is permitted")
            created = json.loads((output / "wmi-create-result.json").read_text(encoding="utf-8"))
            require(created["ReturnValue"] == 0 and created["ProcessId"] > 0, "WMI process creation failed")
            child = None
        else:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            env, _ = sanitized_environment({})
            with (output / "supervisor.stdout.log").open("xb") as stdout, \
                    (output / "supervisor.stderr.log").open("xb") as stderr:
                child = subprocess.Popen(supervisor_command, cwd=str(cwd), env=env,
                    stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                    startupinfo=startup, creationflags=STRICT_FLAGS, close_fds=True)
    except OSError as exc:
        write_new(output / "parent-launch-failure.json", {"failed_utc": utc(),
            "error_type": type(exc).__name__, "error": str(exc),
            "winerror": getattr(exc, "winerror", None), "no_fallback": True})
        raise
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (output / "launch-receipt.json").exists():
            return json.loads((output / "launch-receipt.json").read_text(encoding="utf-8"))
        if (output / "launch-failure.json").exists():
            raise RuntimeError((output / "launch-failure.json").read_text(encoding="utf-8"))
        if (output / "wmi-handoff-failure.json").exists():
            raise RuntimeError((output / "wmi-handoff-failure.json").read_text(encoding="utf-8"))
        if child is not None and child.poll() is not None:
            raise RuntimeError("Detached supervisor exited before a launch receipt; inspect retained logs")
        time.sleep(.05)
    raise RuntimeError("No launch receipt within 15 seconds; do not duplicate the retained one-shot launch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    hidden = sub.add_parser("_supervise")
    hidden.add_argument("config", type=Path)
    handoff = sub.add_parser("_wmi_handoff")
    handoff.add_argument("config", type=Path)
    run = sub.add_parser("launch")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--cwd", type=Path, required=True)
    run.add_argument("--env", action="append", default=[])
    run.add_argument("--bind-input", action="append", default=[], type=Path)
    run.add_argument("--mechanism", choices=["strict_flags", "wmi_service_parent", "wmi_two_stage"], default="strict_flags")
    run.add_argument("--job-policy", choices=["no_any_job", "ambient_non_killing"], default="no_any_job")
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.mode == "_supervise":
        return supervise(args.config)
    if args.mode == "_wmi_handoff":
        return wmi_handoff(args.config)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    overrides = {}
    for item in args.env:
        name, separator, value = item.partition("=")
        require(separator and name not in overrides, "Expected a unique NAME=value environment override")
        overrides[name] = value
    receipt = launch(command, args.cwd, args.output, overrides, args.bind_input, args.mechanism, args.job_policy)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
