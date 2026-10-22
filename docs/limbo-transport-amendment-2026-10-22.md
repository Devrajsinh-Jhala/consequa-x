# Precollection schema compatibility correction

The first excluded native development case (`guard-migration-000`, source
6899d49bc87ee7d11f14f230ef6db0ae086d027a) stopped before any generation. The
strict offline predictor rejected native `additionalProperties: true` at a
tool-parameter node. The unchanged native runner returned an LLM-error result
with native TS/EOS false after its ordinary flush; no tool, verifier or package
receipt executed. The independent replay audit passed that limited record,
which does not satisfy readiness. All bytes and the failed condition remain.

The compatibility correction changes only a copied offline-render input in
the new LIMBO transport. The pinned provider elides this typed schema field.
Literal JSON Schema `true` has the same unrestricted meaning as omission.
Only that literal value may be omitted from typed parameter/property/anyOf
nodes for prediction. False, numeric values, null and schema-valued restrictions
are refused. Arbitrary `items` and `$defs` remain untouched. The actual native
HTTP schema, model-visible history and tool arguments are never rewritten.
The earlier frozen airline implementation is unchanged.

The full set of 26 public native tool schemas passed live server-byte and
runtime-token-ID parity using invented task-independent messages: 2,883 prompt
tokens and 3,459 required context tokens out of 8,192, including the 512-token
output allowance and margin. This check performs zero model completions and
executes no task or service. Its sealed bundle is
`output/limbo-development-2026-10-22/all-public-schemas-000/`.
The new compatibility tests plus existing transport tests passed 61 cases.

Official generation has not started. A fresh excluded native episode and clean
baseline must satisfy the existing readiness gates under this corrected source
before protocol publication. The next guarded reservation is limited to 11
permitted invocations and the clean baseline to 12, so together with the prior
one gated native invocation the maximum remains 24 even under conservative
invocation accounting. Actual dispatches, refusals and usage remain distinct.
