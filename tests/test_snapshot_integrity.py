"""Committed evidence snapshots must retain the bytes declared in their manifests."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "output"


def committed_manifests():
    """Committed manifests only: in-progress study outputs are not snapshots yet."""
    try:
        listed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "output"],
            capture_output=True, check=True,
        ).stdout.decode("utf-8").split("\0")
    except (OSError, subprocess.CalledProcessError):
        return sorted(SNAPSHOTS.glob("**/manifest.json"))
    return sorted(ROOT / name for name in listed if name.endswith("/manifest.json"))


def digest(data):
    return sha256(data).hexdigest()


def declared_files(manifest_path, manifest):
    """Yield (label, actual bytes, expected sha256) for every recorded artifact."""
    base = manifest_path.parent
    if "artifacts" in manifest:
        for record in manifest["artifacts"]:
            yield record["path"], (base / record["path"]).read_bytes(), record["sha256"]
    elif "cases" in manifest:
        for record in manifest["cases"]:
            yield record["file"], (base / record["file"]).read_bytes(), record["sha256"]
    elif manifest.get("format") == "render-site-export-v1":
        archive = manifest["archive"]
        blob = (base / archive["path"]).read_bytes()
        assert len(blob) == archive["bytes"], archive["path"]
        yield archive["path"], blob, archive["sha256"]
        with zipfile.ZipFile(base / archive["path"]) as members:
            assert sorted(members.namelist()) == [record["path"] for record in manifest["files"]]
            for record in manifest["files"]:
                yield record["path"], members.read(record["path"]), record["sha256"]
    else:
        pytest.fail(f"Unrecognized manifest format: {manifest_path.relative_to(ROOT).as_posix()}")


@pytest.mark.parametrize("manifest", committed_manifests(),
                         ids=lambda path: path.parent.relative_to(SNAPSHOTS).as_posix())
def test_committed_snapshot_artifact_hashes(manifest):
    records = list(declared_files(manifest, json.loads(manifest.read_text(encoding="utf-8"))))
    assert records
    for label, data, expected in records:
        assert digest(data) == expected, label
