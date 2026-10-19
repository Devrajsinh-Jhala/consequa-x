"""Provider response/effect divergence and world-isolation fixture tests."""

from __future__ import annotations

from dataclasses import replace
import unittest

from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.models import Action, OutcomeContract, ResponseStatus


def refund_action(
    *, amount: int = 200_000, key: str | None = None, action_id: str = "action_1"
) -> Action:
    arguments = {"payment_id": "pay_42", "amount_minor": amount, "currency": "INR"}
    return Action(
        action_id=action_id,
        actor="agent",
        name="refund",
        arguments=arguments,
        registered_at_ms=0,
        contract=OutcomeContract(
            contract_id="contract_1",
            predicate="refund_processed",
            expected=dict(arguments),
            deadline_ms=100,
        ),
        idempotency_key=key,
    )


def gold_effects(world: PaymentWorld) -> tuple[dict, ...]:
    return tuple(record for record in world.ground_truth if record["kind"] == "refund")


def gold_attempts(world: PaymentWorld) -> tuple[dict, ...]:
    return tuple(record for record in world.ground_truth if record["kind"] == "execution_attempt")


class PaymentWorldTests(unittest.TestCase):
    def test_clean_refund_response_and_independent_evidence(self) -> None:
        world = PaymentWorld(seed=19)
        response = world.refund(refund_action(), "attempt_1")
        view = world.read_refunds("pay_42")
        self.assertEqual(response.status, ResponseStatus.SUCCESS)
        self.assertEqual(response.time_ms, 1)
        self.assertEqual(view.as_of_ms, 1)
        self.assertEqual(len(view.records), 1)
        self.assertEqual(view.records[0]["amount_minor"], 200_000)
        self.assertEqual(view.records[0]["action_id"], "action_1")
        self.assertEqual(view.records[0]["attempt_id"], "attempt_1")
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 800_000)

    def test_faults_have_distinct_public_status_and_gold_effects(self) -> None:
        expected = {
            Fault.CLEAN: (ResponseStatus.SUCCESS, 1),
            Fault.FAIL_BEFORE_DISPATCH: (ResponseStatus.ERROR, 0),
            Fault.TIMEOUT_BEFORE_COMMIT: (ResponseStatus.TIMEOUT, 0),
            Fault.TIMEOUT_AFTER_COMMIT: (ResponseStatus.TIMEOUT, 1),
            Fault.FALSE_SUCCESS: (ResponseStatus.SUCCESS, 0),
            Fault.DELAYED_VISIBILITY: (ResponseStatus.SUCCESS, 1),
            Fault.PARTIAL_EFFECT: (ResponseStatus.SUCCESS, 1),
            Fault.DUPLICATE_EFFECT: (ResponseStatus.SUCCESS, 2),
            Fault.WRONG_PARAMETER: (ResponseStatus.SUCCESS, 1),
            Fault.WRONG_TARGET: (ResponseStatus.SUCCESS, 1),
        }
        for fault, (status, count) in expected.items():
            with self.subTest(fault=fault):
                world = PaymentWorld({"pay_42": 1_000_000, "pay_other": 1_000_000})
                response = world.refund(refund_action(), "attempt_1", fault)
                self.assertEqual(response.status, status)
                self.assertEqual(len(gold_effects(world)), count)
                (attempt,) = gold_attempts(world)
                self.assertEqual(attempt["fault"], fault.value)
                self.assertEqual(attempt["fault_applied"], fault is not Fault.CLEAN)
                self.assertEqual(attempt["response_status"], status.value)
                self.assertEqual(attempt["response_result"], response.result)
                self.assertEqual(
                    set(attempt["committed_effect_ids"]),
                    {record["effect_id"] for record in gold_effects(world)},
                )

    def test_clean_and_false_success_are_observationally_same_provider_result(self) -> None:
        clean, false = PaymentWorld(), PaymentWorld()
        clean_response = clean.refund(refund_action(), "attempt_1")
        false_response = false.refund(refund_action(), "attempt_1", Fault.FALSE_SUCCESS)
        self.assertEqual(clean_response, false_response)
        self.assertEqual(len(clean.read_refunds("pay_42").records), 1)
        self.assertEqual(false.read_refunds("pay_42").records, ())

    def test_timeout_does_not_disclose_commit_status(self) -> None:
        before, after = PaymentWorld(), PaymentWorld()
        self.assertEqual(
            before.refund(refund_action(), "attempt_1", Fault.TIMEOUT_BEFORE_COMMIT),
            after.refund(refund_action(), "attempt_1", Fault.TIMEOUT_AFTER_COMMIT),
        )
        self.assertEqual(before.read_refunds("pay_42").records, ())
        self.assertEqual(len(after.read_refunds("pay_42").records), 1)

    def test_duplicate_partial_refunds_fit_original_balance(self) -> None:
        world = PaymentWorld()
        response = world.refund(refund_action(amount=400_000), "attempt_1", Fault.DUPLICATE_EFFECT)
        self.assertEqual(response.status, ResponseStatus.SUCCESS)
        records = world.read_refunds("pay_42").records
        self.assertEqual(len(records), 2)
        self.assertEqual(sum(item["amount_minor"] for item in records), 800_000)
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 200_000)
        self.assertEqual(len({item["effect_id"] for item in records}), 2)

    def test_duplicate_fault_insufficient_funds_is_atomic(self) -> None:
        world = PaymentWorld()
        response = world.refund(refund_action(amount=600_000), "attempt_1", Fault.DUPLICATE_EFFECT)
        self.assertEqual(response.status, ResponseStatus.ERROR)
        self.assertEqual(response.result["code"], "insufficient_balance")
        self.assertEqual(world.read_refunds("pay_42").records, ())
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 1_000_000)

    def test_unsafe_retry_can_duplicate_requested_partial_refund(self) -> None:
        world = PaymentWorld()
        action = refund_action(amount=400_000)
        lost = world.refund(action, "attempt_1", Fault.TIMEOUT_AFTER_COMMIT)
        retry = world.refund(action, "attempt_2")
        self.assertEqual(lost.status, ResponseStatus.TIMEOUT)
        self.assertEqual(retry.status, ResponseStatus.SUCCESS)
        view = world.read_refunds("pay_42")
        self.assertEqual({item["action_id"] for item in view.records}, {"action_1"})
        self.assertEqual({item["attempt_id"] for item in view.records}, {"attempt_1", "attempt_2"})
        self.assertEqual(sum(item["amount_minor"] for item in view.records), 800_000)

    def test_stable_key_prevents_retry_effect_and_survives_timeout(self) -> None:
        world = PaymentWorld()
        action = refund_action(key="refund:pay_42:request_1")
        first = world.refund(action, "attempt_1", Fault.TIMEOUT_AFTER_COMMIT)
        retry = world.refund(action, "attempt_2", Fault.DUPLICATE_EFFECT)
        self.assertEqual(first.status, ResponseStatus.TIMEOUT)
        self.assertEqual(retry.status, ResponseStatus.SUCCESS)
        self.assertEqual(len(world.read_refunds("pay_42").records), 1)
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 800_000)
        self.assertNotEqual(first.provider_request_id, retry.provider_request_id)
        self.assertEqual(gold_effects(world)[0]["attempt_id"], "attempt_1")
        first_attempt, retry_attempt = gold_attempts(world)
        self.assertFalse(first_attempt["cache_hit"])
        self.assertTrue(retry_attempt["cache_hit"])
        self.assertFalse(retry_attempt["fault_applied"])
        self.assertEqual(retry_attempt["fault"], Fault.DUPLICATE_EFFECT.value)
        self.assertEqual(retry_attempt["committed_effect_ids"], [])
        self.assertEqual(retry_attempt["result_effect_ids"], first_attempt["committed_effect_ids"])
        self.assertEqual(
            retry_attempt["cache_origin"],
            {
                "action_id": "action_1",
                "attempt_id": "attempt_1",
                "provider_request_id": first.provider_request_id,
                "time_ms": first.time_ms,
            },
        )

    def test_key_rejects_changed_amount_without_more_effects(self) -> None:
        world = PaymentWorld()
        world.refund(refund_action(key="stable"), "attempt_1")
        response = world.refund(refund_action(amount=300_000, key="stable"), "attempt_2")
        self.assertEqual(response.status, ResponseStatus.ERROR)
        self.assertEqual(response.result["code"], "idempotency_payload_mismatch")
        self.assertEqual(len(world.read_refunds("pay_42").records), 1)
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 800_000)

    def test_key_rejects_changed_auxiliary_payload(self) -> None:
        world = PaymentWorld()
        action = refund_action(key="stable")
        world.refund(action, "attempt_1")
        changed = replace(action, arguments={**action.arguments, "memo": "changed"})
        response = world.refund(changed, "attempt_2")
        self.assertEqual(response.result["code"], "idempotency_payload_mismatch")
        self.assertEqual(len(gold_effects(world)), 1)

    def test_uncommitted_timeout_can_retry_same_key(self) -> None:
        world = PaymentWorld()
        action = refund_action(key="stable")
        world.refund(action, "attempt_1", Fault.TIMEOUT_BEFORE_COMMIT)
        response = world.refund(action, "attempt_2")
        self.assertEqual(response.status, ResponseStatus.SUCCESS)
        self.assertEqual(gold_effects(world)[0]["attempt_id"], "attempt_2")

    def test_delay_uses_complete_source_wide_watermark(self) -> None:
        world = PaymentWorld({"pay_42": 1_000_000, "pay_other": 1_000_000})
        world.refund(refund_action(), "attempt_1", Fault.DELAYED_VISIBILITY)
        world.external_refund("pay_other", 100_000)
        hidden = world.read_refunds("pay_42")
        unrelated = world.read_refunds("pay_other")
        self.assertEqual(hidden.records, ())
        self.assertEqual(unrelated.records, ())
        self.assertTrue(hidden.complete)
        self.assertTrue(unrelated.complete)
        self.assertEqual(hidden.scope["lag_ms"], 50)
        self.assertEqual(hidden.as_of_ms, 0)
        world.advance(50)
        visible = world.read_refunds("pay_42")
        self.assertEqual(visible.as_of_ms, 2)
        self.assertEqual(len(visible.records), 1)
        self.assertEqual(len(world.read_refunds("pay_other").records), 1)

    def test_completeness_does_not_reveal_hidden_effect(self) -> None:
        present, absent = PaymentWorld(), PaymentWorld()
        present.refund(refund_action(), "attempt_1")
        absent.refund(refund_action(), "attempt_1", Fault.FALSE_SUCCESS)
        a, b = present.read_refunds("pay_42", lag_ms=50), absent.read_refunds("pay_42", lag_ms=50)
        self.assertEqual(a, b)

    def test_current_read_preserves_history_needed_for_stability_horizon(self) -> None:
        world = PaymentWorld()
        world.refund(refund_action(), "attempt_1")
        effect_id = gold_effects(world)[0]["effect_id"]
        world.advance(9)
        world.reverse(effect_id)
        record = world.read_refunds("pay_42").records[0]
        self.assertEqual(record["committed_at_ms"], 1)
        self.assertEqual(record["reversed_at_ms"], 11)
        self.assertEqual(record["status"], "reversed")
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 1_000_000)
        self.assertEqual(world.ground_truth[-1]["kind"], "synthetic_compensation")

    def test_historical_watermark_does_not_leak_future_reversal(self) -> None:
        world = PaymentWorld()
        world.refund(refund_action(), "attempt_1")
        effect_id = gold_effects(world)[0]["effect_id"]
        world.advance(9)
        world.reverse(effect_id)
        earlier = world.read_refunds("pay_42", lag_ms=1)
        self.assertEqual(earlier.as_of_ms, 10)
        self.assertEqual(earlier.records[0]["status"], "processed")
        self.assertNotIn("reversed_at_ms", earlier.records[0])

    def test_compensation_is_one_time_and_unknown_effect_fails(self) -> None:
        world = PaymentWorld()
        effect_id = world.external_refund("pay_42", 200_000)
        world.reverse(effect_id)
        before = world.snapshot()
        with self.assertRaises(ValueError):
            world.reverse(effect_id)
        with self.assertRaises(ValueError):
            world.reverse("missing")
        self.assertEqual(world.snapshot(), before)

    def test_provenance_can_be_removed_without_removing_state(self) -> None:
        world = PaymentWorld()
        world.refund(refund_action(), "attempt_1")
        record = world.read_refunds("pay_42", include_provenance=False).records[0]
        self.assertNotIn("action_id", record)
        self.assertNotIn("attempt_id", record)
        self.assertNotIn("actor", record)
        self.assertEqual(record["amount_minor"], 200_000)

    def test_external_refund_has_actor_without_agent_action_provenance(self) -> None:
        world = PaymentWorld()
        effect_id = world.external_refund("pay_42", 200_000)
        record = world.read_refunds("pay_42").records[0]
        self.assertEqual(record["effect_id"], effect_id)
        self.assertEqual(record["actor"], "external_operator")
        self.assertNotIn("action_id", record)
        self.assertNotIn("attempt_id", record)

    def test_unavailable_read_has_no_records_and_no_effect_leak(self) -> None:
        world = PaymentWorld()
        world.external_refund("pay_42", 200_000)
        view = world.read_refunds("pay_42", available=False)
        self.assertFalse(view.available)
        self.assertTrue(view.complete)
        self.assertEqual(view.records, ())

    def test_wrong_target_uses_existing_alternative_and_correct_scope(self) -> None:
        world = PaymentWorld({"pay_42": 1_000_000, "pay_other": 1_000_000})
        response = world.refund(refund_action(), "attempt_1", Fault.WRONG_TARGET)
        self.assertEqual(response.result["payment_id"], "pay_42")
        self.assertEqual(world.read_refunds("pay_42").records, ())
        self.assertEqual(len(world.read_refunds("pay_other").records), 1)
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 1_000_000)

    def test_wrong_target_does_not_invent_funds(self) -> None:
        world = PaymentWorld()
        response = world.refund(refund_action(), "attempt_1", Fault.WRONG_TARGET)
        self.assertEqual(response.status, ResponseStatus.ERROR)
        self.assertEqual(response.result["code"], "alternative_payment_unavailable")
        self.assertEqual(gold_effects(world), ())
        self.assertEqual(len(gold_attempts(world)), 1)

    def test_snapshot_fork_and_evidence_are_deeply_independent(self) -> None:
        original = {"pay_42": 1_000_000}
        world = PaymentWorld(original)
        original["pay_42"] = 0
        action = refund_action(key="stable")
        world.refund(action, "attempt_1")
        snapshot = world.snapshot()
        snapshot["payments"]["pay_42"] = 0
        snapshot["effects"][0]["amount_minor"] = 1
        snapshot["idempotency"]["stable"]["result"]["amount_minor"] = 1
        snapshot["execution_attempts"][0]["request"]["arguments"]["amount_minor"] = 1
        snapshot["idempotency"]["stable"]["origin"]["attempt_id"] = "changed"
        gold = gold_effects(world)
        gold[0]["amount_minor"] = 1
        attempts = gold_attempts(world)
        attempts[0]["response_result"]["amount_minor"] = 1
        view = world.read_refunds("pay_42")
        with self.assertRaises(TypeError):
            view.records[0]["amount_minor"] = 1
        fork = world.fork()
        fork.reverse(gold_effects(fork)[0]["effect_id"])
        fork.external_refund("pay_42", 50_000)
        fork.advance(99)
        self.assertEqual(world.time_ms, 1)
        self.assertEqual(world.snapshot()["payments"]["pay_42"], 800_000)
        self.assertEqual(gold_effects(world)[0]["amount_minor"], 200_000)
        self.assertEqual(gold_effects(world)[0]["status"], "processed")
        self.assertEqual(gold_attempts(world)[0]["response_result"]["amount_minor"], 200_000)
        self.assertEqual(gold_attempts(world)[0]["request"]["arguments"]["amount_minor"], 200_000)
        replay = world.refund(action, "attempt_2")
        self.assertEqual(replay.result["amount_minor"], 200_000)
        self.assertNotEqual(world.snapshot(), fork.snapshot())

    def test_idempotent_retry_cannot_claim_the_original_action_provenance(self) -> None:
        world = PaymentWorld()
        first_action = refund_action(key="shared", action_id="original_action")
        world.refund(first_action, "attempt_1")
        second_action = replace(first_action, action_id="later_action", actor="other_actor")
        response = world.refund(second_action, "attempt_2")
        self.assertEqual(response.status, ResponseStatus.SUCCESS)
        (record,) = world.read_refunds("pay_42").records
        self.assertEqual(record["action_id"], "original_action")
        self.assertEqual(record["actor"], "agent")
        replay = gold_attempts(world)[1]
        self.assertEqual(replay["action_id"], "later_action")
        self.assertEqual(replay["cache_origin"]["action_id"], "original_action")
        self.assertEqual(replay["committed_effect_ids"], [])

    def test_invalid_refund_input_returns_validation_error_with_auditable_attempt(self) -> None:
        action = refund_action()
        invalid = [
            ([], "invalid_payment_id"),
            ({}, "invalid_payment_id"),
            (None, "invalid_payment_id"),
            ("", "invalid_payment_id"),
            ("missing", "payment_not_found"),
        ]
        for payment_id, code in invalid:
            with self.subTest(payment_id=payment_id):
                world = PaymentWorld()
                bad = replace(action, arguments={**action.arguments, "payment_id": payment_id})
                response = world.refund(bad, "attempt_1", Fault.DUPLICATE_EFFECT)
                self.assertEqual(response.status, ResponseStatus.ERROR)
                self.assertEqual(response.result["code"], code)
                self.assertEqual(world.snapshot()["payments"]["pay_42"], 1_000_000)
                (attempt,) = gold_attempts(world)
                self.assertFalse(attempt["fault_applied"])
                self.assertEqual(attempt["committed_effect_ids"], [])
                self.assertEqual(attempt["request"]["arguments"]["payment_id"], payment_id)

    def test_invalid_caller_mutated_payload_does_not_enter_gold_as_non_json(self) -> None:
        world = PaymentWorld()
        action = refund_action()
        # Captured payloads are read-only; this deliberately bypasses that guard.
        dict.__setitem__(action.arguments, "memo", float("nan"))
        response = world.refund(action, "attempt_1")
        self.assertEqual(response.result["code"], "invalid_payload")
        (attempt,) = gold_attempts(world)
        self.assertFalse(attempt["request_payload_valid"])
        self.assertIsNone(attempt["request"]["arguments"])
        self.assertEqual(gold_effects(world), ())

    def test_invalid_refund_amount_cannot_decrease_balance(self) -> None:
        for amount in (True, 0, -1, 1.5, [], {}, None, "200000"):
            with self.subTest(amount=amount):
                world = PaymentWorld()
                action = refund_action()
                action = replace(action, arguments={**action.arguments, "amount_minor": amount})
                response = world.refund(action, "attempt_1")
                self.assertEqual(response.status, ResponseStatus.ERROR)
                self.assertEqual(response.result["code"], "invalid_amount")
                self.assertEqual(world.snapshot()["payments"]["pay_42"], 1_000_000)
                self.assertEqual(gold_effects(world), ())

    def test_wrong_parameter_and_partial_faults_do_not_cross_balance_bounds(self) -> None:
        for fault in (Fault.WRONG_PARAMETER, Fault.PARTIAL_EFFECT):
            with self.subTest(fault=fault):
                world = PaymentWorld({"pay_42": 1})
                response = world.refund(refund_action(amount=1), "attempt_1", fault)
                self.assertEqual(response.status, ResponseStatus.ERROR)
                self.assertEqual(world.snapshot()["payments"]["pay_42"], 1)
                self.assertEqual(gold_effects(world), ())

    def test_completed_history_copies_do_not_change_after_future_execution(self) -> None:
        world = PaymentWorld()
        world.refund(refund_action(key="stable"), "attempt_1")
        captured = world.snapshot()
        captured_truth = world.ground_truth
        world.refund(refund_action(key="stable"), "attempt_2")
        world.reverse(gold_effects(world)[0]["effect_id"])
        self.assertEqual(len(captured["execution_attempts"]), 1)
        self.assertEqual(captured["effects"][0]["status"], "processed")
        self.assertEqual(len(captured_truth), 2)
        self.assertEqual(captured_truth[0]["status"], "processed")

    def test_fork_preserves_deterministic_counters_and_idempotency(self) -> None:
        world = PaymentWorld(seed=23)
        world.refund(refund_action(key="stable"), "attempt_1")
        fork = world.fork()
        self.assertEqual(world.snapshot(), fork.snapshot())
        self.assertEqual(
            world.refund(refund_action(key="stable"), "attempt_2"),
            fork.refund(refund_action(key="stable"), "attempt_2"),
        )
        self.assertEqual(world.snapshot(), fork.snapshot())

    def test_bad_clock_and_balances_are_rejected(self) -> None:
        world = PaymentWorld()
        for value in (-1, True, 0.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                world.advance(value)
        self.assertEqual(world.time_ms, 0)
        with self.assertRaises(ValueError):
            PaymentWorld({"pay_42": -1})
        with self.assertRaises(ValueError):
            PaymentWorld({"pay_42": True})
        with self.assertRaises(ValueError):
            world.external_refund("pay_42", 1_000_001)
        with self.assertRaises(ValueError):
            world.external_refund("missing", 1)
        self.assertEqual(world.time_ms, 0)


if __name__ == "__main__":
    unittest.main()
