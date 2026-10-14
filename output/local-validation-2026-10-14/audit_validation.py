"""Read-only audit of saved local validation; never generates policy decisions."""
from collections import Counter
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import random
import sys
import zipfile

from consequa_x.models import Trace, to_dict
from consequa_x.schema import get_trace_schema
from consequa_x.verification import verify
from consequa_x.explanation import explain
from consequa_x.policies import PolicyRequest, get_decision_schema
from consequa_x.adapters.ollama import PROMPT_PROFILES
import consequa_x

WORKSPACE = Path(__file__).resolve().parent.parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
parser.add_argument("--report", type=Path, help="Optional fresh audit report; default is read-only.")
args = parser.parse_args()
ROOT = args.root.resolve()
# Audit-only existing development library; no install and no runtime dependency.
try:
    import jsonschema
except ModuleNotFoundError:
    sys.path.append(str(WORKSPACE / ".venv/Lib/site-packages"))
    import jsonschema

checks = 0
def check(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)
def strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value
def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
def rate(n, d):
    return {"numerator": n, "denominator": d, "value": n/d if d else None}

protocol = read(ROOT / "protocol.json")
execution = read(ROOT / "execution.json")
check(execution["status"] == "finished", "both blocks finished")
check(digest(ROOT / "protocol.json") == execution["protocol_sha256"], "protocol immutable")
check(datetime.fromisoformat(protocol["frozen_utc"]) <= datetime.fromisoformat(execution["started_utc"]), "freeze precedes execution")
check(digest(ROOT / "study-plan.source.json") == protocol["manifest_sha256"], "manifest immutable")
check(digest(ROOT / "candidate-checkpoint.whl") == protocol["wheel_sha256"], "candidate wheel retained")
check(protocol["source_revision"] == "2c4adfeb2a364a8116d6edbccbbdac64b413fc9c", "source checkpoint")
check(protocol["planned_episodes"] == 24, "planned episode total")
check(protocol["settings"]["max_calls_total"] == 72, "global cap")
check([item["block"] for item in execution["blocks"]] == ["v1", "v2"], "complete unique executed blocks")
check(len(protocol["schedule_per_profile"]) == 12, "complete planned schedule")
for executed, planned in zip(execution["blocks"], protocol["blocks"], strict=True):
    check(executed["argv"] == planned["argv"], "exact frozen command")
    check(executed["status"] == "finished", "block finished")
    check(datetime.fromisoformat(protocol["frozen_utc"]) <= datetime.fromisoformat(executed["started_utc"])
          <= datetime.fromisoformat(executed["finished_utc"]), "block time order")
for name in ("runtime-before.json", "runtime-after.json"):
    runtime = read(ROOT / name)
    check(runtime["generation_calls"] == 0, name+" inspection only")
    models = [model for model in runtime["tags"]["models"] if model["name"] == protocol["requested_model"]]
    check(len(models) == 1 and models[0]["digest"] == protocol["model_digest"], name+" model digest")
for profile, expected in protocol["prompt_sha256"].items():
    check(sha256(PROMPT_PROFILES[profile].encode()).hexdigest() == expected, "checkpoint prompt bytes "+profile)
package = Path(consequa_x.__file__).resolve().parent
check("site-packages" in package.parts, "installed artifact rather than source tree")
check(importlib.metadata.version("consequa-x") == "0.1.0a2", "candidate version")
for relative, recorded in protocol["package_module_sha256"].items():
    check(digest(package / relative) == recorded, "installed module: " + relative)
with zipfile.ZipFile(ROOT / "candidate-checkpoint.whl") as wheel:
    for relative, recorded in protocol["package_module_sha256"].items():
        check(sha256(wheel.read("consequa_x/"+relative)).hexdigest() == recorded, "wheel module: " + relative)
study = read(ROOT / "study-plan.source.json")
cases = [item for item in study["cases"] if item["split"] == "validation"]
random.Random(12000099).shuffle(cases)
check([case["case_id"] for case in cases] == protocol["case_order"], "independent case-order shuffle")
schedule = [(case, rep) for case in cases for rep in range(2)]
templates = {item["template_id"]: item for item in study["templates"]}
check({templates[case["template_id"]]["family_id"] for case in cases} == {"refund-case-note"}, "validation family only")
validator = jsonschema.Draft202012Validator(get_trace_schema())
rows = []
blocks = []
paired = {}
tokens = {"prompt_eval_count": 0, "eval_count": 0}
actual_calls = 0

