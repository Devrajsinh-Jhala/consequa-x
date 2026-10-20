"""Build blinded recovery study packets or score independent human exports.

Standard-library only. Tests use synthetic fixtures, never the held-out corpus.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import html
import json
import random
import re
import zipfile
from pathlib import Path, PurePosixPath


SHUFFLE_SEED = 20261019
SCHEMA = "recovery-human-review-v1"
CATEGORIES = {
    "state": ("satisfied", "violated", "unknown"),
    "action_linked": ("true", "false", "unknown"),
    "report_state_alignment": ("supported", "contradicted", "unassessable"),
}
FORBIDDEN = {"method", "case_id", "family_id", "trial_id", "seed", "domain",
             "truth", "gold", "hidden_world", "metrics", "fault", "fault_id",
             "fault_name", "scenario", "scenario_id", "evaluator_truth"}
RECORD_META = {"effect_id", "committed_at_ms", "removed_at_ms", "action_id",
               "actor", "attempt_id", "present_through_ms"}
RESULT_KEYS = RECORD_META | {"record", "records", "operation_id", "status", "ok",
                             "success", "accepted", "acknowledged", "committed",
                             "count", "code", "message", "reason", "request_id"}
IDENTITY_KEYS = {
    "operation_id": "action", "action_id": "action", "idempotency_key": "action",
    "actor": "actor", "attempt_id": "attempt", "effect_id": "effect",
    "observation_id": "observation", "source": "source",
    "provider_request_id": "request", "request_id": "request",
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_bytes(encoded(value))


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("manifest path must be a canonical relative POSIX path")
    part = PurePosixPath(relative)
    if (part.is_absolute() or part.as_posix() != relative
            or any(item in ("", ".", "..") for item in part.parts)):
        raise ValueError("manifest path traversal or noncanonical path")
    path = root.joinpath(*part.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("manifest path escapes its study directory")
    return path


def verify_files(root, manifest, *, excluded=()):
    if manifest.get("complete") is not True or not isinstance(manifest.get("files"), dict):
        raise ValueError("manifest must be complete with a files mapping")
    files = manifest["files"]
    for relative, expected in files.items():
        path = safe_path(root, relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("invalid artifact SHA-256")
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"missing artifact or hash mismatch: {relative}")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*")
              if path.is_file() and path.relative_to(root).as_posix() not in excluded}
    if actual != set(files):
        raise ValueError("study contains unmanifested or missing artifacts")
    return files


def verify_study(root):
    root = Path(root).resolve()
    receipt = load_json(root / "completion-receipt.json")
    manifest = load_json(root / "manifest.json")
    if receipt.get("complete") is not True:
        raise ValueError("study completion receipt is not complete")
    bindings = {"manifest_sha256": digest(root / "manifest.json"),
                "protocol_sha256": digest(root / "protocol.json")}
    if any(receipt.get(key) != value for key, value in bindings.items()):
        raise ValueError("completion receipt hash binding mismatch")
    files = verify_files(root, manifest, excluded=("manifest.json", "completion-receipt.json"))
    if "protocol.json" not in files:
        raise ValueError("protocol.json must be bound by the study manifest")
    protocol = load_json(root / "protocol.json")
    builder_hash = protocol.get("human_review_builder_sha256")
    if builder_hash is not None and builder_hash != digest(__file__):
        raise ValueError("frozen human-review builder hash mismatch")
    schedule = protocol.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        raise ValueError("protocol needs a nonempty frozen schedule array")
    planned, slots = {}, set()
    for row in schedule:
        if not isinstance(row, dict):
            raise ValueError("schedule rows must be objects")
        for key in ("trial_id", "case_id", "family_id", "domain", "method"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(f"schedule is missing {key}")
        if type(row.get("seed")) is not int or row["seed"] < 0:
            raise ValueError("schedule seed must be a nonnegative integer")
        slot = (row["case_id"], row["method"], row["seed"])
        if row["trial_id"] in planned or slot in slots:
            raise ValueError("duplicate scheduled trial or case/method/seed slot")
        planned[row["trial_id"]] = row
        slots.add(slot)
    selected = {identity: row for identity, row in planned.items() if row["seed"] == 0}
    if not selected:
        raise ValueError("protocol has no seed-0 review slots")
    if {(row["case_id"], row["method"]) for row in planned.values()} != {
            (row["case_id"], row["method"]) for row in selected.values()}:
        raise ValueError("some planned case/method pairs lack seed 0")
    trials, seen = {}, set()
    for relative in sorted(files):
        if not (relative.startswith("trials/") and relative.endswith(".json.gz")):
            continue
        with gzip.open(safe_path(root, relative), "rt", encoding="utf-8") as stream:
            row = json.load(stream)
        if not isinstance(row, dict):
            raise ValueError("trial must be a JSON object")
        identity = row.get("trial_id")
        if identity not in planned or identity in seen:
            raise ValueError("unknown or duplicate trial artifact")
        seen.add(identity)
        if any(row.get(key) != planned[identity][key]
               for key in ("case_id", "family_id", "domain", "seed", "method")):
            raise ValueError("trial disagrees with frozen schedule")
        if row.get("status") not in ("completed", "failed"):
            raise ValueError("trial status must be completed or failed")
        if identity in selected:
            trials[identity] = row
    bindings["completion_receipt_sha256"] = digest(root / "completion-receipt.json")
    return selected, trials, bindings


def no_hidden_keys(value):
    if isinstance(value, dict):
        if FORBIDDEN.intersection(value):
            raise ValueError("registered target/scope contains a forbidden blinding field")
        for child in value.values():
            no_hidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            no_hidden_keys(child)


def result_public(value, business):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key not in RESULT_KEYS | business or key in FORBIDDEN:
                continue
            result[key] = admitted_value(child) if key in business else result_public(child, business)
        return result
    if isinstance(value, list):
        return [result_public(child, business) for child in value]
    return value


def admitted_value(value):
    """Never alter a predicate-relevant business value to achieve blinding."""
    no_hidden_keys(value)
    return copy.deepcopy(value)


def normalized_identities(value):
    aliases, counts = {}, {}

    def strings(item):
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for key, child in item.items():
                yield key
                yield from strings(child)
        elif isinstance(item, list):
            for child in item:
                yield from strings(child)

    original_strings = tuple(strings(value))

    def collect(item):
        if isinstance(item, dict):
            for key in sorted(item):
                child = item[key]
                if key in IDENTITY_KEYS and isinstance(child, str) and child:
                    category = IDENTITY_KEYS[key]
                    if child not in aliases:
                        counts[category] = counts.get(category, 0) + 1
                        candidate = f"{category}-{counts[category]}"
                        # A reversible substitution must not merge an identity
                        # with an existing literal business value or substring.
                        while (any(candidate in text for text in original_strings)
                               or any(candidate in old or old in candidate for old in aliases.values())):
                            candidate = "blind-" + candidate
                        aliases[child] = candidate
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    names = sorted(aliases, key=lambda old: -len(old))
    pattern = (re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, names))
                          + r")(?![A-Za-z0-9_])") if names else None)

    def replace(item):
        if isinstance(item, str):
            if item in aliases:
                return aliases[item]
            return pattern.sub(lambda match: aliases[match.group(0)], item) if pattern else item
        if isinstance(item, dict):
            return {key: replace(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child) for child in item]
        return item
    return replace(value)


def public_card(row):
    case, source = row.get("public_case"), row.get("source_receipt")
    if not isinstance(case, dict) or not isinstance(source, dict):
        raise ValueError("completed trial lacks public case/source declaration")
    target, scope = case.get("target"), case.get("scope")
    if not isinstance(target, dict) or not isinstance(target.get("expected"), dict):
        raise ValueError("registered target is missing expected fields")
    if not isinstance(scope, dict) or not isinstance(case.get("scope_fields"), list):
        raise ValueError("registered scope and scope_fields are required")
    if (not all(isinstance(key, str) for key in case["scope_fields"])
            or set(case["scope_fields"]) != set(scope)
            or len(case["scope_fields"]) != len(scope)):
        raise ValueError("scope_fields must name every scope key exactly once")
    if target.get("predicate") != "record_present":
        raise ValueError("this review rubric supports record_present contracts only")
    exact = target.get("exact_count")
    if exact is not None and (type(exact) is not int or exact < 0):
        raise ValueError("contract exact_count must be a nonnegative integer or null")
    no_hidden_keys(target["expected"])
    no_hidden_keys(scope)
    for key in ("deadline_ms", "stability_ms"):
        if type(case.get(key)) is not int or case[key] < 0:
            raise ValueError("contract deadline/stability must be nonnegative integers")
    if not all(isinstance(case.get(key), str) and case[key] for key in ("operation_id", "actor")):
        raise ValueError("registered action/actor identifiers are required")
    if not isinstance(source.get("source"), str) or not source["source"]:
        raise ValueError("admitted expected readback source is required")
    if source.get("trusted") is not None and type(source["trusted"]) is not bool:
        raise ValueError("declared source trust must be boolean or absent")
    if "time_base" in source and source["time_base"] not in ("relative_ms", "unix_ms"):
        raise ValueError("source time_base must be relative_ms or unix_ms")
    registered = case.get("registered_at_ms")
    if registered is not None and (type(registered) is not int or registered < 0):
        raise ValueError("registration time must be a nonnegative integer or unknown")
    fixed = {"operation_id": case["operation_id"], "actor": case["actor"],
             "registered_at_ms": registered,
             "contract": {key: copy.deepcopy(target[key]) for key in
                          ("expected", "predicate", "exact_count") if key in target},
             "deadline_ms": case["deadline_ms"], "stability_ms": case["stability_ms"],
             "horizon_ms": case["deadline_ms"] + case["stability_ms"],
             "scope": copy.deepcopy(scope), "scope_fields": list(case["scope_fields"])}
    admitted_source = {key: admitted_value(source[key]) for key in
                       ("source", "trusted", "time_base", "clock", "commit_clock_authoritative",
                        "history_semantics", "completeness_semantics", "provenance_semantics")
                       if key in source}
    business = set(target["expected"]) | set(scope)
    trajectory = []
    if not isinstance(row.get("trajectory"), list):
        raise ValueError("completed trial lacks a public trajectory")
    for event in row["trajectory"]:
        if not isinstance(event, dict):
            raise ValueError("trajectory events must be objects")
        kind = event.get("kind")
        if kind == "dispatch":
            decision = event.get("decision", event)
            if not isinstance(decision, dict):
                raise ValueError("dispatch decision must be an object")
            entry = {"kind": kind, "at_ms": event.get("at_ms")}
            entry.update({key: copy.deepcopy(decision[key]) for key in
                          ("action_id", "attempt_id", "idempotency_key") if key in decision})
            trajectory.append(entry)
        elif kind == "response":
            response = event.get("response")
            if not isinstance(response, dict):
                raise ValueError("response event lacks admitted response")
            clean = {key: copy.deepcopy(response[key]) for key in
                     ("status", "response_at_ms", "attempt_id", "provider_request_id",
                      "terminal_not_committed") if key in response}
            if "result" in response:
                clean["result"] = result_public(response["result"], business)
            trajectory.append({"kind": kind, "at_ms": event.get("at_ms"), "response": clean})
        elif kind == "readback":
            observation = event.get("observation")
            if not isinstance(observation, dict):
                raise ValueError("readback event lacks admitted observation")
            clean = {key: copy.deepcopy(observation[key]) for key in
                     ("observation_id", "source", "observed_at_ms", "as_of_ms", "scope",
                      "complete", "available") if key in observation}
            if not isinstance(clean.get("scope", {}), dict):
                raise ValueError("readback scope must be an object")
            clean["scope"] = {key: admitted_value(child) for key, child in clean.get("scope", {}).items()
                              if key in business and key not in FORBIDDEN}
            records = observation.get("records", [])
            if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
                raise ValueError("observation records must be objects")
            clean["records"] = [{key: admitted_value(child) for key, child in record.items()
                                 if key in business | RECORD_META and key not in FORBIDDEN}
                                for record in records]
            trajectory.append({"kind": kind, "at_ms": event.get("at_ms"), "observation": clean})
    report = row.get("report")
    if not isinstance(report, dict):
        raise ValueError("completed trial is missing final report claims")
    claims = {key: report.get(key) for key in ("reported_state", "reported_action_linked")}
    if any(value is not None and type(value) is not bool for value in claims.values()):
        raise ValueError("report claims must be boolean or null")
    return normalized_identities({"registered_action": fixed, "admitted_source": admitted_source,
                                  "trajectory": trajectory, "report_claims": claims})


RUBRIC = """# Independent evidence review rubric

