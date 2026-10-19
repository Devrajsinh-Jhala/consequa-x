# Schema 0.1 fixtures

Traces written by the published Consequa-X 1.2.0 wheel (installed from the
reviewed `consequa_x-1.2.0-py3-none-any.whl`, SHA-256
`4cdfb44c6a56e1671e50ee9efddc97816d8742fa388130ffa7d351eee3686438`):

- `refund-timeout-after-commit.json`, `refund-stale-readback.json` and
  `refund-another-actor.json`: `consequa-x demo` episodes 01, 05 and 09, with
  the 1.x `explain()` output for episode 01 alongside.
- `record-timeout-after-commit.json`: `examples/agent_loop_sqlite.py --mode
  timeout_after_commit` from the 1.2.0 source distribution.

They are migration fixtures; do not regenerate them with a newer package.
