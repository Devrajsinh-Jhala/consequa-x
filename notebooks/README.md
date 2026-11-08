# Full benchmark on Kaggle GPU

Use the [complete notebook](ConseqaX_Kaggle_COMPLETE.ipynb) for the simplest
first run. Its one execution cell includes the exact verified study bundle,
initializes every variable, supplies the native import path, installs the
runtime/models, checks the GPU, collects episodes and exports the checkpoint.
No separate study Input or recovery snippets are needed.

Import it into a **fresh Kaggle notebook/session**, enable **GPU + Internet**,
and choose **Save Version → Save & Run All once**. For continuation, attach the
**entire latest saved output** as an Input before starting the next fresh
session. The current version declares the Granite native-format correction as
a new source/template condition. Preserve the earlier failed qualification
output separately; its zero-start checkpoint is not an Input for the first
corrected run. Actual GPU execution remains subject to the live preflight.

The separate-bundle notebook below remains available for advanced use.

Use [the notebook](ConseqaX_Full_Benchmark_Kaggle.ipynb) with the matching
[small study bundle](../output/kaggle-format-repair-2026-11-08/conseqax-kaggle-benchmark.zip).
The bundle contains the fixed 3,456-slot design, code, model identities and
research wheel. Setup downloads the pinned model weights and Linux GPU runtime.

The notebook launcher now explicitly adds the frozen study and its `native`
folder to each child process's import path. This fixes the preflight
`ModuleNotFoundError: No module named 'limbo'` without changing the study bundle
or checkpoint lineage. Command output is streamed and also saved beside the
active ledger in `conseqax-diagnostics`.

For an already-open session with that exact import error, add this code in a
new cell, then rerun **only the collection cell** within the original budget:

```python
import os
from pathlib import Path
os.environ["PYTHONPATH"] = os.pathsep.join(
    (str(STUDY_DIR), str(Path(STUDY_DIR) / "native"))
)
```

Keep the existing bundle, downloads and complete output. The failure occurred
in preflight before any measured slot. Rerunning extraction or setup is not
needed for this import-path repair.

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

Setup downloads several gigabytes before starting any benchmark slot. It prints
download progress and uses bounded retries for temporary download failures,
including HTTP 504. Partial downloads resume when the server supports it, and
the complete bytes must still match the declared size and SHA256 before use.
These setup retries do not retry model requests or started benchmark slots.

If setup still fails in an active interactive session, keep its original error
and rerun **only the setup cell** while the original seven-hour budget remains.
Do not rerun the extraction cell or edit integrity pins. After the budget has
elapsed, start a fresh Kaggle session; rerunning cells or restarting the kernel
does not extend the current session. For a failed background version, start a
fresh session with the same inputs. If any study slots had already started,
preserve and attach the entire latest saved output before continuing.

Keep the complete ledger, evidence, `checkpoint.zip`, `checkpoint-export.json`
and `progress.json`. The raw ledger takes precedence over an older ZIP.
Use the same GPU class and driver for subsequent sessions; incompatible
conditions stop rather than being silently combined.

The matrix is three model families × 48 base instances × three assigned
conditions × four policies × two seeds. It is not 3,456 independent tasks.
The notebook does not promise completion in one session.

The source, packaging, native replay, checkpoint continuation and notebook
bootstrap passed **323 focused offline tests**. The revised condition's GPU
qualification and measured benchmark throughput are still pending. Retained
local CPU tool-roundtrip checks are engineering evidence, not native task results.
GitHub Actions remains disabled; no human evaluation or paid inference is used.

See [the execution and audit details](../docs/KAGGLE_BENCHMARK.md).
