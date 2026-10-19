"""Composite contracts: all_of / any_of parts verified from one or several readbacks."""

import asyncio
import json

import pytest

from consequa_x import (
    Action, CompositeVerifier, ConsequaTypeError, ContractError, Observation, OriginStatus,
    OutcomeContract, RecordVerifier, RefundVerifier, Trace, TraceRecorder, ValidationError,
    VerificationResult, VerificationStatus, all_of, any_of, contract_parts, explain,
    poll_readback, render_report, retry_advice, verify,
)
from consequa_x.models import Evidence


REFUND = OutcomeContract(contract_id="refund", predicate="refund_processed",
                         expected={"payment_id": "p-1", "amount_minor": 5000, "currency": "INR"},
                         deadline_ms=100, stability_ms=50)
TICKET = OutcomeContract(contract_id="ticket", predicate="record_present",
                         expected={"ticket_id": "t-9", "state": "closed"},
                         deadline_ms=120, stability_ms=40)
CREDIT = OutcomeContract(contract_id="credit", predicate="record_present",
                         expected={"customer_id": "c-3", "amount_minor": 5000},
                         deadline_ms=100, stability_ms=50)
VERIFIER = CompositeVerifier(
    {"refund": RefundVerifier(), "ticket": RecordVerifier(scope_fields=("ticket_id",))},
    sources={"refund": "payments-db", "ticket": "crm"})


def action(contract=None):
    return Action(action_id="resolve-1", actor="agent", name="resolve_case",
                  arguments={"payment_id": "p-1", "ticket_id": "t-9"}, registered_at_ms=10,
                  contract=contract or all_of("resolve", REFUND, TICKET))


def refund_row(effect_id="rf-1", **fields):
    record = {"effect_id": effect_id, "payment_id": "p-1", "amount_minor": 5000,
              "currency": "INR", "committed_at_ms": 40, "status": "processed",
              "action_id": "resolve-1", "actor": "agent"}
    record.update(fields)
    return {key: value for key, value in record.items() if value is not None}


def ticket_row(effect_id="tk-1", **fields):
    record = {"effect_id": effect_id, "ticket_id": "t-9", "state": "closed",
              "committed_at_ms": 50, "action_id": "resolve-1", "actor": "agent"}
    record.update(fields)
    return {key: value for key, value in record.items() if value is not None}


def payments(*records, watermark=200, **kwargs):
    return Observation(observation_id="payments-1", source="payments-db", observed_at_ms=watermark,
                       as_of_ms=watermark, scope={"payment_id": "p-1"}, records=records, **kwargs)


def crm(*records, watermark=200, **kwargs):
    return Observation(observation_id="crm-1", source="crm", observed_at_ms=watermark + 5,
                       as_of_ms=watermark, scope={"ticket_id": "t-9"}, records=records, **kwargs)


def test_builders_combine_timing_and_keep_each_part():
    contract = all_of("resolve", REFUND, TICKET)
    assert contract.predicate == "all_of" and contract.exact_count is None
    assert contract.deadline_ms == 120 and contract.horizon_ms == 160
    assert contract_parts(contract) == (REFUND, TICKET)
    either = any_of("compensate", REFUND, CREDIT)
    assert either.predicate == "any_of" and either.horizon_ms == 150
    assert json.loads(json.dumps(either.to_dict()))["expected"]["parts"][1]["contract_id"] == "credit"


@pytest.mark.parametrize("contract,message", [
    (OutcomeContract(contract_id="x", predicate="record_present", expected={}, deadline_ms=1),
     "Not a composite"),
    (OutcomeContract(contract_id="x", predicate="all_of", expected={"parts": []},
                     deadline_ms=1, exact_count=None), "at least one part"),
    (OutcomeContract(contract_id="x", predicate="all_of", expected={"items": []},
                     deadline_ms=1, exact_count=None), "'parts' list"),
    (OutcomeContract(contract_id="x", predicate="all_of",
                     expected={"parts": [REFUND.to_dict()]}, deadline_ms=200), "exact_count"),
    (OutcomeContract(contract_id="x", predicate="all_of",
                     expected={"parts": [REFUND.to_dict(), REFUND.to_dict()]},
                     deadline_ms=200, exact_count=None), "distinct"),
    (OutcomeContract(contract_id="refund", predicate="any_of",
                     expected={"parts": [REFUND.to_dict()]}, deadline_ms=200, exact_count=None),
     "distinct"),
    (OutcomeContract(contract_id="x", predicate="all_of",
                     expected={"parts": [REFUND.to_dict()]}, deadline_ms=100, exact_count=None),
     "after the combined horizon"),
    (OutcomeContract(contract_id="x", predicate="all_of",
                     expected={"parts": [{**REFUND.to_dict(), "colour": "red"}]},
                     deadline_ms=200, exact_count=None), "Invalid part contract"),
])
def test_malformed_composite_contracts_are_refused(contract, message):
    with pytest.raises(ContractError, match=message):
        contract_parts(contract)
    with pytest.raises(ContractError):
        all_of("x")


