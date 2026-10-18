# Local completion job

This one-time local job waits for the already running collection process. It
launches no generation and uses no scheduled automation or GitHub Actions.
`plan.json` binds the frozen protocol and exact postprocessing sources.
`complete.ps1` checks the owned process identity, waits for it to exit, and
rechecks those hashes before running the strict finalizer.

If collection exits normally, finalization accounts for every planned slot,
including any failures or budget-stopped residual slots. A stale lock, torn
journal, changed source, invalid receipt or existing output directory causes
refusal. No evidence is repaired, overwritten or redrawn. A fresh successful
analysis is followed by two figure exports from the isolated plotting runtime.

Expected new output locations:

- `output/matched-local-analysis-2026-10-18/`
- `output/matched-local-figures-2026-10-18/`

Those paths are future outputs at job launch, not existing final results.
Human review of the results, visual checking of the generated scientific
figures, manuscript integration and a newly compiled paper remain required.
The author affiliation for that revision is Independent Researcher.

This script records the current machine's paths and process identity. It is an
execution receipt, not a general service or a command to relaunch blindly.
Portable manual entry points are the repository's separate finalizer and figure
builder CLIs. Preserve any failed output for diagnosis; use a new directory for
an explicitly reviewed retry.
