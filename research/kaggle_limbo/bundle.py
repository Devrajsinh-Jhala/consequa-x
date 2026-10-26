"""Verify a small frozen research-source bundle before executing its contents."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def binding(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def verify(study_dir):
    root = Path(study_dir).resolve(strict=True)
    record = json.loads((root / "bundle-manifest.json").read_text(encoding="utf-8"))
    if record.get("schema") != "conseqax-kaggle-source-bundle-v1":
        raise ValueError("Unsupported source bundle")
    if record.get("engineering_only") is not False:
        raise ValueError("An engineering bundle cannot authorize measured inference")
    commit = record.get("source_commit", "")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Bundle lacks an immutable source revision")
    for name, expected in record["files"].items():
        path = root / name
        if (Path(name).is_absolute() or ".." in Path(name).parts
                or not path.resolve().is_relative_to(root) or path.is_symlink()
                or binding(path) != expected):
            raise ValueError("Source bundle file changed or escaped its root: " + name)
    return record


def safe_extract(archive, destination, expected_sha256):
    """No executable source is imported until the whole archive hash is checked."""
    if binding(archive)["sha256"] != expected_sha256:
        raise ValueError("Uploaded benchmark archive SHA256 differs from the notebook pin")
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Extract only into a new owned source directory")
    with zipfile.ZipFile(archive) as source:
        names = [item.filename for item in source.infolist()]
        if len(names) != len(set(names)) or len(names) > 2000:
            raise ValueError("Duplicate or excessive source-bundle entries")
        if sum(item.file_size for item in source.infolist()) > 256 * 1024**2:
            raise ValueError("Source bundle is too large")
        for item in source.infolist():
            name = item.filename
            mode = item.external_attr >> 16
            if ("\\" in name or Path(name).is_absolute() or ".." in Path(name).parts
                    or not name.startswith("conseqax-kaggle-study/")
                    or mode & 0o170000 == 0o120000):
                raise ValueError("Unsafe source bundle member")
        destination.mkdir(parents=True, exist_ok=False)
        source.extractall(destination)
    root = destination / "conseqax-kaggle-study"
    verify(root)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="phase", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--study-dir", required=True)
    args = parser.parse_args()
    record = verify(args.study_dir)
    print(json.dumps({"verified": True, "source_commit": record["source_commit"],
                      "bound_files": len(record["files"])}))


if __name__ == "__main__":
    main()
