# Maintained tau3 task/tool state-transfer validation

This is a **model-free integration and state-transfer experiment**, not an
autonomous-agent benchmark run, pass@k estimate, policy compliance assessment,
user-simulator evaluation, causal-method reproduction or leaderboard submission.
The experiment checks whether the released Consequa-X observation/verifier/
explanation boundary works over genuine, maintained external benchmark tools
and data in a second application domain. It does not demonstrate independent
predicate accuracy simply because an application implements its own predicate.

## External source and selection (fixed before execution)

- Source: <https://github.com/sierra-research/tau2-bench>
- Exact reviewed commit: `96a3ef92329baf908ffe9dfe188cea34e8701d2a`.
- Upstream distribution: `tau2` 1.0.1, currently branded tau3-bench; MIT license.
- Both complete canonical `base` corpora: retail 114 tasks and airline 50 tasks,
  in their original source-file order. No outcomes determine task selection.
- Each task has four fixed controls: reference action replay; omit all writes;
  omit writes while exposing a fabricated success acknowledgement to the
  application auditor; and alter the identity/scope argument of the first
  consequential call to a fixed nonexistent identifier while executing the
  remaining calls as specified. Read-only reference calls still run.
- Exactly 164 source tasks and 656 planned task/control cells. These are
  deterministic controlled replays, not 656 independently sampled agent tasks.

The deprecated `sierra-research/tau-bench` README warns that its tasks are
outdated and points to this maintained repository. The maintained corpus
includes corrected retail/airline tasks and tools. We do not use the obsolete
corpus simply to avoid current evaluation requirements.

## Native execution and independent targets

The external `get_environment`, `get_tasks`, `Environment.make_tool_call`,
`Environment.get_response` and `EnvironmentEvaluator.calculate_reward` bodies
run unchanged from the pinned checkout. Source files, both domains' inputs,
license, runner, tests, application runtime, dependency versions and imported
dependency bodies are bound to a freeze receipt. The exclusive
`protocol.sha256.json` receipt binds the exact `protocol.json` bytes; run and
verification reject changes, including whitespace-only mutations, before any
cell starts. Both files should be committed as the external provenance anchor.
The source revision records the Git HEAD at freezing; subsequent commits of
receipts are allowed while exact frozen code/data hashes remain authoritative.
No upstream files are edited
or vendored into the published Consequa-X runtime.

The upstream DB evaluator replays the complete reference actions on a fresh
gold environment and compares the entire predicted DB hash. Equivalent final
states may pass through different action sequences. We call the unchanged
**environment evaluator component**, with strict replay of the actually
executed trajectory. We do not relabel an omitted or false acknowledgement as
a native write; doing so would execute that write during evaluator replay.

Task-level DB success is kept separate from the **action-level field contract**.
The application contract compiler accepts only the intended operation name,
payload and a native public preflight lookup. It never receives the task,
reference action list, gold database, native evaluator reward or hidden label.
Captured post-action records come only from native `get_order_details`,
`get_user_details` and `get_reservation_details` lookups. Canonical source
actions provide the scripted experimental intent; this is not a test that an
agent inferred the correct user intent.

Retail contracts cover cancellation status/reason, requested user/order
addresses, exchange/return item and payment identifiers, requested modified
item identifiers/status, and addition of a payment row. Airline contracts cover
cancellation status, baggage counts, flight number/date/cabin, passenger
records, a newly added booking with the requested payload fields, and a newly
added certificate matching the requested amount. These record-level contracts
do **not** cover every financial side effect, future settlement, policy,
intermediate reasoning, communication requirement, seat-release behavior,
side-effect-free correctness, action origin or causal necessity. Existing
matching bookings/certificates/payments cannot serve as newly created witnesses.

Each captured record exercises actual Consequa-X
`verify(action, observation, verifier=TauRecordVerifier())` and `explain(trace)`.
Missing readback is evaluated separately and must return `unknown`; native
tools do not emit action-linked provenance, so origin remains `unknown`.
Captured inputs and native DB state must remain unchanged by verification,
explanation and public readback. There is no fabricated agent belief: assessment
is `unknown`, and custom-predicate assessment alignment is unassessable.

