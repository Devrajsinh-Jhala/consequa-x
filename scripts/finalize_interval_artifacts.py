"""Retain the original export manifest, then hash all added derived artifacts.

Run before an audit, and again after copying audit receipts into the artifact.
This inventories bytes; it does not authenticate a source or rerun a study.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol = json.loads((root/"protocol.json").read_text(encoding="utf-8"))
    if protocol.get("study_kind") != "same_draw_interval_comparison_v1":
        raise ValueError("Expected a completed same-draw interval comparison directory")
    manifest_path = root/"manifest.json"
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    if original.get("status") != "completed":
        raise ValueError("Expected completed export manifest")
    preserved = root/"export-manifest.json"
    if not preserved.exists():
        preserved.write_bytes(manifest_path.read_bytes())
    manifest = {"status": "completed", "package_version": protocol["package_version"],
                "source_revision": protocol["source_revision"],
                "original_export_manifest": "export-manifest.json",
                "scope": "all export and derived files; only this manifest excludes itself",
                "artifacts": [{"path": p.relative_to(root).as_posix(),
                               "bytes": p.stat().st_size, "sha256": sha256(p.read_bytes()).hexdigest()}
                              for p in sorted(root.rglob("*")) if p.is_file() and p != manifest_path]}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8", newline="\n")
    print(f"Inventoried {len(manifest['artifacts'])} artifacts; original export manifest retained")


if __name__ == "__main__":
    main()
