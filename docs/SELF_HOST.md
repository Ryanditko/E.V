# Run E.V. as a service on your own PC (free, no credit card)

Runs the bot in the background, starting automatically with the computer, no
terminal window needed. Online whenever the PC is on. Pick your OS below.

Prerequisite: the project already runs manually (see [SETUP.md](SETUP.md) —
`.env` filled and `python run_telegram.py` works). Replace `USERNAME` and paths
with yours; the examples assume the project is at `~/ev`.

---

## macOS (launchd)

1. Create `~/Library/LaunchAgents/com.ev.bot.plist` with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ev.bot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/USERNAME/ev/.venv/bin/python</string>
    <string>/Users/USERNAME/ev/run_telegram.py</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/USERNAME/ev</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/USERNAME/ev/ev.log</string>
  <key>StandardErrorPath</key><string>/Users/USERNAME/ev/ev.log</string>
</dict>
</plist>
```

2. Load and start it:
```bash
launchctl load ~/Library/LaunchAgents/com.ev.bot.plist
launchctl start com.ev.bot
```
3. Logs: `tail -f ~/ev/ev.log`. Stop: `launchctl unload ~/Library/LaunchAgents/com.ev.bot.plist`.

> The Mac must be on and awake. To keep it running with the lid closed, keep it
> plugged in (and consider `caffeinate`), or disable sleep in System Settings.

## Linux (systemd)

If it's the same machine style as a server, the repo's `deploy/setup_vm.sh`
already creates the service. Otherwise, create `~/.config/systemd/user/ev.service`:

```ini
[Unit]
Description=E.V. assistant
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/ev
ExecStart=%h/ev/.venv/bin/python %h/ev/run_telegram.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Then:
```bash
systemctl --user daemon-reload
systemctl --user enable --now ev
loginctl enable-linger $USER      # keep it running after you log out
journalctl --user -u ev -f        # logs
```

## Windows (Task Scheduler)

1. Create a file `run_ev.bat` in the project folder:
   ```bat
   @echo off
   cd /d %USERPROFILE%\ev
   .venv\Scripts\python.exe run_telegram.py
   ```
2. Open **Task Scheduler** -> **Create Task**.
   - General: name `E.V.`; check **Run whether user is logged on or not**.
   - Triggers: **New -> At log on** (or **At startup**).
   - Actions: **New -> Start a program** -> browse to `run_ev.bat`.
   - Settings: check **If the task fails, restart every 1 minute**.
3. Save. It starts with Windows and stays running in the background.

> The PC must be on. Set power options so it doesn't sleep while plugged in.

## Update to the latest code (any OS)

```bash
cd ~/ev && git pull
# then restart the service:
#   macOS:   launchctl unload ... && launchctl load ...
#   Linux:   systemctl --user restart ev
#   Windows: end the task and let it restart, or reboot
```
