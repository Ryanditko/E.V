#!/usr/bin/env bash
# Runs ON the VM (called every ~15min by .github/workflows/watchdog.yml over SSH).
# 1) If E.V. is down, restart it and alert the owner on Telegram.
# 2) Warn if disk or memory get tight (once per day per condition, to avoid spam).
# Reads TELEGRAM_TOKEN / EV_OWNER_ID from ~/ev/.env so no token leaves the VM.
set -uo pipefail

env_file="$HOME/ev/.env"
token="$(grep -E '^TELEGRAM_TOKEN=' "$env_file" | head -1 | cut -d= -f2-)"
owner="$(grep -E '^EV_OWNER_ID=' "$env_file" | head -1 | cut -d= -f2-)"

send() {  # send() <text>
  [ -n "$token" ] && [ -n "$owner" ] || return 0
  curl -s "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${owner}" \
    --data-urlencode "text=${1}" >/dev/null || true
}

# Alert at most once per calendar day per condition (stamp file holds the date).
alert_once() {  # alert_once <key> <text>
  local stamp="$HOME/ev/.wd_$1" today; today="$(date +%F)"
  if [ "$(cat "$stamp" 2>/dev/null)" != "$today" ]; then
    send "$2"
    echo "$today" > "$stamp"
  fi
}
clear_alert() { rm -f "$HOME/ev/.wd_$1"; }  # reset so it can alert again later

# --- 1) service health -----------------------------------------------------
check_service() {  # check_service <unit> <friendly-name>
  local unit="$1" name="$2"
  systemctl list-unit-files "$unit.service" >/dev/null 2>&1 || return 0  # not installed -> skip
  [ "$(systemctl is-active "$unit")" = "active" ] && return 0
  echo "$unit is down — restarting"
  sudo systemctl restart "$unit"
  sleep 5
  local state; state="$(systemctl is-active "$unit")"
  if [ "$state" = "active" ]; then
    send "$name estava fora do ar e foi reiniciada automaticamente pelo watchdog. Já estou de volta."
  else
    send "Alerta: $name caiu e o watchdog NÃO conseguiu reiniciar (estado: $state). Dá uma olhada no servidor quando puder."
  fi
}

check_service ev "E.V."
check_service ev-web "A interface web da E.V."

# --- 2) resources ----------------------------------------------------------
disk="$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')"
mem_avail="$(free -m | awk '/^Mem:/ {print $7}')"
swap_used="$(free -m | awk '/^Swap:/ {print $3}')"

if [ -n "$disk" ] && [ "$disk" -ge 85 ]; then
  alert_once disk "⚠️ Disco da VM em ${disk}% (acima de 85%). Pra liberar espaço: \
sudo journalctl --vacuum-time=3d && sudo apt-get clean. Passo a passo: docs/TROUBLESHOOTING.md."
else
  clear_alert disk
fi

if [ -n "$mem_avail" ] && [ "$mem_avail" -lt 120 ]; then
  alert_once mem "⚠️ Memória baixa na VM (disponível ${mem_avail}MB, swap usado ${swap_used}MB). \
Primeiro: sudo systemctl restart ev. Se repetir, aumente o swap (docs/TROUBLESHOOTING.md)."
else
  clear_alert mem
fi

echo "ok disk=${disk}% mem_avail=${mem_avail}MB swap_used=${swap_used}MB"
