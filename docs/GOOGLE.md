# Connecting Google (Calendar + email) — run on YOUR personal computer

The Google authorization opens a browser and logs into YOUR Google accounts, so
it must run on the machine where your browser and accounts live (your personal
PC), not on a shared/work machine.

One Google Cloud project/OAuth client serves all your accounts. The project and
`client_secret.json` were already created — you only need to authorize each
account on your PC.

---

## Step 0 — Make sure the project is set up on that PC

Follow [SETUP.md](SETUP.md) sections 2-5 (clone, venv, install, `.env`). Then
ensure these two things are in place:

1. **`client_secret.json` in the project root.** It is NOT in git (it's a secret).
   Bring it to the PC by either:
   - copying `client_secret.json` from the other machine, or
   - re-downloading it: Google Cloud Console -> APIs & Services -> Credentials ->
     your OAuth client -> Download JSON -> save as `client_secret.json`.

2. **`.env` has these lines:**
   ```
   GOOGLE_OAUTH_CLIENT=client_secret.json
   EV_GOOGLE_ACCOUNTS=pessoal,faculdade
   ```
   (Also make sure `TELEGRAM_TOKEN` and `GEMINI_API_KEY` are filled — see SETUP.md.)

## Step 1 — Authorize each account (the commands to run)

From the project folder, with the virtualenv active:

```bash
cd ~/ev                       # or wherever you cloned it
source .venv/bin/activate      # Windows: .venv\Scripts\activate

python authorize_google.py pessoal
python authorize_google.py faculdade
```

For each command:
1. The browser opens. Log in with the matching account.
2. You'll see "Google hasn't verified this app" -> click **Advanced** ->
   **Go to E.V. (unsafe)** (it's your own app, it's safe).
3. Approve the Calendar + Gmail-send permissions -> **Continue**.
4. The terminal prints "Authorized!" and your next events. A token is cached as
   `google_token_<account>.json`.

If the browser doesn't open automatically, copy the URL the terminal prints into
your browser.

## Step 2 — Use it

In Telegram (or terminal):

```
/agenda                     # default account (first in EV_GOOGLE_ACCOUNTS)
/agenda faculdade           # a specific account
/evento pessoal amanhã 15:00 Dentista
/email pessoal fulano@x.com | Assunto | Corpo do e-mail
```

Omitting the account name uses the default (first) account.

## Notes

- **Institutional accounts** (faculty/work) may be blocked by admin policy from
  authorizing third-party OAuth apps. If that account fails to authorize, it's an
  institution restriction with no client-side workaround — the personal account
  still works.
- Tokens are **per account** (`google_token_pessoal.json`, `google_token_faculdade.json`)
  and must not be committed (already git-ignored).
- On a headless server (deploy), authorize on your PC first, then copy the
  `google_token_*.json` files to the server.
