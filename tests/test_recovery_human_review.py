"""Synthetic DEVELOPMENT fixtures only; no corpus, controller or measured input."""
import copy
import gzip
import importlib.util
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_recovery_human_review.py"
SPEC = importlib.util.spec_from_file_location("synthetic_recovery_human_review", SCRIPT)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def synthetic_row(identity, *, method="synthetic-reference", case="synthetic-case", seed=0):
    operation = f"original-operation-{identity}"
    actor = f"original-actor-{identity}"
    source = f"original-source-{identity}"
    attempt = f"{operation}:attempt-1"
    expected = {"tenant": "synthetic-tenant", "resource": "synthetic-widget", "state": "active"}
    scope = {"tenant": expected["tenant"], "resource": expected["resource"]}
    record = {**expected, "effect_id": f"original-effect-{identity}", "committed_at_ms": 10,
              "action_id": operation, "actor": actor, "attempt_id": attempt,
              "hidden_world": "DO-NOT-PUBLISH-RECORD"}
    return {"trial_id": identity, "case_id": case, "family_id": "synthetic-family",
            "domain": "synthetic-domain", "seed": seed, "method": method, "status": "completed",
            "public_case": {"operation_id": operation, "actor": actor, "registered_at_ms": 0,
                            "target": {"predicate": "record_present", "expected": expected, "exact_count": 1},
                            "deadline_ms": 100, "stability_ms": 20, "recovery_deadline_ms": 200,
                            "safety_horizon_ms": 400, "scope_fields": list(scope), "scope": scope,
                            "hidden_world": "DO-NOT-PUBLISH-CASE"},
            "source_receipt": {"source": source, "trusted": True, "time_base": "relative_ms",
                               "clock": "synthetic logical clock", "commit_clock_authoritative": True,
                               "history_semantics": "complete lifecycle history through watermark",
                               "completeness_semantics": "exhaustive declared scope",
                               "provenance_semantics": "stored provider action/actor metadata",
                               "hidden_world": "DO-NOT-PUBLISH-SOURCE"},
            "trajectory": [
                {"kind": "dispatch", "at_ms": 0, "decision": {"action_id": operation,
                 "attempt_id": attempt, "idempotency_key": operation,
                 "reason": "DO-NOT-PUBLISH-POLICY"}},
                {"kind": "response", "at_ms": 20,
                 "response": {"status": "timeout", "response_at_ms": 20, "attempt_id": attempt,
                              "result": {"message": f"Request {operation} timed out",
                                         "hidden_world": "DO-NOT-PUBLISH-RESPONSE"}}},
                {"kind": "readback", "at_ms": 120,
                 "observation": {"observation_id": f"original-observation-{identity}", "source": source,
                                 "observed_at_ms": 120, "as_of_ms": 120, "scope": scope,
                                 "records": [record], "available": True, "complete": True,
                                 "gold": "DO-NOT-PUBLISH-OBSERVATION"}},
            ],
            "report": {"reported_state": True, "reported_action_linked": True,
                       "method": method, "reason": "DO-NOT-PUBLISH-REPORT"},
            "truth": {"gold": "DO-NOT-PUBLISH-TRUTH"}, "metrics": {"safe_success": True}}


def seal(study, schedule, rows):
    study.mkdir()
    (study / "trials").mkdir()
    review.write_json(study / "protocol.json", {"schedule": schedule,
                      "human_review_builder_sha256": review.digest(SCRIPT)})
    for row in rows:
        (study / "trials" / f"{row['trial_id']}.json.gz").write_bytes(
            gzip.compress(review.encoded(row), mtime=0))
    (study / "snapshot.sqlite.gz").write_bytes(gzip.compress(b"SYNTHETIC-NOT-A-DATABASE", mtime=0))
    reseal(study)
    return study


