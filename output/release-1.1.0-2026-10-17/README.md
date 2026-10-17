# Consequa-X 1.1.0 hard-launch release

Completed 17 October 2026. Version 1.1.0 is public on
[PyPI](https://pypi.org/project/consequa-x/1.1.0/). The
[animated landing and public docs](https://consequa-x.brawny-deer-5658.chatgpt.site)
are deployed publicly; [community support](https://github.com/Devrajsinh-Jhala/consequa-x-community)
and private vulnerability reporting work without private-repository access.
The research/source repository remains private. GitHub Actions stayed disabled.

## Release identity

Runtime freeze: `23f871ee0d01d6aef452211fe3facc31963adefc`.
Complete distribution source: `2e1ea177bffb3c7649b1ef055a277b196a58f8b9`.
`SOURCE_DATE_EPOCH=1792244657` produced identical runtime-wheel bytes across both
freezes. Later public-site status and receipt commits do not alter these files.

| Public artifact | Bytes | SHA-256 |
| --- | --- | --- |
| consequa_x-1.1.0-py3-none-any.whl | 160679 | `73828c5879a9523cf2db97a7b2fd77fd09c66d8744b820757b58a1d984be4f40` |
| consequa_x-1.1.0.tar.gz | 418470 | `6bc2c1062fef8c6bee82b66fc950378e9165fe78dc032b23beb64ec94c664019` |

[checks.json](checks.json) records all twelve release gates. The
[inventory audit](inventory.json) verified Git HEAD and clean tracked source,
37 runtime files, 43 wheel entries and 145 source-archive files. The wheel
retains MIT licensing, typing information, schema 0.1 and zero required runtime
dependencies. Private research, credentials, website files, paper PDFs and virtual
machine images are excluded from Python distributions.

## Validation and publication

The frozen-source suite passed **1,624 tests plus 240 subtests**, with no errors,
failures or skips. `source-tests.xml`, `source-tests.log`, `lint.log` and
`metadata.log` retain actual results. Installed checks ran outside the checkout
with isolated imports and verified all 37 payloads against the exact wheel:

| Environment | Receipt | Scope |
| --- | --- | --- |
| Windows / official Python 3.11.9 embedded interpreter | windows311.json | Minimum-version installed-wheel conformance |
| Windows / Python 3.12.14 fresh venv | windows312.json | Fresh installed-wheel checks |
| Windows / Python 3.12.14 fresh venv | sdist312.json | Source archive installed with setuptools 84; runtime bytes match wheel |
| Alpine Linux 3.24.2 / Python 3.14.8 / kernel 6.18.52-0-virt | linux.json | Actual Linux guest, QEMU TCG on Windows; console entry point also passed |
| Windows / Python 3.12.14 fresh public-index install | registry312.json | Public PyPI installation, no cache; all payloads match reviewed wheel |

Each installed checker retained four trace round-trips, sixteen strict schema
refusals and twelve report CLI checks, including disclosure, escaping and
source/output preservation. API-process benchmark imports are zero; existing CLI
parsing imports packaged research modules without executing scenarios or replay.
There were no provider/model calls. The Linux result covers one emulated guest,
not every Linux distribution or native deployment; macOS remains untested.

[publication.json](publication.json) records independent downloads matching both
reviewed public artifact hashes/sizes and the successful public-index install.
The upload log retains an initial metadata-propagation delay; the idempotent
follow-up verified both files without uploading again.

## Report and website review

[browser-qa.json](browser-qa.json) and `browser-fixtures/` bind the exact report
source and synthetic examples. Desktop/mobile, hostile details, missing evidence,
newer unknown receipts, successive conflicting witnesses and complete graph
tables were reviewed. Print media styles omit the SVG overview and retain every
node/link table; physical printer pagination was not exercised. Captured default
fields are deliberately omitted, not universally anonymized; explicit details
may be sensitive. Rendering performs no verifier, target matching or replay.

[public-final.json](public-final.json) verifies anonymous public pages and the
downloaded quickstart, run with the fresh registry installation.
[site-publication.json](site-publication.json) identifies the deployed public
version and exact source commit. `site-launch.tar.gz` contains exactly fourteen
reviewed public assets plus the hosting manifest. The hosting CDN appends its
browser challenge script; authored markup and downloadable assets were checked
separately. Offline report files have no hosting runtime or JavaScript.

`manifest.json` seals every retained file in this directory except itself.
Historical 1.0 releases, study collections and checked IEEE paper remain unchanged.
