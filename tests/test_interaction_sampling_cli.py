"""Installed research command delegates the complete offline protocol."""

import json

from consequa_x import cli


def test_cli_interaction_sampling_exports_full_small_schedule(tmp_path, capsys):
    output = tmp_path/"study"
    assert cli.main(["calibrate-interactions", "--repeats", "1", "--pairs", "2",
                     "--endpoint-samples", "2", "--source-revision", "cli-conformance",
                     "--seed", "33000000", "--output", str(output)]) == 0
    assert "16 interaction trials" in capsys.readouterr().out
    protocol = json.loads((output/"protocol.json").read_text(encoding="utf-8"))
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    assert protocol["source_revision"] == "cli-conformance"
    assert protocol["execution"]["workers"] == 1
    assert summary["planned_trials"] == summary["retained_trials"] == 16
    assert summary["planned_branches"] == 320
    previous = (output/"manifest.json").read_bytes()
    assert cli.main(["calibrate-interactions", "--repeats", "1", "--source-revision", "other",
                     "--output", str(output)]) == 2
    assert (output/"manifest.json").read_bytes() == previous
