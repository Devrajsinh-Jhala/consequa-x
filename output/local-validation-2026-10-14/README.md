# Capped local model validation, 14 October 2026

All 24 planned episodes completed, using 59 actual local model calls within the
72-call cap. This is a small exploratory integration validation on six cases
from the `refund-case-note` validation family, with two seed repetitions and two
unchanged prompt profiles. It is not a held-out attribution comparison.

[FINDINGS.md](FINDINGS.md) gives the complete denominators and interpretation.
[protocol.json](protocol.json) was frozen before the first generation call;
[execution.json](execution.json) retains both completed block receipts and
timing. Client dates use Asia/Calcutta; retained UTC timestamps fall on
13 October 2026, beginning at 18:35 UTC.

## Frozen identity and controls

- Research checkpoint: source
  `2c4adfeb2a364a8116d6edbccbbdac64b413fc9c`, package `0.1.0a2`.
- Candidate wheel SHA-256:
  `9250ad76c02075248aa6a12fd6e20b9be363bbf626093e13d893dfd1edd25d0e`.
  Its bytes are retained as `candidate-checkpoint.whl` and under the correctly
  named file in [checkpoint-artifacts](checkpoint-artifacts). This is distinct
  from the final release artifact built after an interaction-manifest repair.
- Existing local Ollama model: `qwen3:4b-instruct-2507-q4_K_M`, digest
  `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
  No model download, remote API, paid call or GitHub Actions was used.
- Ollama 0.40.3, Windows 11, Python 3.12.14, Intel i5-8365U, approximately
  16 GiB physical memory. Post-run model residency reports zero VRAM and a
  4,096-token runtime context. Full inspection is retained in the hardware and
  runtime files; it is not proof of provider authenticity.
- Temperature 0, `num_predict=512`, 180-second request timeout, two tool
  attempts, at most 36 calls per profile. Profile order was v1 then v2.
- Trial/world seeds 12,000,000–12,000,011 are shared between profiles. Reserved
  phase keys are 72,000,000–72,000,071; initial inputs, world configurations and
  logical contracts match across profiles. Server sampling can still vary.
- The `refund-operations-ticket` held-out reserve was not generated. Validation
  fault conditions overlap other study splits, so this is not a held-out
  fault-composition result. This validation family is now exposed.

## Evidence and audits

Each of [v1](v1) and [v2](v2) retains the original export manifest, source study
plan, schema, result receipts and twelve traces/explanations/evaluator-truth
records. Evaluator truth remains separate from evidence available to the agent.
The root [manifest.json](manifest.json) inventories every retained file except
itself, recording byte sizes and SHA-256 hashes. Original block exports were
not edited after collection.

[audit.json](audit.json) records 2,227 saved-evidence assertions: strict trace
round trips and schema validation, candidate-package payloads, schedule and
phase keys, prompt/public-request/full-payload hashes, case identities, fresh
verification/explanations, independent readback formulas, complete inventories,
all aggregates and exact budgets. It made no generation calls. Seven targeted
corrupted smoke copies were rejected in [negative-checks.json](negative-checks.json).
Checks are integrity and semantic tests, not cryptographic provider-origin or
language-model independence proofs.

[rationale-audit.json](rationale-audit.json) contains all 24 verbatim final
rationales and separate manual annotations. It is a single unblinded review,
not a validated language classifier or inter-rater study. Successful-processing
clauses are recorded even when followed by uncertainty. Their interpretation
as achievement of the requested exactly-one effect is distinguished from an
assertion that a particular attempt committed.

## Recheck without generating

Install the retained, correctly named checkpoint wheel in a clean environment,
plus `jsonschema` as an audit-only dependency. Run that environment's Python:

```text
python -I output/local-validation-2026-10-14/audit_validation.py
python -I output/local-validation-2026-10-14/check_negative_audits.py
```

The semantic auditor and negative checker default to read-only operation.
`--report` may write a fresh report outside this closed evidence folder. The
negative checker only changes temporary copies under the repository's ignored
`tmp` folder. Construction helpers refuse to overwrite files inside the closed
snapshot.
Do not rerun `execute_blocks.py` to “complete” this finished study. Doing so would
generate a new experiment and must use a new frozen protocol and output folder.
