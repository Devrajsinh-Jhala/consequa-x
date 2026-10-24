"""Offline checks for auxiliary launch/copy integrity and strict refusal paths."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


launcher = load("launch_durable_research")
copier = load("copy_private_ollama_runtime")
starter = load("start_durable_limbo_runtime")


def installed_fixture(tmp_path):
    source = tmp_path / "installed"
    library = source / "lib/ollama"
    library.mkdir(parents=True)
    (source / "ollama.exe").write_bytes(b"offline fake executable")
    for name in ("llama-server.exe", "ggml-base.dll", "ggml.dll", "libllama.dll",
                 "libllama-common.dll", "libllama-server-impl.dll", "libomp.dll",
                 "LLAMA_CPP_LICENSE"):
        (library / name).write_bytes(name.encode())
    (library / "cuda_v13").mkdir()
    (library / "cuda_v13/not-copied.dll").write_bytes(b"gpu")
    return source


def test_private_copy_exact_inventory_and_no_gpu_or_models(tmp_path):
    source = installed_fixture(tmp_path)
    destination = tmp_path / "ollama-runtime-0.40.10"
    result = copier.copy_private(source, destination, "0.40.10")
    assert result["source_before_equals_source_after_equals_private_copy"] is True
    assert result["model_generations"] == result["model_loads"] == result["downloads"] == 0
    assert not (destination / "lib/ollama/cuda_v13").exists()
    assert starter.verify_private(destination) == result
    assert json.loads((destination / "private-runtime-manifest.json").read_text()) == result


def test_private_copy_refuses_existing_destination(tmp_path):
    source = installed_fixture(tmp_path)
    destination = tmp_path / "ollama-runtime-0.40.10"
    destination.mkdir()
    with pytest.raises(ValueError, match="overwriting"):
        copier.copy_private(source, destination, "0.40.10")


def test_private_verification_refuses_changed_or_extra_file(tmp_path):
    source = installed_fixture(tmp_path)
    destination = tmp_path / "ollama-runtime-0.40.10"
    copier.copy_private(source, destination, "0.40.10")
    (destination / "ollama.exe").write_bytes(b"replacement")
    with pytest.raises(ValueError, match="file changed"):
        starter.verify_private(destination)


def test_private_verification_refuses_extra_inventory(tmp_path):
    source = installed_fixture(tmp_path)
    destination = tmp_path / "ollama-runtime-0.40.10"
    copier.copy_private(source, destination, "0.40.10")
    (destination / "new.dll").write_bytes(b"new")
    with pytest.raises(ValueError, match="inventory"):
        starter.verify_private(destination)


def test_environment_removes_secret_and_proxy_names(monkeypatch):
    monkeypatch.setenv("EXAMPLE_API_KEY", "not-a-real-secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://not-an-endpoint")
    result, removed = launcher.sanitized_environment({"OLLAMA_NO_CLOUD": "1"})
    assert "EXAMPLE_API_KEY" not in result and "HTTPS_PROXY" not in result
    assert "EXAMPLE_API_KEY" in removed and "HTTPS_PROXY" in removed
    assert result["OLLAMA_NO_CLOUD"] == "1"
    with pytest.raises(ValueError, match="Credential"):
        launcher.sanitized_environment({"EXAMPLE_API_KEY": "refuse"})


def test_strict_flags_include_every_required_flag():
    assert launcher.STRICT_FLAGS == 0x01000208


def test_supervisor_refuses_job_before_target_launch(tmp_path, monkeypatch):
    config = tmp_path / "launch-config.json"
    config.write_text(json.dumps({"schema": launcher.CONFIG_SCHEMA}))
    monkeypatch.setattr(launcher, "process_identity", lambda pid: {"pid": pid, "in_any_windows_job": True})
    def forbidden(*args, **kwargs):
        raise AssertionError("Must not launch target in a job")
    monkeypatch.setattr(launcher.subprocess, "Popen", forbidden)
    assert launcher.supervise(config) == 1
    failure = json.loads((tmp_path / "launch-failure.json").read_text())
    assert failure["no_fallback"] is True and "job membership" in failure["error"]
    assert not (tmp_path / "launch-receipt.json").exists()


@pytest.mark.parametrize("flags", [0, 10240, 14336])
def test_handoff_refuses_unknown_or_killing_job(tmp_path, monkeypatch, flags):
    config = tmp_path / "launch-config.json"
    config.write_text(json.dumps({"schema": launcher.CONFIG_SCHEMA, "mechanism": "wmi_two_stage",
                                  "parent": {"username": "same-test-user"}}))
    monkeypatch.setattr(launcher, "process_identity", lambda pid: {
        "pid": pid, "in_any_windows_job": True, "username": "same-test-user"})
    monkeypatch.setattr(launcher, "current_job_limits", lambda: {
        "limit_flags": flags, "silent_breakaway_ok": bool(flags & 0x1000),
        "kill_on_job_close": bool(flags & 0x2000)})
    def forbidden(*args, **kwargs):
        raise AssertionError("Unrecognized job must not create a child")
    monkeypatch.setattr(launcher.subprocess, "Popen", forbidden)
    assert launcher.wmi_handoff(config) == 1
    failure = json.loads((tmp_path / "wmi-handoff-failure.json").read_text())
    assert failure["no_fallback"] is True and "unrecognized WMI job" in failure["error"]


def test_ambient_policy_is_explicit_and_non_killing_only():
    identity = {"in_any_windows_job": True}
    limits = {"limit_flags": 6144, "kill_on_job_close": False, "silent_breakaway_ok": True}
    launcher.validate_job_policy(identity, limits, "ambient_non_killing")
    with pytest.raises(ValueError, match="job membership"):
        launcher.validate_job_policy(identity, limits, "no_any_job")
    with pytest.raises(ValueError, match="job membership"):
        launcher.validate_job_policy(identity, {**limits, "kill_on_job_close": True}, "ambient_non_killing")
