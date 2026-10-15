"""Check the paper's ideal refund game using exact rational enumeration.

This is a mathematical check, independent of Consequa-X code and saved studies.
It does not execute a simulator, replay, verifier, model, or network request.
"""

import argparse
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from itertools import permutations, product
import json
from pathlib import Path


GRID = (Fraction(0), Fraction(1, 5), Fraction(1, 2), Fraction(4, 5), Fraction(1))


def rational(value):
    return str(value)


def enumerate_case(p, q, *, idempotent, target):
    """Enumerate fresh Boolean choices, then all six three-player orders.

    Bits 0, 1 and 2 hold factual selection, retry and stop, respectively.
    Unreached held decisions are inactive in the on-reach game. A selected
    first attempt commits one effect despite its timeout; a retry commits
    another effect unless the logical operation is idempotent. Complete
    exactly-one readback succeeds only at one effect. The stop is a dummy.
    """
    values = {}
    for mask in range(8):
        value = Fraction(0)
        total_weight = Fraction(0)
        for selected, retried in product((False, True), repeat=2):
            weight = (p if selected else 1 - p) * (q if retried else 1 - q)
            selected = bool(mask & 1) or selected
            retried = selected and (bool(mask & 2) or retried)
            effects = int(selected) + (0 if idempotent else int(retried))
            achieved = selected if target == "action" else effects == 1
            value += weight * int(not achieved)
            total_weight += weight
        if total_weight != 1:
            raise AssertionError("Fresh-choice weights do not sum to one")
        values[mask] = value

    shares = [Fraction(0)] * 3
    for order in permutations(range(3)):
        mask = 0
        for player in order:
            after = mask | (1 << player)
            shares[player] += (values[after] - values[mask]) / 6
            mask = after

    simple = idempotent or target == "action"
    expected_values = (
        (1 - p, Fraction(0), 1 - p, Fraction(0))
        if simple
        else (1 - p * (1 - q), q, Fraction(1), Fraction(1))
    )
    expected_shares = (
        (-(1 - p), Fraction(0), Fraction(0))
        if simple
        else (-(1 - p) * (1 - q) / 2, (1 + p) * (1 - q) / 2, Fraction(0))
    )
    expected_endpoint = -(1 - p) if simple else p * (1 - q)
    expected_interaction = Fraction(0) if simple else (1 - p) * (1 - q)
    endpoint = values[7] - values[0]
    interaction = values[3] - values[1] - values[2] + values[0]
    if tuple(values[i] for i in range(4)) != expected_values:
        raise AssertionError("Enumerated coalition law differs from closed form")
    if tuple(shares) != expected_shares:
        raise AssertionError("Six-order allocation differs from closed form")
    if endpoint != expected_endpoint or sum(shares) != endpoint:
        raise AssertionError("Endpoint or Shapley efficiency differs")
    if interaction != expected_interaction:
        raise AssertionError("Interaction differs from closed form")
    if any(values[mask | 4] != values[mask] for mask in range(4)):
        raise AssertionError("Final stop is not a dummy")

    return {
        "p": rational(p),
        "q": rational(q),
        "idempotent": idempotent,
        "target": target,
        "coalition_bad_rates_by_mask": [rational(values[i]) for i in range(8)],
        "enumerated_shares": [rational(value) for value in shares],
        "closed_form_shares": [rational(value) for value in expected_shares],
        "endpoint_difference": rational(endpoint),
        "selection_retry_interaction": rational(interaction),
        "passed": True,
    }


def verify():
    cases = [
        enumerate_case(p, q, idempotent=idempotent, target=target)
        for p, q in product(GRID, repeat=2)
        for idempotent, target in product((False, True), ("action", "consequence"))
    ]
    return {
        "schema_version": "analytic-refund-reference-check-v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "passed": True,
        "arithmetic": "Exact fractions; no floating-point interval comparisons",
        "grid": [rational(value) for value in GRID],
        "case_count": len(cases),
        "controls": {"idempotent": [False, True], "target": ["action", "consequence"]},
        "coalition_values_enumerated": len(cases) * 8,
        "weighted_choice_components_enumerated": len(cases) * 8 * 4,
        "permutation_orders_enumerated": len(cases) * 6,
        "framework_imports": 0,
        "framework_or_simulator_calls": 0,
        "model_calls": 0,
        "network_calls": 0,
        "saved_study_files_read": 0,
        "assumptions": [
            "Independent ideal Bernoulli selection p and retry q, not a statement about model seeds",
            "Planted factual refund/retry/stop; on-reach holding, with final stop a dummy",
            "First timeout commits; at most one subsequent clean retry; sufficient funds and deadline",
            "Unsafe retries create a second effect; idempotency reuses the first effect",
            "Exactly-one complete horizon-covering state readback; no other actor or reversal",
            "Linked target agrees only with sufficient provenance; missing evidence remains unknown",
            "No finite call-cap truncation; a budget control can refuse a finite estimate of this ideal law",
        ],
        "limitations": [
            "Finite grid check complements the algebraic derivation; it is not a proof for arbitrary policies",
            "Does not execute or independently validate simulator/verifier/replay implementations",
            "No sampling coverage, model recovery, strict-game completion or empirical superiority claim",
            "Repeated target/idempotency controls are not independent empirical replications",
        ],
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(f"Passed {receipt['case_count']} exact-rational cases; saved {args.output}")


if __name__ == "__main__":
    main()
