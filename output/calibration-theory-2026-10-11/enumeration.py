"""Enumerate finite interval behavior for the declared two-player refund game.

Standard library only. No model, rollout, production scorer, analytic-reference
module, or random-number generator is invoked. Probability weights and moment
checks use exact fractions. Interval classification uses the current adapter's
declared normal rule and Python's floating-point normal quantile.
"""

import argparse
from fractions import Fraction
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path
from statistics import NormalDist


REFERENCE_SOURCE = "9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0"
PAIRS, ENDPOINT_SAMPLES, CONTRASTIVE_SAMPLES = 16, 16, 16
CONFIDENCE = Fraction(95, 100)
Q_VALUES = (Fraction(1, 10), Fraction(1, 2), Fraction(9, 10))


def fraction_record(value):
    return {"numerator": value.numerator, "denominator": value.denominator,
            "decimal": float(value)}


def normal_interval(center, sample_variance, count):
    # The pair-mean standard error treats a forward/reverse pair as one unit.
    # Independent endpoint full-held observations have zero variance here.
    z = -NormalDist().inv_cdf(float((1 - CONFIDENCE) / 2))
    margin = z * math.sqrt(float(sample_variance / count))
    return float(center) - margin, float(center) + margin


def joint_pair_checks(q):
    """Derive both pair marginals from eight independent A/B/C configurations."""
    support = {}
    for a, b, c in itertools.product((0, 1), repeat=3):
        bad_count = a + b + c
        probability = q**bad_count * (1 - q)**(3 - bad_count)
        x0, x1 = Fraction(b - a, 2), Fraction(-b - c, 2)
        support[x0, x1] = support.get((x0, x1), Fraction(0)) + probability
    assert sum(support.values()) == 1
    selection_mean = sum(x0 * p for (x0, _), p in support.items())
    stop_mean = sum(x1 * p for (_, x1), p in support.items())
    covariance = sum((x0 - selection_mean) * (x1 - stop_mean) * p
                     for (x0, x1), p in support.items())
    selection_variance = sum((x0 - selection_mean)**2 * p for (x0, _), p in support.items())
    stop_variance = sum((x1 - stop_mean)**2 * p for (_, x1), p in support.items())
    sum_variance = sum((x0 + x1 + q)**2 * p for (x0, x1), p in support.items())
    assert selection_mean == 0 and stop_mean == -q
    assert selection_variance == stop_variance == sum_variance == q * (1 - q) / 2
    assert covariance == -q * (1 - q) / 4
    return {"joint_bernoulli_configurations": 8, "probability_mass": fraction_record(sum(support.values())),
            "selection_mean": fraction_record(selection_mean), "stop_mean": fraction_record(stop_mean),
            "each_pair_marginal_variance": fraction_record(selection_variance),
            "pair_covariance": fraction_record(covariance), "pair_sum_variance": fraction_record(sum_variance),
            "mean_coefficient_variance": fraction_record(selection_variance / PAIRS),
            "endpoint_difference_variance": fraction_record(q * (1 - q) / ENDPOINT_SAMPLES),
            "independent_discrepancy_variance": fraction_record(
                q * (1 - q) * (Fraction(1, 2 * PAIRS) + Fraction(1, ENDPOINT_SAMPLES))),
            "all_moment_identities_passed": True}