Review the original fixed outcome contract only: its payload, count, deadline,
and deadline plus stability window. Later recovery and safety horizons are not
review targets. Use only this card's evidence; do not guess a hidden fault or
future commit. Identifiers are consistently aliased within a card.

Source admission/trust is a declared study assumption, not authentication.
Check the observed source against the admitted source, scope, availability,
completeness and watermark. Missing/incomplete/wrongly scoped evidence cannot
prove absence. A current row alone does not prove past persistence. Unknown
registration time limits temporal conclusions; do not infer an unrecorded time.
An absent/false trust declaration cannot be upgraded into source authority.
Use the declared clock, commit-time authority, lifecycle history, completeness,
and provenance semantics. A trusted source does not automatically authenticate
its actor metadata or support an unprovided persistence history.

Answer each question independently and cite observation/effect/attempt IDs:

* **state**: `satisfied`, `violated`, or `unknown`. A matching effect must meet
  the original deadline and persistence horizon. Exact-count contracts require
  the requested count throughout the stability interval; a transient extra can
  violate it. Removal at the horizon does not establish persistence through it.
  A readback whose watermark does not cover the horizon remains unknown.
  Tool success/error/timeout alone does not establish this state.
* **action_linked**: `true`, `false`, or `unknown` for this action's full target.
  Any known global contract violation makes this false, even if an own matching
  witness exists. A satisfied contract with supported qualifying own effects
  is true; exclusively other-actor satisfaction is false. Missing provenance is
  unknown, not evidence of another actor. A provenance link is not causal proof.
