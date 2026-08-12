# HTTPS para a E.V. via Cloudflare Tunnel

Coloca a interface web da E.V. em `https://ev.SEUDOMINIO.com` **sem abrir nenhuma
porta na Oracle**. O `cloudflared` faz uma conexão de saída até a Cloudflare, que
termina o TLS e encaminha para o `uvicorn` local em `http://localhost:8000`.

Isso destrava o que exige "secure context": microfone/voz na web, Picture-in-Picture
real, notificações do navegador e, mais tarde, login Google/GitHub.

## Pré-requisitos (do seu lado)

1. Conta **Cloudflare** (grátis).
2. Um **domínio adicionado à Cloudflare** (os nameservers do domínio apontando para
   a Cloudflare). Cloudflare **não** dá domínio de graça — use um que você já tenha
   ou registre um barato. O subdomínio (ex.: `ev.`) a gente cria; ele não precisa
   existir ainda.
3. Acesso SSH à VM (você já usa pra fazer deploy).

> Sem um domínio na Cloudflare só dá pra usar os túneis efêmeros `trycloudflare.com`,
> que geram uma URL aleatória a cada execução — ruim para um assistente fixo. Por isso
> o domínio é necessário para um endereço estável.

---

## Passo 0 — instalar o cloudflared na VM

```bash
cd ~/ev && git pull
bash deploy/cloudflared/install.sh
cloudflared --version   # confirme que instalou
```

Agora escolha **um** dos fluxos abaixo. O **Fluxo A (painel)** é o mais simples.

---

## Fluxo A — pelo painel da Cloudflare (recomendado)

1. Painel Cloudflare → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel**.
2. Tipo **Cloudflared**. Dê um nome (ex.: `ev`) e **Save**.
3. A tela mostra um comando de instalação com um token longo. Na aba **Debian/Red Hat**
   ela sugere instalar o pacote; como já instalamos o binário, rode **só a parte do
   serviço** na VM (troque `SEU_TOKEN` pelo token mostrado):

   ```bash
   sudo cloudflared service install SEU_TOKEN
   sudo systemctl enable --now cloudflared
   systemctl status cloudflared --no-pager
   ```

4. Ainda no painel, aba **Public Hostname** → **Add a public hostname**:
   - **Subdomain**: `ev`
   - **Domain**: seu domínio
   - **Type**: `HTTP`
   - **URL**: `localhost:8000`
   - **Save**.

5. Abra `https://ev.SEUDOMINIO.com` — deve carregar a E.V. com cadeado válido.

---

## Fluxo B — pela linha de comando (alternativa)

```bash
# 1. Autentica (abre uma URL; abra no navegador e autorize o seu domínio)
cloudflared tunnel login

# 2. Cria o túnel (guarda um <TUNNEL_ID> e um arquivo <TUNNEL_ID>.json)
cloudflared tunnel create ev

# 3. Move credenciais e config para /etc/cloudflared
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/*.json /etc/cloudflared/
sudo cp deploy/cloudflared/config.yml.example /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml   # ponha o TUNNEL_ID e o hostname reais

# 4. Cria o registro DNS (CNAME) apontando o hostname para o túnel
cloudflared tunnel route dns ev ev.SEUDOMINIO.com

# 5. Sobe como serviço
sudo cloudflared service install
sudo systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
```

---

## Passo final — fechar o HTTP público (recomendado)

Hoje a E.V. web escuta em `0.0.0.0:8000`, ou seja, o `http://IP:8000` fica exposto
em texto puro (o token trafega sem TLS). Depois que o túnel estiver funcionando,
force o app a escutar só localmente — o túnel continua acessando por `localhost`:

```bash
cd ~/ev
grep -q '^EV_WEB_HOST=' .env && sed -i 's/^EV_WEB_HOST=.*/EV_WEB_HOST=127.0.0.1/' .env || echo 'EV_WEB_HOST=127.0.0.1' >> .env
sudo systemctl restart ev-web
```

A partir daí só `https://ev.SEUDOMINIO.com` responde; o `http://IP:8000` para de abrir
de fora (o que é o certo).

## Diagnóstico rápido

- `journalctl -u cloudflared -f` — logs do túnel.
- `curl -I http://localhost:8000` na VM — confirma que o app está de pé localmente.
- No painel, o túnel deve aparecer como **HEALTHY**.
