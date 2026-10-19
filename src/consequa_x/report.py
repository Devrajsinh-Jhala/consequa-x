"""Dependency-free, offline presentation of a captured trace.

The structural view deliberately omits captured strings and payloads, rather
than attempting to detect personal information. It is not a replacement for the
original evidence. Rendering neither verifies an outcome nor runs an action.
"""

from __future__ import annotations

from html import escape
import json

from .errors import ConsequaTypeError, ValidationError
from .explanation import CORE_DIAGNOSES, explain
from .graph import ConsequenceGraph, GraphNode, build_graph
from .models import EventType, Trace, to_dict


_CSS = """
:root{color-scheme:light;--ink:#17283a;--muted:#4a6175;--line:#d9e5eb;
--paper:#fff;--canvas:#edf3f6;--accent:#126c73;--soft:#e7f5f3}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);
font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:#075d68}a:focus-visible,summary:focus-visible,.table-wrap:focus-visible,
.graph-scroll:focus-visible{outline:3px solid #a55308;
outline-offset:4px}header,main,footer{max-width:1160px;margin:auto;padding:24px}
header{padding-top:48px}h1{font-size:clamp(2rem,5vw,3.3rem);line-height:1.1;
letter-spacing:-.04em;margin:12px 0}h2{font-size:1.55rem;margin:0 0 16px}
h3{font-size:1.05rem;margin:0 0 8px}p{margin:8px 0 16px}.eyebrow{font-size:.8rem;
font-weight:750;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.subtitle,.muted{color:var(--muted)}nav{display:flex;flex-wrap:wrap;gap:10px 24px;
margin-top:22px}nav a{font-weight:650}section,.notice{background:var(--paper);
border:1px solid var(--line);border-radius:18px;padding:24px;margin-bottom:24px}
.notice{border-left:5px solid var(--accent);background:var(--soft)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}
.card{border:1px solid var(--line);border-radius:12px;padding:18px;background:#f8fbfc}
.value{font-size:1.4rem;font-weight:750;overflow-wrap:anywhere}.small{font-size:.87rem}
.pill{display:inline-block;padding:2px 9px;border-radius:20px;background:#e5eff3;
font-weight:650;font-size:.85rem}.status-satisfied,.status-confirmed{background:#dff4e9}
.status-violated,.status-other_actor,.status-contradicted{background:#ffeadb}
.status-unknown,.status-unassessable{background:#fff2cd}.status-consistent{background:#dff4e9}
.codes{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 0;padding:0;list-style:none}
.codes li{font:12px/1.5 ui-monospace,Consolas,monospace;background:#eef4f6;border-radius:6px;
padding:2px 7px}
dl{display:grid;grid-template-columns:minmax(130px,1fr) 2fr;gap:8px 16px;margin:0}
dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.table-wrap{overflow:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem;text-align:left}
caption{text-align:left;color:var(--muted);padding-bottom:10px}th,td{padding:10px 12px;
border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
th{font-weight:700;background:#f2f7f9}tbody tr:hover{background:#f6fafb}
.timeline{list-style:none;margin:0;padding:0}.timeline li{display:grid;
grid-template-columns:105px 1fr;gap:18px;border-left:2px solid #c2d7de;
margin-left:8px;padding:0 0 20px 20px}.time{font-variant-numeric:tabular-nums;
font-weight:650;color:var(--accent)}.timeline li:last-child{padding-bottom:0}
.graph-scroll{overflow:auto;border:1px solid var(--line);border-radius:12px;
background:#fafcfd;margin-bottom:22px}.graph{display:block;min-width:880px;width:100%}
.graph text{font-family:system-ui,sans-serif;fill:var(--ink)}.graph .node{fill:#fff;
stroke:#b6cdd7;stroke-width:1.5}.graph .node-evidence{fill:#e9f7f3;stroke:#7db5aa}
.graph .link{fill:none;stroke:#93abb9;stroke-width:1.3;opacity:.65}
.graph .link-effect{stroke:#076b63;stroke-width:2;opacity:.9}
.graph .lane{font-size:12px;font-weight:700;fill:var(--muted)}
.graph .node-label{font-size:13px;font-weight:700}.graph .node-kind{font-size:10px}
details{border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:18px}
summary{cursor:pointer;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;
font:12px/1.65 ui-monospace,Consolas,monospace;background:#f2f6f8;padding:16px;
border-radius:8px}footer{color:var(--muted);font-size:.85rem;padding-bottom:40px}
.print-only{display:none}
@media(max-width:640px){header,main,footer{padding:18px}header{padding-top:32px}
section,.notice{padding:18px}dl{grid-template-columns:1fr;gap:3px}dd{margin-bottom:10px}
.timeline li{grid-template-columns:75px 1fr;gap:10px;padding-left:12px}}
@media print{body{background:white;font-size:10pt}header,main,footer{max-width:none;
padding:10px}section,.notice{border-radius:0;box-shadow:none;break-inside:auto}
.cards,.card{break-inside:avoid}nav,.graph-scroll,.overview-description{display:none}
.print-only{display:block}.table-wrap{overflow:visible}
thead{display:table-header-group}tr,.timeline li{break-inside:avoid}
a{color:inherit;text-decoration:none}details:not([open]){display:none}}
"""

