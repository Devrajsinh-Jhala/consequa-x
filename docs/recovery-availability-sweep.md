# Controlled availability follow-up

This separate study is motivated **after** the first recovery-controller study
was completed and independently audited. That original finite challenge suite
did not expose an incremental polling benefit. Its negative finding remains in
the paper and is not replaced by this follow-up. The new cases deliberately
intervene on readback availability, completeness and lag. They are controlled
developer-authored cases, not held-out tasks, independent external validation or
an autonomous model benchmark.

## Fixed design and prospective hypotheses

All three original SQLite application domains are used: inventory reservation,
support transition and delivery registration. The original world, controller,
driver and semantic auditor remain byte-identical to source commit
`22e88498cff0e2afd1549803fb4d9645902e74b9`. The installed ConseqaX distribution
must be exactly 2.1.1; every installed Python/JSON file is checked against that
commit, including exact inventory. The follow-up imports the unchanged original
driver's `execute(case, seed, method, database)` function. It does not prepend
`src`, modify the application or add a new policy.

Each operation has registration 0 ms, deadline D=100 ms, stability W=50 ms,
original horizon H=150 ms, recovery deadline R=250 ms and safety cutoff S=330 ms.
The initial dispatch returns a success acknowledgement at 2 ms and commits one
correct business effect at 10 ms. The same stable operation key and declared
native idempotency guarantee are available to every arm. There are no removals,
external actors, wrong payloads or source/scope/trust differences.

The full factorial grid crosses:

| Factor | Values in milliseconds |
| --- | --- |
| Readback lag | 0, 40, 80, 95 |
| Source unavailable until | 0, H+20=170, H+60=210, H+100=250 |
| Scope incomplete until | 0, H+20=170, H+60=210, H+100=250 |

Windows apply on `[0, until)`; a zero end means no window. Lag applies to every
readback. Availability and completeness are independent declared limitations;
both must have resolved at a read time, and its watermark must cover H.
The unchanged read schedule is [50, 150, 190, 230] ms, with the original cap of
two dispatches. The one-final-read arm uses its single final read at H, retaining
the original optional predeadline gate behavior where applicable.

There are 64 profiles x 3 domains = 192 cases, each run once at seed 0 with all
five original methods. This produces 960 scheduled worlds. Method order rotates
by case index modulo five. Deterministic cells receive no redundant timing
repetitions. All case values and all 960 ordered schedule entries are included
in the frozen protocol; a separate `cases.json` is bound by exact bytes.

The following are hypotheses specified before the follow-up is executed; they
are not substituted for measured outcomes if the implementation differs:

- Physical original/recovery completion and operational safe recovery should be
  true for every completed arm, with one dispatch, no duplicates and no unwanted
  effects. The uniform-safe design is expected to show no primary improvement.
- The one-final-read arm should produce a definite correct global-state claim
  in 1/64 profiles per domain: zero lag, outage and incomplete window.
- Polling, the strong reference and the state-only policy should produce a
  definite correct global-state claim in 27/64 profiles per domain: lag <=80 ms
  and both window ends <=210 ms. This is the intersection of conditions at the
  actual common final read opportunity, not three independent probabilities.
- The response policy should report success in every profile from its immediate
  acknowledgement. This is not evidence-grounded verification. Because all
  these controlled effects are correct, this design cannot estimate its
  false-success risk.

Any observed polling advantage over a single final read is shared by the
unchanged reference and state-only controller. It would establish sensitivity
to delayed evidence in this finite grid, not framework superiority, safer
dispatch decisions or new task generalization. Source admission, exhaustive
history and provider guarantees remain application assumptions. The finite
safety cutoff cannot prove unbounded exactly-once behavior.

## Analysis and failures

The original endpoint definitions and summarizer are reused unchanged. The
primary endpoint is operational safe recovery over **all scheduled slots**.
A failed slot contributes zero operational success; its unobserved physical or
semantic endpoints remain unavailable. Secondary endpoints include definite
correct state-reporting yield, original/recovery completion, action-linked
claims, harm, reads and dispatches. All factor cells, domains, profiles and
planned pairwise contrasts are retained. The profile is the original
summarizer's family unit, with all three domains equally represented.

Report exact full-grid counts and paired finite-grid differences, including
equal-profile means. Do not add bootstrap/population confidence intervals,
p-values, task-population claims or selective endpoint/cell reporting. The
three domains repeat a common mechanism rather than sampling independent tasks.

The first run is exclusive. There is no resume, retry, replacement or case
exclusion. Every error remains in the journal and planned denominators. If the
collector is interrupted, the packet remains incomplete. A repair requires a
new disclosed protocol. Each successful or failed slot preserves its raw JSON
record and any created SQLite database, compressed with deterministic gzip.

## Freeze, run and provenance

First commit the follow-up runner, its synthetic development tests, this design,
and the separately authored follow-up auditor/tests. The source freeze records
the full source commit, origin URL, exact source file bindings, the original
22e8849 engine bindings, exact interpreter binary/version/path and the installed
2.1.1 payload. Run the following from a **new frozen checkout at that source
commit**, using the isolated installed 2.1.1 environment:

```text
python -I -B scripts/run_recovery_availability_sweep.py freeze
  --expected-source-commit FULL_SOURCE_COMMIT
  --output NEW_WRITING_CHECKOUT/output/NEW_PROTOCOL_DIRECTORY
```

Commit the resulting `protocol.json`, `protocol.sha256.json` and `cases.json`
before collection. The protocol commit must descend from the source commit and
contain exact protocol and case JSON bytes. The run checks this committed Git
evidence and refuses future-dated commits. Collection then uses:

```text
python -I -B scripts/run_recovery_availability_sweep.py run
  --protocol NEW_WRITING_CHECKOUT/output/NEW_PROTOCOL_DIRECTORY/protocol.json
  --expected-protocol-sha256 SHA256_FROM_FREEZE
  --protocol-commit FULL_PROTOCOL_COMMIT
  --output NEW_WRITING_CHECKOUT/output/NEW_RESULTS_DIRECTORY
  --database-root NEW_SEPARATE_DATABASE_DIRECTORY
```

Both output roots must be absent and nonnested. A canonical exclusive claim is
created under the bound frozen source root at
`output/.availability-sweep-run-claims/PROTOCOL_SHA256.json`. Copying the protocol
or choosing another output directory cannot create a second first run. Identical
claim bytes are retained beside the protocol and as results `started.json`.
Claims bind the protocol/source commits, protocol/case Git paths, output root,
database root and recorded absolute host paths. This prevents accidental reruns;
an operator manually deleting a claim would be a protocol deviation.

Before and after collection, the runner rechecks its own exact root/HEAD/origin,
source and original engine bytes, installed framework/interpreter identity and
research module origins. The output retains `cases.json`, `protocol.json`,
`analysis-rows.jsonl`, every compressed trial and SQLite snapshot, `summary.json`,
an exact inventory manifest and a completion receipt. Manifest and receipt
creation occur only after the final checks. No model, external application or
production calls are made. Git is used only for local provenance inspection.

The separately authored auditor checks artifacts without importing the world,
controller, original runner or framework. This is independent audit code, not
independent human authorship or human validation. Synthetic tests use distinct
non-grid factor fixtures and do not execute the 192 measured cells.