def test_all_parts_satisfied_by_this_action():
    receipt = verify(action(), (payments(refund_row()), crm(ticket_row())), verifier=VERIFIER)
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.origin is OriginStatus.CONFIRMED
    assert receipt.effect_ids == ("rf-1", "tk-1")
    assert receipt.target_effect_ids == ("rf-1", "tk-1")
    assert receipt.findings == ()
    assert receipt.observed_at_ms == 205
    assert receipt.reason == "All 2 parts are required: refund satisfied; ticket satisfied"
    parts = [item.details for item in receipt.evidence]
    assert [(item["part_id"], item["status"]) for item in parts] == [
        ("refund", "satisfied"), ("ticket", "satisfied")]
    assert [item.observation_id for item in receipt.evidence] == ["payments-1", "crm-1"]


def test_one_violated_part_violates_all_of_even_when_another_is_unknown():
    receipt = verify(action(), (payments(refund_row(amount_minor=4000)),
                                crm(ticket_row(), complete=False)), verifier=VERIFIER)
    assert receipt.status is VerificationStatus.VIOLATED
    codes = {item.code: item for item in receipt.findings}
    assert set(codes) == {"PARAMETER_MISMATCH", "PARTIAL_EFFECT", "PART_VIOLATED",
                          "PART_UNKNOWN"}
    assert codes["PART_VIOLATED"].effect_ids == ("rf-1",)
    assert codes["PART_UNKNOWN"].detail.startswith("ticket: unknown (Readback is not exhaustive")
    assert codes["PARAMETER_MISMATCH"].detail.startswith("refund: ")
    # The violated part did target matching, so the agent's report can be judged.
    assert receipt.target_effect_ids == ()
    assert retry_advice(receipt).advice.value == "escalate"


def test_unknown_part_keeps_all_of_unknown():
    receipt = verify(action(), (payments(refund_row()), crm(ticket_row(), watermark=150)),
                     verifier=VERIFIER)
    assert receipt.status is VerificationStatus.UNKNOWN
    assert receipt.target_effect_ids is None
    assert [item.code for item in receipt.findings] == ["PART_UNKNOWN"]
    assert "watermark precedes" in receipt.findings[0].detail


def test_missing_readback_for_a_part_is_unknown_not_assumed():
    receipt = verify(action(), payments(refund_row()), verifier=VERIFIER)
    assert receipt.status is VerificationStatus.UNKNOWN
    assert receipt.findings[0].code == "PART_UNKNOWN"
    assert receipt.findings[0].detail == "ticket: unknown (no readback from crm was supplied)"
    assert [item.observation_id for item in receipt.evidence] == ["payments-1"]


def test_all_of_with_a_part_done_by_someone_else_cannot_judge_the_report():
    other = ticket_row(action_id=None, actor="support-staff")
    receipt = verify(action(), (payments(refund_row()), crm(other)), verifier=VERIFIER)
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.origin is OriginStatus.CONFIRMED
    assert receipt.target_effect_ids == ()
    assert [item.code for item in receipt.findings] == ["PART_OTHER_ACTOR"]
    assert receipt.findings[0].effect_ids == ("tk-1",)


def test_any_of_needs_one_satisfied_alternative():
    contract = any_of("compensate", REFUND, CREDIT)
    either = CompositeVerifier(
        {"refund": RefundVerifier(), "credit": RecordVerifier(scope_fields=("customer_id",))},
        sources={"refund": "payments-db", "credit": "ledger"})
    ledger = Observation(observation_id="ledger-1", source="ledger", observed_at_ms=200,
                         as_of_ms=200, scope={"customer_id": "c-3"}, records=())
    done = verify(action(contract), (payments(refund_row()), ledger), verifier=either)
    assert done.status is VerificationStatus.SATISFIED
    assert done.target_effect_ids == ("rf-1",) and done.findings == ()
    neither = verify(action(contract), (payments(), ledger), verifier=either)
    assert neither.status is VerificationStatus.VIOLATED
    assert neither.findings[0].code == "PART_VIOLATED"
    assert retry_advice(neither).advice.value == "retry_permitted"
    pending = verify(action(contract), (payments(available=False), ledger), verifier=either)
    assert pending.status is VerificationStatus.UNKNOWN
    assert [item.code for item in pending.findings] == ["PART_VIOLATED", "PART_UNKNOWN"]


