"""Preserve an original interaction export and inventory its derived envelope."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    original = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root/"protocol.json").read_text(encoding="utf-8"))
    if original.get("completed") is not True:
        raise ValueError("Expected completed refund interaction export")
    if not all(key in protocol for key in ("cases", "schedule", "source_revision")):
        raise ValueError("Expected frozen refund interaction protocol")
    preserved = root/"export-manifest.json"
    if not preserved.exists():
        preserved.write_bytes((root/"manifest.json").read_bytes())
    result = {"status": "completed", "completed": True,
              "source_revision": protocol["source_revision"],
              "original_export_manifest": "export-manifest.json",
              "scope": "derived manifest covering original export and preserved original envelope",
              "artifacts": [{"path": path.relative_to(root).as_posix(),
                             "bytes": path.stat().st_size,
                             "sha256": sha256(path.read_bytes()).hexdigest()}
                            for path in sorted(root.rglob("*"))
                            if path.is_file() and path != root/"manifest.json"]}
    (root/"manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n",
                                     encoding="utf-8", newline="\n")
    print(f"Inventoried {len(result['artifacts'])} artifacts; original manifest preserved")


if __name__ == "__main__":
    main()
