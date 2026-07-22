#!/usr/bin/env python3
"""One-time Google authorization for E.V. (Calendar + Gmail).

Run this once on a machine with a browser:

    python authorize_google.py

It opens your browser, asks you to authorize, and caches the token next to the
project (google_token.json). After that, E.V. can use /agenda, /evento and /email.

Prerequisite: set GOOGLE_OAUTH_CLIENT in .env to the path of the OAuth client
secret JSON you downloaded from Google Cloud Console.
"""

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
    print("Opening the browser to authorize Google access...")
    # Building the service triggers the OAuth flow and caches the token.
    tools._google_service(config, "calendar", "v3")
    print("\nAuthorized! Testing by reading your next calendar events:\n")
    print(tools.calendar_upcoming(config, max_results=3))
    print(f"\nToken saved to: {config.google_token_path}")
    print("E.V. can now use /agenda, /evento and /email.")


if __name__ == "__main__":
    main()
