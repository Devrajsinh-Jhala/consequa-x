"""Notebook setup entry point: source verification, dependencies, GPU and models."""
import argparse
import json
import subprocess
import sys

from .bundle import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--models-dir", required=True)
    args = parser.parse_args()
    from pathlib import Path
    root = Path(args.study_dir).resolve()
    verify(root)
    wheel = next((root / "assets").glob("consequa_x-2.1.1-*.whl"))
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "psutil==7.0.0", "zstandard==0.23.0", str(wheel)], check=True)
    from . import runtime
    devices = runtime.gpu_inventory()
    runtime_dir = runtime.install_runtime(args.runtime_dir)
    server = runtime.start_server(runtime_dir, args.models_dir, devices)
    protocol = runtime.load(root / "study-design.json")
    runtime.install_models(root, args.models_dir, protocol)
    state = {"server": server, "condition": runtime.condition(devices), "gpu_devices": devices,
             "study_manifest": runtime.binding(root / "bundle-manifest.json")}
    target = runtime_dir / "setup.json"
    if target.exists():
        previous = runtime.load(target)
        runtime.require(previous == state, "Setup changed within the current session")
    else:
        runtime.save(target, state)
    print(json.dumps({"ready": True, "models": len(protocol["models"]),
                      "gpu": devices[0]["name"], "measured_episodes": 0,
                      "setup_receipt": str(target)}))


if __name__ == "__main__":
    main()