def enumerate_trinomial(values, probabilities, reference):
    """Enumerate every count triple of P iid pair values with exact weights."""
    count = PAIRS
    mass = covered = degenerate = degenerate_covered = Fraction(0)
    center_mean = center_square = variance_mean = Fraction(0)
    nonzero_boundary_distances = []
    equality_mass = Fraction(0)
    cells = 0
    for first in range(count + 1):
        for second in range(count - first + 1):
            third = count - first - second
            counts = (first, second, third)
            coefficient = math.comb(count, first) * math.comb(count - first, second)
            probability = Fraction(coefficient)
            for p, n in zip(probabilities, counts):
                probability *= p**n
            center = sum(v * n for v, n in zip(values, counts)) / count
            sample_variance = sum((v - center)**2 * n for v, n in zip(values, counts)) / (count - 1)
            lo, hi = normal_interval(center, sample_variance, count)
            includes = lo <= float(reference) <= hi
            mass += probability
            covered += probability * includes
            degenerate += probability * (sample_variance == 0)
            degenerate_covered += probability * (sample_variance == 0 and includes)
            center_mean += probability * center
            center_square += probability * center**2
            variance_mean += probability * sample_variance
            distances = (abs(lo - float(reference)), abs(hi - float(reference)))
            if min(distances) == 0:
                equality_mass += probability
            nonzero_boundary_distances.extend(distance for distance in distances if distance > 0)
            cells += 1
    population_mean = sum(v * p for v, p in zip(values, probabilities))
    population_variance = sum((v - population_mean)**2 * p for v, p in zip(values, probabilities))
    assert mass == 1 and center_mean == population_mean == reference
    assert center_square - center_mean**2 == population_variance / count
    assert variance_mean == population_variance
    assert min(nonzero_boundary_distances) > 1e-12
    return {"reference": fraction_record(reference), "support": [fraction_record(v) for v in values],
            "support_probabilities": [fraction_record(p) for p in probabilities],
            "count_cells_enumerated": cells, "probability_mass": fraction_record(mass),
            "interval_coverage": fraction_record(covered), "interval_exclusion": fraction_record(1 - covered),
            "degenerate_interval_probability": fraction_record(degenerate),
            "covered_degenerate_interval_probability": fraction_record(degenerate_covered),
            "uncovered_degenerate_interval_probability": fraction_record(degenerate - degenerate_covered),
            "exact_boundary_equality_probability": fraction_record(equality_mass),
            "minimum_nonzero_boundary_distance": min(nonzero_boundary_distances),
            "enumerated_estimator_mean": fraction_record(center_mean),
            "enumerated_estimator_variance": fraction_record(center_square - center_mean**2),
            "enumerated_expected_sample_variance": fraction_record(variance_mean),
            "probability_and_moment_checks_passed": True}


def enumerate_endpoint(q):
    """Full-held bad=0; empty-held bad samples are E independent Bernoulli(q)."""
    count = ENDPOINT_SAMPLES
    mass = covered = degenerate = Fraction(0)
    center_mean = center_square = variance_mean = Fraction(0)
    boundary_distances = []
    for bad in range(count + 1):
        probability = math.comb(count, bad) * q**bad * (1 - q)**(count - bad)
        center = -Fraction(bad, count)
        sample_variance = Fraction(bad * (count - bad), count * (count - 1))
        lo, hi = normal_interval(center, sample_variance, count)
        mass += probability
        covered += probability * (lo <= float(-q) <= hi)
        degenerate += probability * (sample_variance == 0)
        center_mean += probability * center
        center_square += probability * center**2
        variance_mean += probability * sample_variance
        boundary_distances.extend(abs(bound - float(-q)) for bound in (lo, hi) if bound != float(-q))
    assert mass == 1 and center_mean == -q
    assert center_square - center_mean**2 == q * (1 - q) / count
    assert variance_mean == q * (1 - q)
    assert min(boundary_distances) > 1e-12
    return {"reference": fraction_record(-q), "count_cells_enumerated": count + 1,
            "probability_mass": fraction_record(mass), "interval_coverage": fraction_record(covered),
            "interval_exclusion": fraction_record(1 - covered),
            "degenerate_interval_probability": fraction_record(degenerate),
            "enumerated_estimator_mean": fraction_record(center_mean),
            "enumerated_estimator_variance": fraction_record(center_square - center_mean**2),
            "enumerated_expected_sample_variance": fraction_record(variance_mean),
            "minimum_nonzero_boundary_distance": min(boundary_distances),
            "probability_and_moment_checks_passed": True}


