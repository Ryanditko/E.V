# E.V. — Troubleshooting (what to do if she stops responding)

A calm, ordered runbook. 90% of issues are fixed by step 1 (restart). Replace the
IP/key if yours differ.

Connect to the server:
```bash
ssh -i ~/ev/oracle_ev.key ubuntu@129.158.194.108
```

## The 3 golden steps (try in order)

### 1. Restart the bot (fixes most things)
```bash
sudo systemctl restart ev
sudo systemctl status ev          # should say "active (running)"
```
Then send her a message. Fixed? Done.

### 2. Look at the logs (what went wrong)
```bash
sudo journalctl -u ev -n 60 --no-pager
```
Scan for `ERROR`, `Traceback`, `429` (quota), `404` (bad model/URL). See "Common
issues" below.

### 3. Redeploy the last known-good code (from your machine, not the server)
```bash
cd ~/ev && bash deploy.sh
```
This re-ships the code + your keys and restarts. Use it if a change broke something.

## Common issues → fixes

| Symptom (in logs / chat) | Cause | Fix |
|--------------------------|-------|-----|
| `404 ... models/<x> is not found` | Primary model set to something invalid (e.g. via `/modelo`) | Send **`/modelo reset`** in Telegram (or restart) |
| "todos os meus cérebros estão no limite" | All cloud AIs hit their daily quota | Wait a bit / next day; or enable Ollama on a bigger host |
| `429 RESOURCE_EXHAUSTED` (Gemini) | Gemini daily limit | Normal — she falls back to Groq automatically |
| Google agenda/email error | Token expired or not authorized | Re-run `authorize_google.py` on your PC, redeploy |
| Bot silent after you edited `.env` | Bad value/typo in `.env` | Fix the line; `sudo systemctl restart ev`. If unsure, compare with `.env.example` |
| Service not "active" / crash loop | Code or config error at startup | `journalctl -u ev -n 60` to see the error; then `bash deploy.sh` to restore |
| Two bots answering / "conflict" | Another copy running (e.g. local + VM) with the same token | Keep only ONE running per Telegram token |

> [!WARNING]
> A single Telegram token can only be polled by **one** running instance. If you start
> E.V. locally while the VM copy is up, both fight for updates and you'll see "conflict"
> errors — stop one of them.

## Reset just the model (most common self-fix)
In Telegram: **`/modelo reset`** → back to the default Gemini model. `/modelo`
(no argument) shows what's active and today's usage.

## Restore your data from a backup
E.V. sends a DB backup to your Telegram (weekly). To restore it on the server:
```bash
# copy the backup .db you downloaded from Telegram to the server, then:
scp -i ~/ev/oracle_ev.key ~/Downloads/ev_memory.XXXX.db ubuntu@129.158.194.108:~/ev/ev_memory.db
ssh -i ~/ev/oracle_ev.key ubuntu@129.158.194.108 'sudo systemctl restart ev'
```
(Local daily backups are also on the server in `~/ev/backups/`.)

## VM running low on memory or disk (keep E.V. always up)

The watchdog warns you on Telegram if disk goes over 85% or free memory gets
tight. `/status` shows the current numbers any time. What "used%" means: on Linux,
`buff/cache` is reclaimable, so the number that matters for memory is
**available** (and there's 2 GB of swap as a cushion).

### Memory is tight (bot got killed / keeps restarting)
```bash
sudo systemctl restart ev          # 1) free memory immediately (usually enough)
free -h                            # 2) check "available" and swap
ps aux --sort=-%rss | head -6      # 3) see what's using RAM
grep -c '^OLLAMA_ENABLED=false' ~/ev/.env   # 4) confirm Ollama is OFF (must print 1)
```
If it keeps happening, **grow the swap** (cheap and very effective on a 1 GB VM):
```bash
sudo swapoff -a
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
# make it permanent:
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
Last resort: move to a bigger Oracle shape (e.g. ARM A1 with more RAM) when
capacity is available — that's a migration, not a quick fix.

### Disk is filling up (over 85%)
```bash
df -h /                                   # confirm
sudo journalctl --vacuum-time=3d          # trim systemd logs (usual culprit)
sudo apt-get clean                        # clear apt cache
du -sh ~/ev/backups/* 2>/dev/null         # DB backups (auto-pruned to 7)
du -sh /var/log/* ~/* 2>/dev/null | sort -h | tail   # find big files
```
E.V.'s own footprint is small (~150 MB RAM, a few MB of DB), so disk growth is
almost always logs — the vacuum above fixes it.

## Nothing worked?
Grab the logs and hand them to any AI assistant:
```bash
sudo journalctl -u ev -n 100 --no-pager > ~/ev-logs.txt
```
The project is standard, documented Python — the logs almost always point straight
to the cause. See also `docs/EXTENDING.md` and `docs/CAPABILITIES.md`.

## Golden rule

> [!TIP]
> **Restart → read logs → redeploy → ask an AI with the logs.** In that order. A plain
> `sudo systemctl restart ev` fixes the large majority of hiccups.
