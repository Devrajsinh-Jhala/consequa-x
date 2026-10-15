"""Parallel collection must preserve every declared result and its exact order."""

import gzip
import json

import pytest

from consequa_x.benchmark.interaction_sampling import (
    InteractionSamplingPlan, export_interaction_sampling,
)


def test_parallel_export_matches_serial_records_points_and_costs(tmp_path):
    plan = InteractionSamplingPlan(repeats=2, pairs=2, endpoint_samples=2,
                                   seed=31_000_000, mechanisms=("refund-p50-q50",))
    roots = [tmp_path/"serial", tmp_path/"parallel"]
    results = []
    for root, workers in zip(roots, (1, 2)):
        seen = []
        results.append(export_interaction_sampling(plan, root, source_revision="worker-conformance",
                       workers=workers, on_trial=lambda trial, row: seen.append(row["trial_plan"]["index"])))
        assert seen == list(range(plan.trial_count))
        protocol = json.loads((root/"protocol.json").read_text(encoding="utf-8"))
        assert protocol["execution"]["workers"] == workers
    assert results[0] == results[1]
    for path in (roots[0]/"trials").glob("*.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as source:
            serial = source.read()
        with gzip.open(roots[1]/"trials"/path.name, "rt", encoding="utf-8") as source:
            assert source.read() == serial
    for directory in ("evidence", "evaluator_truth"):
        for path in (roots[0]/directory).glob("*.gz"):
            assert path.read_bytes() == (roots[1]/directory/path.name).read_bytes()


@pytest.mark.parametrize("workers", [True, 0, -1, 9, 1.5])
def test_invalid_workers_refuse_before_creating_export(tmp_path, workers):
    output = tmp_path/"not-started"
    with pytest.raises(ValueError, match="workers"):
        export_interaction_sampling(InteractionSamplingPlan(), output,
                                    source_revision="worker-conformance", workers=workers)
    assert not output.exists()
