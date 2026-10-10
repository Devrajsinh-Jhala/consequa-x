"""Independent, bounded outcome evidence and effect-origin regression tests."""

from copy import deepcopy
from dataclasses import replace
import unittest

from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.models import Action, Observation, OriginStatus, OutcomeContract, VerificationStatus
from consequa_x.verification import RefundVerifier, verify


def refund_action(*, exact_count=1, stability_ms=20, registered_at_ms=10):
    expected = {"payment_id": "pay_42", "amount_minor": 200_000, "currency": "INR"}
    return Action(
        action_id="action_1", trace_id="trace_1", actor="agent", name="refund",
        arguments=expected, registered_at_ms=registered_at_ms,
        contract=OutcomeContract("contract_1", "refund_processed", expected, 100,
                                 exact_count=exact_count, stability_ms=stability_ms),
    )


def effect(**changes):
    return {
        "effect_id": "effect_1", "payment_id": "pay_42", "amount_minor": 200_000,
        "currency": "INR", "committed_at_ms": 40, "status": "processed",
        "action_id": "action_1", "attempt_id": "attempt_1", "actor": "agent", **changes,
    }


def observation(*records, **changes):
    return Observation(
        **{
            "observation_id": "obs_1", "source": "independent_ledger",
            "observed_at_ms": 200, "as_of_ms": 200, "scope": {"payment_id": "pay_42"},
            "records": tuple(records), "complete": True, "available": True, **changes,
        }
    )