# Finding codes of the built-in verifiers. Other verifier findings are counted, not shown,
# because their codes are application-defined strings.
_BUILT_IN_FINDINGS = {"EXCESS_EFFECTS", "DUPLICATE_EFFECT", "PARAMETER_MISMATCH",
                      "PARTIAL_EFFECT", "REVERSED_EFFECT", "REMOVED_EFFECT"}
_NODE_LABELS = {item.value: item.value.replace("_", " ") for item in EventType}
_NODE_LABELS.update({
    "postcondition": "outcome contract",
    "observed_external_effect": "effect witness",
    "external_effect_identity": "shared effect identity",
})
_EDGE_LABELS = {
    "DEPENDENCY": "Declared dependency",
    "TEMPORAL": "Captured order",
    "RESPONSE": "Response to attempt",
    "EFFECT": "Provider origin metadata",
    "OBSERVATION": "Readback witness",
    "IDENTITY": "Shared effect identifier",
    "CONTRACT": "Declared contract",
    "VERIFICATION": "Verification evidence",
}
_EDGE_MEANINGS = {
    "DEPENDENCY": "Declared parent relationship; does not prove causal necessity.",
    "TEMPORAL": "Captured event chronology; does not establish causation.",
    "RESPONSE": "Response joined to one unambiguous captured attempt.",
    "EFFECT": "Readback contains matching propagated action and attempt metadata; "
              "source authenticity is not established by this link.",
    "OBSERVATION": "This observation contains this individual effect witness.",
    "IDENTITY": "Witnesses share a reported effect identifier; payloads remain separate.",
    "CONTRACT": "Verification concerns the registered outcome contract.",
    "VERIFICATION": "Captured observation or witness supports a recorded verification.",
}


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _status(value: str) -> str:
    # Callers pass only values of validated, closed schema enums.
    return f'<span class="pill status-{_text(value)}">{_text(value)}</span>'