def test_one_shared_readback_serves_every_part_without_sources():
    shared = CompositeVerifier({"ticket": RecordVerifier(scope_fields=("ticket_id",)),
                                "note": RecordVerifier(scope_fields=("ticket_id",))})
    note = OutcomeContract(contract_id="note", predicate="record_present",
                           expected={"ticket_id": "t-9", "kind": "note"}, deadline_ms=120)
    rows = crm(ticket_row(), ticket_row("nt-1", state=None, kind="note"))
    receipt = verify(action(all_of("close", TICKET, note)), rows, verifier=shared)
    assert receipt.status is VerificationStatus.SATISFIED
    assert [item.details["part_id"] for item in receipt.evidence] == ["ticket", "note"]


def test_nested_composites():
    nested = all_of("resolve", REFUND, any_of("follow-up", TICKET, CREDIT))
    verifier = CompositeVerifier({
        "refund": RefundVerifier(),
        "follow-up": CompositeVerifier({
            "ticket": RecordVerifier(scope_fields=("ticket_id",)),
            "credit": RecordVerifier(scope_fields=("customer_id",))},
            sources={"ticket": "crm", "credit": "ledger"}),
    }, sources={"refund": "payments-db", "follow-up": ("crm", "ledger")})
    receipt = verify(action(nested), (payments(refund_row()), crm(ticket_row())),
                     verifier=verifier)
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.target_effect_ids == ("rf-1", "tk-1")
    inner = receipt.evidence[1].details
    assert inner["part_id"] == "follow-up" and inner["details"]["part_id"] == "ticket"


def test_configuration_and_readback_errors():
    with pytest.raises(ConsequaTypeError, match="reads one readback"):
        verify(action(REFUND), (payments(), crm()), verifier=RefundVerifier())
    with pytest.raises(ValidationError, match="distinct observation_id"):
        verify(action(), (payments(), payments()), verifier=VERIFIER)
    with pytest.raises(ContractError, match="configured for parts"):
        verify(action(), payments(), verifier=CompositeVerifier({"refund": RefundVerifier()}))
    with pytest.raises(ValidationError, match="No part reads"):
        stray = Observation(observation_id="x", source="elsewhere", observed_at_ms=200,
                            as_of_ms=200, scope={})
        verify(action(), (payments(), crm(), stray), verifier=VERIFIER)
    loose = CompositeVerifier({"refund": RefundVerifier(),
                               "ticket": RecordVerifier(scope_fields=("ticket_id",))})
    with pytest.raises(ValidationError, match="map it to one source"):
        verify(action(), (payments(), crm()), verifier=loose)
    with pytest.raises(ValidationError, match="unknown part"):
        CompositeVerifier({"refund": RefundVerifier()}, sources={"ticket": "crm"})
    with pytest.raises(ConsequaTypeError, match="verify method"):
        CompositeVerifier({"refund": object()})


def test_receipt_check_still_binds_every_evidence_item():
    class Forger:
        def verify_readbacks(self, act, observations):
            return VerificationResult(
                action_id=act.action_id, contract_id=act.contract.contract_id,
                status=VerificationStatus.UNKNOWN, observed_at_ms=300,
                evidence=(Evidence(observation_id="invented", source="payments-db",
                                   as_of_ms=200, details={}),))

    with pytest.raises(Exception, match="supplied observation_id"):
        verify(action(), (payments(), crm()), verifier=Forger())


def test_async_part_verifiers_need_averify():
    class SlowRecords(RecordVerifier):
        async def verify(self, act, observation):
            await asyncio.sleep(0)
            return RecordVerifier.verify(self, act, observation)

    verifier = CompositeVerifier({"refund": RefundVerifier(),
                                  "ticket": SlowRecords(scope_fields=("ticket_id",))},
                                 sources={"refund": "payments-db", "ticket": "crm"})
    readback = (payments(refund_row()), crm(ticket_row()))
    with pytest.raises(ConsequaTypeError, match="asynchronous"):
        verify(action(), readback, verifier=verifier)
    rec = TraceRecorder("run-async", actor="agent", clock=lambda: 10)
    rec.register("resolve-1", "resolve_case", {}, contract=all_of("resolve", REFUND, TICKET))
    receipt = asyncio.run(rec.averify(readback, verifier=verifier))
    assert receipt.status is VerificationStatus.SATISFIED
    assert len(rec.trace().observations) == 2


