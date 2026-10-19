# Offline 2.0 migration conformance on the retained matched traces

This is a new **post-hoc compatibility study**, using the 503 retained factual
traces from the closed 2026-10-18 matched local study. Its original denominator
remains 504 planned slots: 503 completed, one failed (`episode_00109`, invalid
policy JSON), and 896 already completed local model calls. The failed slot is
inventoried and reported; it is never regenerated or given a substitute trace.
The original outputs, labels, analysis and historical package version remain
unchanged. There are zero new model calls, action executions or service requests.

The measured corpus has **not** been processed during runner development. The
protocol is frozen only after the runner, its tests and this design are committed.
This is a prospective freeze of a post-hoc conformance analysis, not a claim that
the original experiment or the analysis hypothesis was externally preregistered.

## Scope and feasibility

The public 2.0 `migrate_trace` accepts the saved schema `0.1` JSON and returns a
schema `1.0` trace. Its one action and assessment become one-item lists; responses
and verification receipts gain the action ID; the assessment gains an ID. The
legacy schema never recorded a clock origin, so migration declares `relative_ms`.
No epoch is inferred, and this clock-origin loss is disclosed for every trace.

The retained study uses the built-in `refund_processed` predicate. Consequently
the public 2.0 `verify(action, recorded_observation)` can independently recompute
its receipts, and `explain(trace).for_action(action_id)` supplies the per-action
assessment alignment and diagnosis codes. Target matching moved from the 1.1
explanation into the 2.0 verifier. Migration adds target IDs and findings only
when the current verifier reproduces the recorded **status, origin, ordered
effect IDs and ordered attributable effect IDs**. That is the migration
implementation's four-field condition, not a promise of byte-identical receipts.

Migration preserves old recorded conclusions by construction. Therefore the
runner treats structural preservation, migration explanation and **fresh 2.0
verification** as separate results. A successful migration alone cannot establish
verifier parity. Fresh receipts replace receipts only in a separate in-memory
trace for explanation; the historical trace remains untouched.

This study cannot establish new empirical performance for 2.0 policies, general
multi-action correctness, arbitrary custom-verifier compatibility, a recovered
absolute time origin, causal responsibility, or performance on a new population.
It evaluates compatibility with this retained single-action evidence only.

## Frozen inputs and code

`scripts/run_v2_migration_conformance.py freeze` inventories bytes and identities;
it does not execute migration, verification, explanation, a collector or a
benchmark on any corpus trace. Import inspection is limited to source version,
module path and installed distribution metadata.

The protocol records:

- The explicit full current Git commit, complete `src/consequa_x` file inventory,
  source package version `2.0.0`, project metadata, migration documentation,
  existing migration tests and their development fixtures.
- Runner, dedicated tests and this document hashes. Pinned files must be tracked
  and clean at freeze time; unrelated paper/research edits are allowed.
- The frozen legacy commit `940ebfcc0059c992977dd8e9f112361ff5b31edd`, its complete
  package inventory and source version `1.1.0`. Every legacy runtime hash must
  also match the **original study's** recorded runtime inventory.
- The complete historical study and analysis directory inventories, the 503
  individual trace/explanation/receipt hashes and slot identities, the failed
  slot's receipt/error, and each old analysis `consequa_state_origin` prediction.
  The original finalization receipt and closed-study inventory are checked.
  Evaluator truth is hashed as historical provenance, never used for a prediction
  or new outcome label.
- Both exact Python executables, executable hashes and interpreter versions,
  imported module paths/source versions, and ambient installed distribution
  versions/locations. Imported pinned source defines behavior. A wheel's installed
  metadata does not silently replace source provenance.
- The canonical mappings, planned metrics, denominators, missing-data rule,
  diagnosis policy, limitations and development-fixture disclosure in `PLAN`.

Before constructing slot dictionaries, the runner requires exactly 504 unique
schedule IDs and analysis-episode IDs with equal sets, and exactly 503 unique
baseline-row IDs matching the completed episodes. Duplicate or missing IDs cannot
be hidden by dictionary overwrites. Source cleanliness checks include entire
runtime/fixture directory pathspecs, so a tracked module deleted before freeze
cannot silently disappear from the pinned inventory.