def _table(caption: str, headings: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return '<p class="muted">None recorded.</p>'
    return (
        '<div class="table-wrap" role="region" tabindex="0" aria-label="'
        + _text(caption) + '"><table><caption>' + _text(caption) + '</caption><thead><tr>'
        + ''.join('<th scope="col">' + _text(label) + '</th>' for label in headings)
        + '</tr></thead><tbody>'
        + ''.join('<tr>' + ''.join('<td>' + cell + '</td>' for cell in row) + '</tr>'
                  for row in rows)
        + '</tbody></table></div>'
    )


def _aliases(trace: Trace, graph: ConsequenceGraph) -> dict[str, str]:
    aliases = {event.id: f"Event {index}" for index, event in enumerate(trace.events, 1)}
    for index, action in enumerate(trace.actions, 1):
        aliases[f"contract:{action.contract.contract_id}"] = f"Contract {index}"
    for index, observation in enumerate(trace.observations, 1):
        aliases[f"observation:{observation.observation_id}"] = f"Observation {index}"
    for index, verification in enumerate(trace.verifications):
        aliases[f"verification:{verification.contract_id}:{index}"] = f"Verification {index + 1}"
    counters: dict[str, int] = {}
    for node in graph.nodes:
        if node.id not in aliases:
            prefix = "Witness" if node.kind == "observed_external_effect" else "Effect identity"
            counters[prefix] = counters.get(prefix, 0) + 1
            aliases[node.id] = f"{prefix} {counters[prefix]}"
    return aliases


def _lane(node: GraphNode) -> int:
    if node.kind in {"observed_external_effect", "external_effect_identity"}:
        return 1
    if node.kind == "external_observation":
        return 2
    if node.kind in {"postcondition", "verification"}:
        return 3
    return 0


def _graph_svg(graph: ConsequenceGraph, aliases: dict[str, str]) -> str:
    # Bound the overview only. Complete node and edge tables below are never truncated.
    shown = sorted(enumerate(graph.nodes), key=lambda item: (item[1].time_ms, item[0]))[:32]
    positions = {node.id: (16 + 228 * _lane(node), 50 + 64 * index)
                 for index, (_, node) in enumerate(shown)}
    height = 84 + 64 * len(shown)
    parts = [f'<svg class="graph" viewBox="0 0 928 {height}" role="img" '
             'aria-labelledby="graph-title graph-description" '
             'xmlns="http://www.w3.org/2000/svg">',
             '<title id="graph-title">Captured evidence graph overview</title>',
             '<desc id="graph-description">Nodes use report-local aliases. Arrows show '
             'the captured evidence links described in the complete tables below. '
             'The overview includes at most 32 nodes.</desc>',
             '<defs><marker id="arrow" markerWidth="7" markerHeight="7" '
             'refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7Z" '
             'fill="#93abb9"/></marker></defs>']
    for lane, label in enumerate(("Captured events", "Effect witnesses", "Readback", "Contract / result")):
        parts.append(f'<text class="lane" x="{24 + lane * 228}" y="26">{label}</text>')
    for edge in graph.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1 = positions[edge.source]
        x2, y2 = positions[edge.target]
        if x1 == x2:
            path = f"M{x1 + 90} {y1 + 46}L{x2 + 90} {y2}"
        else:
            start = x1 + (206 if x2 > x1 else 0)
            end = x2 + (0 if x2 > x1 else 206)
            middle = (start + end) / 2
            path = (f"M{start} {y1 + 23}C{middle} {y1 + 23} "
                    f"{middle} {y2 + 23} {end} {y2 + 23}")
        style = "link link-effect" if edge.kind == "EFFECT" else "link"
        parts.append(f'<path class="{style}" d="{path}" marker-end="url(#arrow)">'
                     f'<title>{_text(aliases[edge.source])} to {_text(aliases[edge.target])}: '
                     f'{_text(_EDGE_LABELS[edge.kind])}</title></path>')
    for _, node in shown:
        x, y = positions[node.id]
        style = "node" if _lane(node) == 0 else "node node-evidence"
        parts.append(f'<g><rect class="{style}" x="{x}" y="{y}" width="206" '
                     f'height="46" rx="8"/><text class="node-label" x="{x + 10}" '
                     f'y="{y + 18}">{_text(aliases[node.id])}</text>'
                     f'<text class="node-kind" x="{x + 10}" y="{y + 35}">'
                     f'{_text(_NODE_LABELS[node.kind])} · {node.time_ms} ms</text></g>')
    return ('<div class="graph-scroll" role="region" tabindex="0" '
            'aria-label="Captured evidence graph overview">' + ''.join(parts) + '</svg></div>')


def _timeline(trace: Trace, numbers: dict[str, int]) -> str:
    entries = [(action.registered_at_ms, f"Action {index} registered", f"Contract {index} declared")
               for index, action in enumerate(trace.actions, 1)]
    entries.extend((event.time_ms, f"Event {index}", _NODE_LABELS[event.type.value])
                   for index, event in enumerate(trace.events, 1))
    entries.extend((response.time_ms, f"Response {index}",
                    f"Action {numbers[response.action_id]}: {response.status.value}")
                   for index, response in enumerate(trace.responses, 1))
    entries.extend((assessment.time_ms, f"Assessment {index}",
                    f"Action {numbers[assessment.action_id]}: agent reported "
                    f"{assessment.status.value}")
                   for index, assessment in enumerate(trace.assessments, 1))
    entries.extend((observation.observed_at_ms, f"Observation {index}",
                    f"Readback watermark {observation.as_of_ms} ms; "
                    f"{'complete' if observation.complete else 'incomplete'}; "
                    f"{'available' if observation.available else 'unavailable'}")
                   for index, observation in enumerate(trace.observations, 1))
    entries.extend((verification.observed_at_ms, f"Verification {index}",
                    f"Action {numbers[verification.action_id]}: state "
                    f"{verification.status.value}; origin {verification.origin.value}")
                   for index, verification in enumerate(trace.verifications, 1))
    entries.sort(key=lambda entry: entry[0])  # Stable within equal timestamps.
    return '<ol class="timeline">' + ''.join(
        f'<li><span class="time">{time} ms</span><div><strong>{_text(label)}</strong>'
        f'<div class="muted">{_text(description)}</div></div></li>'
        for time, label, description in entries
    ) + '</ol>'


def _redacted(value, names: frozenset[str]):
    if isinstance(value, dict):
        return {key: "[redacted]" if key.lower() in names else _redacted(item, names)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item, names) for item in value]
    return value


