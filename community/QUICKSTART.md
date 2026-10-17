# Five-minute offline quickstart

Use Python 3.11 or 3.12. No model, API key, provider account or runtime dependency
is required. Version 1.1 commands below become available with that release;
check the package's PyPI version before installing a pinned version.

```console
python -m pip install consequa-x==1.1.0
consequa-x --version
```

Download and extract the [quickstart archive](https://consequa-x.brawny-deer-5658.chatgpt.site/quickstart.zip)
or use the two Python files in examples in this repository. Run from the folder
containing both files:

```console
python report_quickstart.py --output my-first-capture
```

Open my-first-capture/verified.html in your browser, then compare unknown.html
and other-actor.html. All records are synthetic. The example reads fixture bytes
independently from the declared action, applies an explicit ArtifactVerifier,
and saves the captured trace separately from its HTML presentation. It executes
no delivery or payment. The unknown example has unavailable readback; the
other-actor example satisfies the requested state with a different actor's effect.

To render the saved trace again:

```console
consequa-x report my-first-capture/verified.json --output another-report.html
```

The output must be new. On systems where the console command is not on PATH,
use python -m consequa_x in its place. To start with the packaged refund fixtures:

```console
consequa-x demo --output sample-run
consequa-x report sample-run/traces/episode_00.json --output sample-report.html
```

## Sharing and trust

Default reports omit arbitrary captured values and use local aliases. Timing,
counts, enum statuses and relationships remain visible; review before sharing.
This is deliberate field omission, not universal anonymization. The optional
--include-details flag includes the complete trace as escaped text and may
expose sensitive information. Keep the original trace separately as evidence.

Rendering performs no verifier call, target matching, application action or
replay. It shows captured verification; it does not establish source truth.
Assessment alignment is unassessable in the report. An application's explicit
TargetMatcher can qualify alignment through explain(trace, target_matcher=...).

## Connect your own application

Declare the target contract before the action. Capture dispatches, responses and
the agent's reported assessment. Obtain an independent readback with explicit
source, scope, completeness, watermark and origin metadata. Implement a read-only
Verifier for your domain, and a TargetMatcher when alignment is meaningful.
The artifact_delivery.py example uses only public APIs and contains both adapters.

The schema validates structure and identity linkage. Source authentication,
transaction guarantees and the truth of adapter-provided metadata remain your
application's responsibility. Unknown evidence must stay unknown.

The version-1 core and schema 0.1 remain compatible in 1.1. Research replay
interfaces have separate assumptions; no baseline superiority or live-model
accuracy improvement is claimed. Platform validation is listed in release notes
using actual environments, rather than inferred from a pure-Python wheel.
