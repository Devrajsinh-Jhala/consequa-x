"""Outcome contracts made of several parts, verified from one or several readbacks.

Some consequential actions have more than one required effect: a refund is
issued *and* the ticket is closed, or a refund goes to the card *or* to store
credit. ``all_of`` and ``any_of`` build one outcome contract from part
contracts, each with its own predicate, expected values and timing.
``CompositeVerifier`` checks each part with its own verifier, against the
readback from that part's source, and combines the part receipts with
three-valued logic so that unknown evidence stays unknown:

- ``all_of`` is violated when any part is violated, satisfied when every part
  is satisfied, and unknown otherwise;
- ``any_of`` is satisfied when any part is satisfied, violated when every part
  is violated, and unknown otherwise.

The combined receipt keeps every part's evidence (tagged with the part's
contract ID, status and reason), the union of the parts' effects, and the
parts' findings. Effect identifiers name one effect across the whole trace, as
they do in the evidence graph, so parts that read different sources should use
distinct identifiers.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .errors import ConsequaTypeError, ContractError, ValidationError
from .models import (
    Action,
    Evidence,
    Finding,
    Observation,
    OriginStatus,
    OutcomeContract,
    VerificationResult,
    VerificationStatus,
    _decode_record,
    thaw,
)
from .verification import Verifier, averify, verify


ALL_OF = "all_of"
ANY_OF = "any_of"
COMPOSITE_PREDICATES = (ALL_OF, ANY_OF)

PART_FINDINGS = {
    "PART_VIOLATED": "A required part of the outcome is violated.",
    "PART_UNKNOWN": "The readback cannot settle a part of the outcome.",
    "PART_OTHER_ACTOR": "Another actor produced the effects observed for a part.",
}
"""Finding codes ``CompositeVerifier`` adds to the parts' own findings."""


def _compose(predicate: str, contract_id: str, parts: tuple[OutcomeContract, ...]
             ) -> OutcomeContract:
    if not parts:
        raise ContractError(f"{predicate} needs at least one part contract")
    for part in parts:
        if not isinstance(part, OutcomeContract):
            raise ConsequaTypeError(f"{predicate} parts must be OutcomeContract records")
    deadline = max(part.deadline_ms for part in parts)
    contract = OutcomeContract(
        contract_id=contract_id, predicate=predicate,
        expected={"parts": [part.to_dict() for part in parts]},
        deadline_ms=deadline, exact_count=None,
        stability_ms=max(part.horizon_ms for part in parts) - deadline,
    )
    contract_parts(contract)
    return contract


def all_of(contract_id: str, *parts: OutcomeContract) -> OutcomeContract:
    """An outcome that holds when every part contract holds.

    The combined deadline is the latest part deadline and the horizon is the
    latest part horizon; each part keeps its own timing and count.
    """
    return _compose(ALL_OF, contract_id, parts)


def any_of(contract_id: str, *parts: OutcomeContract) -> OutcomeContract:
    """An outcome that holds when at least one part contract holds."""
    return _compose(ANY_OF, contract_id, parts)


def contract_parts(contract: OutcomeContract) -> tuple[OutcomeContract, ...]:
    """Decode and check the part contracts of an ``all_of`` or ``any_of`` contract.

    Part contract IDs must be distinct and differ from the combined contract's
    ID, every part horizon must fall within the combined horizon, and the
    combined contract has no count of its own (``exact_count`` is ``None``).
    """
    if not isinstance(contract, OutcomeContract):
        raise ConsequaTypeError("contract_parts requires an OutcomeContract")
    if contract.predicate not in COMPOSITE_PREDICATES:
        raise ContractError(f"Not a composite predicate: {contract.predicate!r}")
    expected = thaw(contract.expected)
    if set(expected) != {"parts"} or type(expected["parts"]) is not list:
        raise ContractError(f"{contract.predicate} expects a 'parts' list of part contracts")
    if not expected["parts"]:
        raise ContractError(f"{contract.predicate} needs at least one part contract")
    if contract.exact_count is not None:
        raise ContractError(f"{contract.predicate} contracts have no exact_count of their own")
    parts = []
    for index, item in enumerate(expected["parts"]):
        try:
            parts.append(_decode_record(OutcomeContract, item, f"parts[{index}]"))
        except (TypeError, ValueError) as error:
            raise ContractError(f"Invalid part contract: {error}") from error
    identifiers = [part.contract_id for part in parts]
    if len(set(identifiers)) != len(identifiers) or contract.contract_id in identifiers:
        raise ContractError("Part contract IDs must be distinct and differ from the "
                            "combined contract ID")
    for part in parts:
        if part.horizon_ms > contract.horizon_ms:
            raise ContractError(f"Part {part.contract_id!r} ends after the combined horizon")
        if part.predicate in COMPOSITE_PREDICATES:
            contract_parts(part)
    return tuple(parts)


