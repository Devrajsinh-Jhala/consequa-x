"""Build an unlabeled, offline human review packet from frozen public inputs only.

Never reads judge responses, evaluation context, evaluator truth, or automatic
predictions. The private source mapping and source hashes stay outside the ZIP.
Building a packet is not human validation: reviewers must perform the annotation.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import html
import io
import json
from pathlib import Path
import random
import re
import zipfile


SCHEMA = "consequa-blinded-trace-review-v1"
SHUFFLE_SEED = 20261018084
COLUMNS = ("reviewer_id", "case_id", "state", "action_linked", "origin", "support", "note")
LABEL_COLUMNS = ("state", "action_linked", "origin")
FORBIDDEN_KEYS = {"gold", "fault", "case_id", "model", "policy", "policy_request", "policy_reply",
                  "verifications", "verification", "explanation", "assessment", "rationale",
                  "world_seed", "trial_seed", "prompt_version", "evaluator_truth", "trace_id"}
IDENTITY_KEYS = {"action_id", "actor", "payment_id", "attempt_id", "effect_id", "refund_id",
                 "idempotency_key", "provider_request_id", "observation_id"}

RUBRIC = """# Evidence annotation rubric

Read the registered contract and the captured independent readback. Public tool
responses are acknowledgements about requests; they do not establish effects.
Identifiers are opaque and local to each card. Equal identifiers within one card
refer to the same entity; equal spellings on different cards need not.

Use only evidence on the card. Do not infer missing facts from a case number,
another card, a successful response, or the study's purpose. A blank annotation
means not yet reviewed; use the explicit `unknown` label for a reviewed but
unassessable target. The optional support field should cite a visible field,
record identifier or timestamp, not invent an unseen event.

## State: satisfied / violated / unknown

Match the contract's payment, amount and currency. Registration is the earliest
in-scope commit time. The horizon is `deadline_ms + stability_ms`, with both
deadline and horizon inclusive. A qualifying effect commits no later than the
deadline and remains unreversed through the horizon. A reversal exactly at the
horizon does not satisfy persistence. An effect after the horizon is outside
scope. With `exact_count`, the number of matching effects must equal that count
throughout the inclusive stability window; an extra matching effect during the
window violates that requirement, even if it is later reversed.

`satisfied`: adequate independent readback establishes the contract.
`violated`: adequate independent readback establishes a contract failure.
`unknown`: the evidence cannot establish either, including unavailable,
incomplete, malformed, wrong-scope or horizon-stale readback. Do not treat a
missing or stale record as evidence of absence. An exhaustive empty snapshot
can establish absence only when scope and the required horizon are covered.

## Origin: confirmed / other_actor / unknown

Consider relevant observed refunds from registration through the horizon,
including wrong-amount and reversed effects; these can establish origin even
when the requested target fails. `confirmed` requires a trustworthy observed
link to this action and its actor. `other_actor` requires observed effects
explicitly belonging only to other actors, with none linked to this action.
`unknown` applies to missing or insufficient provenance, no relevant effect, or
insufficient independent readback. A request identifier alone is not an origin
proof. Origin is provenance evidence, not counterfactual causal responsibility.

## Action-linked target: satisfied / not_satisfied / unknown

`satisfied`: the state target is satisfied and sufficient qualifying effects are
linked to this action and actor. Check payload, deadline and persistence as well
as the provenance link.
`not_satisfied`: a known state violation, or a satisfied state supported only by
other actors' effects.
`unknown`: insufficient target/provenance evidence. State satisfaction alone
does not establish this action's target. An exact-count-zero target has unknown
action linkage because absence is not a qualifying action-produced effect.

## Independent review procedure

1. Two reviewers each make a separate copy of `blank_annotations.csv`, assign
   their own reviewer identifier, and label every case independently using this
   rubric. Keep each reviewer's original completed file. Do not share labels
   before both initial annotation files are locked.
2. Record uncertain evidence as `unknown`, with an optional short support/note.
   Do not force agreement or guess an outcome. The packet contains no expected
   labels, machine predictions, model identity or evaluator truth.
