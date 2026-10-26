"""Offline notebook tests: never download, install, contact Kaggle, or call a model."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat
import time
import zipfile

import pytest

from scripts import build_kaggle_limbo_notebook as builder


SHA = "a" * 64
COMMIT = "b" * 40


def code(cell):
    return "".join(cell["source"])


def cells(notebook):
    return {cell["id"]: cell for cell in notebook["cells"]}


def environment(tmp_path, monkeypatch, *, checkpoint=False):
    inputs = tmp_path / "input"
    inputs.mkdir()
    (inputs / "conseqax-kaggle-benchmark.zip").write_bytes(b"offline placeholder only")
    if checkpoint:
        previous = inputs / "previous-output"
        previous.mkdir()
        (previous / "checkpoint.json").write_text("{}", encoding="utf-8")
        (previous / "checkpoint.zip").write_bytes(b"same checkpoint candidate")
    monkeypatch.setenv("CONSEQAX_NOTEBOOK_DRY_RUN", "1")
    monkeypatch.setenv("CONSEQAX_NOTEBOOK_INPUT_ROOT", str(inputs))
    monkeypatch.setenv("CONSEQAX_NOTEBOOK_TEMP_ROOT", str(tmp_path / "temp"))
    return inputs


def bootstrap(tmp_path, monkeypatch, *, checkpoint=False):
    inputs = environment(tmp_path, monkeypatch, checkpoint=checkpoint)
    notebook_cells = cells(builder.build_notebook(SHA, COMMIT))
    scope = {}
    exec(code(notebook_cells["configuration"]), scope)
    exec(code(notebook_cells["open-bundle"]), scope)
    return scope, notebook_cells, inputs


def make_bundle(tmp_path, *, extra=None, changed_binding=False, commit=COMMIT):
    content = b"# fixture; no executable dependencies\n"
    manifest = {"schema": "conseqax-kaggle-source-bundle-v1", "source_commit": commit,
                "files": {"fixture.py": {"bytes": len(content),
                                         "sha256": hashlib.sha256(content).hexdigest()}}}
    if changed_binding:
        manifest["files"]["fixture.py"]["sha256"] = "f" * 64
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("conseqax-kaggle-study/bundle-manifest.json", json.dumps(manifest))
        handle.writestr("conseqax-kaggle-study/fixture.py", content)
        if extra is not None:
            name, value = extra
            handle.writestr(name, value)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_bound_notebook_all_cells_compile_and_metadata_is_honest():
    notebook = builder.build_notebook(SHA, COMMIT)
    assert notebook["nbformat"] == 4
    ids = [cell["id"] for cell in notebook["cells"]]
    assert len(ids) == len(set(ids))
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            ast.parse(code(cell))
            assert cell["outputs"] == [] and cell["execution_count"] is None
    details = notebook["metadata"]["conseqax"]
    assert details["planned_slots"] == 3456
    assert details["source_commit"] == COMMIT
    assert details["actual_kaggle_gpu_tested"] is False
    text = json.dumps(notebook)
    assert "checkpoint-state.json" not in text
    assert "checkpoint.json" in text
    assert "GitHub Actions" in text
    assert "never automatically run again" in text
    assert "7-hour deadline includes setup" in text


def test_save_workflow_warns_against_running_collection_twice():
    notebook = builder.build_notebook(SHA, COMMIT)
    text = "\n".join(code(cell) for cell in notebook["cells"])
    assert "Save Version → Save & Run All" in text
    assert "fresh background session" in text
    assert "Do not run the study" in text
    assert "interactively first and then choose Save & Run All just to save it" in text
    assert "Quick Save with outputs" in text
    assert "until the new checkpoint/output is attached as an Input" in text
    assert "save regularly using" not in text


@pytest.mark.parametrize("sha,commit", [(SHA, None), (None, COMMIT), ("x" * 64, COMMIT),
                                       (SHA, "main"), (SHA, "HEAD"), (SHA.upper(), COMMIT)])
def test_builder_rejects_incomplete_or_moving_pins(sha, commit):
    with pytest.raises(ValueError):
        builder.build_notebook(sha, commit)


def test_unbound_engineering_copy_refuses_before_setup(tmp_path, monkeypatch):
    environment(tmp_path, monkeypatch)
    notebook_cells = cells(builder.build_notebook())
    scope = {}
    exec(code(notebook_cells["configuration"]), scope)
    with pytest.raises(RuntimeError, match="archive hash is missing"):
        exec(code(notebook_cells["open-bundle"]), scope)
    assert scope["COMMAND_PLAN"] == []


@pytest.mark.parametrize("resume", [False, True])
def test_full_notebook_dry_run_exact_cli_without_external_operations(tmp_path, monkeypatch, resume):
    scope, notebook_cells, inputs = bootstrap(tmp_path, monkeypatch, checkpoint=resume)
    for name in ("runtime-setup", "collect", "export"):
        exec(code(notebook_cells[name]), scope)
    commands = scope["COMMAND_PLAN"]
    assert len(commands) == 4
    assert commands[0][2:4] == ["research.kaggle_limbo.bundle", "verify"]
    assert commands[1][2] == "research.kaggle_limbo.setup"
    assert commands[2][2] == "research.kaggle_limbo.run"
    assert commands[3][-1] == "--export-only"
    assert commands[2][commands[2].index("--session-hours") + 1] == "7"
    assert "--resume-from" in commands[2] if resume else "--resume-from" not in commands[2]
    if resume:
        assert commands[2][-1] == str((inputs / "previous-output").resolve())
    assert not (tmp_path / "temp").exists()
    assert scope["os"].environ["CONSEQAX_SESSION_START_MONOTONIC"] == str(scope["_SESSION_STARTED_AT"])


def test_ambiguous_inputs_and_previous_checkpoints_refuse(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="Found 2"):
        scope["unique_path"](None, [inputs, inputs / "conseqax-kaggle-benchmark.zip"], "study")
    for name in ("prior-a", "prior-b"):
        folder = inputs / name
        folder.mkdir()
        (folder / "checkpoint.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Found 2"):
        scope["discover_resume"]()


def test_explicit_checkpoint_is_selected_and_missing_marker_refuses(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch, checkpoint=True)
    scope["RESUME_FROM"] = str(inputs / "previous-output" / "checkpoint.zip")
    assert scope["discover_resume"]().name == "checkpoint.zip"
    scope["RESUME_FROM"] = str(inputs)
    with pytest.raises(RuntimeError, match="entire saved output"):
        scope["discover_resume"]()


def test_export_zip_at_saved_output_parent_is_discovered(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    saved = inputs / "previous-kaggle-output"
    active = saved / "conseqax-benchmark"
    active.mkdir(parents=True)
    (active / "identity.json").write_text("{}", encoding="utf-8")
    (active / "schedule.json").write_text("[]", encoding="utf-8")
    exported = saved / "checkpoint.zip"
    exported.write_bytes(b"snapshot fixture; runner performs validation")
    assert scope["discover_resume"]() == active.resolve()
    scope["RESUME_FROM"] = str(saved)
    assert scope["discover_resume"]() == active.resolve()
    scope["RESUME_FROM"] = str(active)
    assert scope["discover_resume"]() == active.resolve()
    scope["RESUME_FROM"] = str(exported)
    assert scope["discover_resume"]() == active.resolve()


def test_partial_raw_marker_cannot_silently_fall_back_to_older_zip(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    saved = inputs / "previous-kaggle-output"
    active = saved / "conseqax-benchmark"
    active.mkdir(parents=True)
    (active / "identity.json").write_text("{}", encoding="utf-8")
    (saved / "checkpoint.zip").write_bytes(b"older snapshot fixture")
    with pytest.raises(RuntimeError, match="schedule.json is missing"):
        scope["discover_resume"]()


def test_multiple_raw_campaigns_remain_ambiguous(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    for name in ("campaign-a", "campaign-b"):
        saved = inputs / name
        active = saved / "conseqax-benchmark"
        active.mkdir(parents=True)
        (active / "identity.json").write_text("{}", encoding="utf-8")
        (active / "schedule.json").write_text("[]", encoding="utf-8")
        (saved / "checkpoint.zip").write_bytes(b"snapshot fixture")
    with pytest.raises(RuntimeError, match="Found 2"):
        scope["discover_resume"]()


def test_elapsed_setup_does_not_reset_or_double_subtract_deadline(tmp_path, monkeypatch):
    scope, notebook_cells, _ = bootstrap(tmp_path, monkeypatch)
    started = scope["_SESSION_STARTED_AT"]
    exec(code(notebook_cells["configuration"]), scope)
    assert scope["_SESSION_STARTED_AT"] == started
    scope["_SESSION_STARTED_AT"] = time.monotonic() - 3600
    exec(code(notebook_cells["collect"]), scope)
    command = scope["COMMAND_PLAN"][-1]
    assert command[command.index("--session-hours") + 1] == "7"
    scope["_SESSION_STARTED_AT"] = time.monotonic() - 7 * 3600 - 1
    before = len(scope["COMMAND_PLAN"])
    with pytest.raises(RuntimeError, match="deadline has been reached"):
        exec(code(notebook_cells["collect"]), scope)
    assert len(scope["COMMAND_PLAN"]) == before


def test_verified_bundle_extraction_and_no_overwrite(tmp_path, monkeypatch):
    scope, _, _ = bootstrap(tmp_path, monkeypatch)
    archive, archive_hash = make_bundle(tmp_path)
    scope["EXPECTED_BUNDLE_SHA256"] = archive_hash
    destination = tmp_path / "opened"
    study = scope["open_bundle"](archive, destination)
    assert (study / "fixture.py").read_bytes().startswith(b"# fixture")
    with pytest.raises(RuntimeError, match="already exists"):
        scope["open_bundle"](archive, destination)


def unpacked_fixture(tmp_path, inputs):
    archive, _ = make_bundle(tmp_path)
    tree = inputs / "uploaded-dataset"
    tree.mkdir()
    with zipfile.ZipFile(archive) as source:
        for name in ("bundle-manifest.json", "fixture.py"):
            (tree / name).write_bytes(source.read("conseqax-kaggle-study/" + name))
    manifest = tree / "bundle-manifest.json"
    return tree, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_unpacked_upload_discovery_and_verified_copy_with_top_folder_stripped(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    tree, manifest, manifest_hash = unpacked_fixture(tmp_path, inputs)
    # Standard dataset upload may unpack the ZIP and expose the manifest directly.
    (inputs / "conseqax-kaggle-benchmark.zip").unlink()
    scope["EXPECTED_MANIFEST_SHA256"] = manifest_hash
    assert scope["discover_bundle"]() == ("tree", manifest)
    copied = scope["open_unpacked_bundle"](manifest, tmp_path / "verified-copy")
    assert copied != tree
    assert (copied / "fixture.py").read_bytes() == (tree / "fixture.py").read_bytes()
    scope["BUNDLE_PATH"] = str(tree)
    assert scope["discover_bundle"]() == ("tree", manifest.resolve())
    # If both representations are attached, the separately hash-pinned ZIP wins.
    scope["BUNDLE_PATH"] = None
    (inputs / "conseqax-kaggle-benchmark.zip").write_bytes(b"fixture placeholder")
    assert scope["discover_bundle"]()[0] == "zip"


@pytest.mark.parametrize("change", ["manifest", "payload", "unlisted"])
def test_unpacked_upload_tampering_refuses_before_copy(tmp_path, monkeypatch, change):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    tree, manifest, manifest_hash = unpacked_fixture(tmp_path, inputs)
    scope["EXPECTED_MANIFEST_SHA256"] = manifest_hash
    if change == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b" ")
    elif change == "payload":
        (tree / "fixture.py").write_bytes(b"changed source")
    else:
        (tree / "unlisted.py").write_bytes(b"unexpected importable source")
    destination = tmp_path / "must-not-copy"
    with pytest.raises(RuntimeError):
        scope["open_unpacked_bundle"](manifest, destination)
    assert not destination.exists()


def test_unpacked_upload_requires_its_own_manifest_pin(tmp_path, monkeypatch):
    scope, _, inputs = bootstrap(tmp_path, monkeypatch)
    _, manifest, _ = unpacked_fixture(tmp_path, inputs)
    assert scope["EXPECTED_MANIFEST_SHA256"] is None
    with pytest.raises(RuntimeError, match="requires the released manifest SHA256"):
        scope["open_unpacked_bundle"](manifest, tmp_path / "not-pinned")
    pinned = builder.build_notebook(source_commit=COMMIT, manifest_sha256=SHA)
    assert pinned["metadata"]["conseqax"]["manifest_sha256"] == SHA
    with pytest.raises(ValueError, match="manifest SHA256"):
        builder.build_notebook(source_commit=COMMIT, manifest_sha256="invalid")


@pytest.mark.parametrize("failure", ["archive", "binding", "commit", "unlisted", "traversal", "alias", "link"])
def test_unsafe_or_changed_bundle_stops_before_extraction(tmp_path, monkeypatch, failure):
    scope, _, _ = bootstrap(tmp_path, monkeypatch)
    kwargs = {}
    if failure == "binding":
        kwargs["changed_binding"] = True
    elif failure == "commit":
        kwargs["commit"] = "c" * 40
    elif failure in ("unlisted", "traversal", "alias"):
        names = {"unlisted": "conseqax-kaggle-study/unlisted.txt",
                 "traversal": "conseqax-kaggle-study/../../escaped.txt",
                 "alias": "conseqax-kaggle-study/./alias.txt"}
        kwargs["extra"] = (names[failure], "unexpected")
    elif failure == "link":
        info = zipfile.ZipInfo("conseqax-kaggle-study/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        kwargs["extra"] = (info, "fixture.py")
    archive, archive_hash = make_bundle(tmp_path, **kwargs)
    scope["EXPECTED_BUNDLE_SHA256"] = "0" * 64 if failure == "archive" else archive_hash
    destination = tmp_path / "blocked"
    with pytest.raises(RuntimeError):
        scope["open_bundle"](archive, destination)
    assert not destination.exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_generator_writes_valid_json_and_requires_release_bindings(tmp_path):
    with pytest.raises(SystemExit):
        builder.main(["--require-bound", "--output-dir", str(tmp_path)])
    assert builder.main(["--bundle-sha256", SHA, "--source-commit", COMMIT,
                         "--manifest-sha256", "c" * 64,
                         "--require-bound", "--output-dir", str(tmp_path)]) == 0
    notebook = json.loads((tmp_path / builder.NOTEBOOK_NAME).read_text(encoding="utf-8"))
    assert notebook == builder.build_notebook(SHA, COMMIT, "c" * 64)
    metadata = json.loads((tmp_path / "kernel-metadata.json").read_text(encoding="utf-8"))
    assert metadata["enable_gpu"] is True and metadata["enable_internet"] is True
    assert metadata["is_private"] is True
    assert "id" not in metadata


def test_committed_generated_notebook_matches_unbound_builder_until_release_binding():
    path = builder.ROOT / "notebooks" / builder.NOTEBOOK_NAME
    notebook = json.loads(path.read_text(encoding="utf-8"))
    pin = notebook["metadata"]["conseqax"]
    assert notebook == builder.build_notebook(pin["bundle_sha256"], pin["source_commit"],
                                              pin["manifest_sha256"])
