"""Offline causal-replay and uncertainty checks; no provider access required."""

import dataclasses
import json
import math
import random
import unittest
from types import SimpleNamespace

from consequa_x.attribution import (
    EffectEstimate,
    InsufficientEvidenceError,
    Intervention,
    ReplayOutcome,
    leave_one_out,
    recency_attribution,
)


class FunctionRunner:
    def __init__(self, function):
        self.function = function
        self.calls = []

    def run(self, intervention, seed):
        self.calls.append((intervention, seed))
        return self.function(intervention, seed)


class AttributionTests(unittest.TestCase):
    def test_interacting_causes_are_not_normalized_into_responsibility(self):
        def replay(intervention, seed):
            removed = intervention.event_id if intervention else None
            selected = removed not in {"authorization", "refund_policy"}
            return ReplayOutcome(selected, selected)

        runner = FunctionRunner(replay)
        estimates = leave_one_out(
            runner,
            [
                Intervention("authorization"),
                Intervention("refund_policy"),
                Intervention("unrelated"),
            ],
        )
        self.assertEqual([item.effect for item in estimates], [1.0, 1.0, 0.0])
        self.assertEqual(sum(item.effect for item in estimates), 2.0)
        self.assertTrue(all(item.unknown_pairs == 0 for item in estimates))
        self.assertGreater(estimates[0].confidence_interval[0], 0.0)
        self.assertLessEqual(estimates[2].confidence_interval[0], 0.0)
        self.assertGreaterEqual(estimates[2].confidence_interval[1], 0.0)

    def test_redundant_causes_can_have_zero_single_intervention_effect(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        estimates = leave_one_out(
            runner, [Intervention("sufficient_a"), Intervention("sufficient_b")]
        )
        self.assertEqual([item.effect for item in estimates], [0.0, 0.0])

    def test_negative_effect_is_preserved(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(
                intervention is not None, intervention is not None
            )
        )
        estimate = leave_one_out(runner, [Intervention("blocker")])[0]
        self.assertEqual(estimate.baseline_rate, 0.0)
        self.assertEqual(estimate.intervention_rate, 1.0)
        self.assertEqual(estimate.effect, -1.0)
        self.assertLess(estimate.confidence_interval[1], 0.0)

    def test_action_selection_and_consequence_are_distinct_targets(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(True, intervention is None)
        )
        action = leave_one_out(runner, [Intervention("execution_context")], target="action")[0]
        consequence = leave_one_out(
            runner, [Intervention("execution_context")], target="consequence"
        )[0]
        self.assertEqual(action.effect, 0.0)
        self.assertEqual(consequence.effect, 1.0)

    def test_factual_replays_are_cached_once_per_seed_across_candidates(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        estimates = leave_one_out(
            runner, [Intervention("a"), Intervention("b")], samples=4, seed=31
        )
        factual_seeds = [seed for intervention, seed in runner.calls if intervention is None]
        self.assertEqual(factual_seeds, [31, 32, 33, 34])
        for event_id in ("a", "b"):
            changed_seeds = [
                seed
                for intervention, seed in runner.calls
                if intervention and intervention.event_id == event_id
            ]
            self.assertEqual(changed_seeds, factual_seeds)
        self.assertEqual(len(runner.calls), 12)
        self.assertEqual(estimates[0].seeds, (31, 32, 33, 34))

    def test_stochastic_replay_is_reproducible_with_matched_randomness(self):
        def replay(intervention, seed):
            threshold = 0.4 if intervention else 0.8
            success = random.Random(seed).random() < threshold
            return ReplayOutcome(success, success)

        first = leave_one_out(
            FunctionRunner(replay), [Intervention("context")], samples=100, seed=7
        )[0]
        second = leave_one_out(
            FunctionRunner(replay), [Intervention("context")], samples=100, seed=7
        )[0]
        self.assertEqual(first, second)
        expected_factual = sum(random.Random(seed).random() < 0.8 for seed in first.seeds) / 100
        expected_changed = sum(random.Random(seed).random() < 0.4 for seed in first.seeds) / 100
        self.assertEqual(first.baseline_rate, expected_factual)
        self.assertEqual(first.intervention_rate, expected_changed)
        self.assertAlmostEqual(first.effect, expected_factual - expected_changed)
        self.assertLessEqual(first.confidence_interval[0], first.effect)
        self.assertGreaterEqual(first.confidence_interval[1], first.effect)
        self.assertGreater(first.confidence_interval[0], 0.0)

    def test_more_replays_narrow_interval_for_same_deterministic_effect(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(intervention is None, intervention is None)
        )
        small = leave_one_out(runner, [Intervention("cause")], samples=2)[0]
        large = leave_one_out(runner, [Intervention("cause")], samples=100)[0]

        def width(estimate):
            return estimate.confidence_interval[1] - estimate.confidence_interval[0]

        self.assertGreater(width(small), width(large))
        self.assertEqual(small.effect, large.effect)
        self.assertGreater(width(large), 0.0)

    def test_wilson_interval_uses_bonferroni_adjusted_marginal_bounds(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(intervention is None, intervention is None)
        )
        estimate = leave_one_out(runner, [Intervention("cause")], samples=20)[0]
        # z = Phi^-1(.9875); exact formula for all-success versus no-success.
        z = 2.241402727604947
        bound = 20 / (20 + z * z)
        self.assertAlmostEqual(estimate.confidence_interval[0], 2 * bound - 1)
        self.assertAlmostEqual(estimate.confidence_interval[1], 1.0)

    def test_deterministic_extremes_include_observed_effect_without_roundoff(self):
        for samples in (2, 3, 20, 21, 39, 100):
            for positive in (False, True):
                with self.subTest(samples=samples, positive=positive):
                    runner = FunctionRunner(
                        lambda intervention, seed: ReplayOutcome(
                            (intervention is None) == positive,
                            (intervention is None) == positive,
                        )
                    )
                    estimate = leave_one_out(runner, [Intervention("cause")], samples=samples)[0]
                    self.assertEqual(estimate.effect, 1.0 if positive else -1.0)
                    endpoint = estimate.confidence_interval[1 if positive else 0]
                    self.assertEqual(endpoint, estimate.effect)
                    self.assertTrue(
                        all(math.isfinite(bound) for bound in estimate.confidence_interval)
                    )

    def test_unknown_factual_consequence_refuses_complete_estimate(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(
                True, None if intervention is None and seed == 2 else True
            )
        )
        with self.assertRaises(InsufficientEvidenceError) as caught:
            leave_one_out(runner, [Intervention("candidate")], samples=4)
        error = caught.exception
        self.assertEqual(error.event_id, "candidate")
        self.assertEqual(error.target, "consequence")
        self.assertEqual(error.samples, 4)
        self.assertEqual(error.known_pairs, 3)
        self.assertEqual(error.unknown_pairs, 1)
        self.assertEqual(error.seeds, (0, 1, 2, 3))
        self.assertIn("No estimate is produced", str(error))
        self.assertNotIn("effect", error.to_dict())

    def test_unknown_intervention_consequence_is_not_counted_as_failure(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(
                True, None if intervention and seed % 2 else True
            )
        )
        with self.assertRaises(InsufficientEvidenceError) as caught:
            leave_one_out(runner, [Intervention("candidate")], samples=4)
        self.assertEqual(caught.exception.known_pairs, 2)
        self.assertEqual(caught.exception.unknown_pairs, 2)

    def test_unknown_in_both_worlds_counts_as_one_unknown_pair(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(True, None if seed == 1 else False)
        )
        with self.assertRaises(InsufficientEvidenceError) as caught:
            leave_one_out(runner, [Intervention("candidate")], samples=3)
        self.assertEqual(caught.exception.known_pairs, 2)
        self.assertEqual(caught.exception.unknown_pairs, 1)

    def test_all_unknown_refuses_without_selection_conditioning(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, None))
        with self.assertRaises(InsufficientEvidenceError) as caught:
            leave_one_out(runner, [Intervention("candidate")], samples=5)
        self.assertEqual(caught.exception.known_pairs, 0)
        self.assertEqual(caught.exception.unknown_pairs, 5)

    def test_later_unknown_candidate_returns_no_partial_result(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(
                True, None if intervention and intervention.event_id == "missing" else True
            )
        )
        with self.assertRaises(InsufficientEvidenceError) as caught:
            leave_one_out(runner, [Intervention("known"), Intervention("missing")], samples=3)
        self.assertEqual(caught.exception.event_id, "missing")

    def test_unknown_consequence_does_not_prevent_action_effect(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(intervention is None, None)
        )
        estimate = leave_one_out(runner, [Intervention("candidate")], samples=4, target="action")[0]
        self.assertEqual(estimate.effect, 1.0)
        self.assertEqual(estimate.unknown_pairs, 0)

    def test_empty_candidates_do_not_run_experiment(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        self.assertEqual(leave_one_out(runner, []), ())
        self.assertEqual(runner.calls, [])

    def test_duplicate_candidate_ids_are_rejected_before_any_replay(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        for duplicate in (
            Intervention("candidate"),
            Intervention("candidate", "replace", {"authorized": False}),
        ):
            with (
                self.subTest(duplicate=duplicate),
                self.assertRaisesRegex(ValueError, "unique event_id"),
            ):
                leave_one_out(runner, [Intervention("candidate"), duplicate])
        self.assertEqual(runner.calls, [])

    def test_runner_must_return_validated_record(self):
        runner = FunctionRunner(
            lambda intervention, seed: SimpleNamespace(
                action_selected=True, consequence_satisfied=True
            )
        )
        with self.assertRaises(TypeError):
            leave_one_out(runner, [Intervention("candidate")])

    def test_invalid_experiment_configuration_is_rejected_before_run(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        for samples in (True, 0, 1, 2.0, math.inf, math.nan):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                leave_one_out(runner, [Intervention("candidate")], samples=samples)
        for seed in (True, 1.0, math.inf, math.nan, "0"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                leave_one_out(runner, [Intervention("candidate")], seed=seed)
        for target in ("responsibility", "", None, []):
            with self.subTest(target=target), self.assertRaises(ValueError):
                leave_one_out(runner, [Intervention("candidate")], target=target)
        with self.assertRaises(TypeError):
            leave_one_out(runner, ["candidate"])
        self.assertEqual(runner.calls, [])

    def test_negative_integer_seed_has_a_reproducible_schedule(self):
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        self.assertEqual(
            leave_one_out(runner, [Intervention("candidate")], samples=2, seed=-3)[0].seeds,
            (-3, -2),
        )

    def test_most_recent_context_can_be_irrelevant_to_experimental_effect(self):
        events = [
            SimpleNamespace(id="authorization", type="user_input", time_ms=1),
            SimpleNamespace(id="irrelevant", type="retrieval", time_ms=9),
            SimpleNamespace(id="decision", type="agent_decision", time_ms=10),
        ]
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(
                intervention is None or intervention.event_id != "authorization",
                intervention is None or intervention.event_id != "authorization",
            )
        )
        estimates = leave_one_out(
            runner, [Intervention("authorization"), Intervention("irrelevant")]
        )
        self.assertEqual(recency_attribution(events, before_ms=10), "irrelevant")
        self.assertEqual(max(estimates, key=lambda item: item.effect).event_id, "authorization")

    def test_recency_excludes_noncontext_and_at_or_after_decision(self):
        events = [
            SimpleNamespace(id="input", type="user_input", time_ms=1),
            SimpleNamespace(id="retrieval", type="retrieval", time_ms=8),
            SimpleNamespace(id="assessment", type="agent_assessment", time_ms=9),
            SimpleNamespace(id="same_time", type="memory_read", time_ms=10),
            SimpleNamespace(id="future", type="system_instruction", time_ms=11),
            SimpleNamespace(id="verification", type="verification", time_ms=12),
        ]
        self.assertEqual(recency_attribution(events, before_ms=10), "retrieval")
        self.assertIsNone(recency_attribution(events, before_ms=0))
        self.assertIsNone(recency_attribution([], before_ms=10))

    def test_recency_tie_uses_input_order_and_accepts_string_enum(self):
        from enum import Enum

        class EventKind(str, Enum):
            MEMORY_READ = "memory_read"

        events = [
            SimpleNamespace(id="first", type="retrieval", time_ms=3),
            SimpleNamespace(id="second", type=EventKind.MEMORY_READ, time_ms=3),
        ]
        self.assertEqual(recency_attribution(events, before_ms=4), "second")
        with self.assertRaises(ValueError):
            recency_attribution(events, before_ms=True)

    def test_typed_records_reject_truthy_values_and_unsupported_interventions(self):
        for action, consequence in ((1, True), (True, 1), (None, True), (True, "true")):
            with (
                self.subTest(action=action, consequence=consequence),
                self.assertRaises(ValueError),
            ):
                ReplayOutcome(action, consequence)
        for event_id in ("", " ", None):
            with self.assertRaises(ValueError):
                Intervention(event_id)
        for kind in ("delete", "", None, []):
            with self.assertRaises(ValueError):
                Intervention("candidate", kind=kind)
        with self.assertRaises(ValueError):
            Intervention("candidate", replacement="ignored")
        self.assertEqual(
            Intervention("candidate", "replace", {"authorized": False}).kind, "replace"
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Intervention("candidate").kind = "replace"

    def test_estimate_constructor_rejects_nonfinite_or_inconsistent_statistics(self):
        fields = dict(
            event_id="candidate",
            target="consequence",
            baseline_rate=0.5,
            intervention_rate=0.0,
            effect=0.5,
            confidence_interval=(-0.1, 1.0),
            samples=2,
            seeds=(0, 1),
        )
        for changed in (
            {"baseline_rate": math.nan},
            {"intervention_rate": math.inf},
            {"effect": -0.5},
            {"confidence_interval": (0.9, 0.1)},
            {"confidence_interval": (-math.inf, 1.0)},
            {"samples": True},
            {"seeds": (0, 0)},
            {"seeds": (0, True)},
            {"unknown_pairs": 1},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                EffectEstimate(**(fields | changed))

    def test_replacement_rejects_nonjson_values_before_experiment(self):
        for replacement in (
            {"value": math.nan},
            [math.inf],
            {-1: "nonstring key"},
            {"value": object()},
            ("tuple",),
        ):
            with self.subTest(replacement=replacement), self.assertRaises((TypeError, ValueError)):
                Intervention("candidate", "replace", replacement)
        cycle = []
        cycle.append(cycle)
        with self.assertRaisesRegex(ValueError, "cyclic"):
            Intervention("candidate", "replace", cycle)

    def test_replacement_is_detached_from_nested_caller_payload(self):
        replacement = {"policy": {"rules": ["authorized"]}}
        candidate = Intervention("candidate", "replace", replacement)
        replacement["policy"]["rules"].append("caller mutation")
        self.assertEqual(candidate.replacement, {"policy": {"rules": ["authorized"]}})

    def test_each_replay_receives_the_original_replacement_payload(self):
        candidate = Intervention("policy", "replace", {"allow": [False]})
        observed = []

        def replay(intervention, seed):
            if intervention is None:
                return ReplayOutcome(True, True)
            allowed = intervention.replacement["allow"][0]
            observed.append(allowed)
            intervention.replacement["allow"][0] = True
            return ReplayOutcome(allowed, allowed)

        first = leave_one_out(FunctionRunner(replay), [candidate], samples=3)[0]
        second = leave_one_out(FunctionRunner(replay), [candidate], samples=3)[0]
        self.assertEqual(observed, [False] * 6)
        self.assertEqual(first, second)
        self.assertEqual(first.effect, 1.0)
        self.assertEqual(candidate.replacement, {"allow": [False]})

    def test_mutated_invalid_replacement_is_rejected_before_baseline_replays(self):
        candidate = Intervention("candidate", "replace", {"value": True})
        candidate.replacement["value"] = math.nan
        runner = FunctionRunner(lambda intervention, seed: ReplayOutcome(True, True))
        with self.assertRaises(ValueError):
            leave_one_out(runner, [candidate])
        self.assertEqual(runner.calls, [])

    def test_exports_are_json_safe_and_keep_signed_effect(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(
                intervention is not None, intervention is not None
            )
        )
        estimate = leave_one_out(runner, [Intervention("blocker")], samples=3)[0]
        serialized = json.loads(json.dumps(estimate.to_dict(), allow_nan=False))
        self.assertEqual(serialized["event_id"], "blocker")
        self.assertEqual(serialized["target"], "consequence")
        self.assertEqual(serialized["baseline_rate"], 0.0)
        self.assertEqual(serialized["intervention_rate"], 1.0)
        self.assertEqual(serialized["effect"], -1.0)
        self.assertEqual(serialized["confidence_interval"][0], -1.0)
        self.assertEqual(serialized["samples"], 3)
        self.assertEqual(serialized["seeds"], [0, 1, 2])
        self.assertEqual(serialized["unknown_pairs"], 0)
        self.assertEqual(
            json.loads(json.dumps(ReplayOutcome(True, None).to_dict(), allow_nan=False)),
            {"action_selected": True, "consequence_satisfied": None},
        )
        self.assertEqual(
            Intervention("context", "replace", {"text": "safe"}).to_dict()["replacement"],
            {"text": "safe"},
        )

    def test_unknown_error_export_preserves_refusal_and_evidence_counts(self):
        runner = FunctionRunner(
            lambda intervention, seed: ReplayOutcome(True, None if seed == 1 else False)
        )
        with self.assertRaises(InsufficientEvidenceError) as caught:
            leave_one_out(runner, [Intervention("context")], samples=3)
        serialized = json.loads(json.dumps(caught.exception.to_dict(), allow_nan=False))
        self.assertEqual(
            serialized,
            {
                "error": "InsufficientEvidenceError",
                "event_id": "context",
                "target": "consequence",
                "samples": 3,
                "known_pairs": 2,
                "unknown_pairs": 1,
                "seeds": [0, 1, 2],
            },
        )

    def test_replacement_export_is_detached_from_record(self):
        candidate = Intervention("context", "replace", {"allow": [False]})
        serialized = candidate.to_dict()
        serialized["replacement"]["allow"][0] = True
        self.assertEqual(candidate.replacement, {"allow": [False]})


if __name__ == "__main__":
    unittest.main()
