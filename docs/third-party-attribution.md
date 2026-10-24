# Research artifact attribution

The external fault study uses LIMBO by Jiapeng Li, pinned to
`2db09fba22a0572a70639162a808906409f612a8` from
[jaxblack/limbo-bench](https://github.com/jaxblack/limbo-bench/tree/2db09fba22a0572a70639162a808906409f612a8).
Its MIT copyright and permission notice is retained verbatim in
[third-party/limbo-MIT-LICENSE.txt](third-party/limbo-MIT-LICENSE.txt).
Native instructions, schemas, simulated service outputs and grading semantics
in the newly collected traces derive from that source. The benchmark's
separately released episode archive and published result figures were not
downloaded or reused as our experimental results. Our exact source pin differs
from its v1.0 release and is identified independently from its preprint.

Local inference uses the official
[Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
model, whose model card identifies Apache 2.0 licensing, through the exact
[Ollama Q4_K_M tag](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M).
The official study uses [Ollama 0.40.8](https://github.com/ollama/ollama/releases/tag/v0.40.8).
Model weights and Ollama executable binaries are not redistributed in this
repository. The frozen runtime records retain their exact hashes and local
configuration; the upstream projects retain their own license notices.

Earlier airline evidence retains the Sierra Research source pin and upstream
MIT license in `output/tau3-state-transfer-2026-10-18/upstream-MIT-LICENSE.txt`.
The manuscript distinguishes those historical feasibility executions from the
new native fault comparison. None of these third-party projects endorses
ConseqaX or its paper.