The old arm runs under a separate `-I -B` Python subprocess with only the frozen
legacy `src` explicitly inserted. It never imports the current old collector or
changes either environment. The new arm requires `PYTHONPATH` to the pinned
paper-writing `src` and checks the actual imported path and code version.

## Comparisons and missing evidence

For every recorded receipt, fresh verification uses its **one exact evidence
observation ID** to select the saved observation. It does not select the latest
readback as a fallback. Multiple evidence items, missing identities, unsupported
predicates and runtime errors are retained as processing failures/unavailable
comparisons. The latest explanation uses the last recorded receipt and assessment
for that action, preserving recorded order rather than sorting by timestamp.

Canonical state is `satisfied → true`, `violated → false`, `unknown → null`.
Origin retains the exact `confirmed`, `other_actor` and `unknown` values. Reported
assessment retains `success`, `failure`, `partial` and `unknown`. Alignment
retains `consistent`, `contradicted` and `unassessable`. Action-linked outcome uses
each pinned version's `benchmark.targets.action_linked_consequence`; it is not
`bool(target_effect_ids)` because count, absence, external-origin and missing
provenance semantics differ.

Primary trace-level checks cover migration success; exact legacy structural
projection; schema round-trip; preservation of old receipts and reported
assessment; old re-verification versus recorded receipt core; fresh old/new core,
state, origin, action linkage and receipt identities; migrated/fresh assessment
alignment; frozen-old agreement with the saved explanation alignment and old
analysis prediction. Receipt identity includes contract ID, observed time,
ordered effect/attributable IDs, and every evidence observation ID/source/watermark.

Secondary checks retain full legacy receipt equality (including details/reason),
exact ordered diagnosis-code equality, additions/removals, migration reproduction
counts, unavailable/empty/nonempty target metadata and newly unassessable
alignment. An empty target tuple and unavailable (`null`) target matching are
separate. Existing known unassessability and newly lost assessability are separate.
2.0 can add `UNASSESSABLE_ASSESSMENT` for known refund outcomes whose report or
target linkage cannot be judged; those changes are reported, not normalized away.
Messages, display labels and graph serialization are not primary invariants.

Every trace metric reports success/equal, failure/different and unavailable counts
over **all 503 retained traces**, plus successes divided by the original 504
planned slots. The failed historical slot is listed, not scored as semantic
disagreement. Receipt-level counts have a separate receipt denominator. Equality
of two null states, or two unassessable alignments, is agreement rather than
known-state/assessable coverage; state and alignment distributions are reported.
No failures are excluded, no retries or replacement samples are allowed, and no
inferential p-values or population-level claims are planned.

## Reproducible commands

Use the isolated 2.0 environment for freezing and the measured new arm, and the
isolated 1.1 environment for the old worker. The published 2.0 wheel installed in
the new environment supplies metadata; `PYTHONPATH` deliberately selects the
committed, separately hashed 2.0 source. These commands do not enable Actions.

After committing the three research files, create a detached source worktree at
that exact commit, named `D:/ConsequaX-Research/paper-frozen-v2-conformance` in
this execution plan. Run the committed script there while explicitly pointing to
the historical input directories in the writing worktree. This allows the frozen
protocol to be committed in the writing worktree before measurement without
moving the execution source's pinned HEAD. Freeze to a **new** directory:

```powershell
$env:PYTHONPATH = 'D:/ConsequaX-Research/paper-frozen-v2-conformance/src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$currentRevision = (& git -C 'D:/ConsequaX-Research/paper-frozen-v2-conformance' rev-parse HEAD).Trim()
& 'D:/ConsequaX-Research/migration-2.0-venv/Scripts/python.exe' `
  'D:/ConsequaX-Research/paper-frozen-v2-conformance/scripts/run_v2_migration_conformance.py' freeze `
  --expected-current-commit $currentRevision `
  --study-dir 'D:/ConsequaX-Research/paper-writing/output/matched-local-study-2026-10-18' `
  --analysis-dir 'D:/ConsequaX-Research/paper-writing/output/matched-local-analysis-2026-10-18' `
  --legacy-root 'D:/ConsequaX-Research/paper-frozen-940ebfc' `
  --legacy-python 'D:/ConsequaX-Research/analysis-1.1.0-venv/Scripts/python.exe' `
  --output-dir 'D:/ConsequaX-Research/paper-writing/output/v2-migration-protocol-2026-10-19'