3. After both independent files are complete, compare labels and retain all
   original disagreements. If adjudication is needed, have a third reviewer
   inspect the evidence/rubric and record a separate adjudication file and reason.
   Do not overwrite the two independent records.
4. Report actual reviewed counts, missing cases, reviewer qualifications,
   disagreement/adjudication counts and agreement methodology before making a
   human-validation claim. A single author's self-review is not independent
   double annotation. Agreement is not a substitute for an independent source
   of simulator or real-service truth.

These are 84 recorded evidence cards from fixed simulator conditions. Some
evidence may repeat. Card count, repeated evidence and repeated annotations do
not establish 84 independent tasks, held-out mechanisms or real-service transfer.
Preparing this packet does not mean any human has reviewed it.
"""

README = """# Blinded evidence review packet

Open `index.html` in a browser; it works offline and makes no network requests.
Read `rubric.md`, then fill a separate copy of `blank_annotations.csv` for each
independent reviewer. Use a spreadsheet editor or a text editor and preserve
the CSV column names. Each of the 84 renamed cards has a corresponding JSON
file in `cases/`. Labels and reviewer identifiers are deliberately blank.

Allowed labels:

| CSV field | Values |
| --- | --- |
| state | satisfied, violated, unknown |
| action_linked | satisfied, not_satisfied, unknown |
| origin | confirmed, other_actor, unknown |

The optional `support` field may cite the visible evidence; `note` may explain
an ambiguity. Each reviewer should label all cards independently before seeing
another reviewer's labels. Keep original independent files and any later
adjudication separately. Follow the full instructions in `rubric.md`.

No expected answers or automatic predictions are supplied. The packet is ready
for human annotation; it is **not evidence that human validation has occurred**.
Repeated cards are not independent tasks. Identifiers are meaningful only within
a card. `manifest.json` lists shareable file hashes for checking unchanged bytes;
it does not authenticate evidence or establish correctness.

