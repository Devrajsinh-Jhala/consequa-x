"""Public CLI retains separately named games and guards existing evidence."""

import json

from consequa_x import cli


def test_cli_exports_both_physical_games_with_the_frozen_source(tmp_path):
    output = tmp_path/"interaction"
    assert cli.main(["refund-interactions", "--source-revision", "cli-frozen-source",
                     "--mechanism", "refund-p50-q50", "--output", str(output)]) == 0
    protocol = json.loads((output/"protocol.json").read_text(encoding="utf-8"))
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    assert protocol["source_revision"] == "cli-frozen-source"
    games = summary["cases"]["refund-p50-q50"]["games"]
    assert games["on_reach"]["targets"]["consequence"]["shapley_values"] == [-.125, .375, 0.]
    assert games["strict"]["targets"]["consequence"]["shapley_values"] is None
    assert summary["actual_policy_calls"] == 98


def test_cli_preserves_nonempty_destination(tmp_path):
    (tmp_path/"retain.txt").write_text("original evidence", encoding="utf-8")
    assert cli.main(["refund-interactions", "--source-revision", "source",
                     "--output", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == [tmp_path/"retain.txt"]