* **report_state_alignment**: `supported`, `contradicted`, or `unassessable`.
  Compare reported_state with the evidence-supported fixed state. A true report
  with satisfied evidence or false report with violated evidence is supported;
  the opposite definite pairing is contradicted. Missing/unknown reports or an
  unknown supported state are unassessable. A correct hidden-world guess earns
  no evidence-support credit.

Leave a question unanswered if you have not reviewed it; an explicit `unknown`
(or `unassessable`) is an answer, distinct from a blank. Supply witness IDs and
brief reasons, including any ambiguity in the rubric. Do not consult another
reviewer. Export and seal each initial review before discussion/adjudication.
The packet contains no generated human labels. A later full-ledger truth audit
must be separate and cannot retroactively support an earlier claim.
"""

README = """# Blinded recovery evidence review

Open reviewer.html in a browser; it works offline and exports review JSON.
Export regularly to save your work. The blank JSON template supports other
annotation tools. Use an identifier you choose; no participant is prefilled.
Two reviewers work independently before their exports are compared.

Cards combine identical normalized admissible evidence and report claims.
Deduplication weights and identities are private and are absent from this
packet and its ZIP. Card order is deterministically shuffled, independent of
method names or labels. Selected seed-0 failed/absent cells remain unavailable
in the sampling totals rather than receiving replacement cards.
Identity labels are blinded, but trajectory length/read behavior may reveal a
strategy class; the packet does not promise perfect strategy blinding.

