"""Stable upload gates reject corrupt receipts before accessing credentials."""

from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest


def subject():
    return runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts/publish_release.py"))


LAUNCH_GATES = ("report_security", "report_browser_qa", "linux_wheel_install",
                "public_docs_support")


def receipt(tmp_path, *, version="1.0.0", launch_checks=False):
    module = subject()
    items = []
    for name in (f"consequa_x-{version}-py3-none-any.whl", f"consequa_x-{version}.tar.gz"):
        path = tmp_path/name
        path.write_bytes(b"reviewed stable fixture")
        items.append({"path": name, "bytes": path.stat().st_size,
                      "sha256": sha256(path.read_bytes()).hexdigest()})
    record = {"distribution": "consequa-x", "version": version, "source_revision": "a"*40,
              "artifacts": items, "local_checks": {key: True for key in module["REQUIRED_CHECKS"]}}
    if launch_checks:
        record["local_checks"].update({key: True for key in LAUNCH_GATES})
    path = tmp_path/"checks.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return module, path, record


def test_historical_1_0_receipt_still_validates_without_later_launch_checks(tmp_path):
    module, path, record = receipt(tmp_path)
    assert not set(LAUNCH_GATES) & record["local_checks"].keys()
    checked, files = module["checked_files"](path)
    assert checked == record
    assert {item.name for item in files} == {
        "consequa_x-1.0.0-py3-none-any.whl", "consequa_x-1.0.0.tar.gz"}


@pytest.mark.parametrize("version", ["1.1.0", "1.1.1", "1.10.0", "2.0.0"])
def test_1_1_and_later_receipts_accept_all_four_explicit_launch_checks(tmp_path, version):
    module, path, record = receipt(tmp_path, version=version, launch_checks=True)
    assert module["LAUNCH_CHECKS"] == frozenset(LAUNCH_GATES)
    checked, files = module["checked_files"](path)
    assert checked == record
    assert len(files) == 2
    assert all(record["local_checks"][key] is True for key in LAUNCH_GATES)


@pytest.mark.parametrize("check", LAUNCH_GATES)
@pytest.mark.parametrize("mutation", ["missing", "false", "integer", "string"])
def test_each_1_1_launch_gate_refuses_missing_false_and_truthy_before_any_external_access(
    tmp_path, monkeypatch, check, mutation,
):
    module, path, record = receipt(tmp_path, version="1.1.0", launch_checks=True)
    if mutation == "missing":
        record["local_checks"].pop(check)
    else:
        record["local_checks"][check] = {"false": False, "integer": 1, "string": "true"}[mutation]
    path.write_text(json.dumps(record), encoding="utf-8")
    registry_calls, credential_calls = [], []

    def unexpected_registry(version):
        registry_calls.append(version)
        raise AssertionError("Incomplete launch review must fail before registry access")

    def unexpected_credentials(*args):
        credential_calls.append(args)
        raise AssertionError("Incomplete launch review must fail before credential access")

    monkeypatch.setitem(module["upload"].__globals__, "published_files", unexpected_registry)
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=unexpected_credentials))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="All named release checks must pass"):
        module["upload"](path)
    assert registry_calls == credential_calls == []
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", ["1.1.1", "1.10.0", "2.0.0"])
def test_future_stable_versions_cannot_reuse_only_the_1_0_check_set(tmp_path, version):
    module, path, _ = receipt(tmp_path, version=version)
    with pytest.raises(ValueError, match="All named release checks must pass"):
        module["checked_files"](path)


@pytest.mark.parametrize("mutation", ["version", "revision", "no_checks", "missing_check",
                                    "truthy_check", "duplicate_file", "path", "bytes", "hash"])
def test_invalid_release_receipt_is_refused(tmp_path, mutation):
    module, path, record = receipt(tmp_path)
    if mutation == "version":
        record["version"] = "1.0.0a1"
    elif mutation == "revision":
        record["source_revision"] = "unfrozen"
    elif mutation == "no_checks":
        record["local_checks"] = {}
    elif mutation == "missing_check":
        record["local_checks"].pop("python311_conformance")
    elif mutation == "truthy_check":
        record["local_checks"]["source_tests"] = 1
    elif mutation == "duplicate_file":
        record["artifacts"][1] = record["artifacts"][0]
    elif mutation == "path":
        record["artifacts"][0]["path"] = "../"+record["artifacts"][0]["path"]
    elif mutation == "bytes":
        record["artifacts"][0]["bytes"] = True
    else:
        record["artifacts"][0]["sha256"] = "0"*64
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        module["checked_files"](path)


def test_matching_registry_files_require_no_authentication_or_second_upload(tmp_path, monkeypatch):
    module, path, record = receipt(tmp_path)
    existing = [{"filename": item["path"], "size": item["bytes"],
                 "digests": {"sha256": item["sha256"]}} for item in record["artifacts"]]
    monkeypatch.setitem(module["upload"].__globals__, "published_files", lambda version: existing)
    def unexpected_credentials(*args):
        raise AssertionError("Matching public files must not require local credentials")
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=unexpected_credentials))
    assert module["upload"](path) == 0


