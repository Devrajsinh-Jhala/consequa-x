# Release notes

## 1.1.0 — 17 October 2026

- A self-contained offline HTML report command and public render_report API.
- Chronology, contract bounds, responses, assessment, readbacks, state/origin
  receipts and an evidence graph with individual successive witnesses.
- Minimal disclosure by default; explicit escaped full-capture details mode.
- Strict input validation, exclusive new output files and source preservation.
- Public documentation, synthetic artifact-delivery quickstart and support.
- The schema remains 0.1 and the dependency-free version-1 core is preserved.

Both reviewed files are published on PyPI, with their registry hashes and sizes
verified. The frozen-source suite passed 1,624 tests plus 240 subtests.
Fresh installed checks passed on Windows Python 3.11.9 and 3.12.14 and Alpine
Linux 3.24.2 with Python 3.14.8 and kernel 6.18.52-0-virt. The Linux result came
from a local QEMU TCG guest on Windows; it does not establish every Linux distro
or native deployment configuration. macOS has not been tested. The Windows 3.11
check used the official isolated embedded interpreter; 3.12 used a fresh venv.
GitHub Actions remains disabled.

The report default omits arbitrary captured data; explicit details remain
potentially sensitive. Browser review covered desktop, mobile, hostile text,
unknown evidence and conflicting witnesses. Print styles preserve full tables
while omitting the bounded diagram; physical printer pagination was not tested.

## 1.0.0 — 15 October 2026

Published stable evidence core with typed traces, explicit application verifiers,
domain-specific target matching, separate outcome/origin, witness-preserving
graphs, CLI fixtures and optional local Ollama research integration. Windows
Python 3.11 and 3.12 installations were checked. Broader platform results and
research superiority are not inferred from these tests.
