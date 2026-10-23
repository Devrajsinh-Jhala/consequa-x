"""Preservation must not turn missing terminal evidence into a grade or release."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preserve_interrupted_limbo_development.py"
SPEC = importlib.util.spec_from_file_location("preserve_interrupted_limbo_development", SCRIPT)
preserver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preserver)


def save(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def fixture_inputs(root):
    source = save(root, "research/limbo_agent/transport.py", "# synthetic test source\n")
    save(root, preserver.EPISODE / "worker-config.json", json.dumps({
        "protocol": {"sources": {"research/limbo_agent/transport.py": preserver.binding(source)}}}))
    events = [
        {"event": "before_dispatch", "invocation": 1},
        {"event": "request_return", "invocation": 1, "usage": {"input_tokens": {"available": True, "value": 3}}},
        {"event": "before_dispatch", "invocation": 2},
    ]
    save(root, preserver.EPISODE / "model/model-calls.jsonl", "".join(json.dumps(row) + "\n" for row in events))
    save(root, preserver.EPISODE / "model/0001-terminal.json", json.dumps({"returned": True}))
    save(root, preserver.EPISODE / "model/0001-response.bin", "synthetic response\n")
    save(root, preserver.EPISODE / "framework.jsonl", "")
    save(root, preserver.OBSERVER / "resources.jsonl", json.dumps({"recorded_utc": "2026-10-22T17:00:00+00:00"}) + "\n")
    save(root, preserver.RUNTIME / "server.stderr.log", "synthetic log\n")
    save(root, preserver.RESERVATION, json.dumps({"reserved": 11}))
    for relative in ("scripts/observe_limbo_resources.py", "scripts/observe_native_resources.py", "scripts/preserve_interrupted_limbo_development.py"):
        save(root, relative, "# synthetic fixture source\n")


def test_copy_preserves_prefix_unknowns_and_full_budget(tmp_path):
    fixture_inputs(tmp_path)
    original = {str(path.relative_to(tmp_path)): path.read_bytes()
                for path in tmp_path.rglob("*") if path.is_file()}
    report = preserver.preserve(tmp_path, Path("output/new-bundle"), {"boot_time": "synthetic test only"})
    bundle = tmp_path / "output/new-bundle"
    assert report["native_grade"] is None
    assert report["grade_available"] is False
    assert report["native_replay_performed"] is False
    assert all(report["terminal_record_absence"].values())
    assert report["model_journal_prefix"]["before_dispatch_count"] == 2
    assert report["model_journal_prefix"]["request_return_count"] == 1
    assert report["model_journal_prefix"]["invocations"][1]["transport_terminal"] is None
    assert report["model_journal_prefix"]["invocations"][1]["server_acceptance_from_before_dispatch_alone"] == "unknown"
    assert report["budget"]["remaining_held"] == 11
    assert report["budget"]["released"] == 0
    assert not (tmp_path / preserver.SETTLEMENT).exists()
    for relative, value in original.items():
        assert (tmp_path / relative).read_bytes() == value
        assert (bundle / "copies" / relative).read_bytes() == value
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        assert preserver.binding(bundle / relative) == expected


def test_existing_bundle_is_not_overwritten(tmp_path):
    fixture_inputs(tmp_path)
    destination = tmp_path / "output/already-exists"
    destination.mkdir()
    sentinel = destination / "sentinel.txt"
    sentinel.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        preserver.preserve(tmp_path, Path("output/already-exists"), {})
    assert sentinel.read_bytes() == b"keep"


def test_changed_execution_source_refused_before_copy(tmp_path):
    fixture_inputs(tmp_path)
    (tmp_path / "research/limbo_agent/transport.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source no longer matches"):
        preserver.preserve(tmp_path, Path("output/refused"), {})
    assert not (tmp_path / "output/refused").exists()
    assert not (tmp_path / preserver.SETTLEMENT).exists()
