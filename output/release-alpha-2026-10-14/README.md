# Reviewed Python alpha 2 artifacts

The [GitHub alpha release](https://github.com/Devrajsinh-Jhala/consequa-x/releases/tag/v0.1.0a2)
is published. Its three asset hashes and sizes match the retained local files,
and the tag targets the reviewed runtime source. The
[publication receipt](publication.json) records the GitHub verification and the
separate pending PyPI upload.

The files here are the reviewed `consequa-x 0.1.0a2` wheel and source distribution,
built from source **40fa9bc7612c249dc33899a2ad6a6a12b5087ec4**. The
[receipt](checks.json) binds both files to their hashes, sizes, source revision,
observed test results and actual validation environment.

Local validation passed: the full source suite (1,274 tests and 240 subtests),
14 standalone release-helper tests, lint, strict package metadata checks, a
complete package/source inventory review, and separate fresh wheel/sdist installs.
The installed smoke checks each validate 12 synthetic trace round trips, schema
validation and explanation generation without model calls. New compatibility
checks cover Windows Python 3.12.14. GitHub Actions remains disabled.

- [Inventory review](inventory.json), including wheel RECORD checks and source payload matching.
- [Wheel smoke receipt](wheel-smoke.json) and [sdist smoke receipt](sdist-smoke.json).
- [Build log](build.log) and [installed-package verification script](verify_installed.py).
- [Changes and research limits](../../CHANGELOG.md).
- [Local PyPI authentication setup](../../docs/local-pypi-setup.md).

These artifact hashes differ from the earlier checkpoint used for the local
model validation. That checkpoint and its source revision are preserved with
the [study](../local-validation-2026-10-14/); it was not silently replaced by
this later build.

After authentication is configured locally, the maintainer-authorized upload
uses only these exact files:

```powershell
& .\tmp\interval-reference-env\Scripts\python.exe .\scripts\publish_alpha.py .\output\release-alpha-2026-10-14\checks.json --account devraj0502
```

The helper rejects changed artifacts and mismatched registry files, uploads only
missing files, and verifies both public hashes afterward. PyPI publication and
a fresh registry installation remain pending until recorded in a separate
publication receipt. A GitHub download does not establish PyPI publication.
