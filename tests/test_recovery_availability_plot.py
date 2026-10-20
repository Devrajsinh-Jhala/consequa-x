"""Exporter guard and exact-arithmetic tests; no figures or studies executed."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("availability_plot", ROOT / "scripts/plot_recovery_availability_sweep.py")
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def packet(tmp_path):
    root = tmp_path / "synthetic-packet"
    root.mkdir()
    data = root / "synthetic.json"
    data.write_bytes(b'{"development":true}\n')
    write_json(root / "manifest.json", {"schema": "synthetic", "complete": True,
                                      "files": {"synthetic.json": hashlib.sha256(data.read_bytes()).hexdigest()}})
    return root


def test_complete_exact_inventory_passes_and_altered_bytes_fail(tmp_path):
    root = packet(tmp_path)
    plot.verify_inventory(root, "synthetic")
    (root / "synthetic.json").write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="hash differs"):
        plot.verify_inventory(root, "synthetic")


def test_inventory_rejects_unbound_extra_files(tmp_path):
    root = packet(tmp_path)
    (root / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unmanifested"):
        plot.verify_inventory(root, "synthetic")


def test_incomplete_inventory_cannot_pass(tmp_path):
    root = packet(tmp_path)
    manifest = plot.strict_json(root / "manifest.json")
    manifest["complete"] = False
    write_json(root / "manifest.json", manifest)
    with pytest.raises(ValueError, match="incomplete"):
        plot.verify_inventory(root, "synthetic")


@pytest.mark.parametrize("name", ["../secret", "/absolute", "a/../../b", "a\\b", "a:b", "a//b", "./file"])
def test_manifest_path_traversal_and_aliases_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        plot.safe_path(tmp_path, name)


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}', '[]'])
def test_json_rejects_duplicate_keys_nonfinite_values_and_arrays(tmp_path, text):
    path = tmp_path / "malformed.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        plot.strict_json(path)


def test_summary_mean_last_bit_tolerance_does_not_coerce_counts():
    plot.same_summary({"mean": 0.2 + 0.1}, {"mean": 0.3})
    with pytest.raises(ValueError, match="type"):
        plot.same_summary({"n": 1}, {"n": True})
    with pytest.raises(ValueError, match="value"):
        plot.same_summary({"n": 1}, {"n": 2})


def test_metric_retains_unavailable_and_rejects_invented_observations():
    row = {"metrics": {"reads": {"sum": 0, "observed": 0, "unavailable": 1, "mean": None}}}
    assert plot.metric(row, "reads") == (0, 0, 1)
    row["metrics"]["reads"]["sum"] = 1
    with pytest.raises(ValueError, match="unobserved"):
        plot.metric(row, "reads")


def test_metric_rejects_misleading_denominator_and_mean():
    row = {"metrics": {"reads": {"sum": 4, "observed": 1, "unavailable": 1, "mean": 4.0}}}
    with pytest.raises(ValueError, match="denominator"):
        plot.metric(row, "reads")
    row["metrics"]["reads"].update(unavailable=0, mean=3.0)
    with pytest.raises(ValueError, match="mean"):
        plot.metric(row, "reads")


def test_undefined_and_noninteger_read_means_stay_exact():
    assert plot.mean_reads({"reads_sum": 0, "reads_observed": 0}) is None
    value = plot.mean_reads({"reads_sum": 10, "reads_observed": 3})
    assert str(value) == "10/3"
    assert plot.short_fraction(value) == "3.33"
    assert plot.fraction(3, 3) == "1"
    assert plot.fraction(0, 0) is None


def test_export_creates_nothing_before_all_source_gates_pass(tmp_path, monkeypatch):
    output = tmp_path / "new-output"
    def reject(*args):
        raise ValueError("synthetic audit rejected")
    monkeypatch.setattr(plot, "load_bundle", reject)
    monkeypatch.setattr(plot, "plot_grid", lambda *args: pytest.fail("plotting before audit gate"))
    args = SimpleNamespace(output=output, study_dir=tmp_path / "study", audit_dir=tmp_path / "audit",
                           git_root=tmp_path, expected_protocol_sha256="0" * 64)
    with pytest.raises(ValueError, match="audit rejected"):
        plot.export(args)
    assert not output.exists()


def test_export_never_overwrites_an_existing_directory(tmp_path, monkeypatch):
    output = tmp_path / "existing-output"
    output.mkdir()
    monkeypatch.setattr(plot, "load_bundle", lambda *args: pytest.fail("existing output must reject first"))
    with pytest.raises(ValueError, match="new"):
        plot.export(SimpleNamespace(output=output))


def test_plan_rejects_incomplete_grid_without_reading_results():
    protocol = {"schema": plot.STUDY_SCHEMA, "methods": list(plot.METHODS), "case_count": 192,
                "profile_count": 64, "domain_count": 3, "seed_count": 1,
                "design": {"factors": plot.FACTORS}, "cases": [], "schedule": []}
    with pytest.raises(ValueError, match="incomplete"):
        plot.validate_plan(protocol)
