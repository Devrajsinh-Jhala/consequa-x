# Offline visual reports

Consequa-X renders a dependency-free HTML report for a captured, validated
trace:

```console
consequa-x report trace.json --output report.html
```

Open the resulting file in a browser. It contains no JavaScript, remote fonts,
remote assets or network requests. It works without a server, model or API key.
The command preserves the input and refuses an existing output, including the
input itself. Invalid traces are rejected before an output directory is created.
Trace identities that conflict with reserved evidence-graph identities are also
refused, with a sanitized error; validation does not rename original evidence.

The report shows the registered contract's structural bounds, chronological
events, tool responses, the reported assessment, observation availability,
recorded verifier state and origin, and an evidence graph. Repeated observations
keep distinct witnesses. Graph order, dependency, observation and origin links
have different labels; none establishes counterfactual necessity. The report
does not execute an application action, verifier, target matcher or research
replay, and does not independently establish that captured evidence is true.
Assessment alignment is not evaluated by this renderer. Use the explicit
application target-matcher interface with `explain` for a qualified comparison.

## Minimal disclosure

The default view uses consistent local aliases for identities and omits arbitrary
captured values: payloads, rationales, source names, raw identifiers, paths,
digests, predicate strings and error messages. Omitted content is absent from
the file, not concealed in embedded JSON, attributes or comments. The report
retains structural enum values, counts and timing information. That information
may itself be sensitive in a particular application; review a report before
sharing it. This is field omission, not universal personal-data detection.

To inspect all captured fields locally:

```console
consequa-x report trace.json --output detailed-report.html --include-details
```

This explicitly includes potentially sensitive data as escaped inert text.
It is not the recommended form for a public bug report. To keep the details but
blank particular keys everywhere in the included trace:

```console
consequa-x report trace.json --output detailed.html --include-details --redact card_number --redact email
```

Redaction is by key name only; values under other keys are kept. Both forms preserve
`unknown`, `other_actor` and unassessable conclusions. Missing evidence is not
shown as a successful verification.

A reduced report is a presentation artifact, not replacement verification
evidence. Retain the original trace and its source/provenance separately.

## Python API

```python
from pathlib import Path
from consequa_x import Trace, render_report

trace = Trace.from_json(Path("trace.json").read_text(encoding="utf-8"))
document = render_report(trace)  # include_details=False by default
with Path("report.html").open("x", encoding="utf-8") as destination:
    destination.write(document)
```

`render_report` returns HTML and writes no files. It accepts a `Trace`, a
boolean `include_details` argument and a `redact` sequence of key names. Reports
cover every action in the trace, with each action's latest state, origin,
assessment alignment and diagnosis codes; codes from custom verifiers are counted
rather than printed in the default view. Traces use schema `1.0`; the package
release and portable wire version are separate.
