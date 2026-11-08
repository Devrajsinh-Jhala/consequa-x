"""Source packaging fixtures: no downloads, runtime launch or model execution."""
import json
import os
from pathlib import Path
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


@pytest.fixture
def granite_fixture(tmp_path):
    """Exact released metadata, without reading or creating the 1.5 GB GGUF."""
    archive = package.ROOT / "output/kaggle-benchmark-2026-11-08/conseqax-kaggle-benchmark.zip"
    prefix = "conseqax-kaggle-study/assets/models/granite/"
    blobs = tmp_path / "models/blobs"
    blobs.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        raw_manifest = source.read(prefix + "registry-manifest.json")
        image = json.loads(raw_manifest)
        protocol = json.loads(source.read("conseqax-kaggle-study/study-design.json"))
        model = next(item for item in protocol["models"] if item["family"] == "granite")
        for layer in [image["config"], *image["layers"]]:
            if layer["mediaType"] != "application/vnd.ollama.image.model":
                name = "sha256-" + layer["digest"][7:]
                (blobs / name).write_bytes(source.read(prefix + name))
    manifest = tmp_path / "registry-manifest.json"
    manifest.write_bytes(raw_manifest)
    acquired = {"manifest": {"path": str(manifest), **package.file_binding(manifest)},
        "weights_path": str(blobs / ("sha256-" + model["weights"]["sha256"])),
        "weights": model["weights"], "tag": "granite3.3:2b", "details": {"quantization_level": "Q4_K_M"},
        "tokenizer": model["tokenizer"], "chat_template": model["chat_template"], "license": model["license"],
        "gguf_chat_template": {"sha256": "8a58e18acd9ca00a43a285fe6ba3760efbda06b5ab7fb57875bfacd72957ed5e", "bytes": 4571}}
    write(tmp_path / "output/expanded-model-granite2b-2026-10-25/acquisition.json", acquired)
    return tmp_path, acquired, image, raw_manifest


def test_optional_granite_variant_binds_complete_immutable_oci_graph(granite_fixture):
    root, acquired, original_image, original_raw = granite_fixture
    payload = root / "variant"
    model, catalog = package.package_model(root, payload, "granite2b", "granite", "granite3.3",
        {"sha256": "d" * 64, "bytes": 250}, granite_custom_system_format=True)
    destination = payload / "assets/models/granite"
    active = json.loads((destination / "registry-manifest.json").read_bytes())
    assert (destination / "upstream/registry-manifest.json").read_bytes() == original_raw
    assert catalog["registry_manifest_binding"] == package.file_binding(destination / "registry-manifest.json")
    assert catalog["registry_manifest_binding"] != acquired["manifest"]
    assert model["id"] == "conseqax-kaggle-granite2b:format-repair-v1"
    condition = model["provider_template_condition"]
    assert condition["id"] == "granite-custom-system-format-v1"
    assert condition["original_template"] == acquired["chat_template"]
    assert condition["patched_template"] == model["chat_template"] == {
        "sha256": "18d85e85522dce58d0d31f5a5d953e5897f25fb8e1fba18426a3bce73c7747ab", "bytes": 7042}
    assert condition["native_gguf_template"] == acquired["gguf_chat_template"]
    assert condition["applies_to_all_arms"] is True
    assert condition["model_weights_changed"] is False
    assert condition["native_message_history_rewritten"] is False
    assert condition["independent_offline_parity_claim"] is False
    assert catalog["provider_template_condition"] == condition
    assert model["weights"] == acquired["weights"]
    assert model["tokenizer"] == acquired["tokenizer"]
    assert model["license"] == acquired["license"]
    for layer in [active["config"], *active["layers"]]:
        if layer["mediaType"] == "application/vnd.ollama.image.model":
            assert not (destination / ("sha256-" + layer["digest"][7:])).exists()
            continue
        path = destination / ("sha256-" + layer["digest"][7:])
        assert package.file_binding(path) == {"sha256": layer["digest"][7:], "bytes": layer["size"]}
    original_config = json.loads((destination / "upstream" / ("sha256-" + original_image["config"]["digest"][7:])).read_bytes())
    active_config = json.loads((destination / ("sha256-" + active["config"]["digest"][7:])).read_bytes())
    assert active_config["rootfs"]["diff_ids"] == [item["digest"] for item in active["layers"]]
    assert active_config["rootfs"]["diff_ids"] != original_config["rootfs"]["diff_ids"]
    active_config["rootfs"]["diff_ids"] = original_config["rootfs"]["diff_ids"]
    assert active_config == original_config
    for before, after in zip(original_image["layers"], active["layers"]):
        if before["mediaType"] != "application/vnd.ollama.image.template":
            assert before == after
    receipt = json.loads((destination / "provider-template-condition.json").read_bytes())
    assert receipt["gpu_qualification_completed"] is False
    assert receipt["native_tasks_or_generations_during_packaging"] == 0
    assert receipt["active_registry_manifest"] == catalog["registry_manifest_binding"]


def test_default_granite_packaging_preserves_the_original_condition(granite_fixture):
    root, acquired, _, original_raw = granite_fixture
    model, catalog = package.package_model(root, root / "original", "granite2b", "granite", "granite3.3",
        {"sha256": "d" * 64, "bytes": 250})
    assert model["id"] == "conseqax-kaggle-granite2b:full-v1"
    assert model["chat_template"] == acquired["chat_template"]
    assert "provider_template_condition" not in model and "provider_template_condition" not in catalog
    assert (root / "original/assets/models/granite/registry-manifest.json").read_bytes() == original_raw


@pytest.mark.parametrize("slug,family,registry", [("qwen4b", "qwen", "qwen3"), ("llama3b", "llama", "llama3.2")])
def test_format_flag_does_not_change_other_model_records_or_metadata(model_fixture, slug, family, registry):
    root, _, _, acquisition, _ = model_fixture
    if slug != "qwen4b":
        write(root / f"output/expanded-model-{slug}-2026-10-25/acquisition.json", acquisition)
    placeholder = {"sha256": "d" * 64, "bytes": 250}
    before = package.package_model(root, root / "before", slug, family, registry, placeholder)
    after = package.package_model(root, root / "after", slug, family, registry, placeholder,
                                  granite_custom_system_format=True)
    assert before == after
    before_files = {p.relative_to(root / "before").as_posix(): p.read_bytes()
                    for p in (root / "before").rglob("*") if p.is_file()}
    after_files = {p.relative_to(root / "after").as_posix(): p.read_bytes()
                   for p in (root / "after").rglob("*") if p.is_file()}
    assert before_files == after_files


def test_variant_rejects_changed_original_template_before_installing_it(granite_fixture):
    root, acquired, _, _ = granite_fixture
    blob = Path(acquired["weights_path"]).parent / ("sha256-" + acquired["chat_template"]["sha256"])
    blob.write_bytes(b"changed bytes")
    with pytest.raises(ValueError, match="metadata blob"):
        package.package_model(root, root / "variant", "granite2b", "granite", "granite3.3",
            {"sha256": "d" * 64, "bytes": 250}, granite_custom_system_format=True)
