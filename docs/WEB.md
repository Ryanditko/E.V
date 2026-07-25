# E.V. on the web (use her from any browser)

A second "door" to the same E.V. — inspired by the OpenJarvis pattern (one core,
many access points). A small FastAPI server exposes the **same brain, memory and
tools** as the Telegram bot; you chat from any browser or phone.

- Conversation uses `conv_id="web"` (its own thread), data stays shared.
- Auth: a single bearer token, `EV_WEB_TOKEN`.
- Text chat for now (voice/files still via Telegram).

## Run it

1. Set a strong token in `.env`:
   ```
   EV_WEB_TOKEN=<a long random string>
   EV_WEB_PORT=8000
   ```
2. Start the server:
   ```bash
   python run_web.py
   ```
3. Open `http://localhost:8000`, paste the token when asked.

It reuses the same `ev_memory.db`, so it can run alongside the Telegram bot.

## Expose it "from anywhere" (on the Oracle VM)

The Telegram bot runs as the `ev` systemd service; the web server is a **separate**
process. To make it reachable over the internet:

1. Run it as a second service on the VM (e.g. `ev-web.service`) with the same venv:
   `ExecStart=/home/ubuntu/ev/.venv/bin/python /home/ubuntu/ev/run_web.py`.
2. Open the port:
   - **Oracle console** → VCN → Security List → add an Ingress rule for TCP `8000`
     (this must be done in the Oracle web console — it can't be scripted from here).
   - On the VM: `sudo ufw allow 8000` (if ufw is on) / `sudo iptables ... ` as needed.
3. Access `http://<VM_IP>:8000`.

> Security: the token is the only thing protecting it. Use a long random value.
> For real use, put it behind HTTPS (a reverse proxy like Caddy/Nginx with a
> domain) — plain HTTP over the internet exposes the token in transit.