Questions concern original fixed deadline/stability, not final recovery.
Read rubric.md before labeling. Source trust is assumed as declared, not
independently authenticated. The packet provides no human validation until
people actually complete their independent labels.

Score two exports with the frozen builder:
python scripts/build_recovery_human_review.py --score first.json second.json --packet PACKET_DIR --output NEW_SCORE_DIR

The scorer verifies packet hashes, reports target-specific raw agreement and
Cohen kappa with explicit undefined cases, and creates a blank adjudication
sheet for disagreements/missing labels. Agreement is not proof of correctness.
"""

VIEWER_HTML = r"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Independent evidence review</title>
<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}label{display:block;margin:.8rem 0}select,input,textarea,button{font:inherit;padding:.4rem}pre{white-space:pre-wrap;background:#f3f5f7;padding:1rem;border-radius:6px}textarea{width:95%}button{margin:.5rem}details{margin:1rem 0}</style>
<h1>Independent evidence review</h1><p>Original fixed contract only. Source admission is an assumption, not authentication. Export regularly to save your work.</p>
<label>Your reviewer identifier <input id="reviewer" autocomplete="off"></label>
<label>Card <select id="card"></select></label><button id="previous">Previous</button><button id="next">Next</button>
<details><summary>Rubric</summary><pre id="rubric"></pre></details><pre id="evidence"></pre>
<div id="questions">__OPTIONS__</div><label>Witness IDs (one per line)<textarea id="witnesses" rows="3"></textarea></label>
<label>Reason / rubric ambiguity<textarea id="comment" rows="4"></textarea></label><button id="export">Export review JSON</button>
<label>Resume a saved review <input id="import" type="file" accept="application/json,.json"></label><p id="message" role="status"></p>
<script type="application/json" id="data">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent), packet=data.packet;
let review=data.review,index=0;
const byId=id=>document.getElementById(id),selects=[...document.querySelectorAll('[data-target]')];
byId('rubric').textContent=__RUBRIC__;
for(const card of packet.cards){const option=document.createElement('option');option.value=card.card_id;option.textContent=card.card_id;byId('card').append(option);}
function save(){review.reviewer_id=byId('reviewer').value.trim();if(!packet.cards.length)return;const label=review.labels[index];for(const select of selects)label[select.dataset.target]=select.value||null;label.witnesses=byId('witnesses').value.split('\n').map(s=>s.trim()).filter(Boolean);label.comment=byId('comment').value;}
function show(){if(!packet.cards.length){byId('evidence').textContent='No available sampled cards.';return;}const card=packet.cards[index],label=review.labels[index];byId('card').value=card.card_id;byId('evidence').textContent=JSON.stringify(card.evidence,null,2);for(const select of selects)select.value=label[select.dataset.target]||'';byId('witnesses').value=(label.witnesses||[]).join('\n');byId('comment').value=label.comment||'';}
byId('card').onchange=()=>{save();index=packet.cards.findIndex(c=>c.card_id===byId('card').value);show();};
byId('previous').onclick=()=>{save();index=Math.max(0,index-1);show();};byId('next').onclick=()=>{save();index=Math.min(packet.cards.length-1,index+1);show();};
byId('export').onclick=()=>{save();if(!review.reviewer_id){byId('message').textContent='Enter your reviewer identifier before exporting.';return;}const blob=new Blob([JSON.stringify(review,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='independent-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);byId('message').textContent='Review exported. Keep this file before closing.';};
byId('import').onchange=async event=>{try{const candidate=JSON.parse(await event.target.files[0].text());if(candidate.schema!==review.schema||candidate.packet_id!==packet.packet_id||typeof candidate.reviewer_id!=='string'||!Array.isArray(candidate.labels)||candidate.labels.length!==packet.cards.length)throw Error('Review does not match this packet.');for(let i=0;i<candidate.labels.length;i++){const label=candidate.labels[i];if(label.card_id!==packet.cards[i].card_id)throw Error('Card order differs.');if(!Array.isArray(label.witnesses)||!label.witnesses.every(w=>typeof w==='string')||typeof label.comment!=='string')throw Error('Invalid witnesses or comment.');for(const select of selects){const value=label[select.dataset.target];if(value!==null&&![...select.options].some(o=>o.value===value))throw Error('Invalid label.');}}review=candidate;byId('reviewer').value=review.reviewer_id||'';index=0;show();byId('message').textContent='Saved review loaded.';}catch(error){byId('message').textContent=error.message;}};show();
</script></html>"""