```

Review the frozen protocol and record/commit its hash **before** the measured run.
Then run once, supplying the already frozen hash and a different new directory:

```powershell
$frozenHash = (Get-Content `
  'D:/ConsequaX-Research/paper-writing/output/v2-migration-protocol-2026-10-19/protocol.sha256.json' `
  -Raw | ConvertFrom-Json).sha256
& 'D:/ConsequaX-Research/migration-2.0-venv/Scripts/python.exe' `
  'D:/ConsequaX-Research/paper-frozen-v2-conformance/scripts/run_v2_migration_conformance.py' run `
  --protocol 'D:/ConsequaX-Research/paper-writing/output/v2-migration-protocol-2026-10-19/protocol.json' `
  --expected-protocol-sha256 $frozenHash `
  --output-dir 'D:/ConsequaX-Research/paper-writing/output/v2-migration-conformance-2026-10-19'
```

The run checks frozen hashes before computation and again before its final
receipt. It creates an exclusive `run-claim.json` beside the protocol. That claim
persists after interruption or failure and prevents retry even into another
output directory. Outputs are always created exclusively; there is no overwrite,
resume, repair, automatic retry or sample regeneration. A source or input change
requires a separately disclosed amendment, never silent reuse of this protocol.

Outputs include per-slot paired results, migrated traces, fresh receipts,
runtime metadata, an aggregate `summary.json`, an artifact inventory and a
completion receipt. Processing errors remain in the results and yield exit code
2; semantic disagreements remain ordinary measured results. A fatal error leaves
its claim and `fatal-error.json`. No completion receipt claims input integrity
unless the final hash recheck succeeds.

Migration, migrated explanation, fresh verification and fresh explanation have
separate failure accounting. A later verifier/explanation failure preserves
successful migration, its available metrics and its migrated artifact; affected
fresh comparisons remain unavailable. A legacy re-verification failure likewise
does not erase an available recorded-alignment comparison.

## Development checks and disclosure

The dedicated tests use the four existing schema-0.1 migration examples only:
refund timeout after commit, stale readback, another actor and record timeout
after commit. Only the timeout refund example has a saved explanation fixture;
other expected alignments/codes are explicit synthetic assertions. Additional
mutations cover receipt non-reproduction, unknown assessment, conservative target
matching, observation identity, evidence/reason versus receipt-core differences,
hash tampering, exclusive claims, denominator preservation and protocol gating.
Synthetic schedule mutations cover duplicate/missing IDs and failed-slot baseline
substitution; a mocked Git deletion checks pre-freeze source completeness.
An optional integration check invokes frozen 1.1 on the **three refund fixtures**.
No retained study trace is opened by these tests.

The existing primary development environment has pytest; the two minimal isolated
version environments need no new installed test dependencies:

```powershell
$env:PYTHONPATH = 'D:/ConsequaX-Research/paper-writing/src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:CONSEQUA_V2_LEGACY_ROOT = 'D:/ConsequaX-Research/paper-frozen-940ebfc'
$env:CONSEQUA_V2_LEGACY_PYTHON = 'D:/ConsequaX-Research/analysis-1.1.0-venv/Scripts/python.exe'
& 'C:/Users/DELL/OneDrive/Desktop/ConseqaX/.venv/Scripts/python.exe' -m pytest `
  tests/test_v2_migration_conformance.py tests/test_migrate.py -q -p no:cacheprovider
```

Development results are software checks, excluded from measured counts. The
manuscript must retain the original experiment's frozen 1.1.0 provenance and
describe any eventual 2.0 result separately as this offline post-hoc conformance
study.
