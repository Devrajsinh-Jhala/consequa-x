# Consequa-X 1.1.1 release record

Documentation and metadata release, published to PyPI on 18 October 2026 from
source revision `d6b77854f7c812d4210d62193b2ce1cef5a3710b`. Runtime code and schema 0.1 are identical to 1.1.0 apart
from the version string (compared with `2e1ea17`).

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `consequa_x-1.1.1-py3-none-any.whl` | 158,098 | `bdca26f28b0525d811b3e6512aac01c4b62809d80ce65825048cbf8245f3cf25` |
| `consequa_x-1.1.1.tar.gz` | 528,702 | `d536500085de818c6083a9f37d1cd71d8b8b246f2c010c9eca448b2306bb5bd6` |

## What was checked

- Full source suite: 1,786 passed, 21 skipped, 240 subtests, 0 failures
  ([log](source-tests.log)); lint passed.
- Artifact inventory and strict metadata audit ([inventory.json](inventory.json)).
- Installed-wheel checker on Windows: official embedded Python 3.11.9
  ([windows311.json](windows311.json)) and a fresh Python 3.12.10 venv
  ([windows312.json](windows312.json)).
- Source distribution smoke install on Python 3.12.10 ([sdist312.json](sdist312.json)).
- After upload: PyPI serves both files with the reviewed sizes and hashes, and a
  fresh install from PyPI passed the installed-wheel checker
  ([registry312.json](registry312.json), [publication.json](publication.json)).

## Not rerun for 1.1.1

Published on the maintainer's instruction with Windows checks only.

- Linux install check: not rerun. The 1.1.0 wheel passed on one Alpine Linux
  QEMU guest; 1.1.1 runtime differs only in the version string.
- macOS: never tested.
- Formal report browser QA: not rerun; the renderer is byte-identical to 1.1.0
  and reproduced the published sample report byte for byte.
- Public docs/support gate: pending until private vulnerability reporting is
  enabled on the public repository and Render serves the site from it.

The gate states are recorded in [checks.json](checks.json). GitHub Actions was
not used.