class CompositeVerifier:
    """Verify an ``all_of`` or ``any_of`` contract part by part.

    ``parts`` maps each part's contract ID to the verifier for that part; a part
    may itself be composite, with a nested ``CompositeVerifier``. ``sources``
    maps a part's contract ID to the observation ``source`` (or sources, for a
    nested composite) it reads. A part without an entry reads every supplied
    readback, which suits a single readback shared by all parts.

    A part whose source supplied no readback is ``unknown``: missing evidence is
    reported, never assumed. Several readbacks from one source for a part that
    reads one, or a supplied readback that no part reads, raise
    ``ValidationError``. Each part receipt is checked as ``verify`` checks any
    receipt before it is combined.
    """

    def __init__(self, parts: Mapping[str, Verifier], *,
                 sources: Mapping[str, str | tuple[str, ...]] | None = None) -> None:
        if not isinstance(parts, Mapping) or not parts:
            raise ConsequaTypeError("parts must map part contract IDs to verifiers")
        self.parts = dict(parts)
        for name, part in self.parts.items():
            if not isinstance(name, str) or not name.strip():
                raise ValidationError("part contract IDs must be nonempty strings")
            if not any(callable(getattr(part, method, None)) for method in
                       ("verify", "verify_readbacks", "averify_readbacks")):
                raise ConsequaTypeError(f"part {name!r} needs a verifier with a verify method")
        self.sources: dict[str, tuple[str, ...]] = {}
        for name, value in dict(sources or {}).items():
            if name not in self.parts:
                raise ValidationError(f"sources names an unknown part: {name!r}")
            names = (value,) if isinstance(value, str) else value
            if (type(names) is not tuple or not names
                    or not all(isinstance(item, str) and item.strip() for item in names)):
                raise ValidationError(f"sources[{name!r}] must be a source name or a tuple of them")
            self.sources[name] = names

    def verify(self, action: Action, observation: Observation) -> VerificationResult:
        """Verify every part against one readback."""
        return self.verify_readbacks(action, (observation,))

    def verify_readbacks(self, action: Action,
                         observations: tuple[Observation, ...]) -> VerificationResult:
        """Verify every part against the readback from its source and combine them."""
        parts, plan = self._plan(action, observations)
        receipts = {}
        for part in parts:
            readback = plan[part.contract_id]
            receipts[part.contract_id] = None if readback is None else verify(
                replace(action, contract=part), readback, verifier=self.parts[part.contract_id])
        return _combine(action, parts, receipts, self.sources)

    async def averify_readbacks(self, action: Action,
                                observations: tuple[Observation, ...]) -> VerificationResult:
        """``verify_readbacks`` when some part verifiers are asynchronous."""
        parts, plan = self._plan(action, observations)
        receipts = {}
        for part in parts:
            readback = plan[part.contract_id]
            receipts[part.contract_id] = None if readback is None else await averify(
                replace(action, contract=part), readback, verifier=self.parts[part.contract_id])
        return _combine(action, parts, receipts, self.sources)

    def _plan(self, action, observations):
        if not isinstance(action, Action):
            raise ConsequaTypeError("CompositeVerifier requires an Action")
        parts = contract_parts(action.contract)
        named = {part.contract_id for part in parts}
        if named != self.parts.keys():
            raise ContractError(f"Verifiers are configured for parts {sorted(self.parts)}, "
                                f"but the contract has parts {sorted(named)}")
        plan: dict[str, Any] = {}
        used: set[str] = set()
        for part in parts:
            identifier = part.contract_id
            sources = self.sources.get(identifier)
            chosen = tuple(item for item in observations
                           if sources is None or item.source in sources)
            several = any(callable(getattr(self.parts[identifier], method, None))
                          for method in ("verify_readbacks", "averify_readbacks"))
            if not chosen:
                plan[identifier] = None
                continue
            if not several and len(chosen) > 1:
                raise ValidationError(
                    f"Part {identifier!r} reads one readback but {len(chosen)} were supplied "
                    "for it; map it to one source with sources=")
            plan[identifier] = chosen if several else chosen[0]
            used.update(item.observation_id for item in chosen)
        unused = [item.source for item in observations if item.observation_id not in used]
        if unused:
            raise ValidationError(f"No part reads the readback from {unused}; check sources=")
        return parts, plan


def _union(groups) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for group in groups:
        for item in group:
            seen.setdefault(item, None)
    return tuple(seen)