Task-level DB matching and immediate requested-field matching have different
targets and timing. Their agreement/disagreement is descriptive integration
evidence only. It is **not** action-predicate accuracy against the task reward.
Native DB checks also test side effects outside the field contract, and later
reference calls can change fields observed immediately after an earlier action.

## Official scoring requirements intentionally outside this experiment

Full tau evaluation normally uses domain policy, tool-calling agent and dynamic
user simulator. Retail does not support the native `solo_mode`. Current retail
data has 112 tasks with `reward_basis=[DB, NL_ASSERTION]` and two DB-only tasks;
some NL assertions are null, others require an LLM judge. Airline tasks use
`[DB, COMMUNICATE]`. The official documentation describes these components,
but its generic/default discussion does not override the pinned task files.
Only the DB/environment component is measured here. No omitted communication
or qualitative criterion is silently marked passed. No hosted model calls,
Ollama calls, user simulation, NL judge or paid API calls occur.

The current implementation's known simulator limitations (for example airline
cancellation does not release seats) remain upstream behavior, not real-world
service guarantees. No pass@k or comparison to published agent scores is valid.
Model-free state transfer supports the portability of an audit boundary; it
cannot finish independent human validation or full end-to-end benchmark work.

## Isolated local execution

Use Python 3.12 or 3.13. Clone the pinned repository into an ignored temporary
directory without running its installation scripts. Install only Pydantic,
Loguru, docstring-parser, DeepDiff, Addict, python-dotenv, PyYAML, toml, NumPy,
pandas, python-dateutil and tzdata into an isolated research dependency target;
capture the resolved versions in the freeze. Do not install anything into the
Consequa-X production environment. Third-party transitive dependencies are
also recorded by the local freeze receipt.

Two namespace-only import adapters bypass `tau2/__init__.py` and
`tau2.voice.audio_native.openai/__init__.py`, which eagerly import unrelated
LLM runners or real-time provider stacks. Actual environment, tools, task
models and native evaluator source is untouched. A few upstream voice *data
models* are transitively imported by `RewardInfo`; no voice providers execute.
`PYTHON_DOTENV_DISABLED=1` prevents loading credentials, and a socket guard
refuses network connections during import and all native executions.

First run semantic tests, then enable the optional native integration tests
against this exact reviewed checkout. These tests use a tiny disclosed
development fixture (retail task 0, airline tasks 19 and 20) only to verify the
adapter; the final experiment still includes every canonical task. Freeze the
protocol **after implementation and review and before the final experiment**:

```powershell
$env:PYTHONPATH='D:/ConsequaX-Research/tau-native-dependencies'
$env:CONSEQUA_TAU_SOURCE='C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit'
.venv/Scripts/python.exe -m pytest tests/test_tau_benchmark_validation.py -q
.venv/Scripts/python.exe scripts/run_tau_benchmark_validation.py freeze --source tmp/tau2-bench-audit --output output/tau3-state-transfer-2026-10-18
.venv/Scripts/python.exe scripts/run_tau_benchmark_validation.py run --source tmp/tau2-bench-audit --output output/tau3-state-transfer-2026-10-18
```

An existing lock or result directory is refused. Every scheduled cell gets an
exclusive start record and a completed or retained failure receipt. Started
slots are never regenerated; there are no retries, replacement tasks or
outcome-based exclusions. Code/data/dependency identity is checked before each
cell and at completion. A changed source stops the run instead of quietly
continuing with mixed versions. A final summary binds every episode hash and
includes all dispositions, native DB component counts, action field statuses
and explicit unavailable-capture counts. A crash or missing final summary is
an incomplete experiment requiring a disposition audit, not permission to
erase or redo started cells. GitHub Actions remain disabled throughout.

## Primary sources

- [Maintained source and current corpus](https://github.com/sierra-research/tau2-bench/tree/96a3ef92329baf908ffe9dfe188cea34e8701d2a)
- [Native environment evaluator](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/evaluator/evaluator_env.py)
- [Scoring semantics and target/action distinction](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/docs/evaluation.md)
- [Exact retail task file](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/data/tau2/domains/retail/tasks.json)
- [MIT license](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/LICENSE)