def test_recorded_trace_round_trips_and_explains_and_renders():
    rec = TraceRecorder("run-1", actor="agent", clock=lambda: 10)
    rec.register("resolve-1", "resolve_case", {"payment_id": "p-1"},
                 contract=all_of("resolve", REFUND, TICKET))
    attempt = rec.dispatch(at_ms=20)
    rec.response(attempt, "timeout", at_ms=60)
    rec.assessment("failure", at_ms=61)
    rec.verify((payments(refund_row(attempt_id=attempt)), crm(ticket_row())), verifier=VERIFIER)
    trace = rec.trace()
    assert [item.observation_id for item in trace.observations] == ["payments-1", "crm-1"]
    assert Trace.from_json(trace.to_json()) == trace
    judged = explain(trace).single_action
    assert judged.assessment_alignment == "contradicted"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in judged.codes
    graph = explain(trace).graph
    assert {edge.source for edge in graph.edges if edge.kind == "VERIFICATION"} >= {
        "observation:payments-1", "observation:crm-1"}
    html = render_report(trace)
    assert "All of 2 parts" in html and "<script" not in html
    assert "Part results recorded by composite verifications" in html
    assert "p-1" not in html and "resolve" not in html.replace("Resolve", "")


def test_polling_reads_one_observation_per_source():
    now = [10]
    rec = TraceRecorder("run-poll", actor="agent", clock=lambda: now[0])
    capture = rec.register("resolve-1", "resolve_case", {},
                           contract=all_of("resolve", REFUND, TICKET))

    def read(number):
        lagging = 150 if number == 1 else now[0]
        return (
            Observation(observation_id=f"payments-{number}", source="payments-db",
                        observed_at_ms=now[0], as_of_ms=now[0], scope={"payment_id": "p-1"},
                        records=(refund_row(),)),
            Observation(observation_id=f"crm-{number}", source="crm", observed_at_ms=now[0],
                        as_of_ms=lagging, scope={"ticket_id": "t-9"}, records=(ticket_row(),)))

    def sleep(seconds):
        now[0] += int(seconds * 1000)

    receipt = poll_readback(capture, read, until_ms=400, interval_ms=50, verifier=VERIFIER,
                            sleep=sleep)
    assert receipt.status is VerificationStatus.SATISFIED
    assert [item.status.value for item in rec.trace().verifications] == ["unknown", "satisfied"]


def test_verify_command_reads_one_readback_per_part(tmp_path, capsys):
    from consequa_x import cli

    rec = TraceRecorder("run-cli", actor="agent", clock=lambda: 10)
    rec.register("resolve-1", "resolve_case", {}, contract=all_of("resolve", REFUND, TICKET))
    rec.response(rec.dispatch(at_ms=20), "success", at_ms=30)
    rec.assessment("success", at_ms=31)
    source = tmp_path / "trace.json"
    source.write_text(rec.trace().to_json(), encoding="utf-8")
    files = []
    for observation in (payments(refund_row()), crm(ticket_row())):
        path = tmp_path / f"{observation.source}.json"
        path.write_text(json.dumps(observation.to_dict()), encoding="utf-8")
        files += ["--readback", str(path)]
    output = tmp_path / "verified.json"
    assert cli.main(["verify", str(source), *files, "--output", str(output)]) == 2
    assert "--scope-field" in capsys.readouterr().err
    assert cli.main(["verify", str(source), *files, "--scope-field", "ticket=ticket_id",
                     "--output", str(output)]) == 2
    assert "map it to one source" in capsys.readouterr().err
    assert cli.main(["verify", str(source), *files, "--scope-field", "ticket=ticket_id",
                     "--part-source", "refund=payments-db", "--part-source", "ticket=crm",
                     "--output", str(output)]) == 0
    assert "state satisfied, origin confirmed, alignment consistent" in capsys.readouterr().out
    verified = Trace.from_json(output.read_text(encoding="utf-8"))
    assert len(verified.observations) == 2
    assert verified.verifications[0].target_effect_ids == ("rf-1", "tk-1")
