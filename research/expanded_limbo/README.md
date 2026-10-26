# Prospective expanded LIMBO research

This is a new research namespace. It does not replace or amend the completed
96-slot condition or its results. No measured expanded protocol is frozen by
these source files, and source tests are not benchmark evidence.

The scheduler in `protocol.py` builds 48 fresh parameter instances (four per
each of the twelve pinned native templates), 144 assigned worlds (one clean
plus two compatible distinct fault modes per base), three model families,
four recovery arms and two generation seeds: **3,456 planned slots**. The
default fixed generation temperature is 0.2. Seed support and observed
variation must be checked; changing seed at temperature zero is not evidence
of stochastic robustness. This design adds parameter coverage, not unseen
task templates, external replication or a task-population sample.

## Frozen selection and exposure

The caller first supplies an exact-byte-bound ledger of **all known prior
parameter indices**, including excluded development, failed runs, interrupted
runs and every previously scheduled index. Indices 0 and 1 are always excluded.
The ledger's completeness is an explicit attestation, not something this
module can prove about unrecorded access. `candidate_indices` then chooses
fresh indices with an outcome-independent SHA-256 rule. The trusted
`extract_metadata` constructs tasks internally and emits only template/index,
family/domains/horizon and focal public affordances. Task instructions,
targets, matches, expected results and setup contents cannot enter selection.
The caller verifies the exact pinned native source before extraction.

Every declared fault mode receives prospective coverage, subject to native
affordances: partial faults require a batch, schema drift requires a declared
drift contract. The two selected faults for each base are distinct. Selection
balances mode/domain/focal counts with fixed hash tie breaks; it does not use
observed outcomes or drop untriggered assigned faults. Native random worlds
depend on focal and fault mode, so clean/fault variants share base parameters
but are not asserted to have identical random state.

## Models and execution partitions

The planned families are Qwen, Llama and Granite. Current candidates are the
existing Qwen3-4B-Instruct-2507 Q4_K_M and Llama-3.2-3B-Instruct Q4_K_M, plus
IBM Granite-3.3-2B-Instruct only if its full native tool transport and memory
preflight passes. A model record binds exact weights, tokenizer, chat template,
license, context budget and retained transport-preflight file bytes. A name
or hash of an unreviewed preflight is not readiness. Dynamic process leases
belong to block execution records; static weights and sampling settings stay
fixed across all blocks. A failed candidate cannot silently become a different
model. No inference, downloads or model loading occurs in `protocol.py`.

The four prospective arm names are `vanilla`, `guard`, `no_unkeyed_repeat` and
`obligation_shield`. Their implementation, native behavior, available public
information and costs require independent validation before collection. The
new shield is not assumed to improve task success or exactly-once outcomes.
Arm order rotates within paired model/seed/world cells. The fixed schedule
has 72 blocks of 48 slots, each using one model and generation seed over twelve
assigned worlds. Model order rotates between world blocks. These blocks allow
one resident model at a time; they are execution partitions, **not** adaptive
stopping or outcome-based inclusion gates.

The collector must preserve one immutable record for every planned slot,
including failed, interrupted, refused and unstarted slots. It must never
replace or resume a started measured slot. Untouched later blocks can execute
under their original identities and settings after an interruption; the
interrupted slot remains a distinct unavailable/partial observation. No
Actions, paid inference or human participants are part of this condition.

## Analysis and actual workload

Report exact finite paired TS/EOS discordances and numerator/denominator
differences within each model and seed, clustering repeated observations by
base instance. Keep native grade availability, normal execution, duplicates,
collateral/extraneous effects, false completed claims, receipt claim soundness,
definite claim coverage and actual work/token costs separate. Unknown grades
remain unknown; show both all-planned success yield and conditional available
grade endpoints. No pooled independent-task p-value or population confidence
claim follows from these generated templates. Native EOS remains its original
domain-qualified benchmark quantity, not universal exactly-once execution.

The previous actual 96-slot Qwen condition ran from 04:53 to 17:37 UTC on
24 October 2026, approximately 12 hours 44 minutes on this shared CPU host.
It made 552 generation dispatches, with 1,249,824 known input tokens and 51,582
known output tokens (three invocation usage records unknown). Linear scaling
of that elapsed workload is about **19 days for 3,456 slots**, before new
transport preparation. This is a planning scale, not a promised duration:
model speed, host sleep/contention, thermal behavior and timeout rates differ.
Three generation seeds would mean 5,184 slots and about 29 days at that rate.
An exhaustive all-focal/all-fault design has 386 worlds per parameter index;
it should not be confused with the smaller 144-world balanced design.

## API and publication boundary

1. `candidate_indices(template_names, exposure, ...)` returns the fresh index
   plan. `extract_metadata(native_root, index_plan)` is the trusted extractor.
2. `build_protocol(metadata, models, exposure, *, selection_seed, source_files,
   native_files, wheel_binding, ...)` returns a proposed JSON-compatible
   protocol with worlds, all slots, fixed blocks, exact static input bindings,
   explicit limitations and planned analysis.
3. `verify_protocol_structure(protocol)` reconstructs the proposal and rejects
   changed schedules, counts or claims. This checks structure, not live runtime
   identity or actual file bytes against the supplied bindings.
4. Before a real freeze, independently verify all source/wheel/model/preflight
   files and completed native/tool/transport tests, bind exact limits and
   runtime rules, commit the protocol and publish it before any measured
   generation. The collector and independent replay auditor must match every
   saved native `EpisodeSpec` and model/seed/temperature to its planned row.

The old collector, transport and analysis remain byte unchanged. In particular,
the old tokenizer accepts Qwen2 BPE only and the old client forces temperature
zero. They cannot execute this multi-family stochastic condition by changing
an alias. New validated tokenizer/render support and a separately versioned
collector/auditor are required before this proposed schedule becomes evidence.

The new `harness.py` and `scripts/run_expanded_limbo.py` implement metadata
preparation, prospective freezing and one-shot collection of an explicitly
named fixed block. A proposal with `readiness: null` cannot collect. Actual
freezing requires a separately completed `readiness.json` with schema
`conseqax-expanded-limbo-readiness-v1`, `passed: true` and exact matching
`sources`, `native_sources`, `wheel`, `models` and `limits`. The protocol binds
the receipt bytes. This receipt is only valid when its producer has checked
the actual complete preflight evidence; writing those fields by hand does not
establish readiness.

The protocol must be committed before collection, together with the exact
scientific sources. Every episode saves a small reference to that committed
protocol instead of duplicating the entire matrix. It retains the exact native
specification, per-slot seed/temperature, static model plus live runtime lease,
raw model request/response/context files, native world/result, full delegated
runtime journal and policy call starts/terminals. Each completed policy call
captures its actual top-level operations and cumulative interventions for
separate offline replay. A central protocol-hash/block reservation inside the
research checkout prevents the collector from starting the same block again
under a different output directory. It is an accidental-duplication safeguard
for this trusted workspace, not an adversarial distributed lock.

Default limits are sixteen model invocations and tool proposals, 512 output
tokens per invocation, 1,200 seconds per request and 7,200 seconds per episode.
Work limits bind attempted execute/verify/wait boundaries separately. Larger
uniform limits need a new prospective choice before measured generation. This
is particularly relevant to the long composite template. No positive result,
complete collection or claim of stronger-model validation is implied by the
new source files.
