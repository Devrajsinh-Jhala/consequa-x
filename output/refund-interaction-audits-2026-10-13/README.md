# Independent physical-interaction audit

The [retained enumeration](../refund-interactions-2026-10-13/) contains eight
synthetic cases and 512 planned branches. The final
[independent audit](independent.json) passed 27,277 assertions against actual
readback, call costs, mixture weights, coalition status and exact permutation
calculations. It checks the final seven-file inventory, which preserves the
original legacy-format export manifest.

The [negative checks](negative-checks.json) record 29 semantic corruptions rejected
by the audit. Those checks used the earlier six-file envelope; the final audit
supports both preserved legacy and canonical manifests and rejects conflicts.
Audit receipts live outside the enumerated export to avoid self-referential
manifest hashes. No inference-provider calls were made for these audits.
