"""Strict plot input checks using temporary synthetic exporter fixtures only.

Rendering is stubbed: no real figures, official results, model, Git or network.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plotter = module_from(ROOT / "scripts/plot_native_external_benchmark.py", "native_plotter_fixture")
fixtures = module_from(ROOT / "tests/test_render_native_paper_results.py", "native_exporter_fixture_helpers")
COMMIT = fixtures.PROTOCOL_COMMIT


@pytest.fixture
def rendering(monkeypatch):
    calls = []

    def stub(output, rows, table):
        calls.append({"rows": deepcopy(rows), "table": deepcopy(table)})
        (output / "synthetic-render-not-a-figure.txt").write_text("SYNTHETIC TEST ONLY; NO FIGURE OR RESEARCH RESULT\n")

    monkeypatch.setattr(plotter, "draw_plot", stub)
    return calls, stub


def test_plot_counts_ignore_untrusted_summary_and_bind_validator_and_full_input_inventory(tmp_path, rendering):
    path = fixtures.fixture(tmp_path)
    output = tmp_path / "synthetic-output"
    result = plotter.execute(path, output, COMMIT)
    calls, _ = rendering
    assert len(calls) == 1 and len(calls[0]["rows"]) == 48
    receipt = json.loads((output / "plot-inputs.json").read_text())
    assert receipt["planned_slots"] == 48 and receipt["distinct_task_ids"] == 12
    assert receipt["counts_recomputed_from_rows"] is receipt["audit_summary_not_used"] is True
    assert len(receipt["input_audit"]["files"]) == 97
    assert len(receipt["rows"]) == 8
    assert all((row["native_reward1_operational"], row["audited_native_reward0"], row["other_planned_slots"])
               == (3, 3, 0) for row in receipt["rows"])
    assert receipt["protocol_anchor"]["protocol_commit"] == COMMIT == result["protocol_commit"]
    for key, source in (("plotter", ROOT / "scripts/plot_native_external_benchmark.py"),
                        ("validator_renderer", ROOT / "scripts/render_native_paper_results.py")):
        copied = output / receipt[key]["artifact_copy"]
        assert copied.read_bytes() == source.read_bytes()
        assert plotter.sha256(copied.read_bytes()) == receipt[key]["sha256"]
    inventory = json.loads((output / "manifest.json").read_text())["files"]
    assert set(inventory) == {"synthetic-render-not-a-figure.txt", "plot-inputs.json",
                              "plotter.source.py", "renderer.source.py"}
    assert all(plotter.sha256((output / name).read_bytes()) == digest for name, digest in inventory.items())
    assert not any(output.glob("*.pdf")) and not any(output.glob("*.svg")) and not any(output.glob("*.png"))
    assert "Green requires operational success as well as audited native reward 1" in receipt["caption_limits"]
    assert "Operational native reward 1" in (ROOT / "scripts/plot_native_external_benchmark.py").read_text()


def test_nonoperational_audited_one_unavailable_and_premature_zero_remain_distinct(tmp_path, rendering):
    def mutate(rows, files):
        rows[0].update(collection_disposition="execution_failed", operational_success=0)
        fixtures.unavailable(rows[1], files, "execution_failed")
        rows[3].update(native_reward=0.0, operational_success=0, normal_termination=False,
                       native_component_outcomes={"reward": 0.0, "reward_breakdown": None})
        files["episode-audit-003.json"].update(normal_termination=False, reward=deepcopy(rows[3]["native_component_outcomes"]))
    plotter.execute(fixtures.fixture(tmp_path, mutate), tmp_path / "synthetic-output", COMMIT)
    counts = {(row["arm"], row["nonempty_communication"]): row for row in rendering[0][0]["table"]}
    assert counts["B", True]["native_reward1_operational"] == 2
    assert counts["B", True]["audited_native_reward0"] == 3
    assert counts["B", True]["other_planned_slots"] == 1
    assert counts["C", True]["other_planned_slots"] == 1
    assert counts["G", True]["audited_native_reward0"] == 4
    assert all(row["native_reward1_operational"] + row["audited_native_reward0"]
               + row["other_planned_slots"] == 6 for row in counts.values())


def test_all_unstarted_counts_are_unknown_not_semantic_zeros(tmp_path, rendering):
    def mutate(rows, files):
        for row in rows:
            fixtures.unavailable(row, files)
    plotter.execute(fixtures.fixture(tmp_path, mutate), tmp_path / "synthetic-output", COMMIT)
    assert all((row["native_reward1_operational"], row["audited_native_reward0"], row["other_planned_slots"])
               == (0, 0, 6) for row in rendering[0][0]["table"])


@pytest.mark.parametrize("commit", [None, "main", "f" * 40])
def test_wrong_or_unpinned_commit_never_creates_output(tmp_path, rendering, commit):
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="protocol commit"):
        plotter.execute(fixtures.fixture(tmp_path), output, commit)
    assert not output.exists() and not rendering[0]


def test_cli_requires_explicit_protocol_anchor_before_any_read_or_render(tmp_path, rendering):
    with pytest.raises(SystemExit) as error:
        plotter.main(["--audit", str(tmp_path / "absent"), "--output", str(tmp_path / "not-created")])
    assert error.value.code == 2 and not rendering[0]


@pytest.mark.parametrize("change", ["tampered", "unbound", "deleted", "schema", "duplicate_key"])
def test_invalid_inventory_refuses_plotting_before_output_creation(tmp_path, rendering, change):
    path = fixtures.fixture(tmp_path)
    manifest = path.parent / "manifest.json"
    if change == "tampered":
        (path.parent / "slot-audit-000.json").write_text("{}")
    elif change == "unbound":
        (path.parent / "unbound.json").write_text("{}")
    elif change == "deleted":
        (path.parent / "episode-audit-000.json").unlink()
    elif change == "schema":
        value = json.loads(manifest.read_text())
        value["schema"] = "wrong"
        manifest.write_text(json.dumps(value))
    else:
        manifest.write_text('{"schema":"conseqax-native-offline-audit-artifacts-v1","files":{},"files":{}}')
    output = tmp_path / "not-created"
    with pytest.raises(ValueError):
        plotter.execute(path, output, COMMIT)
    assert not output.exists() and not rendering[0]


@pytest.mark.parametrize("change", ["requests", "tokens", "http", "operational", "duplicate_arm", "stratum"])
def test_rehashed_but_inconsistent_accounting_or_matrix_refuses_plotting(tmp_path, rendering, change):
    def mutate(rows, files):
        if change == "requests":
            rows[0]["diagnostics"]["model"]["attempted"] = 3
        elif change == "tokens":
            rows[0]["diagnostics"]["model"]["tokens"]["prompt_tokens"]["unavailable_attempts"] = 1
        elif change == "http":
            rows[0]["diagnostics"]["model"]["http_generation_dispatch_records"] = 1
        elif change == "operational":
            rows[0]["operational_success"] = False
        elif change == "duplicate_arm":
            rows[1]["arm"] = rows[0]["arm"]
        else:
            rows[0]["nonempty_communication"] = 1
    output = tmp_path / "not-created"
    with pytest.raises(ValueError):
        plotter.execute(fixtures.fixture(tmp_path, mutate), output, COMMIT)
    assert not output.exists() and not rendering[0]


def test_copied_plotter_can_use_its_bound_adjacent_validator_for_standalone_rerun(tmp_path, rendering, monkeypatch):
    path = fixtures.fixture(tmp_path)
    output = tmp_path / "synthetic-artifact"
    plotter.execute(path, output, COMMIT)
    copied = module_from(output / "plotter.source.py", "standalone_plotter_fixture")
    validator, validator_path, validator_source = copied.load_renderer()
    assert validator_path == output / "renderer.source.py"
    assert validator_source == (ROOT / "scripts/render_native_paper_results.py").read_bytes()
    assert callable(validator.verify_inventory) and callable(validator.validate_audit)
    monkeypatch.setattr(copied, "draw_plot", rendering[1])
    rerun = tmp_path / "synthetic-standalone-rerun"
    copied.execute(path, rerun, COMMIT)
    assert (rerun / "renderer.source.py").read_bytes() == validator_source
    assert len(rendering[0]) == 2


def test_existing_output_and_output_inside_sealed_audit_are_refused(tmp_path, rendering):
    path = fixtures.fixture(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="must be new"):
        plotter.execute(path, existing, COMMIT)
    inside = path.parent / "not-created"
    with pytest.raises(ValueError, match="inside sealed audit"):
        plotter.execute(path, inside, COMMIT)
    assert not inside.exists() and not rendering[0]
