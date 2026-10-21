# Native precollection code review — 21 October 2026

This is an automated review by a separate agent within the same project. It covers execution source commit `8bd1cd88ab3644a9c6417e29308ab4b502b40484` in `D:/ConsequaX-Research/paper-frozen-native-2026-10-21`. The eight source files below were read and their actual bytes checked against that commit; all matched the Git bytes exactly. Directly relevant control flow in the pinned native benchmark was also inspected. Measured source and existing evidence were not changed.

No concrete execution-stopping bug was identified in the reviewed normal execution path. This finding is limited to the inspection performed; it is not proof that the code is free of bugs. No official task or model was invoked, and this review does not supply a performance result.

## Reviewed execution paths

| Area | Source locations | Inspection result |
| --- | --- | --- |
| Prospective source and protocol identity | `research/native_agent/protocol.py:191–216`; `scripts/run_native_external_benchmark.py:129–133,192–207,269–276,318–324` | Protocol and receipt bytes must match an explicit immutable Git anchor. The worker checks the frozen source, installed runtime, native bytes and declared ceilings, plus the live server/model lease. Source and native bytes are checked again after a returned episode. |
| Exclusive collection and failure dispositions | `scripts/run_native_external_benchmark.py:611–675` | An exclusive claim uses a new file and collection output must be fresh. The serial schedule retains 48 planned dispositions. Ordinary worker failures occupy their slots; integrity and supervisor failures stop further starts and retain remaining slots as unstarted. No resume or replacement branch is provided. |
| Authentication of actual native calls | `research/native_agent/audit.py:158–207,255–332` | The independent helper checks initialization and chronologically replays every saved actual call, including reads, comparing requests, responses and database hashes. This supplements native strict replay, which skips nonmutating reads. It then invokes unchanged native `ALL` evaluation with strict replay and compares the complete saved reward. |
| Matched classical and framework controllers | `research/native_agent/controller.py:55–172,196–209,222–242,301–334,396–410` | C and G use the same public read plan, current-field predicate and fixed duplicate/unresolved-resource guard. C computes the field report directly; G applies the installed 2.1.1 custom verifier and exposes a framework receipt. Their report representations differ. Field status, native task success and causal origin remain separate; origin is unknown. |
| Model and transport accounting | `research/native_agent/harness.py:112–165,198–221,236–240`; `research/native_agent/transport.py:95–150,212–250`; `scripts/audit_native_external_benchmark.py:193–250` | Native completion scopes bind the original input and refuse a second generation send. Actual parsed HTTP digests are checked against context receipts and native messages/options. Only documented absent/null assistant fields are normalized. Completed-call, token and tool start/terminal counts are reconciled. |
| Missing monetary and usage metadata | `research/native_agent/audit.py:116–135,327–332`; pinned native `tau2/utils/llm_utils.py:513–539` | Both native aggregation and the audit retain unavailable side costs when any participant message has no cost, including deterministic wrapper messages. Message counts are not substituted for model invocations. |

The code also requires exact-source transport, native task-19 and guarded task-20 integration evidence before readiness can support a prospective freeze (`scripts/run_native_external_benchmark.py:487–579`). Inspecting this gate does not establish that its prerequisites have been fulfilled.

## Actual reviewed source hashes

SHA-256 values identify the frozen files' actual bytes, not a later checkout or a later audit result.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `research/native_agent/__init__.py` | 80 | `c3ce2386476dc383fb747759cd2bd135a369442b97d379cecb0946d8ceed397c` |
| `research/native_agent/controller.py` | 22943 | `c6334bec78662379a064cf0f0a7bd0bb3786b421139ed1f21f0dd7c9f35407d6` |
| `research/native_agent/transport.py` | 33759 | `fdf9c37a6c84e37227f8a9aa2b834980cd3719c9313a47750f9550c2162fe8cf` |
| `research/native_agent/harness.py` | 18470 | `4d4e36c729f963649ffc5e3e5bab2b1422a7df1687595266fee2eeebaa8aaec7` |
| `research/native_agent/audit.py` | 19155 | `2ae8c2e5b97d973de1b1000518454a7a9b85b88f7d0f489c75e6cd5be0eab1af` |
| `research/native_agent/protocol.py` | 10964 | `ee522512acaa7c07dad76f2f254d6f160c53024307f05a1ec02dc4686b6a9a9a` |
| `scripts/run_native_external_benchmark.py` | 42395 | `1a09cf6e21b9e618337da299e8d696935b778e55873970dc0866c0d4f6f8b90f` |
| `scripts/audit_native_external_benchmark.py` | 26188 | `d4272ec472a636f350cbd4e3b7231706416c143b630b34ceb05cc9db3650fa92` |

## Limits

This review is source inspection, not fresh execution of the collector, all 48 trajectories, the live transport, or an independent replication. It does not certify future machine resources, provider behavior, process identities or saved artifacts; the runtime gates and subsequent offline artifact audit must evaluate those observations. It neither establishes human validation nor makes a conference-readiness or performance claim. GitHub Actions were not invoked.