def render_report(trace: Trace, *, include_details: bool = False,
                  redact: tuple[str, ...] = ()) -> str:
    """Return a self-contained HTML report without executing application logic.

    The default includes closed schema enums, numeric times/counts and local
    aliases. It omits all arbitrary captured strings, identifiers and payloads
    from the entire file. ``include_details=True`` explicitly appends the whole
    captured trace as escaped, inert JSON; that file may contain sensitive data.
    ``redact`` names JSON keys (case-insensitive) whose values are replaced with
    ``"[redacted]"`` wherever they occur in that included trace, for example
    ``("card_number", "email")``. This is field omission by name, not a general
    redaction or anonymization guarantee: values under other keys are kept.

    All verification records are displayed as captured. Assessment alignment and
    diagnoses are derived from the recorded receipts exactly as ``explain`` derives
    them; no verifier is invoked.
    Source authenticity and causal necessity are not inferred. The returned
    presentation does not replace the original trace or its verification data.
    """
    if not isinstance(trace, Trace):
        raise ConsequaTypeError("render_report requires a Trace")
    if type(include_details) is not bool:
        raise ConsequaTypeError("include_details must be a boolean")
    if isinstance(redact, str) or not all(isinstance(item, str) and item.strip()
                                          for item in redact):
        raise ConsequaTypeError("redact must be a sequence of nonempty key names")
    names = frozenset(item.strip().lower() for item in redact)
    try:
        # Revalidate a detached snapshot: nested JSON containers remain mutable
        # even though public record dataclasses are frozen.
        snapshot = Trace.from_dict(to_dict(trace))
    except (TypeError, ValueError, RecursionError):
        raise ValidationError("Cannot render an invalid trace") from None
    try:
        graph = build_graph(snapshot)
    except (TypeError, ValueError):
        # Graph identity errors can include captured IDs; never repeat them.
        raise ValidationError("Cannot render a trace with conflicting evidence graph identities") from None
    aliases = _aliases(snapshot, graph)
    explanation = explain(snapshot)
    numbers = {action.action_id: index for index, action in enumerate(snapshot.actions, 1)}
    several = len(snapshot.actions) > 1
    detail_notice = (
        "Captured details included. This file contains the complete original trace and may contain "
        "sensitive data. Review it before sharing."
        if include_details else
        "Structural view. Captured text, raw identifiers and payloads are omitted from this entire "
        "file. Times, counts, relationships and status enums remain visible; these can still be "
        "sensitive. This is not a universal anonymization guarantee."
    )
    summary_cards = []
    contract_lists = []
    for index, action in enumerate(snapshot.actions, 1):
        # The portable schema does not require records to be chronologically sorted.
        # Break equal-time ties by capture order without rewriting the evidence.
        latest = max(enumerate(snapshot.verifications_for(action.action_id)),
                     key=lambda item: (item[1].observed_at_ms, item[0]), default=(0, None))[1]
        assessment = snapshot.latest_assessment(action.action_id)
        state = _status(latest.status.value) if latest else "not recorded"
        origin = _status(latest.origin.value) if latest else "not recorded"
        reported = _status(assessment.status.value) if assessment else "not recorded"
        judged = explanation.for_action(action.action_id)
        shown = [code for code in judged.codes
                 if code in CORE_DIAGNOSES or code in _BUILT_IN_FINDINGS]
        other = len(judged.codes) - len(shown)
        codes = ('<ul class="codes" aria-label="Diagnoses">'
                 + ''.join(f'<li>{_text(code)}</li>' for code in shown)
                 + (f'<li>{other} other verifier finding{"s" if other != 1 else ""}</li>'
                    if other else '') + '</ul>')
        summary_cards.append(
            (f'<h3>Action {index}</h3>' if several else '') + '<div class="cards">'
            f'<div class="card"><h3>Tool responses</h3><div class="value">'
            f'{len(snapshot.responses_for(action.action_id))}</div><p class="small muted">'
            'All captured responses below</p></div>'
            f'<div class="card"><h3>Agent assessment</h3><div class="value">{reported}</div>'
            '<p class="small muted">Latest report by the agent</p></div>'
            f'<div class="card"><h3>Latest verified state</h3><div class="value">{state}</div>'
            '<p class="small muted">Captured independent verification</p></div>'
            f'<div class="card"><h3>Latest effect origin</h3><div class="value">{origin}</div>'
            '<p class="small muted">Separate from state satisfaction</p></div>'
            f'<div class="card"><h3>Assessment alignment</h3><div class="value">'
            f'{_status(judged.assessment_alignment)}</div>{codes}</div></div>')
        contract = action.contract
        exact = contract.exact_count if contract.exact_count is not None else "not constrained"
        contract_lists.append(
            f'<dl><dt>Action</dt><dd>Action {index}</dd><dt>Contract</dt><dd>Contract {index}</dd>'
            f'<dt>Registered</dt><dd>{action.registered_at_ms} ms</dd>'
            f'<dt>Deadline</dt><dd>{contract.deadline_ms} ms</dd>'
            f'<dt>Stability window</dt><dd>{contract.stability_ms} ms</dd>'
            f'<dt>Observation horizon</dt><dd>{contract.horizon_ms} ms</dd>'
            f'<dt>Exact count</dt><dd>{exact}</dd></dl>')
    count = len(snapshot.actions)
    subtitle = ("One captured action." if count == 1 else f"{count} captured actions.")
    sections = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        'script-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; img-src &#39;none&#39;; '
        'connect-src &#39;none&#39;; font-src &#39;none&#39;; object-src &#39;none&#39;; '
        'base-uri &#39;none&#39;; form-action &#39;none&#39;">',
        '<title>Consequa-X | Captured evidence report</title><style>', _CSS, '</style></head><body>',
        '<header><div class="eyebrow">Consequa-X / Offline report</div>',
        '<h1>Follow the evidence.</h1><p class="subtitle">', subtitle, ' Separate response, '
        'assessment, observed state and origin.</p><nav aria-label="Report sections">'
        '<a href="#summary">Summary</a><a href="#timeline">Timeline</a>'
        '<a href="#contract">Contract</a><a href="#evidence">Readback</a>'
        '<a href="#graph">Evidence graph</a></nav></header><main>',
        '<aside class="notice" aria-label="Disclosure mode"><strong>',
        'Captured details mode' if include_details else 'Minimal disclosure mode',
        '</strong><p>', _text(detail_notice), '</p></aside>',
        '<section id="summary"><h2>Response is separate from consequence</h2>',
        *summary_cards,
        '<p><strong>Alignment and diagnoses come from the recorded receipts.</strong> '
        'They are computed as explain() computes them; the renderer runs no verifier, readback '
        'or application action. A reported success, a successful response and a satisfied '
        'state are separate claims.</p>',
        _table("Every captured tool response", ("Response", "Action", "Time", "Status"), [
            (f"Response {index}", f"Action {numbers[response.action_id]}",
             f"{response.time_ms} ms", _status(response.status.value))
            for index, response in enumerate(snapshot.responses, 1)
        ]),
        '</section><section id="timeline"><h2>Captured chronology</h2>'
        '<p class="muted">Times are the recorded millisecond values. Ties retain record order; '
        'chronology does not establish causation. Typed records may also appear as captured events.</p>',
        _timeline(snapshot, numbers),
        '</section><section id="contract"><h2>Registered outcome '
        + ('contracts' if several else 'contract') + '</h2>',
        *contract_lists,
        '<p class="muted">Predicate, expected payload, action arguments and raw identifiers '
        'are omitted from the structural view. Outcome semantics remain application-defined.</p></section>',
        '<section id="evidence"><h2>Independent readback and verification</h2>',
        '<p class="muted">These are previously captured records. Rendering performs no readback, '
        'verification, application action or replay. Source authenticity is not established.</p>',
        _table("Every captured observation", ("Observation", "Observed", "Watermark", "Records", "Coverage"), [
            (f"Observation {index}", f"{observation.observed_at_ms} ms",
             f"{observation.as_of_ms} ms", str(len(observation.records)),
             ("complete" if observation.complete else "incomplete") + "; "
             + ("available" if observation.available else "unavailable"))
            for index, observation in enumerate(snapshot.observations, 1)
        ]),
        _table("Every captured verification; earlier unknown results are retained",
               ("Verification", "Action", "Observed", "State", "Origin", "Effects", "Attributable",
                "Evidence"), [
            (f"Verification {index}", f"Action {numbers[verification.action_id]}",
             f"{verification.observed_at_ms} ms",
             _status(verification.status.value), _status(verification.origin.value),
             str(len(verification.effect_ids)), str(len(verification.attributable_effect_ids)),
             ", ".join(aliases[f"observation:{item.observation_id}"] for item in verification.evidence))
            for index, verification in enumerate(snapshot.verifications, 1)
        ]),
        '</section><section id="graph"><h2>Captured evidence graph</h2>'
        '<p class="muted">Local aliases preserve links without exposing captured identifiers. '
        'Successive witnesses remain separate. Provider metadata is a qualified provenance link, '
        'not a proof of source authenticity or causal necessity. No intervention estimates were '
        'supplied to this report.</p>',
        _graph_svg(graph, aliases),
        '<p class="print-only">Visual overview omitted in print; complete node and relationship '
        'tables follow.</p>',
        '<p class="small muted overview-description">Overview: first 32 nodes in recorded time order. '
        'The following tables contain every node and link, including any outside the overview.</p>',
        _table(f"Complete graph: {len(graph.nodes)} nodes", ("Alias", "Kind", "Time", "Witness context"), [
            (_text(aliases[node.id]), _text(_NODE_LABELS[node.kind]), f"{node.time_ms} ms",
             _text(aliases.get(f"observation:{node.data.get('witness_observation_id')}", ""))
             if node.kind == "observed_external_effect" else "")
            for node in graph.nodes
        ]),
        _table(f"Complete graph: {len(graph.edges)} links", ("From", "To", "Relationship", "Meaning"), [
            (_text(aliases[edge.source]), _text(aliases[edge.target]),
             _text(_EDGE_LABELS[edge.kind]), _text(_EDGE_MEANINGS[edge.kind]))
            for edge in graph.edges
        ]),
        '</section>',
    ]
    if include_details:
        captured_json = json.dumps(_redacted(snapshot.to_dict(), names), indent=2,
                                   ensure_ascii=True, allow_nan=False)
        sections.extend([
            '<section id="captured-details"><h2>Explicitly included captured details</h2>'
            '<p>This complete trace may contain secrets, identifiers, payloads, source names and '
            'rationales. Collapsing this panel does not remove its contents from the file.</p>',
            (f'<p>Values of these keys are redacted: {_text(", ".join(sorted(names)))}. Other '
             'keys keep their values.</p>' if names else ''),
            '<details><summary>Show original trace as inert JSON</summary><pre>',
            _text(captured_json), '</pre></details></section>',
        ])
    sections.append(f'</main><footer>Consequa-X · Trace schema {_text(snapshot.schema_version)} · '
                    f'Times in {_text(snapshot.time_base.value)} · Self-contained offline '
                    'presentation · Keep the original trace separately as evidence.</footer></body></html>')
    return ''.join(sections)
