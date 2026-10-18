# Release notes

## 1.2.0 — 19 October 2026

- TraceRecorder records an action as it happens, from the outcome contract to
  readback and verification, and returns an ordinary validated trace.
- Tool-call capture: attempt(), call() and capture_tool record each dispatch and
  response around a synchronous tool, including timeouts and errors.
  call_mcp_tool does the same for MCP client sessions, without an MCP dependency.
- RecordVerifier checks record-shaped outcomes such as rows, orders or tickets:
  field values, count, deadline and persistence. Unavailable, incomplete, stale
  or out-of-scope readback stays unknown, and origin stays a separate conclusion.
- An offline SQLite agent-loop example, also in the quickstart download, and a
  framework integration guide.
- Additive only: the 1.x API and schema 0.1 are unchanged.

Both files are published on PyPI with their registry hashes and sizes verified,
and a fresh install from PyPI passed the installed checks. The source suite
passed 1,839 tests plus 240 subtests. Installed checks of the same wheel, now
covering the recorder, tool capture and record verifier, passed on Windows with
embedded Python 3.11.9 and Python 3.12.10, and on Alpine Linux 3.24.2 with
Python 3.14.8 in a local QEMU guest, where the SQLite example also ran in all
three modes. The source distribution installed and ran the example on
Windows Python 3.12.10. The Linux result covers one emulated guest; macOS has
not been tested. MCP capture was checked with a stand-in session, not a live
MCP server.

## 1.1.1 — 18 October 2026

- Documentation and metadata release: runtime code and schema 0.1 are identical
  to 1.1.0 apart from the version number.
- A rewritten package description and project links for PyPI.
- The source repository is now public and is the home for questions, bug reports
  and private vulnerability reports.

Both files are published on PyPI with their registry hashes and sizes verified.
The source suite passed 1,786 tests plus 240 subtests. Fresh installed checks
passed on Windows with embedded Python 3.11.9 and Python 3.12.10, including a
fresh install from PyPI. Linux and macOS were not rerun for 1.1.1: its runtime
differs from 1.1.0 only in the version string, and the 1.1.0 wheel passed on one
Alpine Linux virtual machine. macOS has not been tested.

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
