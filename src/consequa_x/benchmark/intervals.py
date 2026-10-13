"""Conditional intervals for known binary outcomes and bounded pair means.

These are independently implemented standard statistical methods. The binomial
and concentration statements require independent draws from the declared law;
requested seeds, or observing only complete replays, do not establish that law.
"""

import math
from functools import lru_cache
from statistics import NormalDist
from typing import Iterable, Literal


BinomialMethod = Literal["wilson", "clopper_pearson"]
BINOMIAL_METHODS = ("wilson", "clopper_pearson")


def _confidence(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and 0 < value < 1
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("confidence must be finite and strictly between 0 and 1")


def _counts(successes, total):
    if type(total) is not int or total < 1:
        raise ValueError("total must be a positive integer")
    if type(successes) is not int or not 0 <= successes <= total:
        raise ValueError("successes must be an integer between zero and total")


def _log_binomial_sum(total, probability, first, last):
    """Log probability on an inclusive count range, summed about its mode.

    Adjacent weights are scaled by the largest term on the requested range.
    Both tails are evaluated directly, avoiding subtraction of a tiny tail
    from one. Ratios decrease away from the mode and never overflow.
    """
    if probability == 0:
        return 0. if first == 0 else -math.inf
    if probability == 1:
        return 0. if last == total else -math.inf
    mode = max(first, min(last, math.floor((total + 1) * probability)))
    log_mass = (math.lgamma(total + 1) - math.lgamma(mode + 1)
                - math.lgamma(total - mode + 1) + mode * math.log(probability)
                + (total - mode) * math.log1p(-probability))

    def weights():
        yield 1.
        term = 1.
        for count in range(mode, first, -1):
            term *= (count / (total - count + 1)) * ((1 - probability) / probability)
            if term == 0:
                break
            yield term
        term = 1.
        for count in range(mode, last):
            term *= ((total - count) / (count + 1)) * (probability / (1 - probability))
            if term == 0:
                break
            yield term

    return min(0., log_mass + math.log(math.fsum(weights())))


@lru_cache(maxsize=4096)
def _tail_root(total, successes, log_tail, *, lower):
    lo, hi = 0., 1.
    for _ in range(160):
        mid = lo + (hi - lo) / 2
        if mid == lo or mid == hi:
            break
        value = (_log_binomial_sum(total, mid, successes, total) if lower else
                 _log_binomial_sum(total, mid, 0, successes))
        if (value >= log_tail) == lower:
            hi = mid
        else:
            lo = mid
    # Choose the outward root bracket. The finite numerical implementation is
    # validated against independent high-precision binomial calculations.
    return lo if lower else hi


def binomial_interval(successes: int, total: int, *, confidence: float = .95,
                      method: BinomialMethod = "clopper_pearson") -> tuple[float, float]:
    """Interval for a known binomial probability; endpoints remain exactly 0/1.

    Wilson is a score approximation. Equal-tailed Clopper–Pearson inverts the
    binomial tails and is conservative under the independent binomial model.
    It does not model an uncertain factual baseline or adjust multiplicity.
    """
    _counts(successes, total)
    _confidence(confidence)
    if type(method) is not str or method not in BINOMIAL_METHODS:
        raise ValueError("method must be wilson or clopper_pearson")
    probability = successes / total
    tail = (1 - confidence) / 2
    if method == "wilson":
        z = -NormalDist().inv_cdf(tail)
        scale = 1 + z * z / total
        center = (probability + z * z / (2 * total)) / scale
        margin = z / scale * math.sqrt(
            probability * (1 - probability) / total + z * z / (4 * total * total))
        return (0. if successes == 0 else max(0., center - margin),
                1. if successes == total else min(1., center + margin))
    log_tail = math.log(tail)
    if successes == 0:
        upper = min(1., math.nextafter(-math.expm1(log_tail / total), 1.))
        return 0., upper
    if successes == total:
        lower = max(0., math.nextafter(math.exp(log_tail / total), 0.))
        return lower, 1.
    return (_tail_root(total, successes, log_tail, lower=True),
            _tail_root(total, successes, log_tail, lower=False))


def binomial_difference_interval(full_successes: int, full_total: int,
                                 empty_successes: int, empty_total: int, *,
                                 confidence: float = .95) -> tuple[float, float]:
    """Full-minus-empty interval using two equal-tailed exact marginal intervals.

    Each marginal receives half the failure allowance. A union bound covers
    their difference at least nominally under each binomial marginal model;
    independence BETWEEN marginals is not required for that union bound.
    """
    _counts(full_successes, full_total)
    _counts(empty_successes, empty_total)
    _confidence(confidence)
    # Near confidence one, (1 + confidence)/2 can round to one. Compute the
    # halved marginal tail directly instead of manufacturing an invalid level.
    log_tail = math.log((1 - confidence) / 4)

    def marginal(successes, total):
        lower = (0. if successes == 0 else math.nextafter(math.exp(log_tail / total), 0.)
                 if successes == total else _tail_root(total, successes, log_tail, lower=True))
        upper = (1. if successes == total else math.nextafter(-math.expm1(log_tail / total), 1.)
                 if successes == 0 else _tail_root(total, successes, log_tail, lower=False))
        return max(0., lower), min(1., upper)

    full = marginal(full_successes, full_total)
    empty = marginal(empty_successes, empty_total)
    return full[0] - empty[1], full[1] - empty[0]


def bounded_mean_interval(values: Iterable[float], *, confidence: float = .95,
                          lower: float = -1., upper: float = 1.) -> tuple[float, float]:
    """Two-sided Hoeffding interval for an independent bounded observation mean.

    One Shapley forward/reverse pair is one observation. This uses its declared
    [-1,1] range and does not infer certainty from zero sample variance.
    """
    _confidence(confidence)
    if (type(lower) not in (int, float) or type(upper) not in (int, float)
            or not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper):
        raise ValueError("bounds must be finite numbers with lower < upper")
    observed = tuple(values)
    if not observed or any(type(value) not in (int, float) or not math.isfinite(value)
                           or not lower <= value <= upper for value in observed):
        raise ValueError("values must be nonempty finite observations within the bounds")
    point = math.fsum(value / len(observed) for value in observed)
    width = (upper - lower) * math.sqrt(math.log(2 / (1 - confidence)) / (2 * len(observed)))
    return max(lower, point - width), min(upper, point + width)
