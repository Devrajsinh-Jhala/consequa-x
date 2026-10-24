"""Audit a sealed one-shot LIMBO collection without model/network/SDK access."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.limbo_agent.audit import audit_collection, audit_development  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", required=True)
    parser.add_argument("--protocol")
    parser.add_argument("--protocol-commit")
    parser.add_argument("--collection")
    parser.add_argument("--development")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.development:
        result = audit_development(ROOT, args.native_root, args.development, args.output)
    else:
        if not all((args.protocol, args.protocol_commit, args.collection)):
            parser.error("Official audit requires protocol, protocol commit and collection")
        result = audit_collection(ROOT, args.native_root, args.protocol, args.protocol_commit,
                                  args.collection, args.output)
    print(json.dumps({"passed": result["passed"], "summary": result.get("summary")}))


if __name__ == "__main__":
    main()
