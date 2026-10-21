"""Render descriptive paper tables from a passed, inventoried native audit only.

This renderer runs no model, native evaluator, Git operation or scientific
simulation. It independently counts the saved rows instead of trusting summary.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "output/native-official-pipeline-2026-10-21/audit/audit-result.json"
ARMS = ("B", "C", "R", "G")
DISPOSITIONS = ("worker_returned", "execution_failed", "integrity_failed",
                "supervisor_failed", "unstarted")
JOURNALS = ("model-calls", "tool-dispatch", "tool-dispatch-starts", "controller-events")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
LIMITS = (
    "This is one protocol-declared fixed seed/run on 12 distinct, previously exposed "
    "airline tasks, with four paired conditions and 48 planned slots; it is not 48 independent tasks.",
    "Each arm has six tasks with nonempty communication requirements and six with empty "
    "requirements. Empty COMMUNICATE criteria pass vacuously only when communication-component "
    "evaluation is reached; "
    "they do not measure substantive communication quality.",
    "Every planned slot remains in operational denominators. Unavailable full native reward "
    "is not a semantic reward of zero. Collection failures and unstarted slots have zero "
    "operational success while their actual native-reward availability is retained.",
    "Premature native stops retain the evaluator's returned reward zero and unavailable component "
    "grades. They do not receive an invented successful empty-communication component.",
    "C and G use the same field predicate and guard rules; C presents a compact report "
    "and G a full package receipt. Their comparison includes representation and context "
    "differences and does not independently validate predicate arithmetic or establish superiority.",
    "Token and request figures are observed journal counts, including available failed-request "
    "records. Partial or missing journals leave additional accounting unavailable; observed "
    "prefix totals are not complete resource totals. Native monetary metadata is distinct "
    "from model-request counts and local compute cost; missing amounts remain unavailable.",
    "This exporter verifies retained audit inventory and row consistency; it does not rerun "
    "the evaluator, authenticate source semantics or independently resolve arbitrary prose claims. "
    "Seed numbers are absent from audit rows; the single-run design is reported through the "
    "caller-pinned protocol anchor without inventing a numeric seed.",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, name):
    require(type(value) is int and value >= 0, f"Invalid nonnegative integer: {name}")
    return value


def amount(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            f"Invalid finite monetary amount: {name}")
    return Decimal(str(value))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError(f"Nonfinite JSON number: {value}")
    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), "Nonfinite JSON number")
        return result
    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=nonfinite,
                      parse_float=finite_float)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify_inventory(audit_path):
    audit_path = Path(audit_path).absolute()
    require(audit_path.name == "audit-result.json", "Expected audit-result.json")
    directory = audit_path.parent
    require(directory.is_dir() and not directory.is_symlink(), "Invalid audit directory")
    manifest_path = directory / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = strict_json(manifest_bytes)
    require(isinstance(manifest, dict) and manifest.get("schema") ==
            "conseqax-native-offline-audit-artifacts-v1", "Unexpected audit manifest schema")
    files = manifest.get("files")
    require(isinstance(files, dict) and "audit-result.json" in files, "Missing audit inventory")
    actual = set()
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Symlinks are not permitted in audit inventory")
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(directory).as_posix())
    require(actual == set(files), "Audit inventory is incomplete or has unbound files")
    bound, contents = {}, {}
    for name, digest in files.items():
        relative = PurePosixPath(name)
        require(name and relative.as_posix() == name and not relative.is_absolute()
                and ".." not in relative.parts and "\\" not in name and ":" not in name,
                "Noncanonical audit inventory path")
        require(isinstance(digest, str) and HEX64.fullmatch(digest), "Invalid inventory digest")
        path = directory / name
        require(path.resolve().is_relative_to(directory.resolve()), "Audit path escapes directory")
        data = path.read_bytes()
        require(sha256(data) == digest, f"Audit artifact hash mismatch: {name}")
        bound[name] = {"sha256": digest, "bytes": len(data)}
        if name.endswith(".json"):
            contents[name] = strict_json(data)
    return contents, {"path": str(audit_path.resolve()),
        "manifest_sha256": sha256(manifest_bytes), "manifest_bytes": len(manifest_bytes),
        "files": bound}


def validate_diagnostics(row):
    diagnostics = row.get("diagnostics")
    require(isinstance(diagnostics, dict), "Missing slot diagnostics")
    availability = diagnostics.get("journal_availability")
    require(isinstance(availability, dict) and set(availability) == set(JOURNALS),
            "Invalid journal availability schema")
    for name, value in availability.items():
        require(isinstance(value, dict) and type(value.get("available")) is bool
                and isinstance(value.get("errors"), list), f"Invalid journal status: {name}")
    model = diagnostics.get("model")
    require(isinstance(model, dict), "Missing model accounting")
    counts = {name: integer(model.get(name), name)
              for name in ("attempted", "returned", "failed", "pending")}
    require(counts["attempted"] == counts["returned"] + counts["failed"] + counts["pending"],
            "Model request disposition counts differ")
    require(type(model.get("journal_call_accounting_valid")) is bool, "Missing call integrity status")
    http = model.get("http_generation_dispatch_records")
    if http is not None:
        integer(http, "HTTP generation records")
    tokens = model.get("tokens")
    require(isinstance(tokens, dict) and set(tokens) == {"prompt_tokens", "completion_tokens"},
            "Invalid token accounting schema")
    for name, values in tokens.items():
        require(isinstance(values, dict), "Invalid token observation")
        total = integer(values.get("sum_observed"), name)
        observed = integer(values.get("observed_responses"), name + " observed")
        missing = integer(values.get("unavailable_attempts"), name + " unavailable")
        require(observed <= counts["returned"] and observed + missing == counts["attempted"],
                "Token observation denominators differ")
        require(observed > 0 or total == 0, "Tokens without an observed response")
    if not availability["model-calls"]["available"]:
        require(counts["attempted"] == 0, "Unavailable journal contains invented request counts")
    if row["episode_audit_passed"] is True:
        require(all(value["available"] and not value["errors"] for value in availability.values())
                and model["journal_call_accounting_valid"], "Audited episode has incomplete journals")
        require(counts["pending"] == 0, "Audited episode has pending model requests")
        require(type(http) is int and http == counts["attempted"],
                "Audited episode HTTP dispatch count differs from attempted model requests")


def validate_costs(episode):
    costs = episode.get("message_costs")
    require(isinstance(costs, dict) and set(costs) == {"assistant", "user"},
            "Missing native message monetary accounting")
    for role, record in costs.items():
        require(isinstance(record, dict), "Invalid message monetary accounting")
        messages = integer(record.get("messages"), role + " messages")
        missing = integer(record.get("unavailable_cost_messages"), role + " missing costs")
        observed = amount(record.get("sum_observed_cost"), role + " observed cost")
        require(missing <= messages and (messages > missing or observed == 0),
                "Invalid message cost denominators")
        native = record.get("native_cost")
        if missing:
            require(native is None, "Unavailable native monetary total was replaced with a value")
        else:
            require(native is not None and math.isclose(float(amount(native, role + " native cost")),
                    float(observed), rel_tol=1e-12, abs_tol=1e-12), "Native monetary totals differ")
    return costs


def validate_audit(contents, protocol_commit):
    require(isinstance(protocol_commit, str) and HEX40.fullmatch(protocol_commit),
            "An explicit immutable 40-character protocol commit is required")
    result = contents["audit-result.json"]
    require(isinstance(result, dict) and result.get("schema") == "conseqax-native-offline-audit-v1"
            and result.get("passed") is True and "error" not in result,
            "A passed independent native audit is required")
    for name in ("new_model_calls", "human_labels", "network_attempts"):
        require(type(result.get(name)) is int and result[name] == 0, f"Unexpected audit activity: {name}")
    anchor = result.get("protocol_anchor")
    require(isinstance(anchor, dict) and anchor.get("protocol_commit") == protocol_commit,
            "Caller protocol commit differs from audit binding")
    for key in ("protocol_file_sha256", "protocol_sha256"):
        require(isinstance(anchor.get(key), str) and HEX64.fullmatch(anchor[key]),
                "Invalid protocol digest binding")
    require(isinstance(result.get("source_commit"), str) and HEX40.fullmatch(result["source_commit"])
            and result["source_commit"] != protocol_commit, "Invalid execution source commit")
    require(isinstance(result.get("collection_manifest_sha256"), str)
            and HEX64.fullmatch(result["collection_manifest_sha256"]), "Invalid collection digest binding")
    require(integer(result.get("collection_bound_files"), "collection bound files") > 0,
            "Empty collection binding")
    rows = result.get("rows")
    require(isinstance(rows, list) and len(rows) == 48, "Expected all 48 planned audit rows")
    require(all(isinstance(row, dict) for row in rows), "Invalid audit row")
    require([row.get("slot") for row in rows] == list(range(48))
            and all(type(row["slot"]) is int for row in rows), "Invalid slot inventory/order")
    tasks, costs = {}, {}
    for row in rows:
        require({"slot", "task_id", "arm", "nonempty_communication", "collection_disposition",
                 "operational_success", "required_task_basis", "native_reward", "native_component_outcomes",
                 "episode_audit_passed", "normal_termination", "diagnostics"} <= set(row),
                "Missing required audit row field")
        task_id, arm = row.get("task_id"), row.get("arm")
        require(isinstance(task_id, str) and task_id and len(task_id) <= 128
                and not any(ord(char) < 32 for char in task_id) and task_id not in {"19", "20"},
                "Invalid or excluded task ID")
        require(arm in ARMS and type(row.get("nonempty_communication")) is bool,
                "Invalid arm/communication stratum")
        task = tasks.setdefault(task_id, {"stratum": row["nonempty_communication"], "arms": set()})
        require(task["stratum"] is row["nonempty_communication"] and arm not in task["arms"],
                "Repeated task/arm or inconsistent task stratum")
        task["arms"].add(arm)
        require(row.get("collection_disposition") in DISPOSITIONS, "Unknown collection disposition")
        require(type(row.get("operational_success")) is int and row["operational_success"] in (0, 1),
                "Invalid operational success")
        require(row.get("episode_audit_passed") is None or row["episode_audit_passed"] is True,
                "Passed audit contains a failed episode audit")
        require(row.get("normal_termination") is None or type(row["normal_termination"]) is bool,
                "Invalid native termination availability")
        require(isinstance(row.get("required_task_basis"), list)
                and all(isinstance(item, str) for item in row["required_task_basis"])
                and sorted(row["required_task_basis"]) == ["COMMUNICATE", "DB"],
                "Unexpected required native component")
        saved_row = contents.get(f"slot-audit-{row['slot']:03d}.json")
        require(saved_row is not None and canonical(saved_row) == canonical(row),
                "Row differs from bound slot-audit artifact")
        reward = row.get("native_reward")
        episode_name = f"episode-audit-{row['slot']:03d}.json"
        if reward is None:
            require(row["episode_audit_passed"] is None and row["normal_termination"] is None
                    and row.get("native_component_outcomes") is None and row["operational_success"] == 0
                    and row["collection_disposition"] != "worker_returned" and episode_name not in contents,
                    "Unavailable native reward was assigned a semantic outcome")
        else:
            require(type(reward) in (int, float) and reward in (0, 1)
                    and row["episode_audit_passed"] is True
                    and type(row["normal_termination"]) is bool, "Invalid native reward/audit status")
            episode = contents.get(episode_name)
            require(isinstance(episode, dict) and episode.get("passed") is True
                    and episode.get("normal_termination") is row["normal_termination"]
                    and canonical(episode.get("reward")) == canonical(row.get("native_component_outcomes")),
                    "Native episode audit differs from row")
            for key in ("new_model_calls", "network_attempts"):
                require(type(episode.get(key)) is int and episode[key] == 0, "Unexpected episode audit activity")
            outcomes = row["native_component_outcomes"]
            require(isinstance(outcomes, dict) and type(outcomes.get("reward")) in (int, float)
                    and outcomes["reward"] == reward, "Native component reward differs")
            if row["normal_termination"]:
                breakdown = outcomes.get("reward_breakdown")
                require(isinstance(breakdown, dict) and set(breakdown) == {"DB", "COMMUNICATE"}
                        and all(type(value) in (int, float) and value in (0, 1)
                                for value in breakdown.values())
                        and breakdown["DB"] * breakdown["COMMUNICATE"] == reward,
                        "Required reward product differs")
                require(row["nonempty_communication"] or breakdown["COMMUNICATE"] == 1,
                        "Empty communication criteria did not receive the native vacuous component grade")
            else:
                require(reward == 0 and outcomes.get("reward_breakdown") is None,
                        "Premature native termination has invented component grades")
            require(row["operational_success"] == int(row["collection_disposition"] == "worker_returned"
                    and reward == 1), "Operational/native reward relationship differs")
            costs[row["slot"]] = validate_costs(episode)
        if row["collection_disposition"] == "unstarted":
            require(reward is None, "Unstarted slot has a native reward")
        validate_diagnostics(row)
    require(len(tasks) == 12 and all(task["arms"] == set(ARMS) for task in tasks.values())
            and sum(task["stratum"] for task in tasks.values()) == 6,
            "Expected 12 paired task IDs and six tasks per stratum")
    audited = sum(row["episode_audit_passed"] is True for row in rows)
    require(type(result.get("native_simulations_audited")) is int
            and result["native_simulations_audited"] == audited, "Native audit count differs from rows")
    require(type(result.get("all_slots_attempted")) is bool
            and result["all_slots_attempted"] == all(row["collection_disposition"] != "unstarted" for row in rows),
            "Attempted-slot flag differs from rows")
    return result, rows, costs


def summarize(rows, costs):
    groups = []
    for arm in ARMS:
        for stratum in (None, True, False):
            selected = [row for row in rows if row["arm"] == arm
                        and (stratum is None or row["nonempty_communication"] is stratum)]
            require(len(selected) == (12 if stratum is None else 6), "Wrong arm/stratum denominator")
            observed = [row for row in selected if row["native_reward"] is not None]
            counts = Counter(row["collection_disposition"] for row in selected)
            group = {"arm": arm, "stratum": "all" if stratum is None else "nonempty" if stratum else "empty",
                "planned": len(selected), "operational_successes": sum(row["operational_success"] for row in selected),
                "native_reward_observed": len(observed), "native_reward_successes": sum(row["native_reward"] == 1 for row in observed),
                "native_reward_unavailable": len(selected) - len(observed),
                "normal_terminations": sum(row["normal_termination"] is True for row in selected),
                "premature_terminations": sum(row["normal_termination"] is False for row in selected),
                "dispositions": {name: counts[name] for name in DISPOSITIONS}}
            group["collection_failures"] = sum(counts[name] for name in DISPOSITIONS[1:-1])
            groups.append(group)
    resources = []
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        models = [row["diagnostics"]["model"] for row in selected]
        statuses = [row["diagnostics"]["journal_availability"]["model-calls"] for row in selected]
        complete = [value["available"] and not value["errors"] and model["journal_call_accounting_valid"]
                    and model["pending"] == 0
                    for value, model in zip(statuses, models)]
        native = [costs[row["slot"]] for row in selected if row["slot"] in costs]
        roles = [record for episode in native for record in episode.values()]
        resources.append({"arm": arm, "planned": 12,
            "model_journals_complete": sum(complete), "model_journals_partial_or_missing": 12 - sum(complete),
            "model_journals_missing": sum(not value["available"] for value in statuses),
            "model_journals_malformed": sum(bool(value["errors"]) for value in statuses),
            "model_journals_accounting_invalid": sum(not model["journal_call_accounting_valid"] for model in models),
            "model_journals_with_pending_requests": sum(model["pending"] > 0 for model in models),
            "request_counts_observed": {name: sum(model[name] for model in models)
                                        for name in ("attempted", "returned", "failed", "pending")},
            "http_generation_records_observed": sum(model["http_generation_dispatch_records"] or 0 for model in models),
            "http_record_slots_unavailable": sum(model["http_generation_dispatch_records"] is None for model in models),
            "tokens": {name: {key: sum(model["tokens"][name][key] for model in models)
                for key in ("sum_observed", "observed_responses", "unavailable_attempts")}
                for name in ("prompt_tokens", "completion_tokens")},
            "monetary": {"sum_observed_native_message_amounts": str(sum(
                (Decimal(str(record["sum_observed_cost"])) for record in roles), Decimal(0))),
                "messages_observed": sum(record["messages"] - record["unavailable_cost_messages"] for record in roles),
                "messages_unavailable_in_audited_episodes": sum(record["unavailable_cost_messages"] for record in roles),
                "slots_with_complete_native_cost": sum(all(record["native_cost"] is not None
                    for record in episode.values()) for episode in native),
                "slots_without_audited_message_costs": 12 - len(native)}})
    return {"distinct_task_ids": 12, "planned_slots": 48, "groups": groups, "resources": resources}


def md_escape(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|")


def table(headers, records):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        + ["| " + " | ".join(md_escape(value) for value in record) + " |" for record in records])


def outcome_cells(group):
    return [group["arm"], group["stratum"], group["planned"],
        f"{group['operational_successes']}/{group['planned']}",
        f"{group['native_reward_successes']}/{group['native_reward_observed']}",
        group["native_reward_unavailable"], group["collection_failures"], group["dispositions"]["unstarted"]]


def render_markdown(summary, rows, anchor):
    lines = ["# Audited finite native airline pilot", "",
        f"Protocol commit: `{anchor['protocol_commit']}`.", ""]
    lines += [paragraph + "\n" for paragraph in LIMITS]
    lines += ["## Outcomes", "", "Native 1/observed means reward-one count over available native rewards. "
        "A denominator of zero means no native reward was observed. Collection failures include "
        "execution, integrity and supervisor failures; native task failure is reported separately.", "",
        table(["Arm", "Stratum", "Planned", "Operational successes", "Native 1/observed", "Native unavailable",
               "Collection failures", "Unstarted"], [outcome_cells(group) for group in summary["groups"]]), "",
        "## Every collection disposition", "", table(["Arm", *DISPOSITIONS],
            [[group["arm"], *[group["dispositions"][name] for name in DISPOSITIONS]]
             for group in summary["groups"] if group["stratum"] == "all"]), "",
        "## Observed model requests and tokens", "",
        "Token columns show known token sum; known usage responses; unavailable usage attempts. "
        "Missing/partial journals can hide additional attempts beyond those known denominators. "
        "Journal issues below can overlap; a complete journal has no pending request.", "",
        table(["Arm", "Complete", "Missing", "Malformed", "Invalid call accounting", "With pending requests"],
            [[row["arm"], row["model_journals_complete"], row["model_journals_missing"],
              row["model_journals_malformed"], row["model_journals_accounting_invalid"],
              row["model_journals_with_pending_requests"]] for row in summary["resources"]]), "",
        table(["Arm", "Complete model journals / 12", "Attempted / returned / failed / pending", "HTTP records; slots unavailable",
               "Prompt: sum; observed; unavailable", "Completion: sum; observed; unavailable"],
            [[row["arm"], f"{row['model_journals_complete']}/12",
              " / ".join(str(row["request_counts_observed"][name]) for name in ("attempted", "returned", "failed", "pending")),
              f"{row['http_generation_records_observed']}; {row['http_record_slots_unavailable']}",
              *["; ".join(str(row["tokens"][name][key]) for key in ("sum_observed", "observed_responses", "unavailable_attempts"))
                for name in ("prompt_tokens", "completion_tokens")]] for row in summary["resources"]]), "",
        "## Native monetary metadata", "",
        "Amounts retain the upstream metadata unit. These are observed message amounts, not complete "
        "model-request costs or local compute costs. Deterministic messages are not new model requests.", "",
        table(["Arm", "Known amount sum", "Messages with amount", "Known missing messages", "Complete-cost slots / 12",
               "Slots without audited costs"], [[row["arm"], row["monetary"]["sum_observed_native_message_amounts"],
              row["monetary"]["messages_observed"], row["monetary"]["messages_unavailable_in_audited_episodes"],
              f"{row['monetary']['slots_with_complete_native_cost']}/12", row["monetary"]["slots_without_audited_message_costs"]]
              for row in summary["resources"]]), "", "## All 48 planned slots", "",
        table(["Slot", "Task", "Arm", "Communication", "Disposition", "Operational success", "Native reward", "Native termination"],
            [[row["slot"], row["task_id"], row["arm"], "nonempty" if row["nonempty_communication"] else "empty",
              row["collection_disposition"], row["operational_success"],
              "unavailable" if row["native_reward"] is None else row["native_reward"],
              "unavailable" if row["normal_termination"] is None else "normal" if row["normal_termination"] else "premature"]
             for row in rows]), ""]
    return "\n".join(lines)


def tex_table(caption, label, headers, records):
    return "\n".join([r"\begin{table*}[t]", r"\centering\small", "\\caption{" + caption + "}",
        "\\label{" + label + "}", "\\begin{tabular}{" + "l" * len(headers) + "}", r"\toprule",
        " & ".join(headers) + r" \\", r"\midrule"]
        + [" & ".join(str(value) for value in record) + r" \\" for record in records]
        + [r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""])


def render_tex(summary, anchor):
    lines = ["% Generated only from passed, byte-verified native audit artifacts.",
        "% Protocol commit: " + anchor["protocol_commit"],
        r"\subsection{Finite native airline pilot}",
        "This single protocol-declared fixed-seed run has 12 distinct previously exposed tasks and 48 paired "
        "planned slots, not 48 independent tasks. Each arm contains six nonempty and six empty communication "
        "criteria; empty native COMMUNICATE checks pass vacuously only when communication-component "
        "evaluation is reached. Premature native stops retain reward zero and unavailable component grades. "
        "Unavailable native reward is not a semantic zero; all failures and unstarted slots remain in "
        "operational denominators.", "",
        tex_table("All planned native pilot outcomes. Native 1/obs is reward-one count over available native rewards; "
                  "NA is the number with unavailable reward. Collection failures (CF) exclude unstarted slots (U).",
                  "tab:native-pilot-outcomes", ["Arm", "Stratum", "N", "Op/N", "Native1/obs", "NA", "CF", "U"],
                  [outcome_cells(group) for group in summary["groups"]])]
    lines += [tex_table("Observed request and token accounting. J is complete model journals out of 12; "
        "M/E/I are missing, malformed and invalid-accounting journal counts (issues can overlap). "
        "A/F/P are attempted, failed and pending request counts. PT/CT are known prompt/completion token "
        "sums; PM/CM are known attempts lacking that usage. Missing or partial journals can hide further work.",
        "tab:native-pilot-resources", ["Arm", "J/12", "M/E/I", "A/F/P", "PT", "PM", "CT", "CM"],
        [[row["arm"], f"{row['model_journals_complete']}/12",
          "/".join(str(row[name]) for name in ("model_journals_missing", "model_journals_malformed",
                                               "model_journals_accounting_invalid")),
          "/".join(str(row["request_counts_observed"][name]) for name in ("attempted", "failed", "pending")),
          row["tokens"]["prompt_tokens"]["sum_observed"], row["tokens"]["prompt_tokens"]["unavailable_attempts"],
          row["tokens"]["completion_tokens"]["sum_observed"], row["tokens"]["completion_tokens"]["unavailable_attempts"]]
         for row in summary["resources"]]),
        tex_table("Native message monetary metadata, in upstream metadata units. Observed amount sums do not "
                  "replace unavailable totals or measure local compute cost. C is complete-cost slots out of 12; "
                  "X is slots without audited message costs.", "tab:native-pilot-monetary",
                  ["Arm", "Known sum", "Known messages", "Missing messages", "C/12", "X"],
                  [[row["arm"], row["monetary"]["sum_observed_native_message_amounts"], row["monetary"]["messages_observed"],
                    row["monetary"]["messages_unavailable_in_audited_episodes"],
                    f"{row['monetary']['slots_with_complete_native_cost']}/12", row["monetary"]["slots_without_audited_message_costs"]]
                   for row in summary["resources"]]),
        "C and G share field arithmetic and guard rules, but use compact reports versus full package receipts. "
        "Their comparison includes representation and context differences and does not independently "
        "cross-check predicate arithmetic. Full per-slot dispositions and available/unknown accounting "
        "are retained in the accompanying Markdown and source receipt. These are descriptive finite-pilot "
        "counts; no superiority, population-generalization or unrestricted prose-accuracy inference follows.", ""]
    return "\n".join(lines)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def execute(audit_path, output, protocol_commit):
    contents, inputs = verify_inventory(audit_path)
    result, rows, costs = validate_audit(contents, protocol_commit)
    summary = summarize(rows, costs)
    output = Path(output).absolute()
    require(not output.exists(), "Output directory must be new")
    require(not output.resolve().is_relative_to(Path(audit_path).absolute().parent.resolve()),
            "Output cannot be inside sealed audit input")
    source = Path(__file__).read_bytes()
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.md").write_text(render_markdown(summary, rows, result["protocol_anchor"]), encoding="utf-8")
    (output / "results.tex").write_text(render_tex(summary, result["protocol_anchor"]), encoding="utf-8")
    (output / "renderer.source.py").write_bytes(source)
    write_json(output / "source-receipt.json", {"schema": "conseqax-native-paper-results-source-v1", "complete": True,
        "generated_utc": datetime.now(timezone.utc).isoformat(), "input_audit": inputs,
        "protocol_anchor": result["protocol_anchor"], "execution_source_commit": result["source_commit"],
        "collection_manifest_sha256": result["collection_manifest_sha256"],
        "renderer": {"path": str(Path(__file__).resolve()), "sha256": sha256(source), "bytes": len(source)},
        "counts_recomputed_from_rows": True, "audit_summary_not_used": True,
        "new_model_calls": 0, "human_labels": 0, "all_planned_rows": rows,
        "computed_tables": summary, "native_message_costs_by_slot": costs, "limitations": list(LIMITS)})
    files = {path.name: sha256(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()}
    write_json(output / "manifest.json", {"schema": "conseqax-native-paper-results-artifacts-v1", "files": files})
    return {"output": str(output.resolve()), "planned_slots": 48, "distinct_task_ids": 12,
            "audit_sha256": inputs["files"]["audit-result.json"]["sha256"], "protocol_commit": protocol_commit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-commit", required=True,
                        help="Caller-pinned protocol Git commit; must match the independently audited anchor")
    args = parser.parse_args()
    print(json.dumps(execute(args.audit, args.output, args.protocol_commit), sort_keys=True))


if __name__ == "__main__":
    main()