def test_altered_public_artifact_refuses_before_authentication(tmp_path, monkeypatch):
    module, path, record = receipt(tmp_path)
    existing = [{"filename": record["artifacts"][0]["path"], "size": 1,
                 "digests": {"sha256": record["artifacts"][0]["sha256"]}}]
    monkeypatch.setitem(module["upload"].__globals__, "published_files", lambda version: existing)
    def unexpected_credentials(*args):
        raise AssertionError("Conflicting public files must fail before accessing credentials")
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=unexpected_credentials))
    with pytest.raises(ValueError, match="Published release differs"):
        module["upload"](path)


def test_duplicate_json_receipt_fields_are_not_silently_overridden(tmp_path):
    module, path, _ = receipt(tmp_path)
    path.write_text('{"version":"1.0.0","version":"1.0.0"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        module["checked_files"](path)


def registry_rows(record):
    return [{"filename": item["path"], "size": item["bytes"],
             "digests": {"sha256": item["sha256"]}} for item in record["artifacts"]]


def mock_upload(module, monkeypatch, *, returncode=0):
    """Replace every credential, environment and upload boundary with fixtures."""
    globals_ = module["upload"].__globals__
    credential_calls, upload_calls, sleeps = [], [], []

    def credential(service, account):
        credential_calls.append((service, account))
        return "pypi-mocked-value"

    def run(command, *, env, check):
        upload_calls.append((command, env, check))
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=credential))
    monkeypatch.setitem(globals_, "os", SimpleNamespace(environ={"PATH": "mocked-path"}))
    monkeypatch.setitem(globals_, "subprocess", SimpleNamespace(run=run))
    monkeypatch.setitem(globals_, "time", SimpleNamespace(sleep=sleeps.append))
    return credential_calls, upload_calls, sleeps


def test_partial_publication_uploads_only_missing_reviewed_file_and_verifies_it(tmp_path, monkeypatch):
    module, path, record = receipt(tmp_path)
    credential_calls, uploads, sleeps = mock_upload(module, monkeypatch)
    snapshots = iter([registry_rows(record)[:1], registry_rows(record)])
    monkeypatch.setitem(module["upload"].__globals__, "published_files",
                        lambda version: next(snapshots))
    assert module["upload"](path, account="test-maintainer") == 0
    assert credential_calls == [("https://upload.pypi.org/legacy/", "test-maintainer")]
    assert len(uploads) == 1
    command, environment, check = uploads[0]
    assert command == [sys.executable, "-m", "twine", "upload", "--non-interactive",
                       "--disable-progress-bar", "--repository-url",
                       "https://upload.pypi.org/legacy/", str(tmp_path/record["artifacts"][1]["path"])]
    assert environment == {"PATH": "mocked-path", "TWINE_USERNAME": "__token__",
                           "TWINE_PASSWORD": "pypi-mocked-value"}
    assert check is False and sleeps == []


def test_failed_upload_returns_failure_without_claiming_public_verification(tmp_path, monkeypatch):
    module, path, _ = receipt(tmp_path)
    _, uploads, sleeps = mock_upload(module, monkeypatch, returncode=7)
    registry_calls = []

    def registry(version):
        registry_calls.append(version)
        return []

    monkeypatch.setitem(module["upload"].__globals__, "published_files", registry)
    assert module["upload"](path) == 7
    assert len(uploads) == 1 and registry_calls == ["1.0.0"] and sleeps == []


def test_accepted_upload_with_stale_public_view_remains_pending_after_bounded_retries(
    tmp_path, monkeypatch,
):
    module, path, _ = receipt(tmp_path)
    _, uploads, sleeps = mock_upload(module, monkeypatch)
    registry_calls = []

    def registry(version):
        registry_calls.append(version)
        return []

    monkeypatch.setitem(module["upload"].__globals__, "published_files", registry)
    with pytest.raises(RuntimeError, match="public verification pending"):
        module["upload"](path)
    assert len(uploads) == 1 and registry_calls == ["1.0.0"] * 11
    assert sleeps == [2] * 9


@pytest.mark.parametrize("name,version", [("other-project", "1.0.0"), ("consequa-x", "2.0.0")])
def test_registry_response_identity_is_checked(name, version, monkeypatch):
    module = subject()
    payload = {"info": {"name": name, "version": version}, "urls": []}

    def open_fixture(url, *, timeout):
        assert url.startswith("https://pypi.org/pypi/consequa-x/1.0.0/json?verification=")
        assert timeout == 30
        return StringIO(json.dumps(payload))

    monkeypatch.setitem(module["published_files"].__globals__, "urlopen", open_fixture)
    with pytest.raises(ValueError, match="another project or version"):
        module["published_files"]("1.0.0")


@pytest.mark.parametrize("status", [404, 403, 500])
def test_only_registry_not_found_means_unpublished(status, monkeypatch):
    module = subject()

    def open_fixture(url, *, timeout):
        raise HTTPError(url, status, "mocked registry response", None, None)

    monkeypatch.setitem(module["published_files"].__globals__, "urlopen", open_fixture)
    if status == 404:
        assert module["published_files"]("1.0.0") == []
    else:
        with pytest.raises(HTTPError) as error:
            module["published_files"]("1.0.0")
        assert error.value.code == status