def results():
    rows = []
    for q in Q_VALUES:
        r = q * (1 - q)
        selection = enumerate_trinomial((Fraction(-1, 2), Fraction(0), Fraction(1, 2)),
                                        (r, 1 - 2 * r, r), Fraction(0))
        stop = enumerate_trinomial((Fraction(-1), Fraction(-1, 2), Fraction(0)),
                                   (q * q, 2 * r, (1 - q)**2), -q)
        rows.append({"retry_probability": fraction_record(q), "joint_pair_audit": joint_pair_checks(q),
            "selection_coefficient": selection, "protective_stop_coefficient": stop,
            "independent_endpoint": enumerate_endpoint(q),
            "empirical_percentile_bootstrap": {
                "samples": CONTRASTIVE_SAMPLES,
                "coverage_upper_bound": fraction_record(1 - q**CONTRASTIVE_SAMPLES - (1 - q)**CONTRASTIVE_SAMPLES),
                "wrong_constant_interval_probability": fraction_record(q**CONTRASTIVE_SAMPLES + (1 - q)**CONTRASTIVE_SAMPLES),
                "bound_is_exact_coverage": False,
                "proof": "All-zero and all-one samples produce constant empirical bootstrap resamples. Their intervals exclude interior q, or q minus a constant factual label. Other samples may also miss truth."}})
    return {"artifact": "finite_conditional_refund_interval_theory", "version": 1,
        "consequa_x_reference_source_revision": REFERENCE_SOURCE,
        "enumerator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "production_code_imported": False, "random_draws": 0, "model_calls": 0,
        "mechanism": {"players": ["deterministic refund selection", "planted timeout stop"],
            "world": "One non-idempotent refund commits before timeout; fresh retry commits a duplicate; stopping preserves one refund.",
            "factual_intervention": "timeout stop forced at a declared phase key",
            "game": "v(S)=q if stop player 1 is unheld; v(S)=0 if player 1 is held",
            "population_shapley": ["0", "-q"], "full_minus_empty": "-q",
            "supported_targets": ["consequence", "action_linked_consequence"],
            "evidence_assumption": "complete timely readback with supported action provenance",
            "coalition_assumption": "all two-player positional coalitions valid; extra fresh terminal decisions are unheld"},
        "settings": {"pairs": PAIRS, "walks_per_pair": 2, "draws_per_coalition_occurrence": 1,
            "endpoint_samples_per_coalition": ENDPOINT_SAMPLES, "contrastive_samples_per_position": CONTRASTIVE_SAMPLES,
            "confidence": float(CONFIDENCE), "variance_ddof": 1,
            "normal_z": -NormalDist().inv_cdf(float((1 - CONFIDENCE) / 2)),
            "independent_inference_unit": "one averaged forward/reverse pair vector",
            "interval_clipping": False, "multiplicity_correction": False},
        "derivation": {"pair_selection": "(B-A)/2", "pair_stop": "-(B+C)/2",
            "coins": "A,B,C independently Bernoulli(q); newly evaluated coalitions use fresh draws",
            "trinomial_weight": "P!/(a!b!c!) * p0^a * p1^b * p2^c, a+b+c=P",
            "endpoint_weight": "choose(E,k) * q^k * (1-q)^(E-k)",
            "pair_interval": "mean(X) plus/minus z * sqrt(sample_variance(X,ddof=1)/P)",
            "endpoint_interval": "D plus/minus z * sqrt((s_empty^2+s_full^2)/E); s_full^2=0",
            "coverage_rule": "inclusive lower <= true parameter <= upper",
            "exactness": "All finite count cells and probability/moment arithmetic use exact fractions. Normal quantiles and boundary classification use floating-point arithmetic; nonzero boundaries exceed 1e-12 from truth."},
        "action_zero_control": {"bad_probability": 0, "contrastive_effects": [0, 0],
            "shapley_values": [0, 0], "endpoint_difference": 0,
            "interval": [0, 0], "interval_coverage": 1,
            "false_nonzero_probability": 0,
            "meaning": "Deterministic known selection target only; degenerate coverage does not validate stochastic intervals."},
        "results": rows, "audit_passed": True,
        "limits": ["This enumerates the declared Consequa-X binary refund adaptation, not upstream CAR or a language model.",
            "Independent Bernoulli draws are mathematical assumptions; requested seeds do not establish independence.",
            "The factual stop is planted, so inference is conditional on its mechanism and capture.",
            "No three-player invalid positional game, missing evidence, budget failure or interaction recovery is covered.",
            "State and linked consequence targets share outcomes and are not independent observations.",
            "The bootstrap expression is an upper bound, not enumeration of bootstrap Monte Carlo coverage.",
            "An audited finite calculation does not establish live-model accuracy, superiority or publication readiness."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a new JSON result file; otherwise print JSON")
    args = parser.parse_args()
    record = results()
    encoded = json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        if args.output.exists():
            raise ValueError("Use a new output filename to preserve existing evidence")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
        print("Finite enumeration passed; saved", args.output.name)


if __name__ == "__main__":
    main()