def viewer(packet, template):
    data = json.dumps({"packet": packet, "review": template}, ensure_ascii=True).replace("<", "\\u003c")
    options = "".join(
        f'<label>{html.escape(key)} <select data-target="{key}"><option value="">Unanswered</option>'
        + "".join(f'<option value="{choice}">{choice}</option>' for choice in choices)
        + "</select></label>" for key, choices in CATEGORIES.items())
    return (VIEWER_HTML.replace("__OPTIONS__", options).replace("__DATA__", data)
            .replace("__RUBRIC__", json.dumps(RUBRIC)))


def fresh_output(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output must be a new directory; existing work is preserved")
    output.mkdir(parents=True)
    return output


def build_packet(study_dir, output):
    selected, trials, bindings = verify_study(study_dir)
    unique, mapping = {}, []
    totals = {"scheduled_seed0": len(selected), "completed": 0, "failed": 0, "absent": 0}
    for identity, planned in sorted(selected.items()):
        row = trials.get(identity)
        disposition = "absent" if row is None else row["status"]
        totals[disposition] += 1
        private = {key: planned[key] for key in
                   ("trial_id", "case_id", "family_id", "domain", "seed", "method")}
        private["disposition"] = disposition
        if disposition == "completed":
            evidence = public_card(row)
            key = hashlib.sha256(encoded(evidence)).hexdigest()
            unique.setdefault(key, evidence)
            private["evidence_sha256"] = key
        mapping.append(private)
    keys = sorted(unique)
    random.Random(SHUFFLE_SEED).shuffle(keys)
    ids = {key: f"card-{index + 1:04d}" for index, key in enumerate(keys)}
    cards = [{"card_id": ids[key], "evidence": unique[key]} for key in keys]
    for row in mapping:
        row["card_id"] = ids.get(row.get("evidence_sha256"))
    totals["unique_cards"] = len(cards)
    packet = {"schema": SCHEMA, "source_bindings": bindings,
              "sampling": {"rule": "all scheduled case-by-method slots at seed 0; no replacement",
                           "shuffle_seed": SHUFFLE_SEED, **totals}, "cards": cards}
    packet["packet_id"] = hashlib.sha256(encoded(packet)).hexdigest()
    template = {"schema": SCHEMA, "packet_id": packet["packet_id"], "reviewer_id": "",
                "labels": [{"card_id": card["card_id"], **{key: None for key in CATEGORIES},
                            "witnesses": [], "comment": ""} for card in cards]}
    output = fresh_output(output)
    public = {"cards.json": encoded(packet), "reviewer-template.json": encoded(template),
              "README.md": README.encode(), "rubric.md": RUBRIC.encode(),
              "reviewer.html": viewer(packet, template).encode("utf-8")}
    for name, payload in public.items():
        (output / name).write_bytes(payload)
    manifest = {"complete": True, "schema": SCHEMA, "packet_id": packet["packet_id"],
                "files": {name: digest(output / name) for name in sorted(public)}}
    write_json(output / "manifest.json", manifest)
    private = output / "private"
    private.mkdir()
    (private / ".gitignore").write_text("*\n", encoding="utf-8")
    weights = {card["card_id"]: {} for card in cards}
    for row in mapping:
        if row["card_id"]:
            item = weights[row["card_id"]]
            item[row["method"]] = item.get(row["method"], 0) + 1
    write_json(private / "mapping.json", {"packet_id": packet["packet_id"],
                                          "selected_slots": mapping, "weights_by_method": weights})
    with zipfile.ZipFile(output / "recovery-human-review.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted((*public, "manifest.json")):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (output / name).read_bytes())
    return {"packet_id": packet["packet_id"], **totals, "output": str(output)}


def verify_packet(packet_dir):
    root = Path(packet_dir).resolve()
    manifest = load_json(root / "manifest.json")
    if manifest.get("complete") is not True or not isinstance(manifest.get("files"), dict):
        raise ValueError("packet manifest is incomplete")
    required = {"cards.json", "reviewer-template.json", "README.md", "rubric.md", "reviewer.html"}
    if set(manifest["files"]) != required:
        raise ValueError("packet manifest does not match the public allowlist")
    for relative, expected in manifest["files"].items():
        path = safe_path(root, relative)
        if not path.is_file() or digest(path) != expected:
            raise ValueError("packet artifact hash mismatch")
    packet = load_json(root / "cards.json")
    if packet.get("schema") != SCHEMA or manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported review packet schema")
    identity = packet.pop("packet_id", None)
    actual = hashlib.sha256(encoded(packet)).hexdigest()
    packet["packet_id"] = identity
    if identity != actual or manifest.get("packet_id") != identity:
        raise ValueError("packet identity binding mismatch")
    ids = [row["card_id"] for row in packet["cards"]]
    if len(ids) != len(set(ids)):
        raise ValueError("packet has duplicate card IDs")
    return packet


def read_review(path, packet):
    value = load_json(path)
    if value.get("schema") != SCHEMA or value.get("packet_id") != packet["packet_id"]:
        raise ValueError("review export is bound to a different packet/schema")
    if not isinstance(value.get("reviewer_id"), str) or not value["reviewer_id"].strip():
        raise ValueError("reviewer_id is required; blank templates are not completed reviews")
    if not isinstance(value.get("labels"), list):
        raise ValueError("review export needs a labels array")
    known = {row["card_id"] for row in packet["cards"]}
    labels = {}
    for row in value["labels"]:
        if not isinstance(row, dict) or row.get("card_id") not in known or row["card_id"] in labels:
            raise ValueError("review has unknown or duplicate card IDs")
        for target, choices in CATEGORIES.items():
            if row.get(target) is not None and row[target] not in choices:
                raise ValueError(f"invalid human label for {target}")
        if not isinstance(row.get("witnesses", []), list) or not all(
                isinstance(item, str) for item in row.get("witnesses", [])):
            raise ValueError("witnesses must be an array of strings")
        labels[row["card_id"]] = row
    return value["reviewer_id"], labels


def agreement(first, second, choices):
    pairs = [(left, right) for left, right in zip(first, second)
             if left is not None and right is not None]
    matrix = {left: {right: 0 for right in choices} for left in choices}
    for left, right in pairs:
        matrix[left][right] += 1
    total = len(pairs)
    raw = sum(left == right for left, right in pairs) / total if total else None
    expected = (sum(sum(matrix[key].values()) * sum(matrix[left][key] for left in choices)
                    for key in choices) / total ** 2 if total else None)
    kappa = ((raw - expected) / (1 - expected)
             if total and expected != 1 else None)
    return {"total_cards": len(first), "paired_answered": total,
            "first_answered": sum(item is not None for item in first),
            "second_answered": sum(item is not None for item in second),
            "raw_agreement": raw, "cohen_kappa": kappa,
            "kappa_undefined_reason": ("no paired answers" if not total else
                                       "zero expected-disagreement denominator" if expected == 1 else None),
            "confusion": matrix}


def score_reviews(first_path, second_path, packet_dir, output):
    packet = verify_packet(packet_dir)
    first_id, first = read_review(first_path, packet)
    second_id, second = read_review(second_path, packet)
    if first_id == second_id:
        raise ValueError("independent reviews require distinct reviewer identifiers")
    ids = [card["card_id"] for card in packet["cards"]]
    summary = {"schema": SCHEMA, "packet_id": packet["packet_id"],
               "reviewers": [first_id, second_id],
               "input_sha256": [digest(first_path), digest(second_path)], "targets": {}}
    for target, choices in CATEGORIES.items():
        summary["targets"][target] = agreement(
            [first.get(identity, {}).get(target) for identity in ids],
            [second.get(identity, {}).get(target) for identity in ids], choices)
    disputes = []
    for identity in ids:
        targets = {}
        for target in CATEGORIES:
            left, right = first.get(identity, {}).get(target), second.get(identity, {}).get(target)
            if left != right or left is None:
                targets[target] = {"first": left, "second": right,
                                   "disposition": "missing" if left is None or right is None else "disagreement",
                                   "adjudicated_label": None, "witnesses": [], "reason": ""}
        if targets:
            disputes.append({"card_id": identity, "targets": targets})
    output = fresh_output(output)
    write_json(output / "agreement.json", summary)
    write_json(output / "adjudication.json", {"schema": SCHEMA, "packet_id": packet["packet_id"],
                                              "adjudicator_id": "", "items": disputes})
    (output / "README.md").write_text(
        "Independent initial labels remain unchanged. Complete adjudication separately.\n"
        "Null labels are missing answers; unknown/unassessable are explicit answers.\n"
        "Agreement is unweighted across unique cards, not task-population accuracy.\n"
        "Method-specific weighted analysis requires the separate private mapping.\n"
        "No human identity, label, or adjudication is generated by this scorer.\n", encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--score", nargs=2, type=Path, metavar=("FIRST", "SECOND"))
    parser.add_argument("--packet", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.score:
            if args.study_dir or not args.packet:
                parser.error("--score requires --packet and cannot use --study-dir")
            result = score_reviews(*args.score, args.packet, args.output)
        else:
            if not args.study_dir or args.packet:
                parser.error("building requires --study-dir and cannot use --packet")
            result = build_packet(args.study_dir, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
