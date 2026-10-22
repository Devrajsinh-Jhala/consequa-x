# Resource observer postcollection finalization

The original observer ended without its summary or manifest. Its retained artifacts do not establish why it stopped. This new bundle preserves and inventories all five original files; their byte lengths and SHA-256 hashes match before and after analysis.

The journal contains 775 complete sequential samples, from 2026-10-21T11:48:08.378293+00:00 through 2026-10-21T18:16:21.668520+00:00. There is no resource evidence after that final sample and no inferred closing status.

The original process lease binds PID, creation time, executable identity, and parent PID. Every retained sample matches the recorded PID and creation time. Historical PIDs must not be treated as current process identities. This analysis performed no process lookup or process control, network request, or model invocation.

## G1 development request alignment

| Call | Terminal | Recorded request seconds | Interior samples | Runner CPU % | Minimum available RAM (GiB) | Maximum runner RSS (GiB) |
|---:|:---|---:|---:|---:|---:|---:|
| 0 | request_return | 35.437 | 1 | unavailable | 2.804 | 2.579 |
| 1 | request_return | 60.219 | 2 | 396.46 | 3.011 | 2.932 |
| 2 | request_return | 156.000 | 5 | 398.28 | 3.161 | 3.004 |
| 3 | request_return | 126.953 | 4 | 398.25 | 3.510 | 3.019 |
| 4 | request_return | 797.094 | 27 | 396.72 | 3.184 | 3.208 |
| 5 | request_return | 80.250 | 3 | 387.41 | 2.628 | 3.765 |
| 6 | request_return | 214.484 | 7 | 394.39 | 2.377 | 3.832 |
| 7 | request_return | 262.203 | 8 | 394.67 | 2.397 | 3.847 |
| 8 | request_error | 1201.750 | 40 | 395.11 | 2.207 | 3.917 |

CPU is calculated between the first and last recorded samples strictly inside each request's inclusive timestamp window, using cumulative user+system CPU delta and monotonic elapsed time. Exact covered bounds appear in result.json. 100% represents one CPU core equivalent; values above 100% are valid.

Call 8 ended with `Timeout` at 2026-10-21T17:50:09.587191+00:00. Its 40 interior samples cover 2026-10-21T17:30:10.425415+00:00 to 2026-10-21T17:49:44.630489+00:00. Sustained CPU activity is consistent with ongoing computation while the client waited. These sampled data cannot establish whether compute, paging, memory pressure, scheduler effects, or another factor caused the timeout.

The original G1 execution receipt records 9 attempted model calls, 8 completions, one timeout, and five completed native tool dispatches. It marks the native reward as not fabricated. This is a failed development run, not an official benchmark score.

## Limits

- No new measurements were taken; there is no coverage beyond the final sample.
- Samples are approximately 30 seconds apart and do not establish true resource peaks.
- Per-request CPU is computed from the first and last samples fully inside that request, not extrapolated to its unsampled edges; each interval is reported explicitly.
- CPU percent is 100 times process user+system CPU seconds delta divided by monotonic wall seconds delta; it may exceed 100 across cores.
- RSS is working-set memory, and VMS is virtual allocation; neither establishes physical resident model cache size or memory bandwidth.
- System available RAM reflects unobserved applications. No paging, GPU utilization, or per-request generation-versus-prefill timing was measured by this observer.
- The linked G1 task is development data and has no fabricated native reward.
- This new bundle is a postcollection inventory and analysis, not the missing original observer terminal receipt or manifest.
