# Configure the first PyPI upload locally

The reviewed release is `consequa-x 0.1.0a2`. Its two distribution files and
checks are retained in [the release receipt](../output/release-alpha-2026-10-14/checks.json).
The release helper verifies their bytes before uploading to production PyPI.
GitHub Actions remains disabled.

1. Sign in to [PyPI](https://pypi.org/account/login/) as `devraj0502` and create
   an API token under [account settings](https://pypi.org/manage/account/).
   Creating a new project requires an account-wide token. After the first
   upload, replace it with a token scoped to this project if desired.
2. In PowerShell, from the ConseqaX folder, run:

   ```powershell
   & .\tmp\interval-reference-env\Scripts\python.exe .\scripts\configure_pypi_auth.py --account devraj0502
   ```

3. Enter the token at the hidden local prompt. It is stored in this machine's
   credential store. Do not paste it in this chat or save it in the repository.
4. Tell the assistant that local setup is complete. The upload is already
   authorized; the assistant can then upload the reviewed files and check the
   public hashes and a fresh registry installation.

This workspace's release tooling is installed in the ignored `tmp` environment.
It is separate from the framework, which requires no runtime dependencies.
To prepare tooling on another machine, install `build`, `twine`, and `keyring`
in a dedicated environment and run the same helper with that interpreter.

The helper does not claim ownership or availability of a PyPI project name.
Any name or account error must be resolved before publication is recorded.
Publication is pending until the public registry returns the reviewed files.