Share this ZIP or its extracted contents. The creator's private mapping and
source inventory are kept outside this packet and must not be given to blinded
reviewers before independent labels are locked.
"""


def digest(content):
    return sha256(content).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_public(value):
    if set(value) != {"action", "attempts", "responses", "observation"}:
        raise ValueError("Unexpected frozen public input shape")

    def walk(current):
        if isinstance(current, dict):
            if set(current) & FORBIDDEN_KEYS:
                raise ValueError("Disallowed metadata in public input")
            for key, nested in current.items():
                if key in IDENTITY_KEYS and nested is not None:
                    if not isinstance(nested, str) or not re.fullmatch(r"id-\d{4}", nested):
                        raise ValueError("Input contains a nonopaque identifier")
                walk(nested)
        elif isinstance(current, list):
            for nested in current:
                walk(nested)
    walk(value)


def json_block(value):
    return "<pre>" + html.escape(json.dumps(value, indent=2, ensure_ascii=False)) + "</pre>"


def page(cards, *, deduplicate=False):
    links = " ".join(f'<a href="#{case_id}">{case_id}</a>' for case_id, _ in cards)
    rendered = []
    for case_id, value in cards:
        rendered.append(f'<article id="{case_id}"><h2>{case_id}</h2>'
            '<p class="hint">Use this case ID in your own copy of the blank CSV. '
            'Evidence only; no supplied answer.</p>'
            '<div class="columns"><section><h3>Registered action and contract</h3>'
            + json_block(value["action"]) + '</section><section><h3>Independent readback</h3>'
            + json_block(value["observation"]) + '</section></div>'
            '<details><summary>Public dispatch attempts and responses</summary>'
            '<h3>Dispatch attempts</h3>' + json_block(value["attempts"])
            + '<h3>Tool responses</h3>' + json_block(value["responses"]) + '</details>'
            f'<p><a href="cases/{case_id}.json">Evidence JSON</a> · '
            '<a href="#cases">Back to case list</a></p></article>')
    rendered_page = ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'">
<title>Blinded evidence review</title><style>
:root{color-scheme:light;font-family:system-ui,sans-serif;color:#1b2530;background:#f2f4f7;line-height:1.6}
body{max-width:1200px;margin:auto;padding:24px}header,article,.rubric{background:white;border:1px solid #ccd4dc;border-radius:12px;padding:24px;margin-bottom:24px}
h1,h2,h3{line-height:1.25}h1{font-size:2rem}h2{font-size:1.5rem}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px;min-width:0}.columns section{min-width:0}
pre{padding:16px;background:#f5f7fa;border:1px solid #dce3eb;border-radius:8px;overflow:auto;font:13px/1.6 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
a{color:#1253a8}nav a{display:inline-block;padding:5px 8px;margin:3px;border:1px solid #c4cedc;border-radius:5px;text-decoration:none}.hint{color:#536273}summary{cursor:pointer;font-weight:600;padding:12px 0}
@media(max-width:760px){body{padding:12px}header,article,.rubric{padding:16px}.columns{grid-template-columns:1fr;gap:8px}}@media print{nav,.back{display:none}article{break-inside:avoid}body{max-width:none;background:white}details>*{display:block}}
</style></head><body><header><h1>Blinded evidence review</h1>
<p>84 recorded evidence cards. Reviewers must supply their own actual judgments;
this packet contains no supplied answers or automatic labels.</p>
<p><a href="rubric.md">Full rubric and independent review instructions</a> ·
<a href="blank_annotations.csv" download>Blank annotation CSV</a> · <a href="README.md">Read me</a></p>
<p>Use two independent reviewers before discussing labels. Preserve both original
annotation files and later adjudication separately. Blank means unreviewed;
<strong>unknown</strong> means reviewed evidence is insufficient. Repeated
evidence is not an independent task. This file works offline.</p></header>
<section class="rubric"><h2>Labels at a glance</h2>
<p><strong>State:</strong> satisfied / violated / unknown.
Match payment, amount, currency, exact count, deadline and persistence horizon.</p>
<p><strong>Action-linked target:</strong> satisfied / not_satisfied / unknown.
Check sufficient qualifying effects linked to this action and actor. State
satisfaction alone does not establish action linkage.</p>
<p><strong>Origin:</strong> confirmed / other_actor / unknown.
Separate observed provenance from target correctness and causal responsibility.</p>
<p>A tool acknowledgement is not an independent effect witness. Missing, stale
or incomplete readback cannot establish absence. Read the full rubric before
labeling; equal opaque IDs are meaningful only within one card.</p></section>
<nav id="cases" aria-label="Evidence cases">""" + links + "</nav>" + "".join(rendered)
            + "</body></html>\n")
    if deduplicate:
        rendered_page = rendered_page.replace("84 recorded evidence cards.",
            f"{len(cards)} unique evidence patterns observed in 84 selected traces.")
        rendered_page = rendered_page.replace("this packet contains no supplied answers or automatic labels.</p>",
            "this packet contains no supplied answers or automatic labels.</p>"
            f"<p>Primary human agreement uses the {len(cards)} unique patterns. Any later "
            "frequency-weighted expansion to 84 traces is descriptive; repeated cases "
            "and annotations are not independent tasks.</p>")
    return rendered_page.encode("utf-8")


