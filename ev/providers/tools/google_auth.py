"""Shared Google OAuth client used by calendar.py and email.py."""

from __future__ import annotations

import logging

log = logging.getLogger("ev.tools")

# Read/write scopes for Calendar and Gmail send. Reading mail is done over IMAP
# with an app password (gmail.readonly is a "restricted" OAuth scope that Google
# blocks for unverified apps), so it is NOT requested here.
_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
]


def _google_service(config, account: str, api: str, version: str, allow_interactive: bool = False):
    """Build an authorized Google API client for `account`. Requires
    GOOGLE_OAUTH_CLIENT. One OAuth client serves many accounts; each account has
    its own cached token (google_token_<account>.json).

    `allow_interactive` opens a browser to authorize (only authorize_google.py
    uses this). The bot itself never does — on a headless server it raises a
    clear error instead of trying to open a browser.
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = config.token_path_for(account)
    creds = None
    if token_path.exists():
        # Load with the scopes ALREADY granted in the token file (not the full
        # _GOOGLE_SCOPES list). Otherwise adding a new scope makes refresh request
        # a scope the token never had -> Google returns invalid_scope and breaks
        # even the previously-working calls. New scopes take effect only after a
        # re-authorization (authorize_google.py), which rewrites the token file.
        creds = Credentials.from_authorized_user_file(str(token_path))

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif allow_interactive:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.google_oauth_client, _GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError(
                f"conta '{account}' ainda não autorizada — rode "
                f"authorize_google.py {account} num PC com navegador."
            )
        token_path.write_text(creds.to_json())

    return build(api, version, credentials=creds, cache_discovery=False)
