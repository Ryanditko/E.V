# Android quick-add widget (gasto / tarefa, sem abrir o app)

Um widget na tela inicial do Android pra registrar um gasto ou criar uma
tarefa em poucos toques, sem abrir o Telegram nem o console web. Não há
nenhum código novo no lado da E.V. — ele fala diretamente com as rotas
`POST /api/expenses` e `POST /api/tasks` que o [console web](WEB.md) já expõe.

## Pré-requisitos

1. **Tailscale no celular, conectado à mesma tailnet da VM.** A API só é
   alcançável em `https://ev.<tailnet>.ts.net` (ver
   [`deploy/HTTPS_TAILSCALE.md`](../deploy/HTTPS_TAILSCALE.md)); não existe
   modo público. Sem o Tailscale ativo, a URL simplesmente não resolve.
2. O valor de `EV_WEB_TOKEN` (o mesmo token usado para logar no console web).
3. O app **[HTTP Shortcuts](https://play.google.com/store/apps/details?id=ch.rmy.android.http_shortcuts)**
   (Waboodoo) instalado — recomendado em vez de Tasker, porque já tem nativamente
   prompts de input, widgets de tela inicial por shortcut/grupo, headers Bearer e
   export/import em JSON.

## Importar a configuração pronta

Um export com os dois shortcuts ("Gasto" e "Tarefa") agrupados em "EV Quick
Add" está em
[`deploy/android/ev-quick-add.http-shortcuts.json`](../deploy/android/ev-quick-add.http-shortcuts.json).
O token **não** vem preenchido nesse arquivo — é um placeholder a completar
depois do import.

1. Copie o `.json` pro celular (Drive, e-mail, etc).
2. Abra o HTTP Shortcuts → menu (⋮) → **Import / Export** → **Import from file**.
3. Depois de importar, edite cada um dos dois shortcuts → aba **Authentication**
   → cole seu `EV_WEB_TOKEN` no campo do valor "Bearer".

## Adicionar à tela inicial

O objetivo é **um único widget** que, ao tocar, abre um menu rápido com
"Gasto" / "Tarefa":

1. Na tela inicial, toque e segure num espaço vazio → **Widgets** →
   **HTTP Shortcuts**.
2. Escolha o widget do tipo **lista de shortcuts** e selecione o grupo
   **"EV Quick Add"** como fonte.
3. Tocar no widget mostra o popup com as duas opções; escolher uma abre os
   prompts de input daquele shortcut.

Se esse popup de grupo ficar ruim no seu launcher, a alternativa simples é
colocar os dois shortcuts ("Gasto" e "Tarefa") como ícones separados na tela
inicial — mesma configuração, sem agrupar.

## O que cada shortcut faz

**Gasto** — pede um número (valor) e um texto (descrição, opcional), então:

| | |
|---|---|
| Método | `POST` |
| URL | `https://ev.<tailnet>.ts.net/api/expenses` |
| Headers | `Authorization: Bearer <EV_WEB_TOKEN>`, `Content-Type: application/json` |
| Body | `{"amount": "{{amount}}", "description": "{{desc}}", "category": "geral"}` |

**Tarefa** — pede um texto único, então:

| | |
|---|---|
| Método | `POST` |
| URL | `https://ev.<tailnet>.ts.net/api/tasks` |
| Headers | `Authorization: Bearer <EV_WEB_TOKEN>`, `Content-Type: application/json` |
| Body | `{"text": "{{text}}", "category": "", "recur": "", "due": ""}` |

Ambos mostram um toast de sucesso na resposta 2xx, e um erro visível em
qualquer outro caso — importante porque não existe outra confirmação (não
chega mensagem no Telegram quando o gasto/tarefa é criado por aqui).

## Configuração manual (se preferir não importar o JSON)

Crie os dois shortcuts do zero no HTTP Shortcuts usando exatamente as tabelas
acima — método, URL, headers e corpo. Configure `amount`/`desc` e `text` como
variáveis do tipo "Ask" (pedem o valor antes de disparar a requisição).

## Troubleshooting

- **401 Unauthorized** → token errado ou não preenchido. Confira o valor de
  `EV_WEB_TOKEN` na VM (`.env`) e recole no shortcut.
- **Timeout / conexão recusada** → o Tailscale não está conectado no celular,
  ou a VM está fora do ar. Confirme o Tailscale ativo; se persistir, veja o
  [watchdog](../deploy/watchdog.sh) e o runbook de
  [`deploy/HTTPS_TAILSCALE.md`](../deploy/HTTPS_TAILSCALE.md).
- **Criou mas não aparece** → abra o console web e confira a aba
  Gastos/Tarefas — os dados são os mesmos, só a UI que não se atualiza sozinha
  fora do navegador.
