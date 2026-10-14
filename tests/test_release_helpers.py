"""Release gates reject changed files and mismatched published versions."""

from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


def subject():
    return runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts/publish_alpha.py"))


def fixture(tmp_path):
    items = []
    for name in ("consequa_x-0.1.0a2-py3-none-any.whl", "consequa_x-0.1.0a2.tar.gz"):
        path = tmp_path/name
        path.write_bytes(b"reviewed fixture bytes")
        items.append({"path": name, "bytes": path.stat().st_size,
                      "sha256": sha256(path.read_bytes()).hexdigest()})
    receipt = tmp_path/"checks.json"
    receipt.write_text(json.dumps({"distribution": "consequa-x", "version": "0.1.0a2",
        "artifacts": items,
        "local_checks": {key: True for key in subject()["REQUIRED_CHECKS"]}}), encoding="utf-8")
    return receipt


@pytest.mark.parametrize("change", ["bytes", "size", "outside", "missing", "duplicate",
                                    "check_failed", "checks_empty", "checks_missing", "truthy_check"])
def test_release_receipt_rejects_changed_or_unreviewed_artifacts(tmp_path, change):
    receipt = fixture(tmp_path)
    record = json.loads(receipt.read_text(encoding="utf-8"))
    if change == "bytes":
        (tmp_path/record["artifacts"][0]["path"]).write_bytes(b"different")
    elif change == "size":
        record["artifacts"][0]["bytes"] = 0
    elif change == "outside":
        record["artifacts"][0]["path"] = "../"+record["artifacts"][0]["path"]
    elif change == "missing":
        record["artifacts"].pop()
    elif change == "duplicate":
        record["artifacts"][1] = record["artifacts"][0]
    elif change == "checks_empty":
        record["local_checks"] = {}
    elif change == "checks_missing":
        record["local_checks"].pop("source_tests")
    elif change == "truthy_check":
        record["local_checks"]["source_tests"] = "passed"
    else:
        record["local_checks"]["source_tests"] = False
    receipt.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        subject()["checked_files"](receipt)


def test_mismatched_published_version_never_reads_credentials_or_uploads(tmp_path, monkeypatch):
    module = subject()
    globals_ = module["upload"].__globals__
    monkeypatch.setitem(globals_, "published_files", lambda: [{"filename": "unexpected.whl",
                                                              "digests": {"sha256": "other"}}])
    with pytest.raises(ValueError, match="Published version differs"):
        module["upload"](fixture(tmp_path))


def test_missing_authentication_never_starts_upload(tmp_path, monkeypatch):
    module = subject()
    globals_ = module["upload"].__globals__
    monkeypatch.setitem(globals_, "published_files", lambda: [])
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=lambda *args: None))
    monkeypatch.setattr(globals_["subprocess"], "run", lambda *a, **k: pytest.fail("upload started"))
    with pytest.raises(RuntimeError, match="not configured"):
        module["upload"](fixture(tmp_path))


def test_upload_checks_public_hashes_and_only_sends_missing_file(tmp_path, monkeypatch):
    receipt = fixture(tmp_path)
    record = json.loads(receipt.read_text(encoding="utf-8"))
    entries = [{"filename": item["path"], "digests": {"sha256": item["sha256"]}}
               for item in record["artifacts"]]
    states = iter([entries[:1], entries])
    module = subject()
    globals_ = module["upload"].__globals__
    monkeypatch.setitem(globals_, "published_files", lambda: next(states))
    monkeypatch.setitem(sys.modules, "keyring",
                        SimpleNamespace(get_password=lambda *args: "pypi-fixture-only"))
    calls = []
    monkeypatch.setattr(globals_["subprocess"], "run",
                        lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(returncode=0))
    assert module["upload"](receipt) == 0
    assert len(calls) == 1
    argv = calls[0][0][0]
    assert str(tmp_path/record["artifacts"][1]["path"]) in argv
    assert str(tmp_path/record["artifacts"][0]["path"]) not in argv
    assert "pypi-fixture-only" not in argv


def test_successful_upload_rejects_mismatched_public_hash(tmp_path, monkeypatch):
    states = iter([[], [{"filename": "consequa_x-0.1.0a2.tar.gz", "digests": {"sha256": "wrong"}}]])
    module = subject()
    globals_ = module["upload"].__globals__
    monkeypatch.setitem(globals_, "published_files", lambda: next(states))
    monkeypatch.setitem(sys.modules, "keyring",
                        SimpleNamespace(get_password=lambda *args: "pypi-fixture-only"))
    monkeypatch.setattr(globals_["subprocess"], "run", lambda *a, **k: SimpleNamespace(returncode=0))
    with pytest.raises(ValueError, match="Published version differs"):
        module["upload"](fixture(tmp_path))


def test_credential_prompt_refuses_echo_fallback(monkeypatch):
    from getpass import GetPassWarning
    import warnings

    module = runpy.run_path(str(Path(__file__).resolve().parents[1]/"scripts/configure_pypi_auth.py"))
    globals_ = module["main"].__globals__
    monkeypatch.setattr(sys, "argv", ["configure_pypi_auth.py"])
    monkeypatch.setitem(sys.modules, "keyring",
                        SimpleNamespace(set_password=lambda *a: pytest.fail("credential saved")))
    def fallback(*args):
        warnings.warn("cannot hide input", GetPassWarning)
        pytest.fail("prompt proceeded to echoed input")
    monkeypatch.setitem(globals_, "getpass", fallback)
    with pytest.raises(GetPassWarning):
        module["main"]()
