"""Committed evidence snapshots must retain the bytes declared in their manifests."""

from hashlib import sha256
import json
from pathlib import Path

import pytest


SNAPSHOTS = Path(__file__).resolve().parents[1] / "output"


@pytest.mark.parametrize("manifest", sorted(SNAPSHOTS.glob("**/manifest.json")),
                         ids=lambda path: path.parent.name)
def test_committed_snapshot_artifact_hashes(manifest):
    records = json.loads(manifest.read_text(encoding="utf-8"))["artifacts"]
    assert records
    for record in records:
        artifact = manifest.parent / record["path"]
        assert sha256(artifact.read_bytes()).hexdigest() == record["sha256"], record["path"]
