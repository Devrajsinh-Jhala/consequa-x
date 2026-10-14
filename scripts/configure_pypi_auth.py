"""Store an upload token locally with hidden input; never put it in chat/files."""

import argparse
from getpass import GetPassWarning, getpass
import warnings


SERVICE = "https://upload.pypi.org/legacy/"


def main():
    import keyring

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="devraj0502")
    args = parser.parse_args()
    if not args.account.strip():
        parser.error("account must be nonempty")
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        token = getpass(f"PyPI API token for {args.account} (hidden): ").strip()
    if not token.startswith("pypi-"):
        raise ValueError("Expected a PyPI API token; no credential was saved")
    keyring.set_password(SERVICE, args.account, token)
    print(f"Saved upload authentication for {args.account} in the local credential store.")


if __name__ == "__main__":
    main()