def evidence_labels(raw):
    """Independent formula for this frozen exact-one, stability-zero study."""
    action = raw["action"]
    contract = action["contract"]
    obs = raw["observations"][-1]
    expected = contract["expected"]
    check(contract["exact_count"] == 1 and contract["stability_ms"] == 0, "audit domain exact-one/stability-zero")
    horizon = contract["deadline_ms"]
    adequate = (obs["available"] and obs["complete"] and obs["as_of_ms"] >= horizon
                and obs["scope"].get("payment_id") == expected["payment_id"])
    if not adequate:
        return "unknown", "unknown", None, [], []
    records = obs["records"]
    check(len({record["effect_id"] for record in records}) == len(records), "unique readback effect ids")
    relevant = []
    for record in records:
        check(record["payment_id"] == expected["payment_id"], "readback payment scope")
        check(type(record["committed_at_ms"]) is int and record["committed_at_ms"] <= obs["as_of_ms"], "readback time")
        check(record["status"] == "processed" and "reversed_at_ms" not in record, "uncompensated validation domain")
        if action["registered_at_ms"] <= record["committed_at_ms"] <= horizon:
            relevant.append(record)
    matching = [record for record in relevant if record["amount_minor"] == expected["amount_minor"] and record["currency"] == expected["currency"]]
    status = "satisfied" if len(matching) == 1 else "violated"
    linked = [record for record in relevant if record.get("action_id") == action["action_id"] and record.get("actor", action["actor"]) == action["actor"]]
    if linked:
        origin = "confirmed"
    elif relevant and all(record.get("actor") and record["actor"] != action["actor"] and record.get("action_id") != action["action_id"] for record in relevant):
        origin = "other_actor"
    else:
        origin = "unknown"
    if status == "violated":
        target = False
    elif len([record for record in matching if record in linked]) == 1:
        target = True
    elif origin == "other_actor":
        target = False
    else:
        target = None
    return status, origin, target, relevant, linked

