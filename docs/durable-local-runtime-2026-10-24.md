# Local process lifetime diagnostics, 24 October 2026

This auxiliary diagnostic does not establish the cause of any earlier interrupted
collection. The old process disappearance could have more than one cause. It
tests a specific risk: a research child inheriting a tool process's Windows job
with `KILL_ON_JOB_CLOSE` enabled.

The first three one-shot launch probes requested `DETACHED_PROCESS`,
`CREATE_NEW_PROCESS_GROUP`, and `CREATE_BREAKAWAY_FROM_JOB`, and required
`IsProcessInJob` to be false before any target launch. A virtual-environment
Python redirector, direct base Python, and a local WMI service-parent bootstrap
all retained some Windows job membership and refused before starting their
harmless target. A subsequent explicitly authorized WMI/bootstrap chain also
retained job membership and refused. These failed diagnostic artifacts remain in
their original directories. None performed inference or contacted a model.

Read-only diagnostics explained why membership alone was overbroad. The tool's
current inner job reported flags 10240: breakaway allowed and kill on close
enabled. WMI bootstrap processes and their strict detached descendants instead
reported flags 6144: breakaway and silent breakaway allowed, kill on close
disabled. That ambient job contained more than 100 processes, and the normal
desktop Explorer process also had job membership. The criterion was therefore
explicitly amended before the successful sentinel probe to escaping the tool's
kill-on-close job while permitting this observed non-killing ambient job. It
does not claim absence of all Windows jobs or survival across reboot, logoff,
power loss, or arbitrary external process termination.

The single delayed sentinel used the same two-stage local WMI chain, the same
Windows user, and flags 6144 with kill on close disabled. Its target launched at
04:36:15 UTC. The launching tool invocation returned after 3.55 seconds. A
separate later invocation read the target's delayed sentinel at 04:36:30 UTC,
after 15 seconds of actual monotonic delay. The target self-observed the
non-killing job before and after the delay and exited with code zero. Evidence is
in `output/durable-launch-lifetime-probe-2026-10-24/`; launcher success is kept
separate from its eventual target exit receipt. No model or network operation
occurred in this sentinel test. No scheduler, startup entry, privilege elevation,
alternate credentials, system settings change, or service installation was used.

The installed Ollama client had updated to version 0.40.10. To prevent another
updater replacement of the bound execution files, a new private CPU runtime was
copied to `C:/Code/ConsequaX-Research/ollama-runtime-0.40.10`. It contains
`ollama.exe` and every top-level `lib/ollama` file, including runtime licenses:
32 files totaling 80,028,727 bytes. GPU subdirectories were excluded. Streamed
hashes of every installed source file before copying, every private copied file,
and every installed source file after copying agreed. The exact inventory is
`private-runtime-manifest.json` in that directory. The model store and ordinary
Ollama service were untouched. This runtime version is a separately declared
execution condition, not interchangeable with earlier collection versions.

The launcher, copy verifier, and empty-prompt runtime loader are auxiliary tools
outside the frozen policy, collector, native auditor, analysis, and pipeline
sources. They do not resume, replace, or retry scientific slots. Launch receipts
record exact inputs, hashes, process identities, creation times, command lines,
user, explicit launch mechanism and job criterion. Terminal receipts establish
process exit only; actual study completion still requires collector, independent
auditor, and analysis evidence. The latest offline helper checks passed 11 tests,
and their static checks passed. Live server logs must not be included in a sealed
artifact manifest until their writer has stopped.
