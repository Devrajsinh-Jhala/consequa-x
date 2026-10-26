# Expanded LIMBO study on Kaggle

This execution path is a new GPU/runtime condition. It does not resume the
historical Windows/Ollama study, and it must not inherit a claim that its model,
quantization, tokenizer or prompt renderer is identical without checking those
bytes. GitHub Actions stays disabled. No human annotation, production service
write or paid inference endpoint is required.

The complete planned matrix contains 48 fresh parameter instances, three
assigned worlds per instance, three model configurations, two generation seeds
and four arms: **3,456 scheduled slots**. These remain 48 base-instance clusters
from 12 existing templates, not 3,456 independent tasks. A complete result must
retain every scheduled disposition, including interrupted and unavailable ones.

## Run the delivered notebook

1. Import `ConseqaX_Full_Benchmark_Kaggle.ipynb` into Kaggle. Enable an NVIDIA GPU
   and Internet access. Attach the matching `conseqax-kaggle-benchmark.zip` as an
   Input. Use the released notebook with its archive hash and source commit
   already filled in; an unbound engineering notebook deliberately refuses use.
2. Configure the inputs, then use **Save Version → Save & Run All once** to run
   the cells in a fresh background session. Do not first collect interactively
   and then use Save & Run All as a save button: it starts another execution.
   If collection already ran interactively, use **Quick Save with outputs**.
   The notebook verifies the ZIP (or Kaggle's automatically unpacked files) and its complete source
   inventory before executing packaged code. The small bundle carries pinned
   native source bytes, model metadata and the research wheel; setup downloads
   the exact hash-addressed model blobs and the pinned Linux runtime separately.
3. Leave `SESSION_HOURS = 7`. The timer starts in the first configuration cell,
   includes setup, and leaves the eighth hour for saving. The runner also reserves
   a full trajectory allowance and a 30-minute flush margin before starting each
   slot. Rerunning a cell does not reset the original timer.
4. The final cell exports the checkpoint and the background version saves its outputs. Retain
   `checkpoint.zip`, `checkpoint-export.json`, `progress.json` and the complete
   underlying state/evidence directory. The portable ZIP is written beside the
   state directory, so preserve the notebook's complete output, not only one
   nested folder.
5. For the next session, attach the same study ZIP and the last saved output as
   Inputs. Run the notebook from the beginning. It discovers a unique prior
   checkpoint automatically. The complete raw ledger takes precedence over its
   older ZIP, because it can contain newer started-slot reservations. If several
   independent histories exist, set `RESUME_FROM` to the intended latest complete
   saved output. Ambiguous inputs stop rather than selecting a history by age.

The released GPU design retains a 300-second request deadline and a
1,800-second trajectory deadline, with at most 16 model invocations, 512 output
tokens per permitted invocation and an 8,192-token context. These GPU deadlines
are separately frozen and differ from the historical CPU condition. Model
responses, failed sends, refusals and unknown usage remain in the evidence.

This notebook has offline engineering coverage. An actual Kaggle GPU run is
still required to establish hardware compatibility and throughput. The number
of sessions needed for all 3,456 dispositions is not guaranteed.

## Before a measured generation

Use an immutable source checkout and the pinned external LIMBO implementation.
Install the exact ConseqaX 2.1.1 research wheel; the current source package can
have a different version. Bind actual Linux source bytes, model files, tokenizer,
chat template, licenses, environment, work limits and the complete schedule.
The complete known-exposure ledger must exclude all previously constructed or
scheduled instance indices, including failed and unstarted historical slots.
The template names themselves are already known.

Perform the declared task-independent transport qualification and record actual
GPU/runtime evidence before starting measured GPU slots. The runner records an
execution declaration after all three model preflights pass; it binds the
readiness evidence, static lineage and source/model/schedule manifest. A source lint or
cached-response test does not establish GPU availability, a loaded model,
native tool rendering, correct context accounting or measured throughput.
Readiness must bind the exact final source inventory and the three exact model
configurations. Preserve the immutable prospective design and execution
declaration before starting measured calls. The local declaration is not a claim
of public preregistration. Do not alter a hard task or model selection
after inspecting its outcome.

Windows paths, executable identities, WMI launch receipts and local listener
process identities are historical provenance only. The GPU path needs its own
actual runtime binding. A CPU provider render proof cannot be renamed a GPU
proof, and a different template/tokenizer cannot claim independent parity just
because it emits plausible tool calls.

Full layer offload is established by the bound runner's retained
`offloaded N/N layers to GPU` load line, checked against the actual runner PID,
creation time, model-weight hash and explicit `-ngl 999` request. Its exact line
hash is saved in `gpu-load-proof.json` and copied into each episode's GPU config.
Every generation also requires positive GPU allocation for the same resident
model, digest and context. A fixed VRAM percentage is deliberately not used:
Ollama's total allocation can include CUDA host buffers even when every layer
is offloaded. See the pinned [Ollama 0.40.10 server source](https://github.com/ollama/ollama/blob/v0.40.10/llm/llama_server.go).

## Eight-hour execution windows

The eight-hour window is an operating target, not a promise about Kaggle's
current service limits. Seven hours are available to setup and collection.
The runner must refuse to start a new slot
unless the full declared trajectory allowance plus the checkpoint flush margin
fits inside the remaining window. Do not silently reduce a later slot's
generation or trajectory cap to squeeze it into a session.

The static study lineage binds source, native implementation, protocol,
models and schedule. Each runtime session records its actual GPU, software and
runtime identity separately. A new Kaggle session can continue only unstarted
slots under the same verified lineage. GPU model, compute capability, driver,
Python/library versions and runtime archive must match the frozen condition;
a different device UUID of the same declared class is retained as a new instance.
An incompatible hardware/software condition stops continuation. It does not
authorize editing the old lineage or pooling a new condition with it.

## Checkpoints preserve evidence, not retries

`research.kaggle_limbo.checkpoint.CheckpointStore` is the persistence boundary.
Its journal reserves each slot before any model dispatch. An advisory exclusive
lock prevents two local collectors from claiming the same lineage concurrently.
A slot that has been reserved is never selected as unstarted again.

On an ordinary completion, seal the episode's exact files and terminal status.
On a later session, reconcile orphaned reservations into explicit interrupted
terminals while preserving all retained prefixes. Do not rerun a started slot
because its result is missing, invalid, unsuccessful or inconvenient. An
interrupted slot's native grade stays unknown unless an intact sealed native
return can actually be independently replayed.

Export checkpoints to a new destination and verify their hash-chain ancestry,
lineage, schedule and all sealed files before resuming. Accept only an identical
checkpoint or a verified ancestor/extension of the same history. Reject a
divergent fork, protocol/model substitution, altered sealed evidence, missing
terminal artifact, reordered slot or rolled-back history. Keep the rejected
input available for inspection; do not repair it by deleting failures.

Kaggle output files must be saved or exported before a session is discarded.
An in-memory notebook variable, a green cell, an unsealed ZIP or an ephemeral
working directory is not a durable completed study.

## Audit and interpretation

The offline auditor replays saved native service operations and model responses
without network access or importing the measured obligation policy. It compares
the full native operation journal, settled world, ledger, RNG state, conversation
and grades. A separate checker reconstructs admission premises from actual
public calls before checking certificates and current-report receipts.

The audit does not regenerate model outputs, authenticate a provider, recreate
inference wall time or independently prove a third-party tokenizer correct.
Runtime/context proofs must identify the actual GPU path and their precise
scope. Synthetic integration fixtures use invented tasks and cached responses;
they are engineering checks with **zero live model/GPU generations**, never
additional scientific episodes or empirical success rates.

Report task success, benchmark-defined exactly-once outcomes, duplicates,
unsupported retry admission, omissions, supported/uncertain completion,
normal-return and grade availability, per-model/seed differences, and actual
read/write/token costs. Preserve unknown usage instead of replacing it with
zero. Report runtime-session strata and the number of independent task clusters.
Completing the scheduled study supports these bounded claims; it cannot promise
acceptance at a top conference.
