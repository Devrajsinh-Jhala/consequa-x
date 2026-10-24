"""One harmless 15-second delayed sentinel; no network, model, or process control."""
import argparse
import os
from pathlib import Path
import time

from launch_durable_research import current_job_limits, file_binding, process_identity, validate_job_policy, utc, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    own, limits = process_identity(os.getpid()), current_job_limits()
    validate_job_policy(own, limits, "ambient_non_killing")
    started = time.monotonic()
    write_new(args.output / "started.json", {"started_utc": utc(), "identity": own,
        "current_job_limits": limits, "planned_delay_s": 15, "model_calls": 0, "network_calls": 0,
        "source": {"path": str(Path(__file__).resolve()), **file_binding(__file__)}})
    time.sleep(15)
    final_identity, final_limits = process_identity(os.getpid()), current_job_limits()
    validate_job_policy(final_identity, final_limits, "ambient_non_killing")
    write_new(args.output / "delayed-sentinel.json", {"finished_utc": utc(), "identity": final_identity,
        "current_job_limits": final_limits, "elapsed_monotonic_s": time.monotonic() - started,
        "model_calls": 0, "network_calls": 0,
        "scope": "Actual delayed completion after launcher/tool return; no reboot/logoff survival claim"})


if __name__ == "__main__":
    main()
