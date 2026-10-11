"""Evaluator-only task-family splits for bounded refund policy studies.

A manifest declares candidate split assignments; it does not certify that a
model or a researcher has never seen a task. Fault compositions can overlap
between these family splits and need a separate final-study allocation.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import random
import re

from ..models import to_dict
from ..policies import PolicyError, strict_json_loads
from .payments import Fault
from .runner import RefundContext, ScenarioConfig
from .templates import DEFAULT_REFUND_TEMPLATE, RefundTaskTemplate


STUDY_SCHEMA_VERSION = "refund-study-v1"
STUDY_SPLITS = ("tuning", "validation", "held_out")
_SCENARIO_FIELDS = (
    "fault", "context", "use_idempotency", "include_provenance", "external_actor",
    "compensate", "reconcile_readback", "read_lag_ms", "deadline_ms", "stability_ms",
    "order_age_days", "amount_minor",
)
_WORDING_FIELDS = (
    "customer_request", "vip_memory", "vip_policy", "retry_instruction", "base_refund_policy",
)


def _identifier(value, label):
    if type(value) is not str or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value) is None:
        raise ValueError(f"{label} must be a lowercase identifier of 1..80 characters")


def template_wording_sha256(template: RefundTaskTemplate) -> str:
    """Fingerprint exact visible wording, independently of evaluator identifiers."""
    if not isinstance(template, RefundTaskTemplate):
        raise TypeError("template must be a RefundTaskTemplate")
    visible = {name: getattr(template, name) for name in _WORDING_FIELDS}
    return sha256(json.dumps(visible, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StudyCase:
    case_id: str
    split: str
    config: ScenarioConfig
    template: RefundTaskTemplate

    def __post_init__(self):
        _identifier(self.case_id, "case_id")
        if self.split not in STUDY_SPLITS:
            raise ValueError(f"split must be one of {STUDY_SPLITS}")
        if not isinstance(self.config, ScenarioConfig):
            raise TypeError("config must be a ScenarioConfig")
        if not isinstance(self.template, RefundTaskTemplate):
            raise TypeError("template must be a RefundTaskTemplate")
        if self.config.name != self.case_id:
            raise ValueError("config.name must equal the evaluator case_id")

    def to_dict(self):
        config = to_dict(self.config)
        return {"case_id": self.case_id, "split": self.split,
                "template_id": self.template.template_id,
                "scenario": {key: config[key] for key in _SCENARIO_FIELDS}}


@dataclass(frozen=True)
class StudyPlan:
    study_id: str
    templates: tuple[RefundTaskTemplate, ...]
    cases: tuple[StudyCase, ...]

    def __post_init__(self):
        _identifier(self.study_id, "study_id")
        if not isinstance(self.templates, tuple) or not self.templates or any(
            not isinstance(item, RefundTaskTemplate) for item in self.templates
        ):
            raise ValueError("templates must be a nonempty tuple of RefundTaskTemplate records")
        if not isinstance(self.cases, tuple) or not self.cases or any(
            not isinstance(item, StudyCase) for item in self.cases
        ):
            raise ValueError("cases must be a nonempty tuple of StudyCase records")
        by_id = {template.template_id: template for template in self.templates}
        if len(by_id) != len(self.templates):
            raise ValueError("template_id values must be unique")
        for template in self.templates:
            _identifier(template.template_id, "template_id")
            _identifier(template.family_id, "family_id")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("case_id values must be unique")
        families = {}
        wording_families = {}
        used_templates = set()
        pilot_wording = template_wording_sha256(DEFAULT_REFUND_TEMPLATE)
        for template in self.templates:
            fingerprint = template_wording_sha256(template)
            if fingerprint in wording_families and wording_families[fingerprint] != template.family_id:
                raise ValueError("identical visible wording cannot belong to different families")
            wording_families[fingerprint] = template.family_id
        for case in self.cases:
            if by_id.get(case.template.template_id) != case.template:
                raise ValueError("every case must refer to an identical declared template")
            used_templates.add(case.template.template_id)
            family = case.template.family_id
            if family in families and families[family] != case.split:
                raise ValueError("a template family cannot cross study splits")
            families[family] = case.split
            if case.split == "held_out" and (
                family == DEFAULT_REFUND_TEMPLATE.family_id
                or template_wording_sha256(case.template) == pilot_wording
            ):
                raise ValueError("the original demo/pilot template cannot be held out")
        if used_templates != set(by_id):
            raise ValueError("every declared template must be used by a study case")

    def select(self, split: str, *, order_seed: int | None = None) -> tuple[StudyCase, ...]:
        if split not in STUDY_SPLITS:
            raise ValueError(f"split must be one of {STUDY_SPLITS}")
        if order_seed is not None and (type(order_seed) is not int or order_seed < 0):
            raise ValueError("order_seed must be a nonnegative integer or None")
        selected = [case for case in self.cases if case.split == split]
        if not selected:
            raise ValueError("the selected split has no study cases")
        if order_seed is not None:
            random.Random(order_seed).shuffle(selected)
        return tuple(selected)

    def to_dict(self):
        return {"schema_version": STUDY_SCHEMA_VERSION, "study_id": self.study_id,
                "templates": [template.to_dict() for template in self.templates],
                "cases": [case.to_dict() for case in self.cases]}


def study_plan_from_json(text: str) -> StudyPlan:
    """Reject ambiguous JSON, unknown fields and split leakage before inference."""
    try:
        value = strict_json_loads(text)
    except PolicyError as error:
        raise ValueError("study manifest must be strict finite JSON") from error
    if type(value) is not dict or set(value) != {
        "schema_version", "study_id", "templates", "cases"
    }:
        raise ValueError("study manifest requires schema_version, study_id, templates and cases")
    if value["schema_version"] != STUDY_SCHEMA_VERSION:
        raise ValueError(f"study schema_version must be {STUDY_SCHEMA_VERSION}")
    if type(value["templates"]) is not list or type(value["cases"]) is not list:
        raise ValueError("study templates and cases must be lists")
    templates = []
    fields = {"template_id", "family_id", *_WORDING_FIELDS}
    for item in value["templates"]:
        if type(item) is not dict or set(item) != fields:
            raise ValueError("each template requires exactly the declared wording and identifiers")
        templates.append(RefundTaskTemplate(**item))
    by_id = {template.template_id: template for template in templates}
    cases = []
    for item in value["cases"]:
        if type(item) is not dict or set(item) != {"case_id", "split", "template_id", "scenario"}:
            raise ValueError("each case requires case_id, split, template_id and scenario")
        if type(item["template_id"]) is not str or item["template_id"] not in by_id:
            raise ValueError("each case must reference a declared template_id")
        scenario = item["scenario"]
        if type(scenario) is not dict or set(scenario) - set(_SCENARIO_FIELDS):
            raise ValueError("scenario contains unsupported fields")
        scenario = dict(scenario)
        if "fault" not in scenario:
            raise ValueError("each study scenario must explicitly declare its fault")
        try:
            scenario["fault"] = Fault(scenario["fault"])
        except (TypeError, ValueError) as error:
            raise ValueError("scenario fault must be a supported Fault value") from error
        if "context" in scenario:
            context = scenario["context"]
            if type(context) is not dict or set(context) - set(RefundContext.__dataclass_fields__):
                raise ValueError("scenario context contains unsupported fields")
            scenario["context"] = RefundContext(**context)
        config = ScenarioConfig(name=item["case_id"], **scenario)
        cases.append(StudyCase(item["case_id"], item["split"], config, by_id[item["template_id"]]))
    return StudyPlan(value["study_id"], tuple(templates), tuple(cases))
