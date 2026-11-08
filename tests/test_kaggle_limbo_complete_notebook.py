"""Fresh-namespace complete notebook checks; no GPU, downloads or inference."""
from __future__ import annotations

import ast
import base64
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts import build_kaggle_limbo_notebook as builder


COMMIT = "b" * 40


def embedded_fixture(tmp_path):
    payload = b"# invented fixture; never imported\n"
    manifest = {"schema": "conseqax-kaggle-source-bundle-v1", "source_commit": COMMIT,
        "files": {"fixture.py": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}}
    raw_manifest = json.dumps(manifest).encode()
    bundle = tmp_path / "study.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("conseqax-kaggle-study/bundle-manifest.json", raw_manifest)
        archive.writestr("conseqax-kaggle-study/fixture.py", payload)
    pins = {"bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(), "source_commit": COMMIT}
    return bundle, pins


def cell_source(notebook):
    cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert len(cells) == 1
    return "".join(cells[0]["source"])


def prepare(tmp_path, monkeypatch, *, prior=False):
    bundle, pins = embedded_fixture(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    # An obsolete upload cannot supersede the notebook's embedded study.
    (inputs / "conseqax-kaggle-benchmark.zip").write_bytes(b"obsolete unselected Input")
    if prior:
        active = inputs / "prior-output" / "conseqax-benchmark"
        active.mkdir(parents=True)
        (active / "identity.json").write_text("{}")
        (active / "schedule.json").write_text("[]")
        (active.parent / "checkpoint.zip").write_bytes(b"older snapshot fixture")
    monkeypatch.setenv("CONSEQAX_NOTEBOOK_DRY_RUN", "1")
    monkeypatch.setenv("CONSEQAX_NOTEBOOK_INPUT_ROOT", str(inputs))
    monkeypatch.setenv("CONSEQAX_NOTEBOOK_TEMP_ROOT", str(tmp_path / "temporary"))
    return builder.build_self_contained_notebook(bundle, **pins), bundle, pins, inputs


@pytest.mark.parametrize("prior", [False, True])
def test_complete_notebook_runs_from_fresh_namespace_and_preserves_resume(tmp_path, monkeypatch, prior):
    notebook, bundle, pins, inputs = prepare(tmp_path, monkeypatch, prior=prior)
    source = cell_source(notebook)
    ast.parse(source)
    scope = {}
    exec(source, scope)
    commands = scope["COMMAND_PLAN"]
    assert len(commands) == 4
    assert commands[0][2:4] == ["research.kaggle_limbo.bundle", "verify"]
    assert commands[1][2] == "research.kaggle_limbo.setup"
    assert commands[2][2] == "research.kaggle_limbo.run"
    assert commands[3][-1] == "--export-only"
    assert Path(scope["BUNDLE_PATH"]).read_bytes() == bundle.read_bytes()
    assert scope["EXPECTED_BUNDLE_SHA256"] == pins["bundle_sha256"]
    if prior:
        assert commands[2][-1] == str((inputs / "prior-output" / "conseqax-benchmark").resolve())
        assert "--resume-from" in commands[2]
    else:
        assert "--resume-from" not in commands[2]
        assert scope["PREVIOUS_CHECKPOINT"] is None
    details = notebook["metadata"]["conseqax"]
    assert details["self_contained"] and details["executable_cells"] == 1
    assert details["requires_separate_study_input"] is False
    assert details["actual_kaggle_gpu_tested"] is False
    assert "native" in source and "PYTHONPATH" in source
    assert "_EMBEDDED_STUDY_BASE64" not in scope


@pytest.mark.parametrize("changed", ["bundle_sha256", "manifest_sha256", "source_commit"])
def test_complete_builder_rejects_mismatched_release_pins(tmp_path, changed):
    bundle, pins = embedded_fixture(tmp_path)
    pins[changed] = "f" * (40 if changed == "source_commit" else 64)
    with pytest.raises(ValueError):
        builder.build_self_contained_notebook(bundle, **pins)


def test_complete_builder_requires_all_pins_and_existing_source(tmp_path):
    bundle, pins = embedded_fixture(tmp_path)
    with pytest.raises(ValueError, match="all three"):
        builder.build_self_contained_notebook(bundle, **{**pins, "manifest_sha256": None})
    with pytest.raises(ValueError, match="regular released ZIP"):
        builder.build_self_contained_notebook(tmp_path / "missing.zip", **pins)


def test_tampered_embedded_payload_rejected_before_execution_or_cache_write(tmp_path, monkeypatch):
    notebook, bundle, _, _ = prepare(tmp_path, monkeypatch)
    source = cell_source(notebook)
    first = base64.b64encode(bundle.read_bytes()).decode()[:100]
    source = source.replace(first, "A" * len(first), 1)
    scope = {}
    with pytest.raises(RuntimeError, match="embedded study failed"):
        exec(source, scope)
    assert "COMMAND_PLAN" not in scope
    assert not (tmp_path / "temporary" / "conseqax-embedded-study").exists()


def test_complete_cli_writes_the_embedded_single_cell_notebook(tmp_path):
    bundle, pins = embedded_fixture(tmp_path)
    output = tmp_path / "out"
    assert builder.main(["--embed-bundle", str(bundle), "--bundle-sha256", pins["bundle_sha256"],
        "--source-commit", pins["source_commit"], "--manifest-sha256", pins["manifest_sha256"],
        "--require-bound", "--output-dir", str(output)]) == 0
    notebook = json.loads((output / builder.NOTEBOOK_NAME).read_text(encoding="utf-8"))
    assert notebook == builder.build_self_contained_notebook(bundle, **pins)
    assert cell_source(notebook)

