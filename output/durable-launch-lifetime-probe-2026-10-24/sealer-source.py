"""Validate and seal a closed delayed-sentinel probe with its raw observations."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from launch_durable_research import file_binding, require, write_new, utc


def read(directory, relative):
    return json.loads((directory / relative).read_text(encoding="utf-8"))


def seal(directory, tool_result):
    directory = Path(directory).resolve(strict=True)
    require(not (directory / "manifest.json").exists(), "Refuse already sealed probe")
    config = read(directory, "launch-config.json")
    launched = read(directory, "launch-receipt.json")
    terminal = read(directory, "terminal-receipt.json")
    started = read(directory, "sentinel/started.json")
    ended = read(directory, "sentinel/delayed-sentinel.json")
    handoff = read(directory, "wmi-handoff-identity.json")
    supervisor = read(directory, "supervisor-identity.json")
    tool = json.loads(Path(tool_result).read_text(encoding="utf-8"))
    require(terminal["return_code"] == 0 and launched["status"] == "launched_not_complete",
            "Target must have a successful closed terminal receipt")
    require(config["job_policy"] == "ambient_non_killing" and config["mechanism"] == "wmi_two_stage",
            "Expected explicitly amended launch criterion and verified chain")
    require(config["parent_current_job_limits"]["kill_on_job_close"] is True,
            "Tool parent must provide actual kill-on-close job evidence")
    require(ended["elapsed_monotonic_s"] >= 15, "Delayed sentinel did not complete its full delay")
    identity_keys = ("pid", "create_time", "executable", "command_line", "username")
    for key in identity_keys:
        require(started["identity"][key] == ended["identity"][key] == launched["target"][key]
                == terminal["target"][key], "Probe target identity changed: " + key)
    user = config["parent"]["username"]
    require(all(item["username"] == user for item in [handoff, supervisor, started["identity"], ended["identity"]]),
            "Launch chain changed user")
    for item in (handoff, supervisor, started, ended):
        limits = item["current_job_limits"]
        require(limits["limit_flags"] == 6144 and limits["kill_on_job_close"] is False,
                "Observed launch/target job must match the known non-killing ambient job")
    require(started["model_calls"] == ended["model_calls"] == 0
            and started["network_calls"] == ended["network_calls"] == 0, "Sentinel performed unexpected work")
    require(tool["exit_code"] == 0 and tool["source_kind"] == "Codex exec_command tool result"
            and 0 < tool["wall_time_seconds"] < 15, "Actual launching tool result is required")
    # Parent process creation occurred after the tool started. Adding the entire
    # tool duration therefore gives a conservative upper bound, not an invented
    # exact timestamp for tool return (the tool result contains no timestamp).
    upper_epoch = config["parent"]["create_time"] + tool["wall_time_seconds"]
    finished = datetime.fromisoformat(ended["finished_utc"]).timestamp()
    require(upper_epoch < finished, "Cannot establish tool return before delayed completion")
    require(file_binding(directory / "launcher-source.py") == config["launcher_source_binding"],
            "Exact launch source copy differs from the launch plan")
    probe_source = Path(started["source"]["path"])
    require(file_binding(probe_source) == {key: started["source"][key] for key in ("sha256", "bytes")},
            "Sentinel source changed before its source copy could be sealed")
    (directory / "sentinel-source.py").write_bytes(probe_source.read_bytes())
    (directory / "sealer-source.py").write_bytes(Path(__file__).read_bytes())
    if Path(tool_result).resolve() != (directory / "tool-return-observation.json").resolve():
        (directory / "tool-return-observation.json").write_bytes(Path(tool_result).read_bytes())
    raw = {path.relative_to(directory).as_posix(): file_binding(path)
           for path in sorted(directory.rglob("*")) if path.is_file()}
    proof = {"schema": "conseqax-durable-lifetime-proof-v1", "passed": True,
        "sealed_utc": utc(), "target_exit_code": 0, "sentinel_elapsed_s": ended["elapsed_monotonic_s"],
        "self_observed_job_flags": [started["current_job_limits"]["limit_flags"],
                                    ended["current_job_limits"]["limit_flags"]],
        "self_observed_kill_on_job_close": [False, False], "same_user_throughout": True,
        "job_policy": "ambient_non_killing", "launch_mechanism": "wmi_two_stage",
        "tool_returned_before_delayed_completion": True,
        "tool_return_upper_bound_utc": datetime.fromtimestamp(upper_epoch, timezone.utc).isoformat(),
        "tool_return_bound_definition": "Parent creation occurs after tool start; parent birth + full observed tool duration is an upper bound, not an exact return timestamp",
        "delayed_completion_utc": ended["finished_utc"], "raw_binding_references": raw,
        "model_calls": 0, "network_calls": 0,
        "scope": "Outlived the launching tool invocation after escaping its kill-on-close job; ambient non-killing job retained. No reboot, logoff, power-loss, or arbitrary termination survival promise."}
    write_new(directory / "lifetime-proof.json", proof)
    manifest = {path.relative_to(directory).as_posix(): file_binding(path)
                for path in sorted(directory.rglob("*")) if path.is_file()}
    write_new(directory / "manifest.json", manifest)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--tool-result", type=Path, required=True)
    args = parser.parse_args()
    result = seal(args.probe, args.tool_result)
    print(json.dumps({"passed": result["passed"], "proof": str(args.probe / "lifetime-proof.json"),
                      "sentinel_elapsed_s": result["sentinel_elapsed_s"]}))


if __name__ == "__main__":
    main()
