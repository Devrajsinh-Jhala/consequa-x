"""The standalone installed-release checker refuses misleading release evidence."""

from hashlib import sha256
import json
from pathlib import Path
import runpy
from zipfile import ZipFile

import pytest


@pytest.fixture
def checker():
    path = Path(__file__).resolve().parents[1] / "scripts/check_installed_release.py"
    return runpy.run_path(str(path))


def fixture_wheel(tmp_path, *, name="consequa-x", version="1.1.0"):
    path = tmp_path / "consequa_x-1.1.0-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr("consequa_x/__init__.py", b"reviewed package payload")
        archive.writestr("consequa_x-1.1.0.dist-info/METADATA",
                         f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n")
    return path


def test_reviewed_wheel_identity_binds_every_payload(checker, tmp_path):
    wheel = fixture_wheel(tmp_path)
    digest = sha256(wheel.read_bytes()).hexdigest()
    result = checker["checked_wheel"](wheel, digest, "1.1.0")
    assert result["sha256"] == digest
    assert result["bytes"] == wheel.stat().st_size
    assert result["payload_sha256"] == {
        "consequa_x/__init__.py": sha256(b"reviewed package payload").hexdigest()}


@pytest.mark.parametrize("name,version", [("different-project", "1.1.0"),
                                         ("consequa-x", "1.0.0")])
def test_wrong_distribution_or_version_refuses_even_with_matching_hash(
    checker, tmp_path, name, version,
):
    wheel = fixture_wheel(tmp_path, name=name, version=version)
    with pytest.raises(ValueError, match="distribution/version"):
        checker["checked_wheel"](wheel, sha256(wheel.read_bytes()).hexdigest(), "1.1.0")


@pytest.mark.parametrize("digest", ["0" * 64, "not-a-hash", "A" * 64])
def test_unreviewed_or_malformed_wheel_digest_refuses(checker, tmp_path, digest):
    wheel = fixture_wheel(tmp_path)
    with pytest.raises(ValueError, match="SHA-256|hash differs"):
        checker["checked_wheel"](wheel, digest, "1.1.0")


def test_duplicate_archive_entries_refuse(checker, tmp_path):
    wheel = fixture_wheel(tmp_path)
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(wheel, "a") as archive:
            archive.writestr("consequa_x/__init__.py", "replacement")
    with pytest.raises(ValueError, match="duplicate"):
        checker["checked_wheel"](wheel, sha256(wheel.read_bytes()).hexdigest(), "1.1.0")


def test_existing_receipt_refuses_before_importing_or_overwriting(checker, tmp_path):
    receipt = tmp_path / "receipt.json"
    original = json.dumps({"passed": True, "older_review": "preserve exactly"}).encode()
    receipt.write_bytes(original)
    with pytest.raises(ValueError, match="Keep prior installation receipts"):
        checker["main"](["--wheel", str(tmp_path / "missing.whl"),
                         "--expected-wheel-sha256", "0" * 64,
                         "--expected-version", "1.1.0", "--output", str(receipt)])
    assert receipt.read_bytes() == original


def test_standalone_fixture_checks_public_custom_adapters_and_strict_schema(checker):
    workflow = checker["check_trace_workflow"]()
    assert workflow["trace_roundtrips"] == 4
    assert workflow["observed_statuses"] == ["satisfied", "unknown", "violated"]
    assert checker["check_schema_refusals"]() == 16
