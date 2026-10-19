"""Independent study audit controls; no model calls or provider dependencies."""

from dataclasses import replace
import json
from pathlib import Path
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_matched_local_study as analysis
from consequa_x.models import Action, Observation, OutcomeContract


def slot(number, model="model-a", case="case-a", repetition=0):
    return {"slot_id": f"episode_{number}", "model": model, "prompt_version": "profile-a",
            "case_id": case, "family_id": f"family-{case}", "repetition": repetition}


def semantic_rows(selected, *, predicted=True, gold=True):
    return [{"slot": selected, "method": method,
             "prediction": {"state": predicted, "action_linked": predicted, "origin": "confirmed"},
             "gold": {"state": gold, "action_linked": gold, "origin": "confirmed"},
             "evidence_supported": {"state": True, "action_linked": True}}
            for method in analysis.METHODS]


def test_missing_executions_remain_in_each_planned_stratum_and_yield():
    completed, failed = slot(0), slot(1)
    partial, unstarted = slot(2, "model-b", "case-b", 1), slot(3, "model-b", "case-b", 1)
    receipts = [{"slot": selected, "status": status} for selected, status in (
        (completed, "completed"), (failed, "failed"),
        (partial, "interrupted_partial"), (unstarted, "unstarted"))]
    calls = [{"slot_id": selected["slot_id"]} for selected in (completed, completed, failed, partial)]
    rows = semantic_rows(completed)
    groups = analysis.build_strata(rows, receipts, calls)
    key_a = json.dumps({"model": "model-a", "prompt_version": "profile-a"}, sort_keys=True)
    key_b = json.dumps({"model": "model-b", "prompt_version": "profile-a"}, sort_keys=True)
    observed = groups["model/prompt_version"][key_a]
    assert observed["planned_episodes"] == observed["started_episodes"] == 2
    assert observed["attempted_chat_calls"] == 3
    assert observed["episode_status"] == {
        "completed": 1, "failed": 1, "interrupted_partial": 0, "unstarted": 0}
    state = observed["summary"]["consequa_state_origin"]["state"]
    assert state["correct_yield"]["value"] == 1
    assert state["full_planned_correct_yield"] == {"numerator": 1, "denominator": 2, "value": .5}
    missing = groups["model/prompt_version"][key_b]
    assert missing["planned_episodes"] == 2 and missing["started_episodes"] == 1
    assert missing["attempted_chat_calls"] == 1
    assert missing["episode_status"] == {
        "completed": 0, "failed": 0, "interrupted_partial": 1, "unstarted": 1}
    for method in analysis.METHODS:
        for target in ("state", "action_linked", "origin"):
            metric = missing["summary"][method][target]
            assert metric["completed"] == 0 and metric["gold_assessable"] == 0
            assert metric["correct_yield"]["value"] is None
            assert metric["claim_error"]["value"] is None
            assert metric["full_planned_correct_yield"] == {"numerator": 0, "denominator": 2, "value": 0}
    # Each partition covers the complete fixed schedule, including empty groups.
    for partition in groups.values():
        assert sum(group["planned_episodes"] for group in partition.values()) == 4
        assert sum(group["attempted_chat_calls"] for group in partition.values()) == 4


def test_unassessable_gold_and_wrong_outputs_never_inflate_planned_yield():
    rows = semantic_rows(slot(0), predicted=True, gold=False)
    rows += semantic_rows(slot(1), predicted=None, gold=None)
    result = analysis.summarize(rows, planned_episodes=6)
    state = result["consequa_state_origin"]["state"]
    assert state["completed"] == 2 and state["gold_assessable"] == 1
    assert state["wrong_claims"] == 1 and state["false_positive"] == 1
    assert state["full_planned_correct_yield"] == {"numerator": 0, "denominator": 6, "value": 0}
    assert analysis.summarize([], planned_episodes=0)["response_only"]["state"][
        "full_planned_correct_yield"]["value"] is None


def test_accounting_rejects_duplicate_or_unknown_slots_and_small_denominator():
    receipt = {"slot": slot(0), "status": "unstarted"}
    with pytest.raises(ValueError, match="Duplicate"):
        analysis.episode_accounting([receipt, receipt], [])
    with pytest.raises(ValueError, match="Unknown"):
        analysis.episode_accounting([{**receipt, "status": "discarded"}], [])
    with pytest.raises(ValueError, match="denominator"):
        analysis.summarize(semantic_rows(slot(0)), planned_episodes=0)


def action(exact_count=1):
    expected = {"payment_id": "payment", "amount_minor": 100, "currency": "INR"}
    return Action(action_id="action", actor="agent", name="refund", arguments=expected, registered_at_ms=5,
                  contract=OutcomeContract(contract_id="contract", predicate="refund_processed", expected=expected, deadline_ms=10,
                                  exact_count=exact_count, stability_ms=10))


def effect(number, committed, reversed_at=None, *, actor="agent", amount=100):
    row = {"kind": "refund", "effect_id": f"refund-{number}", "payment_id": "payment",
           "amount_minor": amount, "currency": "INR", "committed_at_ms": committed,
           "status": "processed" if reversed_at is None else "reversed", "actor": actor}
    if actor == "agent":
        row["action_id"] = "action"
    if reversed_at is not None:
        row["reversed_at_ms"] = reversed_at
    return row


def observation(history):
    return Observation(observation_id="observation", source="ledger", observed_at_ms=25, as_of_ms=25, scope={"payment_id": "payment"},
                       records=tuple({key: value for key, value in row.items() if key != "kind"}
                             for row in history))


@pytest.mark.parametrize("history,state,linked", [
    ([], False, False),
    ([effect(0, 5)], True, True),
    ([effect(0, 10)], True, True),
    ([effect(0, 11)], False, False),
    ([effect(0, 5, 20)], False, False),
    ([effect(0, 5, 21)], True, True),
    ([effect(0, 5), effect(1, 15, 16)], False, False),
    ([effect(0, 5), effect(1, 15, 15)], True, True),
    ([effect(0, 5, actor="operator")], True, False),
    ([effect(0, 5, amount=90)], False, False),
])
def test_ledger_gold_has_explicit_timing_count_and_origin_controls(history, state, linked):
    gold = analysis.ledger_gold(action(), history)
    assert gold["state"] is state and gold["action_linked"] is linked
    public = analysis.public_reference(action(), observation(history))
    assert public["state"] is state and public["action_linked"] is linked


def test_independent_tick_and_event_predicates_agree_on_random_ledger_controls():
    rng = random.Random(20261018)
    for _ in range(1500):
        history = []
        for number in range(rng.randrange(6)):
            committed = rng.randrange(26)
            reversal = rng.randrange(committed, 26) if rng.randrange(3) == 0 else None
            history.append(effect(number, committed, reversal,
                                  actor=rng.choice(("agent", "operator")),
                                  amount=rng.choice((90, 100, 100))))
        selected = action(rng.choice((None, 0, 1, 2)))
        gold = analysis.ledger_gold(selected, history)
        public = analysis.public_reference(selected, observation(history))
        assert public["state"] == gold["state"] and public["origin"] == gold["origin"]
        # The public linkage rule conservatively abstains for mixed provenance;
        # the hidden complete ledger can still have a definite negative target.
        if public["action_linked"] is not None:
            assert public["action_linked"] == gold["action_linked"]
        # Removing public provenance must not change global-state semantics.
        stripped = replace(observation(history), records=tuple(
            {key: value for key, value in row.items() if key not in {"actor", "action_id"}}
            for row in observation(history).records))
        assert analysis.public_reference(selected, stripped)["state"] == gold["state"]
