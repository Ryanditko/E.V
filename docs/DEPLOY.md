# Deploy E.V. 24/7 on Oracle Cloud (Always Free)

Goal: run E.V. on a free Oracle ARM VM that stays on 24/7 (even with your Mac
off) and can also run Ollama (the never-runs-out local fallback).

Do this from your personal computer. It has a bit of one-time bureaucracy
(account + VM), then the deploy itself is a few commands.

---

## Part A — Create the Oracle Cloud account (~10-15 min)

1. Go to **https://www.oracle.com/cloud/free/** and click **Start for free**.
2. Sign up: email, country (**Brazil**), personal details.
3. **Home region:** pick one and know it is **permanent**. `US East (Ashburn)`
   usually has the most free ARM capacity; `Brazil East (Sao Paulo)` gives lower
   latency. Either is fine.
4. **Credit card:** required for identity verification. Always Free does **not**
   charge; you may see a temporary ~US$1 authorization that is reversed.
5. Finish and wait for the account to be provisioned (a few minutes).

> If signup fails ("unable to process"), try another card or browser. Oracle
> signup is occasionally finicky.

## Part B — Create the VM (Always Free ARM)

1. In the console, open the menu -> **Compute -> Instances -> Create instance**.
2. **Name:** `ev`.
3. **Image:** **Canonical Ubuntu 22.04**.
4. **Shape:** click **Change shape -> Ampere (ARM)** -> **VM.Standard.A1.Flex** ->
   set **2 OCPUs** and **12 GB RAM** (well within the Always Free 4 OCPU / 24 GB).
   This is enough to run E.V. + Ollama with a small model.
5. **SSH keys:** choose **Generate a key pair for me** and **download the private
   key** (you will need it to connect). Or paste your own public key.
6. Leave networking defaults (a VCN with SSH allowed is created automatically).
7. **Create**. When it's running, copy the **Public IP address**.

> **"Out of capacity" on ARM?** It's common in busy regions. Options: try again
> later, try a different Availability Domain in the create screen, or use the
> AMD **VM.Standard.E2.1.Micro** (1 GB) — E.V. runs there, but it's too small for
> Ollama (cloud "never runs out" then only works once you add a bigger VM).

## Part C — Connect via SSH (from your PC)

```bash
chmod 400 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@YOUR_PUBLIC_IP
```
(Type `yes` to accept the fingerprint on first connect.)

## Part D — Install E.V.

On the VM:

```bash
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/Ryanditko/E.V.git ev
cd ev
```

Create the `.env`. Easiest is to copy it from your PC — run this **on your PC**
(new terminal), not on the VM:

```bash
scp -i ~/Downloads/ssh-key-*.key ~/ev/.env ubuntu@YOUR_PUBLIC_IP:~/ev/.env
```

Then back **on the VM**, install and register the service:

```bash
bash deploy/setup_vm.sh
```

This creates the Python env, installs dependencies, and registers a `systemd`
service `ev` that starts on boot and restarts on crash.

Check it:
```bash
sudo systemctl status ev
sudo journalctl -u ev -f        # live logs (Ctrl+C to stop watching)
```

Your bot should now respond on Telegram 24/7.

## Part E — Install Ollama (never-runs-out fallback)

On the VM:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1
```

The installer runs Ollama as a service on `http://localhost:11434`, which is
exactly what E.V. expects (`OLLAMA_BASE_URL` default). Restart E.V. to be safe:

```bash
sudo systemctl restart ev
```

Now, if every cloud provider is rate-limited, E.V. falls back to the local
llama3.1 and never goes silent.

> Optional (local embeddings, no quota): `ollama pull nomic-embed-text` and set
> `EV_EMBED_BACKEND=ollama` in `.env`, then `sudo systemctl restart ev`.

## Part F — Google tokens (optional)

If you use `/agenda` and `/email`, authorize on your PC first (see
[GOOGLE.md](GOOGLE.md)), then copy the token + client files to the VM (on your PC):

```bash
scp -i ~/Downloads/ssh-key-*.key ~/ev/client_secret.json ubuntu@YOUR_PUBLIC_IP:~/ev/
scp -i ~/Downloads/ssh-key-*.key ~/ev/google_token_*.json ubuntu@YOUR_PUBLIC_IP:~/ev/
```
Then `sudo systemctl restart ev` on the VM.

## Part G — Managing E.V. on the VM

```bash
sudo systemctl status ev        # is it running?
sudo systemctl restart ev       # restart
sudo journalctl -u ev -f        # live logs
cd ~/ev && git pull && sudo systemctl restart ev   # update to latest code
```

Backups of the memory DB are written to `~/ev/backups/` automatically (kept: 7).
To keep them off the VM, copy them out periodically with `scp`.

## Security reminder

The `.env` on the VM holds all your keys. Keep the SSH private key safe. Never
commit `.env`, `client_secret.json`, or `google_token_*.json` (all git-ignored).