def build(judge_output, output, *, deduplicate=False):
    source, out = Path(judge_output).resolve(), Path(output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Review packet output must be new or empty")
    protocol_bytes = (source / "protocol.json").read_bytes()
    protocol = json.loads(protocol_bytes)
    if digest(protocol_bytes) != load(source / "protocol.sha256.json")["sha256"]:
        raise ValueError("Frozen input protocol hash changed")
    schedule = protocol["schedule"]
    if (protocol["selected_planned"] != 84 or len(schedule) != 84
            or any(s["input_status"] != "available" or s["slot"]["repetition"] != 0 for s in schedule)):
        raise ValueError("Packet requires exactly the 84 available frozen repetition-zero inputs")
    ordered = list(schedule)
    random.Random(SHUFFLE_SEED).shuffle(ordered)
    prepared = []
    for index, entry in enumerate(ordered, 1):
        original = source / entry["input_file"]
        if not original.is_relative_to(source / "inputs") or original.is_symlink():
            raise ValueError("Unexpected input source path")
        content = original.read_bytes()
        if digest(content) != entry["input_sha256"]:
            raise ValueError("Frozen public input changed")
        value = json.loads(content)
        validate_public(value)
        prepared.append((f"C{index:04d}", value, content, entry, original))
    source_groups = {}
    for _, _, content, entry, original in prepared:
        source_groups.setdefault(digest(content), []).append((entry, original))
    if deduplicate:
        unique = {}
        for _, value, content, entry, original in prepared:
            unique.setdefault(digest(content), (value, content, entry, original))
        prepared = [(f"C{index:04d}", *record)
                    for index, record in enumerate(unique.values(), 1)]
        if len(prepared) != 17:
            raise ValueError("This deduplicated packet requires the declared 17 exact input patterns")
    case_count = len(prepared)
    member_count = case_count + 5
    unit_disclosure = (
        f"Human agreement uses {case_count} unique evidence patterns as its primary denominator. "
        "These were observed in 84 selected traces. Any frequency-weighted expansion to 84 "
        "is descriptive; repeated evidence and annotations are not independent tasks."
        if deduplicate else "Repeated evidence and annotations are not independent tasks.")
    pack = out / "pack"
    for case_id, _, content, _, _ in prepared:
        write_new(pack / "cases" / f"{case_id}.json", content)
    write_new(pack / "index.html", page([(case_id, value) for case_id, value, *_ in prepared],
                                       deduplicate=deduplicate))
    readme = README
    rubric = RUBRIC
    if deduplicate:
        readme = readme.replace("Each of the 84 renamed cards", "Each of the 17 renamed unique-pattern cards")
        readme += "\n" + unit_disclosure + "\n"
        rubric = rubric.replace("These are 84 recorded evidence cards from fixed simulator conditions. Some\n"
            "evidence may repeat. Card count, repeated evidence and repeated annotations do\n"
            "not establish 84 independent tasks, held-out mechanisms or real-service transfer.",
            "These are 17 unique public-evidence byte patterns observed in 84 selected\n"
            "traces from fixed simulator conditions. " + unit_disclosure + "\n"
            "These patterns do not establish independent tasks, held-out mechanisms or\n"
            "real-service transfer.")
    write_new(pack / "README.md", readme.encode())
    write_new(pack / "rubric.md", rubric.encode())
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({"case_id": case_id} for case_id, *_ in prepared)
    write_new(pack / "blank_annotations.csv", buffer.getvalue().encode("utf-8"))
    inventory = {p.relative_to(pack).as_posix(): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                 for p in sorted(pack.rglob("*")) if p.is_file()}
    write_new(pack / "manifest.json", encoded({"schema_version": SCHEMA, "case_count": case_count,
        "annotation_unit": "unique exact public-input byte patterns" if deduplicate else "recorded evidence cards",
        "annotation_status": "blank; actual human review has not been performed by this builder",
        "files": inventory, "excludes": ["manifest.json"]}))
    archive = out / ("Consequa-X_blinded-unique-review.zip" if deduplicate else "Consequa-X_blinded-trace-review.zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in sorted(pack.rglob("*")):
            if path.is_file():
                member = zipfile.ZipInfo(path.relative_to(pack).as_posix(), date_time=(2026, 10, 18, 0, 0, 0))
                member.compress_type = zipfile.ZIP_DEFLATED
                member.external_attr = 0o100644 << 16
                zipped.writestr(member, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    private = out / "private"
    write_new(private / "case-map.private.json", encoded({"schema_version": SCHEMA,
        "shuffle_seed": SHUFFLE_SEED, "mapping": {
            case_id: [member[0]["slot"]["slot_id"] for member in source_groups[digest(content)]]
            if deduplicate else entry["slot"]["slot_id"]
            for case_id, _, content, entry, _ in prepared},
        "frequency_weights": {case_id: len(source_groups[digest(content)]) if deduplicate else 1
                              for case_id, _, content, *_ in prepared},
        "annotation_unit_disclosure": unit_disclosure,
        "sharing": "Private mapping. Do not share with blinded reviewers before locked annotations."}))
    write_new(private / "source-input-inventory.private.json", encoded({"schema_version": SCHEMA,
        "frozen_protocol_sha256": digest(protocol_bytes),
        "builder_source_sha256": digest(Path(__file__).read_bytes()),
        "inputs": {case_id: {"representative_source_path": str(original),
                             "all_source_paths": [str(member[1]) for member in source_groups[digest(content)]]
                                                 if deduplicate else [str(original)],
                             "source_sha256": digest(content), "pack_path": f"cases/{case_id}.json"}
            for case_id, _, content, _, original in prepared}}))
    write_new(private / "builder.source.py", Path(__file__).read_bytes())
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)) or len(names) != member_count:
            raise ValueError("Review archive has unexpected files or duplicates")
        expected_names = set(inventory) | {"manifest.json"}
        if set(names) != expected_names or any("private" in name for name in names):
            raise ValueError("Review archive exposed private/nonpack files")
        rows = list(csv.DictReader(io.StringIO(zipped.read("blank_annotations.csv").decode())))
        expected_ids = {f"C{i:04d}" for i in range(1, case_count + 1)}
        if len(rows) != case_count or {row["case_id"] for row in rows} != expected_ids:
            raise ValueError("Blank annotation case denominator changed")
        if any(row[key] for row in rows for key in COLUMNS if key != "case_id"):
            raise ValueError("Review archive contains prefilled annotations")
        original_ids = [entry["slot"]["slot_id"] for entry in schedule]
        labels = {entry["slot"][key] for entry in schedule for key in ("model", "case_id", "prompt_version")}
        for name in names:
            content = zipped.read(name)
            if name != "manifest.json":
                if digest(content) != inventory[name]["sha256"]:
                    raise ValueError("Pack byte hash differs from manifest")
            rendered = content.decode("utf-8")
            if any(label in rendered for label in [*original_ids, *labels]):
                raise ValueError("Original labels leaked into review archive")
            if name.startswith("cases/"):
                validate_public(json.loads(content))
    unique_inputs = len({digest(content) for _, _, content, *_ in prepared})
    receipt = {"schema_version": SCHEMA + "-build-receipt",
        "archive": archive.name, "archive_sha256": digest(archive.read_bytes()),
        "archive_bytes": archive.stat().st_size, "archive_members": member_count,
        "evidence_cases": case_count, "blank_annotation_rows": case_count,
        "deduplicated": deduplicate, "source_selected_traces": 84,
        "annotation_unit_disclosure": unit_disclosure,
        "unique_input_byte_hashes": unique_inputs,
        "frozen_protocol_sha256": digest(protocol_bytes),
        "builder_source_sha256": digest(Path(__file__).read_bytes()),
        "checks": {"all_case_bytes_match_frozen_public_inputs": True,
            "all_labels_and_reviewer_ids_blank": True, "source_ids_and_generator_labels_absent": True,
            "private_mapping_and_inventory_outside_zip": True, "all_public_manifest_hashes_match": True,
            "no_judge_outputs_or_automatic_labels_read": True},
        "human_validation_status": "Not performed; packet requires actual independent human judgments.",
        "interpretation": "Repeated evidence and annotations are not independent tasks. Only the ZIP "
                          "and pack directory are shareable. Keep private mapping and inventory private."}
    write_new(out / "build-receipt.json", encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-output", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--deduplicate", action="store_true")
    args = parser.parse_args()
    result = build(args.judge_output, args.output, deduplicate=args.deduplicate)
    print(json.dumps({key: result[key] for key in ("archive", "archive_sha256", "archive_members",
                                                  "evidence_cases", "blank_annotation_rows")}))


if __name__ == "__main__":
    main()