def reseal(study):
    files = {path.relative_to(study).as_posix(): review.digest(path)
             for path in study.rglob("*") if path.is_file()
             and path.name not in ("manifest.json", "completion-receipt.json")}
    review.write_json(study / "manifest.json", {"complete": True, "files": files})
    review.write_json(study / "completion-receipt.json", {
        "complete": True, "manifest_sha256": review.digest(study / "manifest.json"),
        "protocol_sha256": review.digest(study / "protocol.json")})


def make_study(tmp_path, *, dispositions=False):
    rows = [synthetic_row("synthetic-one"),
            synthetic_row("synthetic-two", method="synthetic-second"),
            synthetic_row("synthetic-seed-one", seed=1)]
    if dispositions:
        failed = synthetic_row("synthetic-failed", method="synthetic-failed-arm")
        failed["status"] = "failed"
        rows.append(failed)
        missing = synthetic_row("synthetic-missing", method="synthetic-missing-arm")
    else:
        missing = None
    schedule = [{key: row[key] for key in
                 ("trial_id", "case_id", "family_id", "domain", "seed", "method")}
                for row in rows + ([missing] if missing else [])]
    return seal(tmp_path / "study", schedule, rows)


def packet_fixture(tmp_path):
    study = make_study(tmp_path)
    output = tmp_path / "packet"
    summary = review.build_packet(study, output)
    return output, summary


def human_export(packet, path, identifier, *, state="satisfied", linked="true", alignment="supported"):
    value = review.load_json(packet / "reviewer-template.json")
    value["reviewer_id"] = identifier
    for label in value["labels"]:
        label.update(state=state, action_linked=linked, report_state_alignment=alignment,
                     witnesses=["observation-1"], comment="Synthetic test annotation, not a participant")
    review.write_json(path, value)
    return path


def test_blinding_dedup_unavailable_accounting_and_private_zip(tmp_path):
    study = make_study(tmp_path, dispositions=True)
    output = tmp_path / "packet"
    summary = review.build_packet(study, output)
    assert summary["scheduled_seed0"] == 4
    assert summary["completed"] == 2 and summary["failed"] == 1 and summary["absent"] == 1
    assert summary["unique_cards"] == 1  # Differences in identities/methods do not add cards.
    packet = review.verify_packet(output)
    card = packet["cards"][0]["evidence"]
    assert "recovery_deadline_ms" not in card["registered_action"]
    assert "safety_horizon_ms" not in card["registered_action"]
    action = card["registered_action"]["operation_id"]
    assert card["trajectory"][0]["action_id"] == action
    assert card["trajectory"][2]["observation"]["records"][0]["action_id"] == action
    assert action in card["trajectory"][1]["response"]["result"]["message"]
    assert card["admitted_source"]["source"] == card["trajectory"][2]["observation"]["source"]
    assert card["admitted_source"]["commit_clock_authoritative"] is True
    assert card["admitted_source"]["history_semantics"] == "complete lifecycle history through watermark"
    assert "strategy class" in (output / "README.md").read_text()
    with zipfile.ZipFile(output / "recovery-human-review.zip") as archive:
        assert not any("private" in name or "mapping" in name for name in archive.namelist())
        public_bytes = b"\n".join(archive.read(name) for name in archive.namelist())
    for secret in (b"DO-NOT-PUBLISH", b"original-", b"synthetic-reference", b"synthetic-second",
                   b"synthetic-case", b"synthetic-family", b"hidden_world"):
        assert secret not in public_bytes
    private = review.load_json(output / "private" / "mapping.json")
    assert len(private["selected_slots"]) == 4
    assert sum(sum(item.values()) for item in private["weights_by_method"].values()) == 2
    assert (output / "private" / ".gitignore").read_text().strip() == "*"
    assert all(label["state"] is None for label in review.load_json(output / "reviewer-template.json")["labels"])


