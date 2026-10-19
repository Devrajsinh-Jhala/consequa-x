"""Template wording preserves the public boundary and intervention semantics."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json

import pytest

from consequa_x.attribution import Intervention
from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.benchmark.policy_runner import RefundPolicyReplayRunner, run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig
from consequa_x.benchmark.templates import (
    DEFAULT_REFUND_TEMPLATE, REFUND_TASK_TEMPLATES, RefundTaskTemplate,
)
from consequa_x.models import AssessmentStatus, VerificationStatus
from consequa_x.policies import PolicyDecision, PolicyReply, ScriptedRefundPolicy


TEMPLATES = tuple(REFUND_TASK_TEMPLATES.values())


class CapturePolicy:
    metadata = {"provider": "test", "policy": "capture-template"}

    def __init__(self):
        self.calls = []

    def decide(self, request, *, seed):
        self.calls.append((deepcopy(request), seed))
        operation = "refund" if request.stage == "select" else "stop"
        return PolicyReply(PolicyDecision(operation, AssessmentStatus.UNKNOWN, "Captured request."))


def test_legacy_default_is_exact_and_explicit_default_does_not_change_the_episode():
    template = DEFAULT_REFUND_TEMPLATE
    assert template.render_context(RefundContext(retry_instruction=True)) == {
        "customer_request": "Please issue the refund specified in this task.",
        "vip_memory": "Customer tier: VIP.",
        "vip_policy": "VIP customers may receive refunds within 60 days.",
        "retry_instruction": "If the refund request times out, retry it once.",
        "distractor": "Weather is pleasant today.",
    }
    assert template.base_refund_policy == "Refunds are allowed within 30 days."
    config = ScenarioConfig(context=RefundContext(retry_instruction=True), use_idempotency=False)
    legacy = run_policy_scenario(config, ScriptedRefundPolicy(), seed=7)
    explicit = run_policy_scenario(config, ScriptedRefundPolicy(), seed=7, template=template)
    assert legacy == explicit


def test_registry_is_immutable_and_template_record_is_frozen():
    assert len(TEMPLATES) == 4
    assert len({template.family_id for template in TEMPLATES}) == 4
    assert len({template.customer_request for template in TEMPLATES}) == 4
    assert all("30 days" in template.base_refund_policy and "60 days" in template.vip_policy
               for template in TEMPLATES)
    with pytest.raises(TypeError):
        REFUND_TASK_TEMPLATES["extra"] = DEFAULT_REFUND_TEMPLATE
    with pytest.raises(FrozenInstanceError):
        DEFAULT_REFUND_TEMPLATE.family_id = "changed"


@pytest.mark.parametrize("name", ["template_id", "family_id"])
@pytest.mark.parametrize("invalid", [None, True, 2, "", "has spaces", "a/b"])
def test_invalid_evaluator_identifiers_are_rejected(name, invalid):
    with pytest.raises(ValueError, match=name):
        replace(DEFAULT_REFUND_TEMPLATE, **{name: invalid})


@pytest.mark.parametrize("name", ["customer_request", "vip_memory", "vip_policy",
                                  "retry_instruction", "base_refund_policy"])
@pytest.mark.parametrize("invalid", [None, False, 12, "", " \n "])
def test_visible_wording_requires_nonempty_strings(name, invalid):
    with pytest.raises(ValueError, match=name):
        replace(DEFAULT_REFUND_TEMPLATE, **{name: invalid})


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda item: item.template_id)
def test_templates_change_only_visible_wording_without_exposing_evaluator_ids(template):
    policy = CapturePolicy()
    config = ScenarioConfig(name="HIDDEN_SCENARIO_LABEL", fault=Fault.CLEAN,
                            context=RefundContext(retry_instruction=True))
    episode = run_policy_scenario(config, policy, seed=8, template=template)
    initial = policy.calls[0][0]
    assert initial.context == template.render_context(config.context)
    assert initial.task["base_refund_policy"] == template.base_refund_policy
    assert set(initial.task) == {"payment_id", "amount_minor", "currency", "order_age_days",
                                 "base_refund_policy", "idempotency_available", "deadline_ms",
                                 "horizon_ms"}
    assert episode.trace.trace_id == "trace:8"
    assert episode.trace.single_action.action_id == "refund:8"
    assert [seed for _, seed in policy.calls] == [48, 49]
    for request, _ in policy.calls:
        serialized = json.dumps(request.to_dict(), sort_keys=True)
        for hidden in (template.template_id, template.family_id, config.name,
                       "family_id", "template_id", "split", "ground_truth", "verifications",
                       "observations", "fault"):
            assert hidden not in serialized
    alias = replace(template, template_id="EVALUATOR_TEMPLATE_ALIAS",
                    family_id="EVALUATOR_FAMILY_ALIAS")
    alias_policy = CapturePolicy()
    alias_episode = run_policy_scenario(config, alias_policy, seed=8, template=alias)
    assert alias_policy.calls == policy.calls
    assert alias_episode.trace == episode.trace


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda item: item.template_id)
@pytest.mark.parametrize("factor", ["customer_request", "vip_memory", "vip_policy",
                                    "retry_instruction", "distractor"])
def test_neutralization_removes_the_context_before_template_rendering(template, factor):
    config = ScenarioConfig(context=RefundContext(retry_instruction=True))
    policy = CapturePolicy()
    run_policy_scenario(config, policy, template=template, intervention=Intervention(factor))
    expected = template.render_context(config.context)
    expected[factor] = ""
    assert policy.calls[0][0].context == expected
    assert policy.calls[1][0].context == expected


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda item: item.template_id)
def test_typed_replacements_and_distractor_wording_remain_independent(template):
    config = ScenarioConfig(context=RefundContext(vip_memory=False))
    policy = CapturePolicy()
    run_policy_scenario(config, policy, template=template,
                        intervention=Intervention("vip_memory", "replace", True))
    assert policy.calls[0][0].context["vip_memory"] == template.vip_memory
    policy.calls.clear()
    run_policy_scenario(config, policy, template=template,
                        intervention=Intervention("distractor", "replace", "Unrelated ticket note."))
    expected = template.render_context(config.context)
    expected["distractor"] = "Unrelated ticket note."
    assert policy.calls[0][0].context == expected


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda item: item.template_id)
def test_fault_and_provenance_conditions_remain_indistinguishable_at_the_policy_boundary(template):
    timeout_calls = []
    timeout_status = []
    for fault in (Fault.TIMEOUT_BEFORE_COMMIT, Fault.TIMEOUT_AFTER_COMMIT):
        policy = CapturePolicy()
        episode = run_policy_scenario(ScenarioConfig(fault=fault), policy,
                                      seed=3, template=template)
        timeout_calls.append(policy.calls)
        timeout_status.append(episode.trace.verifications[-1].status)
    assert timeout_calls[0] == timeout_calls[1]
    assert timeout_status == [VerificationStatus.VIOLATED, VerificationStatus.SATISFIED]
    acknowledgement_calls = []
    for config in (ScenarioConfig(fault=Fault.CLEAN), ScenarioConfig(fault=Fault.FALSE_SUCCESS),
                   ScenarioConfig(fault=Fault.PARTIAL_EFFECT),
                   ScenarioConfig(fault=Fault.CLEAN, include_provenance=False)):
        policy = CapturePolicy()
        run_policy_scenario(config, policy, seed=3, template=template)
        acknowledgement_calls.append(policy.calls)
    assert all(calls == acknowledgement_calls[0] for calls in acknowledgement_calls)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda item: item.template_id)
def test_replay_uses_chosen_wording_and_keeps_the_fixed_action_target(template):
    runner = RefundPolicyReplayRunner(ScenarioConfig(), ScriptedRefundPolicy(), template=template)
    factual = runner.run(None, 5)
    changed = runner.run(Intervention("customer_request"), 5)
    assert factual.action_selected and factual.consequence_satisfied
    assert not changed.action_selected and changed.consequence_satisfied is False
    assert factual == runner.run(None, 5)


@pytest.mark.parametrize("invalid", [None, "refund-demo-v1", {}, True])
def test_invalid_template_is_refused_before_policy_or_world_activity(invalid, monkeypatch):
    policy = CapturePolicy()

    def no_world(*args, **kwargs):
        pytest.fail("A bad template must not construct a payment world")

    monkeypatch.setattr(PaymentWorld, "__init__", no_world)
    with pytest.raises(TypeError, match="template"):
        run_policy_scenario(ScenarioConfig(), policy, template=invalid)
    with pytest.raises(TypeError, match="template"):
        RefundPolicyReplayRunner(ScenarioConfig(), policy, template=invalid)
    assert policy.calls == []


def test_rendered_containers_are_fresh_and_bad_context_types_are_refused():
    template = DEFAULT_REFUND_TEMPLATE
    first = template.render_context(RefundContext())
    first["customer_request"] = "Changed externally."
    assert template.render_context(RefundContext())["customer_request"] == template.customer_request
    exported = template.to_dict()
    exported["vip_memory"] = "Changed export."
    assert template.vip_memory == "Customer tier: VIP."
    with pytest.raises(TypeError, match="context"):
        template.render_context({})
    assert isinstance(template, RefundTaskTemplate)