class RefundVerificationTests(unittest.TestCase):
    def assert_bound_evidence(self, result, view):
        self.assertEqual(len(result.evidence), 1)
        evidence = result.evidence[0]
        self.assertEqual(evidence.observation_id, view.observation_id)
        self.assertEqual(evidence.source, view.source)
        self.assertEqual(evidence.as_of_ms, view.as_of_ms)
        self.assertEqual(evidence.details["scope"], view.scope)
        self.assertEqual(evidence.details["records"], list(view.records))
        self.assertEqual(evidence.details["watermark_ms"], view.as_of_ms)
        self.assertEqual(evidence.details["complete"], view.complete)
        self.assertEqual(evidence.details["available"], view.available)
        self.assertEqual(result.observed_at_ms, view.observed_at_ms)

    def test_positive_result_binds_source_and_final_counts(self):
        view = observation(effect())
        result = verify(refund_action(), view)
        self.assertEqual(result.status, VerificationStatus.SATISFIED)
        self.assertEqual(result.origin, OriginStatus.CONFIRMED)
        self.assertEqual(result.effect_ids, ("effect_1",))
        self.assertEqual(result.attributable_effect_ids, ("effect_1",))
        self.assert_bound_evidence(result, view)
        details = result.evidence[0].details
        self.assertEqual(details["horizon_ms"], 120)
        self.assertEqual(details["matching_count"], 1)
        self.assertEqual(details["eligible_count"], 1)
        self.assertEqual(details["peak_matching_count"], 1)
        self.assertEqual(details["relevant_count"], 1)

    def test_absence_is_negative_only_after_exhaustive_horizon(self):
        view = observation(as_of_ms=120)
        result = verify(refund_action(), view)
        self.assertEqual(result.status, VerificationStatus.VIOLATED)
        self.assertEqual(result.origin, OriginStatus.UNKNOWN)
        self.assertEqual(result.effect_ids, ())
        self.assert_bound_evidence(result, view)
        self.assertEqual(result.evidence[0].details["matching_count"], 0)

    def test_unavailable_incomplete_wrong_scope_and_early_views_abstain(self):
        cases = [
            {"available": False}, {"complete": False},
            {"scope": {}}, {"scope": {"payment_id": "pay_other"}},
            {"scope": {"payment_id": "pay_42", "currency": "USD"}},
            {"as_of_ms": 99}, {"as_of_ms": 100}, {"as_of_ms": 119},
        ]
        for present in (False, True):
            for changes in cases:
                with self.subTest(present=present, changes=changes):
                    view = observation(*(effect(),) if present else (), **changes)
                    result = verify(refund_action(), view)
                    self.assertEqual(result.status, VerificationStatus.UNKNOWN)
                    self.assertEqual(result.origin, OriginStatus.UNKNOWN)
                    self.assertEqual(result.effect_ids, ())
                    self.assert_bound_evidence(result, view)

    def test_deadline_and_horizon_boundaries_are_inclusive(self):
        for committed in (10, 40, 100):
            with self.subTest(committed=committed):
                result = verify(refund_action(), observation(effect(committed_at_ms=committed),
                                                              as_of_ms=120))
                self.assertEqual(result.status, VerificationStatus.SATISFIED)
        result = verify(refund_action(), observation(effect(committed_at_ms=101)))
        self.assertEqual(result.status, VerificationStatus.VIOLATED)
        self.assertEqual(result.evidence[0].details["eligible_count"], 0)

    def test_effects_outside_registration_to_horizon_are_irrelevant(self):
        for committed in (9, 121, 200):
            with self.subTest(committed=committed):
                result = verify(refund_action(), observation(effect(committed_at_ms=committed)))
                self.assertEqual(result.status, VerificationStatus.VIOLATED)
                self.assertEqual(result.effect_ids, ())
                self.assertEqual(result.origin, OriginStatus.UNKNOWN)
        result = verify(refund_action(), observation(
            effect(), effect(effect_id="later", committed_at_ms=121)))
        self.assertEqual(result.status, VerificationStatus.SATISFIED)
        self.assertEqual(result.effect_ids, ("effect_1",))

    def test_reversal_through_horizon_violates_but_later_reversal_does_not(self):
        for reversed_at in (40, 100, 119, 120, 121, 200):
            with self.subTest(reversed_at=reversed_at):
                view = observation(effect(status="reversed", reversed_at_ms=reversed_at))
                result = verify(refund_action(), view)
                expected = (VerificationStatus.VIOLATED if reversed_at <= 120
                            else VerificationStatus.SATISFIED)
                self.assertEqual(result.status, expected)
                self.assertEqual(result.origin, OriginStatus.CONFIRMED)
                self.assert_bound_evidence(result, view)

    def test_distinct_duplicate_effects_are_violation_not_malformed(self):
        view = observation(effect(), effect(effect_id="effect_2", attempt_id="attempt_2"))
        result = verify(refund_action(), view)
        self.assertEqual(result.status, VerificationStatus.VIOLATED)
        self.assertEqual(result.origin, OriginStatus.CONFIRMED)
        self.assertEqual(result.effect_ids, ("effect_1", "effect_2"))
        self.assertEqual(result.evidence[0].details["matching_count"], 2)

    def test_duplicate_during_stability_is_unsafe_including_temporary_duplicate(self):
        for reversed_at in (None, 115, 120, 121):
            with self.subTest(reversed_at=reversed_at):
                extra = effect(effect_id="late_retry", committed_at_ms=110)
                if reversed_at is not None:
                    extra.update(status="reversed", reversed_at_ms=reversed_at)
                result = verify(refund_action(), observation(effect(), extra))
                self.assertEqual(result.status, VerificationStatus.VIOLATED)
                self.assertEqual(result.evidence[0].details["eligible_count"], 1)
                self.assertEqual(result.evidence[0].details["peak_matching_count"], 2)
                self.assertIn("late_retry", result.attributable_effect_ids)

    def test_compensated_extra_before_deadline_does_not_break_future_stability(self):
        extra = effect(effect_id="earlier_retry", committed_at_ms=50,
                       status="reversed", reversed_at_ms=100)
        result = verify(refund_action(), observation(effect(), extra))
        self.assertEqual(result.status, VerificationStatus.SATISFIED)
        self.assertEqual(result.evidence[0].details["peak_matching_count"], 1)

    def test_late_replacement_does_not_hide_original_witness_reversal(self):
        result = verify(refund_action(), observation(
            effect(status="reversed", reversed_at_ms=110),
            effect(effect_id="replacement", committed_at_ms=110),
        ))
        self.assertEqual(result.status, VerificationStatus.VIOLATED)
        self.assertEqual(result.evidence[0].details["matching_count"], 1)
        self.assertEqual(result.evidence[0].details["eligible_count"], 0)
        self.assertEqual(result.evidence[0].details["peak_matching_count"], 1)

    def test_count_contracts_zero_exact_two_and_at_least_one(self):
        duplicate_view = observation(effect(), effect(effect_id="effect_2"))
        self.assertEqual(verify(refund_action(exact_count=2), duplicate_view).status,
                         VerificationStatus.SATISFIED)
        self.assertEqual(verify(refund_action(exact_count=None), duplicate_view).status,
                         VerificationStatus.SATISFIED)
        self.assertEqual(verify(refund_action(exact_count=0), observation()).status,
                         VerificationStatus.SATISFIED)
        self.assertEqual(verify(refund_action(exact_count=0), observation(effect())).status,
                         VerificationStatus.VIOLATED)
        self.assertEqual(verify(refund_action(exact_count=None), observation()).status,
                         VerificationStatus.VIOLATED)
        late = observation(effect(committed_at_ms=110))
        self.assertEqual(verify(refund_action(exact_count=None), late).status,
                         VerificationStatus.VIOLATED)

    def test_wrong_amount_currency_and_partial_effect_fail_state_with_confirmed_origin(self):
        for changes in ({"amount_minor": 100_000}, {"amount_minor": 300_000},
                        {"currency": "USD"}):
            with self.subTest(changes=changes):
                result = verify(refund_action(), observation(effect(**changes)))
                self.assertEqual(result.status, VerificationStatus.VIOLATED)
                self.assertEqual(result.origin, OriginStatus.CONFIRMED)
                self.assertEqual(result.attributable_effect_ids, ("effect_1",))

    def test_external_actor_without_action_id_satisfies_state_without_agent_origin(self):
        external = effect(actor="external_operator")
        external.pop("action_id")
        external.pop("attempt_id")
        result = verify(refund_action(), observation(external))
        self.assertEqual(result.status, VerificationStatus.SATISFIED)
        self.assertEqual(result.origin, OriginStatus.OTHER_ACTOR)
        self.assertEqual(result.effect_ids, ("effect_1",))
        self.assertEqual(result.attributable_effect_ids, ())

    def test_absent_or_insufficient_provenance_preserves_state_but_abstains_on_origin(self):
        cases = [
            {}, {"actor": "agent"}, {"attempt_id": "attempt_1"},
            {"action_id": "different_action", "actor": "agent"},
        ]
        for provenance in cases:
            with self.subTest(provenance=provenance):
                record = effect()
                for key in ("action_id", "attempt_id", "actor"):
                    record.pop(key)
                record.update(provenance)
                result = verify(refund_action(), observation(record))
                self.assertEqual(result.status, VerificationStatus.SATISFIED)
                self.assertEqual(result.origin, OriginStatus.UNKNOWN)
                self.assertEqual(result.attributable_effect_ids, ())

    def test_action_id_is_a_provider_origin_witness_without_actor_or_attempt(self):
        record = effect()
        record.pop("actor")
        record.pop("attempt_id")
        result = verify(refund_action(), observation(record))
        self.assertEqual(result.origin, OriginStatus.CONFIRMED)
        self.assertEqual(result.attributable_effect_ids, ("effect_1",))

    def test_conflicting_actor_and_action_id_abstains_on_origin_without_rejecting_state(self):
        result = verify(refund_action(), observation(effect(actor="external_operator")))
        self.assertEqual(result.status, VerificationStatus.SATISFIED)
        self.assertEqual(result.origin, OriginStatus.UNKNOWN)
        self.assertEqual(result.attributable_effect_ids, ())

    def test_malformed_records_abstain_and_keep_source_binding(self):
        invalid_changes = [
            {"effect_id": []}, {"effect_id": ""}, {"effect_id": " "},
            {"payment_id": []}, {"payment_id": ""}, {"payment_id": "pay_other"},
            {"amount_minor": True}, {"amount_minor": 1.0}, {"amount_minor": 0},
            {"amount_minor": -1}, {"amount_minor": "200000"},
            {"currency": []}, {"currency": ""},
            {"committed_at_ms": True}, {"committed_at_ms": 1.0},
            {"committed_at_ms": -1}, {"committed_at_ms": 201},
            {"status": []}, {"status": {}}, {"status": None}, {"status": "pending"},
            {"status": "reversed"}, {"reversed_at_ms": None},
            {"status": "reversed", "reversed_at_ms": 39},
            {"status": "reversed", "reversed_at_ms": 201},
            {"status": "reversed", "reversed_at_ms": True},
            {"status": "reversed", "reversed_at_ms": 80.0},
            {"status": "processed", "reversed_at_ms": 80},
        ]
        for key in ("actor", "action_id", "attempt_id"):
            invalid_changes.extend({key: value} for value in (None, {}, [], 1, True, "", " "))
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                view = observation(effect(**changes))
                result = verify(refund_action(), view)
                self.assertEqual(result.status, VerificationStatus.UNKNOWN)
                self.assertEqual(result.origin, OriginStatus.UNKNOWN)
                self.assert_bound_evidence(result, view)

    def test_missing_required_fields_and_repeated_source_record_are_unknown(self):
        fields = ("effect_id", "payment_id", "amount_minor", "currency", "committed_at_ms", "status")
        for field in fields:
            with self.subTest(field=field):
                record = effect()
                record.pop(field)
                view = observation(record)
                result = verify(refund_action(), view)
                self.assertEqual(result.status, VerificationStatus.UNKNOWN)
                self.assert_bound_evidence(result, view)
        result = verify(refund_action(), observation(effect(), effect()))
        self.assertEqual(result.status, VerificationStatus.UNKNOWN)

    def test_verification_never_mutates_source_action_or_returned_evidence(self):
        action = refund_action()
        view = observation(effect(), scope={"payment_id": "pay_42", "metadata": {"label": "ledger"}})
        before_view, before_action = deepcopy(view.to_dict()), deepcopy(action.to_dict())
        result = RefundVerifier().verify(action, view)
        self.assertEqual(view.to_dict(), before_view)
        self.assertEqual(action.to_dict(), before_action)
        result.evidence[0].details["scope"]["metadata"]["label"] = "changed"
        result.evidence[0].details["records"][0]["amount_minor"] = 1
        self.assertEqual(view.to_dict(), before_view)
        self.assertEqual(action.to_dict(), before_action)

    def test_unsupported_or_malformed_contract_is_rejected(self):
        action = refund_action()
        for contract in (
            replace(action.contract, predicate="arbitrary_python"),
            replace(action.contract, expected={}),
            replace(action.contract, expected={**action.contract.expected, "unexpected": 1}),
            replace(action.contract, expected={**action.contract.expected, "payment_id": " "}),
            replace(action.contract, expected={**action.contract.expected, "amount_minor": True}),
            replace(action.contract, expected={**action.contract.expected, "amount_minor": 0}),
            replace(action.contract, expected={**action.contract.expected, "currency": ""}),
            replace(action.contract, deadline_ms=9),
        ):
            with self.subTest(contract=contract), self.assertRaises(ValueError):
                verify(replace(action, contract=contract), observation())

    def test_actual_readback_not_tool_acknowledgement_determines_state(self):
        for fault, expected_status in (
            (Fault.CLEAN, VerificationStatus.SATISFIED),
            (Fault.TIMEOUT_AFTER_COMMIT, VerificationStatus.SATISFIED),
            (Fault.TIMEOUT_BEFORE_COMMIT, VerificationStatus.VIOLATED),
            (Fault.FALSE_SUCCESS, VerificationStatus.VIOLATED),
            (Fault.PARTIAL_EFFECT, VerificationStatus.VIOLATED),
            (Fault.DUPLICATE_EFFECT, VerificationStatus.VIOLATED),
        ):
            with self.subTest(fault=fault):
                action = refund_action(registered_at_ms=0)
                world = PaymentWorld()
                world.refund(action, "attempt_1", fault)
                world.advance(120)
                view = world.read_refunds("pay_42")
                snapshot = world.snapshot()
                result = verify(action, view)
                self.assertEqual(result.status, expected_status)
                self.assertEqual(world.snapshot(), snapshot)
                self.assert_bound_evidence(result, view)

    def test_actual_external_readback_preserves_other_actor_origin(self):
        action = refund_action(registered_at_ms=0)
        world = PaymentWorld()
        effect_id = world.external_refund("pay_42", 200_000)
        world.advance(120)
        result = verify(action, world.read_refunds("pay_42"))
        self.assertEqual(result.status, VerificationStatus.SATISFIED)
        self.assertEqual(result.origin, OriginStatus.OTHER_ACTOR)
        self.assertEqual(result.effect_ids, (effect_id,))
        self.assertEqual(result.attributable_effect_ids, ())


if __name__ == "__main__":
    unittest.main()
