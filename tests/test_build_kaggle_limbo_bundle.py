"""Source packaging fixtures: no downloads, runtime launch or model execution."""
import json
import os
from types import SimpleNamespace
import zipfile

import pytest

from scripts import build_kaggle_limbo_bundle as package


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_source_inventory_is_allowlisted_and_excludes_credentials_results_weights(tmp_path):
    names = ["research/kaggle_limbo/checkpoint.py", "research/obligation_shield/policy.py",
             "research/expanded_limbo/protocol.py", "research/limbo_agent/harness.py"]
    forbidden = [".claude/settings.json", "Pypi token.txt", "output/result.json", "models/weights.gguf"]
    for name in [*names, *forbidden]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    selected = package.selected_sources(tmp_path)
    assert set(names).issubset(selected)
    assert not set(forbidden) & set(selected)
    assert all(name.endswith(".py") or name == "LICENSE" for name in selected)


def test_commit_gate_requires_exact_bytes_or_explicit_engineering_label(tmp_path, monkeypatch):
    path = tmp_path / "source.py"
    path.write_bytes(b"committed\n")
    commit = "a" * 40

    def run(command, **kwargs):
        if "rev-parse" in command:
            return SimpleNamespace(stdout=commit + "\n", returncode=0)
        return SimpleNamespace(stdout=b"committed\n", returncode=0)

    monkeypatch.setattr(package.subprocess, "run", run)
    assert package.check_source_commit(tmp_path, commit, ["source.py"]) == []
    path.write_bytes(b"modified\n")
    with pytest.raises(ValueError, match="Commit the exact"):
        package.check_source_commit(tmp_path, commit, ["source.py"])
    assert package.check_source_commit(tmp_path, commit, ["source.py"], engineering=True) == ["source.py"]


def test_deterministic_zip_ignores_filesystem_mtime_and_preserves_root(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "b.txt").write_bytes(b"b")
    (payload / "a.txt").write_bytes(b"a")
    first, second = tmp_path / "one.zip", tmp_path / "two.zip"
    package.deterministic_zip(payload, first)
    os.utime(payload / "a.txt", (1000, 1000))
    package.deterministic_zip(payload, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["conseqax-kaggle-study/a.txt", "conseqax-kaggle-study/b.txt"]
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())


@pytest.fixture
def model_fixture(tmp_path):
    blobs = tmp_path / "models/blobs"
    blobs.mkdir(parents=True)
    metadata = blobs / ("sha256-" + "a" * 64)
    metadata.write_bytes(b"model metadata fixture")
    import hashlib
    sha = hashlib.sha256(metadata.read_bytes()).hexdigest()
    exact = blobs / ("sha256-" + sha)
    metadata.rename(exact)
    weights = {"sha256": "b" * 64, "bytes": 2_000_000_000}
    image = {"config": {"mediaType": "application/vnd.docker.container.image.v1+json",
        "digest": "sha256:" + sha, "size": exact.stat().st_size}, "layers": [{
        "mediaType": "application/vnd.ollama.image.model", "digest": "sha256:" + weights["sha256"],
        "size": weights["bytes"]}]}
    manifest = tmp_path / "registry-manifest.json"
    write(manifest, image)
    small = {"sha256": "c" * 64, "bytes": 100}
    acquisition = {"manifest": {"path": str(manifest), **package.file_binding(manifest)},
        "weights_path": str(blobs / ("sha256-" + weights["sha256"])), "weights": weights,
        "tag": "qwen3:fixture-only", "details": {"quantization_level": "Q4_K_M"},
        "tokenizer": small, "chat_template": small, "license": small}
    path = tmp_path / "output/expanded-model-qwen4b-2026-10-25/acquisition.json"
    write(path, acquisition)
    return tmp_path, manifest, path, acquisition, exact


def test_model_packaging_copies_metadata_and_never_requires_or_bundles_weights(model_fixture):
    root, _, _, acquisition, metadata = model_fixture
    payload = root / "payload"
    placeholder = {"sha256": "d" * 64, "bytes": 250}
    model, catalog = package.package_model(root, payload, "qwen4b", "qwen", "qwen3", placeholder)
    assert model["id"] == "conseqax-kaggle-qwen4b:full-v1"
    assert model["weights"] == acquisition["weights"]
    assert model["transport_preflight"] == placeholder
    assert catalog["model_weights_included"] is False
    assert catalog["registry_name"] == "qwen3"
    assert (payload / "assets/models/qwen" / metadata.name).read_bytes() == metadata.read_bytes()
    assert not list(payload.rglob("*" + acquisition["weights"]["sha256"] + "*"))


def test_model_packaging_rejects_manifest_weight_disagreement(model_fixture):
    root, _, acquisition_path, acquisition, _ = model_fixture
    acquisition["weights"]["sha256"] = "e" * 64
    write(acquisition_path, acquisition)
    with pytest.raises(ValueError, match="weight identities"):
        package.package_model(root, root / "payload", "qwen4b", "qwen", "qwen3",
                              {"sha256": "d" * 64, "bytes": 250})


def test_model_packaging_rejects_changed_metadata_blob(model_fixture):
    root, _, _, _, metadata = model_fixture
    metadata.write_bytes(b"changed bytes")
    with pytest.raises(ValueError, match="metadata blob"):
        package.package_model(root, root / "payload", "qwen4b", "qwen", "qwen3",
                              {"sha256": "d" * 64, "bytes": 250})


def test_exposure_keeps_all_prior_indices_and_binds_original_protocol(tmp_path):
    path = tmp_path / "original.json"
    write(path, {"metadata": [{"template": f"template-{i}", "index": 10000 + i} for i in range(12)]})
    exposure = package.make_exposure(path)
    assert exposure["complete_known_exposure_attested"] is True
    for i in range(12):
        assert exposure["by_template"][f"template-{i}"] == [0, 1, 10000 + i]
    assert next(iter(exposure["sources"].values())) == package.file_binding(path)
