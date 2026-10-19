# Offline migration study: separate design review

Read-only review on 19 October 2026. This is AI-assisted design/code checking,
not independent human validation and not a study result. The measured corpus,
runner, package and development fixtures were not executed by this reviewer.

No remaining blocking design issue was found for the narrowly declared
post-hoc conformance study at the exact bytes bound in `review.json`. The three
files still need their source commit and prospective protocol freeze before
any measured processing.

Three findings were resolved before this receipt:

1. Later verification/explanation errors now preserve successful migration,
   its artifact and available metrics; stage failures remain explicit.
2. Schedule, episode and baseline rows now require exact unique 504/503 ID
   coverage before dictionaries can hide duplicates or missing traces.
3. Whole-directory Git checks now reject a deleted tracked runtime/fixture
   instead of silently omitting it from the advertised source inventory.

The design separates migration-by-construction preservation from fresh
verification/explanation, uses each version's own target mapping, retains
all 503 traces plus the historical failed slot, and treats diagnosis changes
and unknown agreement separately. Source/interpreter identities, original
study hashes, exclusive run claims and final byte rechecks support the frozen
execution plan. Historical evaluator truth is hashed for provenance, not used
to generate or repair new predictions.

The runner author reports 42 development checks and clean Ruff; this reviewer
did not rerun those checks. This is pinned-source, exposed-data conformance.
It cannot establish new model performance, every 2.0 receipt field, arbitrary
custom-domain compatibility, multi-action safety or independent human validity.
Actual parity remains unmeasured and must not be inserted in the paper yet.

Reviewed SHA-256 values:

| File | SHA-256 |
| --- | --- |
| Runner | `398515a1fe2f91f7d9ccdfe3e1c9dfa7bb1b7cae894e50e85154edf8a5bcf843` |
| Dedicated tests | `8872d1d3a378ed1e00d396296f14504b20358224ba5ac5c71e551a96d3d459fb` |
| Design document | `e99f20af4903d7d07433c42db3b18d3c5a66e41a539a6a0df16e4d0bd225febe` |

Any later edit needs review and a new freeze before measured execution. See
`review.json` for exact file sizes, relevant function lines, resolved findings,
checked boundaries and the remaining interpretation limits.
