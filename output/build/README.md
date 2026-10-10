# Consequa-X alpha validation

The local Python package `consequa-x` version `0.1.0a1` is built and validated on Python 3.12.14 on Windows. Python 3.11+ is declared; other interpreter versions and platforms still need CI validation.

- 189 tests and 240 subtests passed.
- Ruff and dependency checks passed.
- The wheel installed in a fresh environment with no runtime dependencies.
- Its installed command generated all 12 demo scenarios from a separate working directory.
- All exported traces passed strict import and roundtrip checks and reproduced their saved explanations.
- All 36 episode artifact hashes matched the demo manifest.
- The wheel includes the JSON Schema and type marker; the source distribution includes documentation and tests.
- Built artifacts exclude local environments, scratch files, simulator exports, and the original research brief.

The artifact hashes and sizes are recorded in [validation.json](validation.json). Local distributions are built into `dist/`; downloadable copies are attached to the [GitHub alpha release](https://github.com/Devrajsinh-Jhala/consequa-x/releases/tag/v0.1.0a1):

- [Python wheel](https://github.com/Devrajsinh-Jhala/consequa-x/releases/download/v0.1.0a1/consequa_x-0.1.0a1-py3-none-any.whl)
- [Source distribution](https://github.com/Devrajsinh-Jhala/consequa-x/releases/download/v0.1.0a1/consequa_x-0.1.0a1.tar.gz)

See the [usage guide](../../README.md), [demo report](../demo/README.md), and [fixture experiment report](../experiments/README.md). The build remains an offline research prototype. Actual LLM evaluation, paper experiments, release metadata, and registry publication are subsequent milestones.
