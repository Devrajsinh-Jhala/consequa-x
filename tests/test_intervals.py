"""Independent tail-inversion and finite-distribution checks for intervals."""

from decimal import Decimal, localcontext
from fractions import Fraction
import math

import pytest

from consequa_x.benchmark.intervals import (
    binomial_difference_interval, binomial_interval, bounded_mean_interval,
)


def decimal_tail(total, successes, probability, lower):
    p = Decimal.from_float(probability)
    indices = range(successes, total + 1) if lower else range(successes + 1)
    return sum(Decimal(math.comb(total, count)) * p**count * (1-p)**(total-count)
               for count in indices)


@pytest.mark.parametrize("successes,total,confidence", [
    (1, 2, .95), (1, 16, .95), (4, 20, .9), (8, 16, .95),
    (15, 16, .99), (3, 64, .95), (63, 64, .95), (37, 100, .95),
])
def test_exact_interval_inverts_independent_decimal_tails(successes, total, confidence):
    lower, upper = binomial_interval(successes, total, confidence=confidence)
    with localcontext() as context:
        context.prec = 80
        expected = Decimal.from_float((1-confidence)/2)
        for endpoint, low in ((lower, True), (upper, False)):
            probability = decimal_tail(total, successes, endpoint, low)
            assert float(probability) == pytest.approx(float(expected), abs=2e-13, rel=2e-11)
    assert lower < successes / total < upper


def test_published_nist_90_percent_example():
    assert binomial_interval(4, 20, confidence=.9) == pytest.approx(
        (.07135388430861805, .40102811733197496), abs=2e-14)


@pytest.mark.parametrize("method", ["wilson", "clopper_pearson"])
def test_homogeneous_samples_retain_uncertainty_and_exact_probability_endpoints(method):
    zero = binomial_interval(0, 16, method=method)
    full = binomial_interval(16, 16, method=method)
    assert zero[0] == 0 and full[1] == 1
    assert 0 < zero[1] < 1 and 0 < full[0] < 1
    assert zero[1] == pytest.approx(1-full[0])
    assert zero[1] == pytest.approx(.19360768053443644 if method == "wilson" else .2059072142078227)


@pytest.mark.parametrize("method", ["wilson", "clopper_pearson"])
def test_high_confidence_and_tiny_confidence_remain_finite(method):
    for confidence in (math.nextafter(1., 0.), 1e-300):
        for count in (0, 1, 8, 16):
            low, high = binomial_interval(count, 16, method=method, confidence=confidence)
            assert math.isfinite(low) and math.isfinite(high)
            assert 0 <= low <= count/16 <= high <= 1
    low, high = binomial_difference_interval(0, 16, 16, 16,
                                            confidence=math.nextafter(1., 0.))
    assert -1 <= low <= high <= 1


@pytest.mark.parametrize("successes,total", [(True, 2), (1, False), (-1, 2),
                                             (3, 2), (0, 0), (1.5, 2), (1, 2.)])
def test_counts_are_strict(successes, total):
    with pytest.raises(ValueError):
        binomial_interval(successes, total)


@pytest.mark.parametrize("confidence", [True, 0, 1, -1, math.nan, math.inf, "95%"])
def test_confidence_is_strict(confidence):
    for function in (lambda: binomial_interval(1, 2, confidence=confidence),
                     lambda: bounded_mean_interval([0., 1.], confidence=confidence),
                     lambda: binomial_difference_interval(1, 2, 1, 2, confidence=confidence)):
        with pytest.raises(ValueError):
            function()


def test_unknown_method_is_rejected():
    with pytest.raises(ValueError):
        binomial_interval(1, 2, method="unknown")


@pytest.mark.parametrize("total", [8, 16, 32, 64])
def test_exact_binomial_coverage_on_predeclared_probability_grid(total):
    intervals = [binomial_interval(count, total) for count in range(total+1)]
    for q in (Fraction(0), Fraction(1,100), Fraction(1,20), Fraction(1,10), Fraction(1,4),
              Fraction(1,2), Fraction(3,4), Fraction(9,10), Fraction(19,20),
              Fraction(99,100), Fraction(1)):
        weights = [math.comb(total, count)*q**count*(1-q)**(total-count)
                   for count in range(total+1)]
        assert sum(weights) == 1
        covered = sum(weight for weight, (low, high) in zip(weights, intervals)
                      if low <= float(q) <= high)
        assert float(covered) >= .95 - 1e-14


def test_difference_uses_two_marginal_failure_allowances():
    full = binomial_interval(4, 16, confidence=.975)
    empty = binomial_interval(2, 16, confidence=.975)
    assert binomial_difference_interval(4, 16, 2, 16) == pytest.approx(
        (full[0]-empty[1], full[1]-empty[0]), abs=1e-14)
    assert binomial_difference_interval(0, 16, 0, 16)[0] < 0
    assert binomial_difference_interval(0, 16, 0, 16)[1] > 0


def test_pair_interval_does_not_collapse_and_respects_known_signed_bounds():
    assert bounded_mean_interval([0.]*16) == pytest.approx((-.6790507578703097, .6790507578703097))
    assert bounded_mean_interval([-1.]*16)[0] == -1
    assert bounded_mean_interval([1.]*16)[1] == 1
    # Hoeffding's two-sided probability bound equals the requested failure allowance.
    width = bounded_mean_interval([0.]*16)[1]
    assert 2 * math.exp(-2 * 16 * width**2 / 4) == pytest.approx(.05)


@pytest.mark.parametrize("values", [[], [math.nan], [math.inf], [True], [2.], [None]])
def test_pair_values_must_be_known_finite_and_within_the_range(values):
    with pytest.raises(ValueError):
        bounded_mean_interval(values)