def test_repeated_build_is_deterministic_and_preserves_existing_output(tmp_path):
    study = make_study(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    review.build_packet(study, first)
    review.build_packet(study, second)
    assert review.digest(first / "cards.json") == review.digest(second / "cards.json")
    assert review.digest(first / "recovery-human-review.zip") == review.digest(second / "recovery-human-review.zip")
    with pytest.raises(ValueError, match="new directory"):
        review.build_packet(study, first)


@pytest.mark.parametrize("mutation", ["bytes", "missing", "receipt", "incomplete", "extra", "builder"])
def test_study_integrity_failures_abort_before_packet(tmp_path, mutation):
    study = make_study(tmp_path)
    if mutation == "bytes":
        (study / "snapshot.sqlite.gz").write_bytes(b"tampered")
    elif mutation == "missing":
        (study / "snapshot.sqlite.gz").unlink()
    elif mutation == "receipt":
        value = review.load_json(study / "completion-receipt.json")
        value["manifest_sha256"] = "0" * 64
        review.write_json(study / "completion-receipt.json", value)
    elif mutation == "incomplete":
        value = review.load_json(study / "completion-receipt.json")
        value["complete"] = False
        review.write_json(study / "completion-receipt.json", value)
    elif mutation == "extra":
        (study / "unbound.txt").write_text("unmanifested")
    else:
        value = review.load_json(study / "protocol.json")
        value["human_review_builder_sha256"] = "0" * 64
        review.write_json(study / "protocol.json", value)
        reseal(study)
    with pytest.raises(ValueError):
        review.build_packet(study, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize("relative", ["../outside.txt", "/outside.txt", "C:/outside.txt", "trials/../outside.txt", "trials\\outside.txt"])
def test_manifest_path_traversal_rejected(tmp_path, relative):
    study = make_study(tmp_path)
    value = review.load_json(study / "manifest.json")
    value["files"][relative] = "0" * 64
    review.write_json(study / "manifest.json", value)
    receipt = review.load_json(study / "completion-receipt.json")
    receipt["manifest_sha256"] = review.digest(study / "manifest.json")
    review.write_json(study / "completion-receipt.json", receipt)
    with pytest.raises(ValueError, match="path"):
        review.build_packet(study, tmp_path / "not-created")


def test_schedule_disagreement_and_unplanned_trial_rejected(tmp_path):
    study = make_study(tmp_path)
    path = study / "trials" / "synthetic-one.json.gz"
    row = json.loads(gzip.decompress(path.read_bytes()))
    row["method"] = "not-the-scheduled-method"
    path.write_bytes(gzip.compress(review.encoded(row), mtime=0))
    reseal(study)
    with pytest.raises(ValueError, match="schedule"):
        review.build_packet(study, tmp_path / "not-created")


def test_scoring_agreement_disagreement_missingness_and_no_filled_adjudication(tmp_path):
    packet, _ = packet_fixture(tmp_path)
    first = human_export(packet, tmp_path / "first.json", "synthetic-rater-A")
    second = human_export(packet, tmp_path / "second.json", "synthetic-rater-B", state="violated", linked=None)
    result = review.score_reviews(first, second, packet, tmp_path / "scores")
    assert result["targets"]["state"]["raw_agreement"] == 0
    assert result["targets"]["state"]["cohen_kappa"] == 0
    assert result["targets"]["action_linked"]["paired_answered"] == 0
    assert result["targets"]["action_linked"]["raw_agreement"] is None
    assert result["targets"]["action_linked"]["cohen_kappa"] is None
    assert result["targets"]["report_state_alignment"]["raw_agreement"] == 1
    assert result["targets"]["report_state_alignment"]["cohen_kappa"] is None
    adjudication = review.load_json(tmp_path / "scores" / "adjudication.json")
    assert adjudication["adjudicator_id"] == ""
    assert all(item["adjudicated_label"] is None for dispute in adjudication["items"]
               for item in dispute["targets"].values())
    assert adjudication["items"][0]["targets"]["action_linked"]["disposition"] == "missing"


def test_kappa_numeric_reference_and_explicit_unknown_is_answered():
    # Two categories agree in three of four; balanced margins give chance agreement .5.
    result = review.agreement(["satisfied", "satisfied", "violated", "violated"],
                              ["satisfied", "violated", "violated", "violated"],
                              review.CATEGORIES["state"])
    assert result["raw_agreement"] == .75 and result["cohen_kappa"] == .5
    explicit = review.agreement(["unknown", None], ["unknown", "satisfied"], review.CATEGORIES["state"])
    assert explicit["paired_answered"] == 1 and explicit["first_answered"] == 1


def test_identity_prose_replacement_does_not_cascade_into_another_original_id():
    value = {"operation_id": "long-original-operation", "actor": "action-1",
             "message": "long-original-operation and action-1"}
    normalized = review.normalized_identities(value)
    assert normalized["message"] == f"{normalized['operation_id']} and {normalized['actor']}"


def test_identity_alias_cannot_turn_an_expected_value_mismatch_into_a_match():
    value = {"operation_id": "long-original-operation", "expected": {"state": "action-1"},
             "records": [{"state": "long-original-operation"}]}
    normalized = review.normalized_identities(value)
    assert value["expected"]["state"] != value["records"][0]["state"]
    assert normalized["expected"]["state"] != normalized["records"][0]["state"]
    assert normalized["records"][0]["state"] == normalized["operation_id"]


def test_identity_substitution_preserves_all_string_equality_relations():
    values = ["long-original-operation", "action-1", "blind-action-1", "actor-1",
              "prefix action-1 suffix", "prefix long-original-operation suffix",
              "prefix blind-action-1 suffix", "long-original-operation", "opaque-actor"]
    original = {"operation_id": "long-original-operation", "actor": "opaque-actor", "values": values}
    normalized = review.normalized_identities(original)["values"]
    for first in range(len(values)):
        for second in range(len(values)):
            assert (values[first] == values[second]) == (normalized[first] == normalized[second])


def test_forbidden_nested_business_value_is_rejected_rather_than_semantically_edited():
    row = synthetic_row("synthetic-nested")
    row["trajectory"][2]["observation"]["records"][0]["state"] = {"hidden_world": "secret"}
    with pytest.raises(ValueError, match="forbidden"):
        review.public_card(row)


def test_all_unavailable_slots_are_retained_without_generated_cards(tmp_path):
    row = synthetic_row("synthetic-all-failed")
    row["status"] = "failed"
    schedule = [{key: row[key] for key in
                 ("trial_id", "case_id", "family_id", "domain", "seed", "method")}]
    study = seal(tmp_path / "study", schedule, [row])
    output = tmp_path / "packet"
    summary = review.build_packet(study, output)
    assert summary["failed"] == 1 and summary["unique_cards"] == 0
    first = human_export(output, tmp_path / "first.json", "synthetic-rater-A")
    second = human_export(output, tmp_path / "second.json", "synthetic-rater-B")
    result = review.score_reviews(first, second, output, tmp_path / "scores")
    assert result["targets"]["state"]["raw_agreement"] is None
    assert result["targets"]["state"]["kappa_undefined_reason"] == "no paired answers"


@pytest.mark.parametrize("mutation", ["packet", "blank", "duplicate", "unknown-card", "invalid", "same-reviewer"])
def test_invalid_review_exports_rejected(tmp_path, mutation):
    packet, _ = packet_fixture(tmp_path)
    first = human_export(packet, tmp_path / "first.json", "synthetic-rater-A")
    second = human_export(packet, tmp_path / "second.json", "synthetic-rater-B")
    value = review.load_json(second)
    if mutation == "packet":
        value["packet_id"] = "different-packet"
    elif mutation == "blank":
        value["reviewer_id"] = ""
    elif mutation == "duplicate":
        value["labels"].append(copy.deepcopy(value["labels"][0]))
    elif mutation == "unknown-card":
        value["labels"][0]["card_id"] = "unknown-card"
    elif mutation == "invalid":
        value["labels"][0]["state"] = "physically-true"
    else:
        value["reviewer_id"] = "synthetic-rater-A"
    review.write_json(second, value)
    with pytest.raises(ValueError):
        review.score_reviews(first, second, packet, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_packet_tampering_rejected_before_score(tmp_path):
    packet, _ = packet_fixture(tmp_path)
    first = human_export(packet, tmp_path / "first.json", "synthetic-rater-A")
    second = human_export(packet, tmp_path / "second.json", "synthetic-rater-B")
    with (packet / "rubric.md").open("a") as stream:
        stream.write("tampered")
    with pytest.raises(ValueError, match="hash"):
        review.score_reviews(first, second, packet, tmp_path / "not-created")


def test_html_escapes_embedded_payload_and_offline_export_script(tmp_path):
    packet, _ = packet_fixture(tmp_path)
    value = review.load_json(packet / "cards.json")
    value["cards"][0]["evidence"]["injected"] = "</script><img src=x onerror=alert(1)>"
    rendered = review.viewer(value, review.load_json(packet / "reviewer-template.json"))
    assert "</script><img" not in rendered
    assert "\\u003c/script>" in rendered
    assert "fetch(" not in rendered and "https://" not in rendered
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable for offline viewer export execution check")
    data = re.search(r'<script type="application/json" id="data">(.*?)</script>', rendered, re.S).group(1)
    script = re.search(r'</script><script>(.*?)</script>', rendered, re.S).group(1)
    harness = r"""
const vm=require('vm'),assert=require('assert');
const elements={};const targets=['state','action_linked','report_state_alignment'];
function element(){return {value:'',textContent:'',options:[],append(option){this.options.push(option);},click(){}};}
for(const id of ['data','rubric','card','reviewer','evidence','witnesses','comment','message','previous','next','export','import'])elements[id]=element();
elements.data.textContent=INPUT;
const choices=[['satisfied','violated','unknown'],['true','false','unknown'],['supported','contradicted','unassessable']];
const selects=targets.map((target,i)=>({...element(),dataset:{target},options:choices[i].map(value=>({value}))}));let exported;
const context={document:{getElementById:id=>elements[id],querySelectorAll:()=>selects,createElement:()=>element()},Blob:class{constructor(parts){exported=parts.join('');}},URL:{createObjectURL:()=>'',revokeObjectURL(){}},setTimeout:()=>{}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
elements.reviewer.value='synthetic-browser-rater';
selects[0].value='satisfied';selects[1].value='true';selects[2].value='supported';
elements.witnesses.value='observation-1\neffect-1';elements.comment.value='Synthetic browser test';elements.export.onclick();
const result=JSON.parse(exported);assert.equal(result.reviewer_id,'synthetic-browser-rater');assert.equal(result.labels[0].state,'satisfied');assert.deepEqual(result.labels[0].witnesses,['observation-1','effect-1']);
result.reviewer_id='synthetic-resumed-rater';result.labels[0].comment='Resumed synthetic annotation';
elements.import.onchange({target:{files:[{text:async()=>JSON.stringify(result)}]}}).then(()=>{
assert.equal(elements.reviewer.value,'synthetic-resumed-rater');assert.equal(elements.comment.value,'Resumed synthetic annotation');elements.export.onclick();process.stdout.write(exported);});
"""
    harness = harness.replace("INPUT", json.dumps(data)).replace("SCRIPT", json.dumps(script))
    executed = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=True)
    export = json.loads(executed.stdout)
    assert export["packet_id"] == value["packet_id"]
    assert export["labels"][0]["report_state_alignment"] == "supported"
    assert export["reviewer_id"] == "synthetic-resumed-rater"


def test_cli_build_and_score_modes(tmp_path, capsys):
    study = make_study(tmp_path)
    packet = tmp_path / "packet"
    assert review.main(["--study-dir", str(study), "--output", str(packet)]) == 0
    assert json.loads(capsys.readouterr().out)["unique_cards"] == 1
    first = human_export(packet, tmp_path / "first.json", "synthetic-rater-A")
    second = human_export(packet, tmp_path / "second.json", "synthetic-rater-B")
    assert review.main(["--score", str(first), str(second), "--packet", str(packet),
                        "--output", str(tmp_path / "scores")]) == 0
    assert json.loads(capsys.readouterr().out)["targets"]["state"]["raw_agreement"] == 1
