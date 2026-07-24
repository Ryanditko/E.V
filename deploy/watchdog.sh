#!/usr/bin/env bash
# Runs ON the VM. If E.V. is down, restart it and alert the owner on Telegram.
# Called on a schedule by .github/workflows/watchdog.yml (over SSH).
# Reads TELEGRAM_TOKEN / EV_OWNER_ID from ~/ev/.env so no token leaves the VM.
set -uo pipefail

if [ "$(systemctl is-active ev)" = "active" ]; then
  echo "ok"
  exit 0
fi

echo "E.V. is down — restarting"
sudo systemctl restart ev
sleep 5
state="$(systemctl is-active ev)"

env_file="$HOME/ev/.env"
token="$(grep -E '^TELEGRAM_TOKEN=' "$env_file" | head -1 | cut -d= -f2-)"
owner="$(grep -E '^EV_OWNER_ID=' "$env_file" | head -1 | cut -d= -f2-)"

if [ -n "$token" ] && [ -n "$owner" ]; then
  if [ "$state" = "active" ]; then
    msg="E.V. estava fora do ar e foi reiniciada automaticamente pelo watchdog. Já estou de volta."
  else
    msg="Alerta: E.V. caiu e o watchdog NÃO conseguiu reiniciar (estado: $state). Dá uma olhada no servidor quando puder."
  fi
  curl -s "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${owner}" \
    --data-urlencode "text=${msg}" >/dev/null || true
fi

echo "restarted; state=$state"
