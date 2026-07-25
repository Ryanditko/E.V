#!/usr/bin/env bash
# Instala o cloudflared na VM (Ubuntu/Debian ou Oracle Linux/RHEL, x86_64 ou ARM).
# Uso:  bash deploy/cloudflared/install.sh
# Depois siga deploy/HTTPS_CLOUDFLARE.md para criar/conectar o túnel.
set -euo pipefail

if command -v cloudflared >/dev/null 2>&1; then
  echo ">> cloudflared já instalado: $(cloudflared --version)"
  exit 0
fi

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) a=amd64 ;;
  aarch64|arm64) a=arm64 ;;   # VMs Ampere A1 da Oracle são ARM
  *) echo "!! arquitetura não suportada: $arch" >&2; exit 1 ;;
esac

url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$a"
echo ">> Baixando cloudflared ($a) de $url"
tmp="$(mktemp)"
curl -fsSL -o "$tmp" "$url"
sudo install -m 0755 "$tmp" /usr/local/bin/cloudflared
rm -f "$tmp"

echo ">> Instalado: $(cloudflared --version)"
