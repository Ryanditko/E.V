# Run E.V. on Android with Termux (free, no credit card)

Run the bot on an Android phone. Best on a spare phone left plugged in. It stays
online in the background (screen off, app closed) once you set the three
reliability steps below.

Ollama does not run well on a phone, so on Android E.V. uses only the cloud
providers (set `OLLAMA_ENABLED=false`).

---

## 1. Install Termux (IMPORTANT: from F-Droid, not the Play Store)

The Play Store build is outdated and broken. Install from **F-Droid**:

1. Install F-Droid: https://f-droid.org
2. In F-Droid, install **Termux** and **Termux:Boot** (the boot plugin).

## 2. Prerequisites inside Termux

Open Termux and run:

```bash
pkg update -y && pkg upgrade -y
pkg install -y python git rust binutils   # rust/binutils: some deps compile
termux-setup-storage                        # allow file access (optional)
```

> `rust` and `binutils` are there because a few dependencies (pydantic-core,
> the web-search lib) may build from source on Android. It can take a few
> minutes. If the web-search package fails to build, you can skip it later by
> setting `EV_WEBSEARCH_ENABLED=false` in `.env`.

## 3. Get the code and install

```bash
git clone https://github.com/Ryanditko/E.V.git ev
cd ev
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure `.env`

```bash
cp .env.example .env
nano .env      # fill TELEGRAM_TOKEN, GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY
```

Set `OLLAMA_ENABLED=false` (no Ollama on the phone). Save in nano with
`Ctrl+O`, `Enter`, then `Ctrl+X`.

## 5. First test

```bash
python run_telegram.py
```

Send `/start` to your bot. If it answers, it works. Stop with `Ctrl+C` for now.

## 6. Keep it running 24/7 (the three reliability steps)

**a) Wake lock** — stops Android from killing the process:
```bash
termux-wake-lock
```

**b) Disable battery optimization for Termux**
Android Settings -> Apps -> Termux -> Battery -> set to **Unrestricted**
(the exact path varies by phone; the goal is "do not optimize/restrict").

**c) Auto-start on boot (Termux:Boot)**
Create a boot script so the bot restarts when the phone reboots:
```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-ev.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
cd ~/ev
. .venv/bin/activate
python run_telegram.py
EOF
chmod +x ~/.termux/boot/start-ev.sh
```
Open the **Termux:Boot** app once (so Android grants it permission to run at boot).

## 7. Start it in the background now

```bash
termux-wake-lock
cd ~/ev && . .venv/bin/activate
nohup python run_telegram.py > ~/ev.log 2>&1 &
```

Now you can close the app / turn the screen off. Check logs anytime with:
```bash
tail -f ~/ev.log
```

## If it ever stops

Reopen Termux and run the commands in step 7 again (or just reboot — Termux:Boot
restarts it). This is the honest trade-off vs a cloud server: a spare phone left
plugged in is very stable; a busy main phone may occasionally kill it.

## Update to the latest code

```bash
cd ~/ev && git pull && pkill -f run_telegram.py
termux-wake-lock; . .venv/bin/activate
nohup python run_telegram.py > ~/ev.log 2>&1 &
```
