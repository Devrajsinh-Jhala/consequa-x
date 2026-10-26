# Full benchmark on Kaggle GPU

Use [the notebook](ConseqaX_Full_Benchmark_Kaggle.ipynb) with the matching
[small study bundle](../output/kaggle-benchmark-2026-10-26/conseqax-kaggle-benchmark.zip).
The bundle contains the fixed 3,456-slot design, code, model identities and
research wheel. Setup downloads the pinned model weights and Linux GPU runtime.

1. Import the notebook into Kaggle and attach the bundle as an Input dataset.
   Automatically unpacked uploads are supported. Enable **GPU** and **Internet**.
2. Use **Save Version → Save & Run All once**. The seven-hour deadline includes
   setup and leaves time within the eight-hour window to preserve outputs.
3. For the next session, attach the **entire latest saved output** as an Input
   alongside the same study bundle. The notebook validates the ledger and
   starts the next unstarted slot. Completed, failed and interrupted starts
   are never retried by this continuation path.

If you already collected interactively, use **Quick Save with outputs**;
Save & Run All starts a fresh execution and is not a save-only operation.

Keep the complete ledger, evidence, `checkpoint.zip`, `checkpoint-export.json`
and `progress.json`. The raw ledger takes precedence over an older ZIP.
Use the same GPU class and driver for subsequent sessions; incompatible
conditions stop rather than being silently combined.

The matrix is three model families × 48 base instances × three assigned
conditions × four policies × two seeds. It is not 3,456 independent tasks.
The notebook does not promise completion in one session.

The source, packaging, native replay, checkpoint continuation and notebook
bootstrap passed **210 focused offline tests**. Actual Kaggle GPU compatibility
and throughput are checked by the first run and have not been measured here.
GitHub Actions remains disabled; no human evaluation or paid inference is used.

See [the execution and audit details](../docs/KAGGLE_BENCHMARK.md).