def _combine(action: Action, parts: tuple[OutcomeContract, ...],
             receipts: dict[str, VerificationResult | None],
             sources: dict[str, tuple[str, ...]]) -> VerificationResult:
    contract = action.contract
    status_of = {identifier: (receipt.status if receipt else VerificationStatus.UNKNOWN)
                 for identifier, receipt in receipts.items()}
    order = [part.contract_id for part in parts]
    satisfied = [name for name in order if status_of[name] is VerificationStatus.SATISFIED]
    violated = [name for name in order if status_of[name] is VerificationStatus.VIOLATED]
    if contract.predicate == ALL_OF:
        if violated:
            status, deciding = VerificationStatus.VIOLATED, violated
        elif len(satisfied) == len(order):
            status, deciding = VerificationStatus.SATISFIED, order
        else:
            status, deciding = VerificationStatus.UNKNOWN, []
    elif satisfied:
        status, deciding = VerificationStatus.SATISFIED, satisfied
    elif len(violated) == len(order):
        status, deciding = VerificationStatus.VIOLATED, order
    else:
        status, deciding = VerificationStatus.UNKNOWN, []

    known = [receipts[name] for name in order if receipts[name] is not None]
    effect_ids = _union(receipt.effect_ids for receipt in known)
    attributable = _union(receipt.attributable_effect_ids for receipt in known)
    effectful = [receipt for receipt in known if receipt.effect_ids]
    if attributable:
        origin = OriginStatus.CONFIRMED
    elif effectful and all(item.origin is OriginStatus.OTHER_ACTOR for item in effectful):
        origin = OriginStatus.OTHER_ACTOR
    else:
        origin = OriginStatus.UNKNOWN

    targets = [receipts[name].target_effect_ids if receipts[name] else None
               for name in deciding]
    if status is VerificationStatus.UNKNOWN:
        target_ids = None
    elif contract.predicate == ANY_OF and status is VerificationStatus.SATISFIED:
        # One satisfied alternative produced by this action is enough.
        matched = [item for item in targets if item is not None]
        target_ids = _union(matched) if matched else None
    elif any(item is None for item in targets):
        target_ids = None
    elif status is VerificationStatus.SATISFIED and not all(targets):
        # Every part holds, but not every part was produced by this action.
        target_ids = ()
    else:
        target_ids = _union(targets)

    merged: dict[str, tuple[list[str], list[str]]] = {}
    for name in order:
        receipt = receipts[name]
        for finding in receipt.findings if receipt else ():
            ids, details = merged.setdefault(finding.code, ([], []))
            ids.extend(finding.effect_ids)
            details.append(f"{name}: {finding.detail or finding.code}")

    def part_finding(code, names):
        ids, details = merged.setdefault(code, ([], []))
        for name in names:
            receipt = receipts[name]
            ids.extend(receipt.effect_ids if receipt else ())
            details.append(f"{name}: {_part_reason(receipt, sources.get(name))}")

    if status is not VerificationStatus.SATISFIED:
        part_finding("PART_VIOLATED", violated)
        part_finding("PART_UNKNOWN", [name for name in order
                                      if status_of[name] is VerificationStatus.UNKNOWN])
    if origin is not OriginStatus.OTHER_ACTOR:
        part_finding("PART_OTHER_ACTOR", [
            name for name in order if receipts[name] is not None
            and receipts[name].origin is OriginStatus.OTHER_ACTOR])
    findings = tuple(Finding(code=code, effect_ids=_union([ids]), detail="; ".join(details))
                     for code, (ids, details) in merged.items() if details)

    evidence = []
    for part in parts:
        receipt = receipts[part.contract_id]
        for item in receipt.evidence if receipt else ():
            evidence.append(Evidence(
                observation_id=item.observation_id, source=item.source, as_of_ms=item.as_of_ms,
                details={
                    "part_id": part.contract_id, "predicate": part.predicate,
                    "status": receipt.status.value, "origin": receipt.origin.value,
                    "reason": receipt.reason,
                    "target_effect_ids": (None if receipt.target_effect_ids is None
                                          else list(receipt.target_effect_ids)),
                    "findings": [finding.code for finding in receipt.findings],
                    "details": item.details,
                }))
    rule = (f"All {len(order)} parts are required" if contract.predicate == ALL_OF
            else f"Any one of {len(order)} parts suffices")
    summary = "; ".join(f"{name} {status_of[name].value}" for name in order)
    return VerificationResult(
        action_id=action.action_id, contract_id=contract.contract_id, status=status,
        observed_at_ms=max(receipt.observed_at_ms for receipt in known),
        evidence=tuple(evidence), origin=origin, effect_ids=effect_ids,
        attributable_effect_ids=attributable, target_effect_ids=target_ids,
        findings=findings,
        reason=f"{rule}: {summary}",
    )


def _part_reason(receipt: VerificationResult | None, sources: tuple[str, ...] | None) -> str:
    if receipt is None:
        where = f" from {', '.join(sources)}" if sources else ""
        return f"unknown (no readback{where} was supplied)"
    return f"{receipt.status.value} ({receipt.reason})" if receipt.reason else receipt.status.value
