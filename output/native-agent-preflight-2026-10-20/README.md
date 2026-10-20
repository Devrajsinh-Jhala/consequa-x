# Native-agent dependency preflight — 20 October 2026

Dependency preparation and normal native imports passed. No
autonomous task, model generation, model download, paid call, provider connection,
service change, upstream edit, staging or commit was performed.

- Environment: `D:/ConsequaX-Research/native-agent-pilot-venv`.
- Base interpreter: bundled Python 3.12.14 at
  `C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
- Upstream checkout: `C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit`,
  revision `96a3ef92329baf908ffe9dfe188cea34e8701d2a`, tracked source clean before
  and after; imported Python source and project metadata hashes unchanged.
- Installed only the pinned revision's 19 declared base requirements and their
  transitive dependencies, with an explicit `litellm==1.82.6` constraint satisfying
  upstream `>=1.80.15,<1.82.7`. A subsequent narrow authorization added only the
  upstream-declared eager voice dependency `websockets`, resolved to **17.3**
  (219 KB wheel). The final isolated environment has **80 distributions**,
  including pip. No whole voice/live/knowledge/gym extra was requested.
- Dependency consistency: `No broken requirements found.`
- Initial base-only native import: **failed**, `ModuleNotFoundError: websockets`.
- Blocker path: `tau2/__init__.py:13` → runner → `data_model/simulation.py:62` →
  `voice/audio_native/openai/__init__.py:5` → discrete-time adapter →
  `voice/audio_native/openai/provider.py:12`.
- `websockets>=13.0` is a declared **voice-extra** dependency, not a base
  requirement. This is an eager-import packaging issue, not a model failure.
- Final normal native import after that minimal addition: **passed**, including
  `tau2`, CLI, builder, simulation, LLMAgent, UserSimulator and required evaluators.
  No further eager dependency surfaced. Transport and task execution remain
  untested; successful imports do not establish model readiness.

The probe uses normal native initializers, not the prior DB namespace bypass.
It disables dotenv loading and remote LiteLLM cost-map retrieval, removes inherited
provider-key variables within its process, blocks Python socket/DNS paths
including loopback, blocks subprocesses during native imports, and refuses Python
file writes to the pinned source. The result records **zero network attempts,
zero source-write attempts, zero imported subprocess attempts**, and unchanged
source hashes. This is a Python audit/monkeypatch guard, not an OS firewall for
arbitrary native-code networking. A clean import requires no swallowed forbidden
operation attempts as well as successful imports.

Files retained:

| File | Purpose |
| --- | --- |
| [requirements-declared.txt](requirements-declared.txt) | Exact base dependency declarations read from pinned pyproject.toml. |
| [constraints.txt](constraints.txt) | Explicit permitted LiteLLM selection. |
| [requirements-resolved.txt](requirements-resolved.txt) | Full installed version lock, including pip. |
| [runtime-metadata.json](runtime-metadata.json) | Interpreter and source identity. |
| [install-report.json](install-report.json) | Resolver/download metadata and archive hashes. |
| [install-report-websockets.json](install-report-websockets.json) | Narrow additional dependency resolution and archive hash. |
| [requirements-eager-voice.txt](requirements-eager-voice.txt) | Upstream declaration of the authorized minimal eager dependency. |
| [install.log](install.log) | Complete dependency install output. |
| [package-inspect.json](package-inspect.json) | Complete installed package metadata. |
| [dependency-versions.json](dependency-versions.json) | Concise exact installed version inventory and explicit-request set. |
| [dependency-check.log](dependency-check.log) | Dependency consistency result. |
| [probe-native-import.py](probe-native-import.py) | Import-only probe, no task/model requests. |
| [native-import-result.json](native-import-result.json) | Successful final imports, guard counters and source hashes. |
| [native-import.log](native-import.log) | Full final import output. |
| [native-import-result.base-only.json](native-import-result.base-only.json) | Preserved initial packaging failure. |
| [native-import.base-only.log](native-import.base-only.log) | Preserved initial traceback. |

The first metadata-export attempt hit a Windows console encoding error on a
Unicode arrow. Repeating that read-only export with Python UTF-8 mode succeeded;
no dependency installation or native task was rerun. No protocol/experiment
manifest has been frozen, and these dependency records are not evaluation data.
The completed dependency/import preflight is separately bound by
`preflight-manifest.json` and its exact-byte SHA-256 receipt; this does not
authorize or certify a model/benchmark run.
