# HTTPS privado para a E.V. via Tailscale Serve

Coloca a interface web da E.V. em `https://<maquina>.<seu-tailnet>.ts.net`, com
certificado TLS válido, **sem domínio, sem custo e sem abrir portas na Oracle**.

Modo **Serve** (privado): a E.V. só responde para os **seus aparelhos** logados no
seu Tailscale (celular + PC). Não vai para a internet pública — é o mais seguro.
(O modo público seria o `funnel`; aqui usamos `serve` de propósito.)

Isso destrava o que exige "secure context": microfone/voz na web, Picture-in-Picture
real, notificações do navegador e, mais tarde, login Google/GitHub.

## Pré-requisitos (do seu lado)

1. Conta **Tailscale** grátis (login com Google/GitHub/e-mail) — https://tailscale.com
2. App **Tailscale** instalado em cada aparelho seu que vai abrir a E.V.
   (celular iOS/Android + notebook). No modo privado, o aparelho precisa estar no
   seu tailnet pra enxergar a URL `.ts.net`.
3. Acesso SSH à VM (o que você já usa pra deploy).

---

## Passo 1 — instalar e conectar o Tailscale na VM

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` imprime uma URL — abra no navegador, faça login e autorize esta máquina.

Confirme o nome da máquina e do seu tailnet (vai compor a URL):

```bash
tailscale status
```

## Passo 2 — habilitar HTTPS no tailnet (uma vez, no painel web)

No admin console (https://login.tailscale.com/admin/dns):
- Ative **MagicDNS**.
- Ative **HTTPS Certificates** (necessário pro certificado `*.ts.net`).

## Passo 3 — servir a E.V. (privado)

```bash
# Forma atual (Tailscale recente): publica https -> localhost:8000, em background
sudo tailscale serve --bg 8000

# Se o comando acima reclamar da sintaxe, confira as opções da sua versão:
tailscale serve --help
# Alternativa em versões um pouco mais antigas:
#   sudo tailscale serve https / http://127.0.0.1:8000

# Ver o que está publicado e a URL exata:
tailscale serve status
```

A URL final é `https://<nome-da-maquina>.<seu-tailnet>.ts.net` (aparece no
`tailscale serve status` / `tailscale status`).

## Passo 4 — instalar o Tailscale nos seus aparelhos

- **Celular**: app Tailscale (iOS/Android) → login com a MESMA conta → ligar.
- **PC**: app desktop Tailscale → login → ligar.

Com o Tailscale ligado no aparelho, abra a URL `.ts.net` no navegador. Como agora é
HTTPS de verdade, o microfone/voz, PiP e notificações passam a funcionar.

## Passo 5 — fechar o HTTP público (recomendado)

Hoje a E.V. web escuta em `0.0.0.0:8000`, então `http://IP:8000` fica exposto em texto
puro (o token trafega sem TLS). Depois que o Serve estiver ok, force o app a escutar só
localmente — o Tailscale continua acessando por `localhost`:

```bash
cd ~/ev
grep -q '^EV_WEB_HOST=' .env && sed -i 's/^EV_WEB_HOST=.*/EV_WEB_HOST=127.0.0.1/' .env || echo 'EV_WEB_HOST=127.0.0.1' >> .env
sudo systemctl restart ev-web
```

A partir daí só a URL `.ts.net` (pelos seus aparelhos) responde; o `http://IP:8000`
para de abrir de fora.

## Diagnóstico rápido

- `tailscale serve status` — o que está sendo servido e a URL.
- `sudo tailscale status` — máquinas do tailnet e conectividade.
- `curl -I http://localhost:8000` na VM — confirma o app de pé localmente.
- `journalctl -u tailscaled -f` — logs do Tailscale.