for short, profile in (("v1", "refund-policy-v1"), ("v2", "refund-policy-v2")):
    folder = ROOT / short
    result = read(folder / "results.json")
    inventory = read(folder / "manifest.json")["artifacts"]
    expected_files = {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file() and path.name != "manifest.json"}
    listed_files = {item["path"] for item in inventory}
    check(len(listed_files) == len(inventory), short+" unique manifest inventory")
    check(listed_files == expected_files, short+" complete manifest inventory")
    for item in inventory:
        path = Path(item["path"])
        check(not path.is_absolute() and ".." not in path.parts and "\\" not in item["path"], short+" safe manifest path")
        artifact = (folder / path).resolve()
        check(artifact.is_relative_to(folder.resolve()), short+" contained manifest artifact")
        check(digest(artifact) == item["sha256"], short+" manifest hash "+item["path"])
    check(digest(folder/"study-plan.json") == protocol["manifest_sha256"], short+" exact study bytes")
    check(read(folder/"trace-schema.json") == get_trace_schema(), short+" packaged schema")
    check(result["evaluation_kind"] == "local_model", short+" local model classification")
    check(result["package_version"] == "0.1.0a2", short+" package version")
    check(result["cases"] == protocol["case_order"], short+" case order")
    check(result["initial_seed"] == 12000000 and result["samples_per_case"] == 2 and result["max_attempts"] == 2, short+" schedule/settings")
    check(result["study"]["split"] == "validation" and result["study"]["order_seed"] == 12000099, short+" split/order")
    check(result["study"]["manifest_sha256"] == protocol["manifest_sha256"], short+" study hash")
    check(result["installed_model"]["digest"] == protocol["model_digest"], short+" model digest")
    check(result["policy"]["prompt_version"] == profile, short+" prompt profile")
    check(len(result["samples"]) == len(schedule) == len(result["study"]["planned_schedule"]), short+" complete episode inventory")
    for key, expected in (("temperature", 0), ("timeout_seconds", 180), ("num_predict", 512)):
        check(result["policy"][key] == expected, short+" generation setting "+key)
    sample_count = Counter()
    outcomes = Counter({name: 0 for name in ("satisfied", "violated", "unknown")})
    origins = Counter({name: 0 for name in ("confirmed", "other_actor", "unknown")})
    links = Counter({name: 0 for name in ("satisfied", "not_satisfied", "unknown")})
    statuses = Counter({name: 0 for name in ("success", "failure", "partial", "unknown")})
    alignments = Counter({name: 0 for name in ("consistent", "contradicted", "unassessable")})
    definite_alignments = Counter({name: 0 for name in ("consistent", "contradicted", "unassessable")})
    calls = 0
    for index, sample in enumerate(result["samples"]):
        case, rep = schedule[index]
        planned = result["study"]["planned_schedule"][index]
        check(sample["index"] == index and sample["seed"] == 12000000+index, short+" trial index/seed")
        check(sample["scenario"] == sample["case_id"] == case["case_id"], short+" case identity")
        check(sample["split"] == "validation" and sample["family_id"] == "refund-case-note", short+" exposure")
        check(planned["seed"] == sample["seed"] and planned["case_id"] == sample["case_id"], short+" planned receipt")
        frozen = protocol["schedule_per_profile"][index]
        check(frozen["index"] == index and frozen["case_id"] == case["case_id"]
              and frozen["repetition"] == rep and frozen["trial_seed"] == sample["seed"], short+" frozen receipt identity")
        check(frozen["reserved_phase_keys"] == list(range(sample["seed"]*6, sample["seed"]*6+6)), short+" complete phase reservation")
        check(1 <= sample["policy_calls"] <= 3, short+" episode call range")
        calls += sample["policy_calls"]
        if sample["status"] != "completed":
            sample_count["failed"] += 1
            check("trace" not in sample and "verified_outcome" not in sample, short+" failed not fabricated")
            rows.append({"block": short, "index": index, "case_id": case["case_id"], "repetition": rep, "status": sample["status"], "receipt": sample})
            continue
        sample_count["completed"] += 1
        for kind in ("trace", "explanation", "evaluator_truth"):
            directory = {"trace": "traces", "explanation": "explanations", "evaluator_truth": "evaluator_truth"}[kind]
            check(sample[kind] == f"{directory}/episode_{index:04d}.json", short+" exact asset path "+kind)
        raw = read(folder/sample["trace"])
        trace = Trace.from_json((folder/sample["trace"]).read_text(encoding="utf-8"))
        validator.validate(raw)
        check(to_dict(trace) == raw and Trace.from_json(trace.to_json()) == trace, short+" strict round trip")
        check(to_dict(verify(trace.action, trace.observations[-1])) == raw["verifications"][-1], short+" fresh installed verifier")
        check(explain(trace).to_dict() == read(folder/sample["explanation"]), short+" fresh installed explanation")
        truth = read(folder/sample["evaluator_truth"])
        check(truth["seed"] == sample["seed"] and truth["scenario"] == case["case_id"], short+" evaluator identity")
        check(truth["config"] == protocol["schedule_per_profile"][index]["scenario"], short+" frozen scenario")
        state, origin, target, relevant, linked = evidence_labels(raw)
        verified = raw["verifications"][-1]
        check(sample["verified_outcome"] == verified["status"] == state, short+" independent state label")
        check(sample["effect_origin"] == verified["origin"] == origin, short+" independent origin label")
        check(sample["action_linked_consequence_satisfied"] is target, short+" independent linked label")
        if state != "unknown":
            check(set(verified["effect_ids"]) == {record["effect_id"] for record in relevant}, short+" relevant witnesses")
            check(set(verified["attributable_effect_ids"]) == {record["effect_id"] for record in linked}, short+" linked witnesses")
        status = raw["assessment"]["status"]
        if status not in ("success", "failure") or state == "unknown" or (state == "satisfied" and not linked):
            alignment = "unassessable"
        else:
            alignment = "consistent" if (status == "success") == (state == "satisfied") else "contradicted"
        check(sample["reported_assessment"] == status and sample["assessment_alignment"] == alignment, short+" independent assessment")
        outcomes[state] += 1
        origins[origin] += 1
        links["unknown" if target is None else "satisfied" if target else "not_satisfied"] += 1
        statuses[status] += 1
        alignments[alignment] += 1
        if status in ("success", "failure"):
            definite_alignments[alignment] += 1
        decisions = [event for event in raw["events"] if event["type"] == "agent_decision"]
        check(len(decisions) == sample["policy_calls"], short+" captured call count")
        check(raw["assessment"]["rationale"] == decisions[-1]["data"]["policy_reply"]["decision"]["rationale"], short+" final rationale capture")
        check(decisions[0]["data"]["policy_reply"]["decision"]["operation"] == ("refund" if sample["action_selected"] else "stop"), short+" initial selection")
        check(decisions[-1]["data"]["policy_reply"]["decision"]["operation"] == "stop", short+" normal termination")
        context = case["scenario"]["context"]
        template = templates[case["template_id"]]
        visible = {key: template[key] if context[key] else "" for key in ("customer_request", "vip_memory", "vip_policy", "retry_instruction")}
        visible["distractor"] = context["distractor"]
        for phase, event in enumerate(decisions):
            data = event["data"]
            request = data["policy_request"]
            reply = data["policy_reply"]
            meta = reply["metadata"]
            model_seed = (12000000+index)*6+phase
            check(data["model_seed"] == meta["seed"] == model_seed, short+" phase key")
            check(meta["requested_model"] == meta["returned_model"] == protocol["requested_model"], short+" returned identity")
            check(meta["prompt_version"] == profile and meta["system_prompt_sha256"] == protocol["prompt_sha256"][profile], short+" prompt hash")
            check(request["context"] == visible, short+" no hidden context labels")
            check(set(request) == {"stage", "task", "context", "responses", "attempts_remaining"}, short+" public request boundary")
            check(set(request["task"]) == {"payment_id", "amount_minor", "currency", "order_age_days", "base_refund_policy", "idempotency_available", "deadline_ms", "horizon_ms"}, short+" no evaluator task fields")
            check(request["stage"] == ("select" if phase == 0 else "after_response"), short+" request stage")
            check(request["attempts_remaining"] == 2-phase, short+" remaining attempts")
            check(len(request["responses"]) == phase, short+" public response history length")
            check(request["responses"] == raw["responses"][:phase], short+" exact captured public response history")
            check(request["task"]["amount_minor"] == case["scenario"]["amount_minor"] and request["task"]["order_age_days"] == case["scenario"]["order_age_days"], short+" configured numeric inputs")
            public_text = canonical(request)
            check(sha256(public_text.encode()).hexdigest() == meta["request_sha256"], short+" public request hash")
            typed = PolicyRequest(request["stage"], request["task"], request["context"], tuple(trace.responses[:phase]), request["attempts_remaining"])
            payload = {"model": protocol["requested_model"], "stream": False, "think": False, "format": get_decision_schema(typed),
                "messages": [{"role": "system", "content": PROMPT_PROFILES[profile]}, {"role": "user", "content": public_text}],
                "options": {"seed": model_seed, "temperature": 0.0, "num_predict": 512}}
            text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            check(sha256(text.encode()).hexdigest() == meta["request_payload_sha256"], short+" full payload hash")
            for key in tokens:
                check(type(meta[key]) is int and meta[key] >= 0, short+" provider count "+key)
                tokens[key] += meta[key]
            for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
                check(type(meta[key]) is int and meta[key] >= 0, short+" provider duration "+key)
        paired[(short,index)] = {"initial_request": decisions[0]["data"]["policy_request"], "config": truth["config"], "action": raw["action"]}
        refunds = [item for item in truth["records"] if item["kind"] == "refund"]
        operations = [item["data"]["policy_reply"]["decision"]["operation"] for item in decisions]
        expected_selection = bool(context["customer_request"] and (
            case["scenario"]["order_age_days"] <= 30 or
            (case["scenario"]["order_age_days"] <= 60 and context["vip_memory"] and context["vip_policy"])))
        rows.append({"block": short, "index": index, "case_id": case["case_id"], "repetition": rep,
            "trial_seed": sample["seed"], "status": "completed", "policy_calls": sample["policy_calls"],
            "operations": operations, "committed_refunds": len(refunds), "state": state,
            "selection_policy_alignment": sample["action_selected"] == expected_selection,
            "expected_initial_operation": "refund" if expected_selection else "stop",
            "origin": origin, "action_linked": target, "final_status": status,
            "assessment_alignment": alignment, "final_rationale": raw["assessment"]["rationale"],
            "trace": f"{short}/{sample['trace']}"})
    completed = sample_count["completed"]
    claims = statuses["success"]+statuses["failure"]
    assessable = definite_alignments["consistent"]+definite_alignments["contradicted"]
    metrics = {"completed_assessments": completed, "reported_assessment": dict(statuses),
        "definite_claims": claims, "abstentions": statuses["unknown"], "partial_assessments": statuses["partial"],
        "assessable_claims": assessable, "unassessable_claims": definite_alignments["unassessable"],
        "consistent_claims": definite_alignments["consistent"], "contradicted_claims": definite_alignments["contradicted"],
        "claim_coverage": rate(claims,completed), "assessable_claim_coverage": rate(assessable,completed),
        "contradiction_rate": rate(definite_alignments["contradicted"],assessable)}
    summary = result["summary"]
    check(summary["assessment_metrics"] == metrics, short+" all independent assessment metrics")
    check(summary["verification"] == dict(outcomes) and summary["origin"] == dict(origins), short+" aggregate state/origin")
    check(summary["action_linked_consequence"] == dict(links) and summary["assessment_alignment"] == dict(alignments), short+" aggregate linked/alignment")
    check(summary["planned_samples"] == 12 and summary["attempted_samples"] == len(result["samples"]), short+" planned/attempted denominator")
    check(summary["completed_samples"] == completed and summary["failed_samples"] == sample_count["failed"], short+" completion/failure denominator")
    check(summary["not_started_samples"] == 12-len(result["samples"]), short+" unstarted denominator")
    check(summary["policy_calls"] == calls and calls <= 36 and summary["max_calls"] == 36, short+" actual budget")
    check(summary["known_outcome_samples"] == outcomes["satisfied"]+outcomes["violated"], short+" known outcome denominator")
    execution_block = next(item for item in execution["blocks"] if item["block"] == short)
    check(execution_block["summary"] == summary, short+" exact execution summary")
    check(execution_block["exit_code"] == (2 if summary["failed_samples"] or summary["budget_exhausted"] else 0), short+" exit code semantics")
    actual_calls += calls
    blocks.append({"block": short, "manifest_entries": len(inventory), "summary": summary})
