#!/usr/bin/env python3
"""One-time Google authorization for E.V. (Calendar + Gmail), per account.

Run this once per account, on a machine with a browser:

    python authorize_google.py            # authorizes the default (first) account
    python authorize_google.py faculdade  # authorizes a specific named account

It opens your browser, asks you to authorize, and caches that account's token
(google_token_<account>.json). One Google Cloud project/OAuth client serves all
your accounts. After authorizing, E.V. can use /agenda, /evento and /email.

Prerequisites in .env:
  - GOOGLE_OAUTH_CLIENT: path to the OAuth client secret JSON from Google Cloud.
  - EV_GOOGLE_ACCOUNTS: comma-separated account names (e.g. "pessoal,faculdade").
"""

import sys

import ev  # noqa: F401  (injects the OS trust store)
from ev.config import Config
from ev.providers import tools


def main() -> None:
    config = Config.load(require_telegram=False)
    if not config.google_oauth_client:
        raise SystemExit(
            "GOOGLE_OAUTH_CLIENT is not set in .env.\n"
            "Point it to the OAuth client secret JSON downloaded from Google Cloud."
        )
    account = sys.argv[1] if len(sys.argv) > 1 else config.default_account
    if not account:
        raise SystemExit("No account. Set EV_GOOGLE_ACCOUNTS in .env (e.g. pessoal).")
    if account not in config.google_accounts:
        print(f"Warning: '{account}' is not in EV_GOOGLE_ACCOUNTS {config.google_accounts}.")

    print(f"Authorizing Google account '{account}' — opening the browser...")
    tools._google_service(config, account, "calendar", "v3")
    print("\nAuthorized! Your next events on this account:\n")
    print(tools.calendar_upcoming(config, account, max_results=3))
    print(f"\nToken saved to: {config.token_path_for(account)}")
    print("Run again with another account name to add more (e.g. 'faculdade').")


if __name__ == "__main__":
    main()
