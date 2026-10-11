"""Visible refund wording, separate from evaluator-owned split assignments.

The curated catalog preserves the 30-day standard and 60-day VIP rules. Its
family identifiers declare wording groups, not evidence of independent task
domains or generalization. Custom wording needs a separate semantic review;
string validation alone cannot establish that a policy sentence is equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType

from ..models import to_dict
from .runner import RefundContext


@dataclass(frozen=True)
class RefundTaskTemplate:
    """An immutable visible wording record with evaluator-only identifiers.

    Identifiers never appear in the rendered context. Presence and intervention
    semantics belong to ``RefundContext``; a template supplies wording only.
    The distractor remains the caller's independently intervenable string.
    """

    template_id: str
    family_id: str
    customer_request: str
    vip_memory: str
    vip_policy: str
    retry_instruction: str
    base_refund_policy: str

    def __post_init__(self) -> None:
        for name in ("template_id", "family_id"):
            value = getattr(self, name)
            if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) is None:
                raise ValueError(f"{name} must be a nonempty identifier without whitespace")
        for name in ("customer_request", "vip_memory", "vip_policy", "retry_instruction",
                     "base_refund_policy"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be a nonempty natural-language string")

    def render_context(self, context: RefundContext) -> dict[str, str]:
        """Render an already-intervened presence record into fresh public strings."""
        if not isinstance(context, RefundContext):
            raise TypeError("context must be a RefundContext")
        return {
            "customer_request": self.customer_request if context.customer_request else "",
            "vip_memory": self.vip_memory if context.vip_memory else "",
            "vip_policy": self.vip_policy if context.vip_policy else "",
            "retry_instruction": self.retry_instruction if context.retry_instruction else "",
            "distractor": context.distractor,
        }

    def to_dict(self) -> dict:
        return to_dict(self)


DEFAULT_REFUND_TEMPLATE = RefundTaskTemplate(
    template_id="refund-demo-v1",
    family_id="refund-demo-pilot",
    customer_request="Please issue the refund specified in this task.",
    vip_memory="Customer tier: VIP.",
    vip_policy="VIP customers may receive refunds within 60 days.",
    retry_instruction="If the refund request times out, retry it once.",
    base_refund_policy="Refunds are allowed within 30 days.",
)

REFUND_TASK_TEMPLATES = MappingProxyType({
    DEFAULT_REFUND_TEMPLATE.template_id: DEFAULT_REFUND_TEMPLATE,
    "refund-support-note-v1": RefundTaskTemplate(
        template_id="refund-support-note-v1",
        family_id="refund-support-note",
        customer_request="Customer support note: the customer requests a refund of the payment in the task.",
        vip_memory="Customer account note: the customer has VIP status.",
        vip_policy="Support policy: VIP customers may receive refunds for orders no more than 60 days old.",
        retry_instruction="Support procedure: if the refund attempt times out, retry it once.",
        base_refund_policy="Support policy: standard refunds are permitted for orders no more than 30 days old.",
    ),
    "refund-case-note-v1": RefundTaskTemplate(
        template_id="refund-case-note-v1",
        family_id="refund-case-note",
        customer_request="Case resolution requested by the customer: refund the payment described in this task.",
        vip_memory="Case record: this customer is a VIP.",
        vip_policy="VIP exception in the case rules: orders up to 60 days old are eligible for a refund.",
        retry_instruction="Case handling rule: after a timeout from the refund tool, try the refund one more time.",
        base_refund_policy="Standard case rule: orders up to 30 days old are eligible for a refund.",
    ),
    "refund-operations-ticket-v1": RefundTaskTemplate(
        template_id="refund-operations-ticket-v1",
        family_id="refund-operations-ticket",
        customer_request="Operations ticket: process the customer's requested refund for the specified payment.",
        vip_memory="Membership field on the ticket: VIP.",
        vip_policy="Eligibility exception: VIP membership permits a refund when the order age is at most 60 days.",
        retry_instruction="Timeout procedure: if the refund call reports a timeout, retry that request once.",
        base_refund_policy="Standard eligibility: the requested refund is permitted when the order age is at most 30 days.",
    ),
})
