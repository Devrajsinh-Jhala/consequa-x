"""Exports preserve declared denominators, public evidence and failures."""

import gzip
from hashlib import sha256
import json

from jsonschema import Draft202012Validator
import pytest

from consequa_x import cli
from consequa_x.models import Trace


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def run(output, *extra):
    return cli.main(["calibrate-attribution", "--output", str(output), "--replicates", "2",
                     "--samples", "2", "--pairs", "2", "--endpoint-samples", "2",
                     "--bootstrap-samples", "20", *extra])


def test_export_retains_every_draw_and_preselected_full_evidence(tmp_path):
    output = tmp_path / "probe"
    assert run(output, "--mechanisms", "protective-stop-q50,budget-stop-q50",
               "--source-revision", "frozen-source") == 0
    protocol = read(output / "protocol.json")
    assert protocol["planned_trials"] == 4
    assert protocol["source_revision"] == "frozen-source"
    assert protocol["retention"]["full_evidence_replicates"] == [0]
    validator = Draft202012Validator(read(output / "trace-schema.json"))
    for name in ("protective-stop-q50", "budget-stop-q50"):
        with gzip.open(output / "trials" / f"{name}.jsonl.gz", "rt", encoding="utf-8") as stream:
            trials = [json.loads(line) for line in stream]
        assert len(trials) == 2
        for record in trials:
            for method in ("contrastive", "shapley"):
                assert record["factual"][method]["status"] == "completed"
                branches = record[method]["branches"]
                assert len(branches) == record["seed_plan"][f"{method}_branches"]
                assert sum(branch["policy_calls"] for branch in branches) == record["calls"][method]
                if name.startswith("budget"):
                    assert record["calls"][method] == 1
                    assert all(branch["target_values"] is None for branch in branches)
                    assert [branch["status"] for branch in branches].count("failed") == 1
                    assert all(item["status"] == "refused" for item in record[method]["results"])
            assert record["factual"]["contrastive"]["trace_sha256"] == (
                record["factual"]["shapley"]["trace_sha256"])
            assert record["calls"]["total"] == sum(record["calls"][key] for key in (
                "contrastive_factual", "shapley_factual", "contrastive", "shapley"))
        evidence = read_gz(output / "evidence" / f"{name}.json.gz")
        gold = read_gz(output / "evaluator_truth" / f"{name}.json.gz")
        assert evidence["seed_plan"]["replicate"] == 0
        for method, episodes in evidence["methods"].items():
            for key, item in episodes.items():
                if "trace" in item:
                    validator.validate(item["trace"])
                    Trace.from_dict(item["trace"])
                    assert "records" not in item and "config" not in item
                    assert key in gold["methods"][method]
                else:
                    assert key not in gold["methods"][method]
    paths = []
    for item in read(output / "manifest.json")["artifacts"]:
        path = output / item["path"]
        assert sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert path.stat().st_size == item["bytes"]
        paths.append(item["path"])
    assert len(paths) == len(set(paths))
    assert set(paths) == {path.relative_to(output).as_posix() for path in output.rglob("*")
                          if path.is_file() and path.name != "manifest.json"}


def test_same_plan_has_identical_export_bytes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for path in (first, second):
        assert run(path, "--mechanisms", "retry-pivot-q50") == 0
    assert read(first / "manifest.json") == read(second / "manifest.json")


@pytest.mark.parametrize("extra", [
    ("--replicates", "0"), ("--mechanisms", "missing"), ("--samples", "1"),
    ("--seed", "357913940"), ("--confidence", "nan"),
])
def test_invalid_plan_has_no_output_or_calls(tmp_path, extra):
    output = tmp_path / "invalid"
    assert run(output, *extra) == 2
    assert not output.exists()


def test_nonempty_run_is_preserved(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    receipt = output / "original.txt"
    receipt.write_text("original", encoding="utf-8")
    assert run(output) == 2
    assert receipt.read_text(encoding="utf-8") == "original"
    assert sorted(path.name for path in output.iterdir()) == ["original.txt"]


def test_protocol_precedes_execution_and_export_failure_is_not_complete(tmp_path, monkeypatch):
    from consequa_x.benchmark import calibration_export

    output = tmp_path / "partial"

    def interrupted(plan, *, on_trial):
        assert read(output / "protocol.json")["planned_trials"] == 2
        raise OSError("fixture interruption")

    monkeypatch.setattr(calibration_export, "run_calibration", interrupted)
    assert run(output, "--mechanisms", "protective-stop-q50") == 2
    assert (output / "protocol.json").exists()
    assert not (output / "manifest.json").exists()
    assert not (output / "summary.json").exists()
