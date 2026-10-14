"""Frozen comparison exports share every sample and preserve refusal coverage."""

import gzip
from hashlib import sha256
import json

import pytest

from consequa_x import cli
from consequa_x.benchmark.interval_comparison import comparison_plan, export_interval_comparison


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_theory_only_has_a_complete_grid_and_no_replays(tmp_path, monkeypatch):
    from consequa_x.benchmark import interval_comparison

    monkeypatch.setattr(interval_comparison, "export_calibration", lambda *a, **k: pytest.fail("replay called"))
    output = tmp_path/"theory"
    assert cli.main(["compare-intervals", "--theory-only", "--output", str(output)]) == 0
    result = read(output/"finite-binomial.json")
    assert len(result["rows"]) == 132
    assert all(row["coverage"] >= .95 for row in result["rows"] if row["method"] == "clopper_pearson")
    assert read(output/"protocol.json")["theory_only"] is True
    assert not (output/"raw").exists()


def test_real_refund_comparison_uses_identical_points_draws_and_refusals(tmp_path):
    output = tmp_path/"integration"
    plan = comparison_plan(repeats=1, samples=2, pairs=2, endpoint_samples=2, bootstrap_samples=20)
    result = export_interval_comparison(plan, output, source_revision="frozen-test-source")
    raw = read(output/"raw/summary.json")
    assert result["planned_trials"] == raw["planned_trials"] == 12
    assert result["actual_policy_calls"] == raw["actual_policy_calls"]
    assert result["additional_policy_calls_for_comparison"] == 0
    with gzip.open(output/"comparisons/budget-stop-q50.jsonl.gz", "rt", encoding="utf-8") as stream:
        budget = json.loads(next(stream))
    for variant in budget["contrastive"].values():
        assert all(item["status"] == "refused" for item in variant["results"])
    for variant in budget["shapley"].values():
        assert all(item["status"] == "refused" for item in variant["results"])
    assert budget["calls"]["total"] == 6
    with gzip.open(output/"comparisons/protective-stop-q50.jsonl.gz", "rt", encoding="utf-8") as stream:
        record = json.loads(next(stream))
    original = record["contrastive"]["percentile_bootstrap"]["results"]
    for name in ("wilson", "clopper_pearson"):
        for before, after in zip(original, record["contrastive"][name]["results"]):
            assert before["effect"] == after["effect"]
            assert before["status"] == after["status"] and before["seeds"] == after["seeds"]
    assert record["additional_policy_calls"] == 0
    paths = set()
    for item in read(output/"manifest.json")["artifacts"]:
        path = output/item["path"]
        assert sha256(path.read_bytes()).hexdigest() == item["sha256"]
        paths.add(item["path"])
    assert paths == {p.relative_to(output).as_posix() for p in output.rglob("*")
                     if p.is_file() and p != output/"manifest.json"}


def test_protocol_saved_before_shared_replays_and_export_failures_remain_partial(tmp_path, monkeypatch):
    from consequa_x.benchmark import interval_comparison

    output = tmp_path/"partial"

    def fail(plan, path, **kwargs):
        assert read(output/"protocol.json")["contrastive_variants"] == ["percentile_bootstrap", "wilson", "clopper_pearson"]
        assert (output/"finite-binomial.json").exists()
        raise OSError("fixture interruption")

    monkeypatch.setattr(interval_comparison, "export_calibration", fail)
    with pytest.raises(OSError):
        export_interval_comparison(comparison_plan(repeats=1), output)
    assert not (output/"manifest.json").exists()


def test_nonempty_directory_and_modified_collection_methods_are_rejected(tmp_path):
    output = tmp_path/"existing"
    output.mkdir()
    (output/"original.txt").write_text("retain", encoding="utf-8")
    with pytest.raises(ValueError, match="new or empty"):
        export_interval_comparison(comparison_plan(repeats=1), output)
    with pytest.raises(ValueError, match="preserve"):
        export_interval_comparison(comparison_plan(repeats=1, contrastive_interval_method="wilson"), tmp_path/"bad")
    assert not (tmp_path/"bad").exists()