for index in range(12):
    if ("v1",index) in paired and ("v2",index) in paired:
        check(paired[("v1",index)] == paired[("v2",index)], "matched initial public request/world/contract "+str(index))
check(actual_calls <= 72, "combined actual call cap")
audit = {"status": "passed", "audited_utc": datetime.now(timezone.utc).isoformat(), "assertions": checks,
    "audit_script_sha256": digest(Path(__file__)),
    "source_revision": protocol["source_revision"], "wheel_sha256": protocol["wheel_sha256"],
    "actual_calls": actual_calls, "maximum_calls": 72, "provider_tokens": tokens,
    "jsonschema_version": importlib.metadata.version("jsonschema"), "blocks": blocks,
    "rows": rows, "generation_calls_by_audit": 0,
    "limits": "Saved-evidence integrity/semantics check; trusted adapter source inputs, not provider authenticity or live-model independence. Rationale assertions require a separate human-readable manual audit."}
if args.report is not None:
    report = args.report.resolve()
    if (ROOT / "manifest.json").exists() and report.is_relative_to(ROOT):
        raise ValueError("closed evidence is read-only; choose an external report path")
    report.write_text(json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
print(json.dumps({"status": "passed", "assertions": checks, "actual_calls": actual_calls, "provider_tokens": tokens}))
