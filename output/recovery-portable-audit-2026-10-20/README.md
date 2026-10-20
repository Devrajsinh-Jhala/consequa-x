# Portable retained-artifact recheck

This receipt is deliberately separate from the original-host audit. It recomputes retained trial/SQLite semantics using the exact hash-verified frozen auditor source extracted from pinned Git objects, with no study rerun or framework import. The collection's original paths and binary/venv need not exist here.

A pass concerns saved-artifact consistency only. Read omitted_original_host_checks and limitations in portable-audit-receipt.json. No authentication, live-host identity, first-run exclusivity, new external replication, or independent-human validation is asserted. The clone must contain both pinned Git commits and all source/protocol blobs; a shallow clone may need those objects fetched. An optional --claim-file supplies a publicly retained claim copy; otherwise a clone-local output/.recovery-run-claims/HASH.json is checked if present. Absence is explicit in the receipt and never replaced by a claim of live canonical-file verification.
