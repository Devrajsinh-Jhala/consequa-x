"""Committed evidence snapshots must retain the bytes declared in their manifests."""

from hashlib import sha256
import gzip
import json
from pathlib import Path, PurePosixPath
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


def mapped_files(base, files):
    """Read relative SHA-256 inventories without leaving the evidence directory."""
    assert type(files) is dict and files, "File hash mapping is missing"
    for name, declaration in files.items():
        assert type(name) is str, "Artifact paths must be strings"
        relative = PurePosixPath(name)
        assert (name and relative.as_posix() == name and not relative.is_absolute()
                and ".." not in relative.parts and "\\" not in name and ":" not in name), (
            "Artifact path must be canonical and relative")
        artifact = base / name
        assert artifact.resolve().is_relative_to(base.resolve()) and not artifact.is_symlink(), (
            "Artifact path leaves its snapshot")
        expected = declaration.get("sha256") if type(declaration) is dict else declaration
        assert (type(expected) is str and len(expected) == 64
                and all(char in "0123456789abcdef" for char in expected)), "Invalid SHA-256"
        data = artifact.read_bytes()
        if type(declaration) is dict:
            assert type(declaration.get("bytes")) is int and declaration["bytes"] == len(data), (
                "Artifact byte count differs")
        yield name, data, expected


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
    elif manifest.get("schema") == "upstream-car-refund-comparison-v1":
        assert manifest.get("complete") is True, "CAR manifest is incomplete"
        planned = manifest.get("planned_trial_files")
        assert type(planned) is int and planned > 0, "CAR planned trial inventory is missing"
        assert type(manifest.get("trial_files")) is int and manifest["trial_files"] == planned, (
            "CAR trial file counts differ")
        files = manifest.get("files")
        assert type(files) is dict and files, "CAR file hash mapping is missing"
        assert all(type(name) is str for name in files), "CAR artifact paths must be strings"
        trial_paths = [name for name in files if name.startswith("trials/")]
        assert len(trial_paths) == planned, "CAR trial inventory count differs from manifest"
        assert all(name.endswith(".json.gz") for name in trial_paths), "CAR trial files must be gzip JSON"
        assert all(type(expected) is str for expected in files.values()), "Invalid CAR SHA-256"
        yield from mapped_files(base, files)
    elif type(manifest.get("files")) is dict:
        # Sealed analyses/figures use plain hashes; blinded review packs also bind byte lengths.
        yield from mapped_files(base, manifest["files"])
    else:
        pytest.fail(f"Unrecognized manifest format: {manifest_path.relative_to(ROOT).as_posix()}")


def verify_manifest(manifest):
    records = list(declared_files(manifest, json.loads(manifest.read_text(encoding="utf-8"))))
    assert records
    for label, data, expected in records:
        assert digest(data) == expected, label


@pytest.mark.parametrize("manifest", committed_manifests(),
                         ids=lambda path: path.parent.relative_to(SNAPSHOTS).as_posix())
def test_committed_snapshot_artifact_hashes(manifest):
    verify_manifest(manifest)


def car_manifest_fixture(directory):
    """A small integrity fixture, never a retained research observation."""
    directory.mkdir()
    payloads = {
        "protocol.json": b'{"synthetic_integrity_fixture":true}',
        "trials/00000-upstream_car.json.gz": gzip.compress(b'{"fixture":true,"bad":0}', mtime=0),
        "trials/00000-consequa_x.json.gz": gzip.compress(b'{"fixture":true,"bad":0}', mtime=0),
    }
    for name, data in payloads.items():
        path = directory / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    content = {"schema": "upstream-car-refund-comparison-v1", "complete": True,
               "trial_files": 2, "planned_trial_files": 2,
               "files": {name: digest(data) for name, data in payloads.items()}}
    path = directory / "manifest.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path, content


def test_car_manifest_verifies_gzip_receipts_and_rejects_changed_payload(tmp_path):
    manifest, _ = car_manifest_fixture(tmp_path / "snapshot")
    verify_manifest(manifest)
    receipt = manifest.parent / "trials/00000-upstream_car.json.gz"
    receipt.write_bytes(gzip.compress(b'{"fixture":true,"bad":1}', mtime=0))
    with pytest.raises(AssertionError, match="00000-upstream_car"):
        verify_manifest(manifest)


def test_car_manifest_rejects_omitted_trial_and_incomplete_status(tmp_path):
    manifest, content = car_manifest_fixture(tmp_path / "snapshot")
    omitted = content["files"].pop("trials/00000-consequa_x.json.gz")
    manifest.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(AssertionError, match="trial inventory count"):
        verify_manifest(manifest)
    content["files"]["trials/00000-consequa_x.json.gz"] = omitted
    content["complete"] = False
    manifest.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(AssertionError, match="incomplete"):
        verify_manifest(manifest)


def test_car_manifest_refuses_paths_outside_snapshot_before_reading_them(tmp_path):
    manifest, content = car_manifest_fixture(tmp_path / "snapshot")
    content["files"]["../outside.json"] = "0" * 64
    manifest.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(AssertionError, match="canonical and relative"):
        verify_manifest(manifest)


@pytest.mark.parametrize("record_metadata", [False, True])
def test_analysis_and_blinded_pack_hashes_detect_changed_evidence(tmp_path, record_metadata):
    evidence = tmp_path / "evidence.json"
    data = b'{"synthetic_integrity_fixture":true}'
    evidence.write_bytes(data)
    declared = {"sha256": digest(data), "bytes": len(data)} if record_metadata else digest(data)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": {evidence.name: declared}}), encoding="utf-8")
    verify_manifest(manifest)
    evidence.write_bytes(data.replace(b"true", b"null"))
    with pytest.raises(AssertionError, match="evidence.json"):
        verify_manifest(manifest)


def test_blinded_pack_manifest_rejects_incorrect_byte_length(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b"{}")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": {"evidence.json": {
        "sha256": digest(b"{}"), "bytes": 3}}}), encoding="utf-8")
    with pytest.raises(AssertionError, match="byte count"):
        verify_manifest(manifest)
