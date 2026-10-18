# Security policy

Please report suspected package vulnerabilities privately through
[GitHub's private vulnerability reporting form](https://github.com/Devrajsinh-Jhala/consequa-x/security/advisories/new).
A GitHub account is required. Do not open a public issue containing an exploit,
credential, private trace or customer data. Use a synthetic reproduction and
include package/Python/OS versions, impact and reproduction steps. Do not send
working production credentials.

The latest stable release is the primary maintenance target. Version 1 core
and schema compatibility are documented; no response deadline or long-term
support period is promised. Security fixes and breaking changes will be stated
in release notes. Research interfaces can evolve under their declared scope.

Default HTML reports omit arbitrary captured fields. They retain timing, counts
and relationships and do not guarantee anonymity. --include-details explicitly
includes the entire captured trace as escaped text. Keep those reports private
when the trace is private. The offline renderer makes no network calls and
does not execute verifiers, replay or application writes.

The framework does not authenticate your readback source or validate that a
provider's metadata is true. Application-owned adapters must establish source
trust and domain semantics. Sharing a report does not replace preserving the
original trace and source evidence.
