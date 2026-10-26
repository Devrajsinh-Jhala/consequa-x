"""Prepare the isolated multi-model runtime; never execute a benchmark episode."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.expanded_limbo.runtime import acquire_model, load_model, start_server, unload_model  # noqa:E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="phase", required=True)
    start = sub.add_parser("start")
    start.add_argument("--private-runtime", required=True)
    start.add_argument("--models", required=True)
    start.add_argument("--output", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--server", required=True)
    acquire.add_argument("--tag", required=True)
    acquire.add_argument("--output", required=True)
    acquire.add_argument("--allow-download", action="store_true")
    load = sub.add_parser("load")
    load.add_argument("--server", required=True)
    load.add_argument("--acquisition", required=True)
    load.add_argument("--alias", required=True)
    load.add_argument("--output", required=True)
    unload = sub.add_parser("unload")
    unload.add_argument("--server", required=True)
    unload.add_argument("--binding", required=True)
    unload.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.phase == "start":
        result = start_server(args.private_runtime, args.models, args.output)
    elif args.phase == "acquire":
        result = acquire_model(args.server, args.tag, args.output, allow_download=args.allow_download)
    elif args.phase == "load":
        result = load_model(args.server, args.acquisition, args.alias, args.output)
    else:
        unload_model(args.server, args.binding, args.output)
        result = {"unloaded": True}
    print(json.dumps({"phase": args.phase, "generation_attempts": 0,
                      "status": "setup_only", "output": args.output,
                      "model": result.get("tag", result.get("model"))}))


if __name__ == "__main__":
    main()
