"""LLM-facing tools, in two synchronized formats.

`_tool_callables` (Gemini-native closures) and `_openai_tools` (OpenAI-schema
format for Groq/OpenRouter) are intentional duplicates that must stay in sync
— kept together in this one file, in the same relative order, on purpose.
See tests/test_brain_tools_sync.py for the guard on this invariant.
"""

import logging

from ...providers import documents as documents_mod, tools as tools_mod
from .. import knowledge

log = logging.getLogger("ev.brain")

# Commands that can't run in the pure logic layer (they send files, drive the
# Telegram UI, or run a live timer). The LLM's executar_comando queues these and
# the interface executes them with the chat context.
_INTERFACE_COMMANDS = frozenset({
    "foco", "silenciar", "exportar", "status", "resumir", "limparchat",
    "dados", "limpar", "quiz", "insights", "modelo", "ajuda", "documento",
    "transcrever", "menu", "provedor", "padroes",
})


class ToolsMixin:
    # --- tools (shared by Gemini and Groq) ---------------------------------

    def _tool_callables(self, user_id: str) -> dict:
        """Tools bound to THIS user. Used by Gemini (Python funcs) and Groq
        (function-calling dispatch)."""
        cfg = self._config
        # Assistant language, bound here so provider tool results/errors follow
        # it. This is an INTERNAL detail — never exposed as an LLM tool argument.
        lang = self._memory.assistant_lang()

        def salvar_memoria(fato: str) -> str:
            """Guarda um fato duradouro sobre o usuário (nome, preferências,
            pessoas, projetos, rotinas).

            Args:
                fato: o fato a memorizar, em uma frase curta.
            """
            self._memory.add_fact(user_id, fato, embedding=self._embed(fato))
            return "ok, memorizado"

        def modo_serio(ativar: bool = True) -> str:
            """Ativa ou desativa o MODO FOCO da E.V.: a interface inteira entra
            em alerta (azul -> vermelho) e o tom das respostas fica direto,
            tático e sem piadas. Use quando o usuário pedir 'modo foco', 'fica
            séria', 'modo de combate', 'modo foco total', ou para desligar:
            'volta ao normal', 'desativa o modo foco', 'relaxa'.

            Args:
                ativar: true para ligar, false para voltar ao normal.
            """
            self._memory.set_setting("serious_mode", "1" if ativar else "0")
            return ("Modo foco ativado. Interface em alerta, foco total."
                    if ativar else
                    "Modo foco desativado. De volta ao normal.")

        def criar_lembrete(texto: str, quando: str = "") -> str:
            """Cria um lembrete para o usuário.

            Args:
                texto: o que lembrar.
                quando: data/hora em ISO 8601 (ex: 2026-07-22T09:00:00-03:00).
            """
            rid = self._memory.add_reminder(user_id, texto, quando or None)
            return f"lembrete #{rid} criado"

        def listar_lembretes() -> str:
            """Lista os lembretes em aberto do usuário."""
            items = self._memory.open_reminders(user_id)
            if not items:
                return "nenhum lembrete em aberto"
            return "; ".join(
                f"#{r['id']} {r['text']}"
                + (f" ({r['when_iso']})" if r["when_iso"] else "")
                for r in items
            )

        def listar_memorias() -> str:
            """Lista as memórias/fatos salvos sobre o usuário, com seus IDs.
            Use ANTES de apagar, para descobrir o ID certo."""
            items = self._memory.list_facts(user_id)
            if not items:
                return "não há memórias salvas"
            return "; ".join(f"#{f['id']}: {f['fact']}" for f in items)

        def apagar_memoria(id: int) -> str:
            """Apaga UMA memória/fato do usuário pelo ID. Se o usuário descrever
            a memória em vez do número, chame listar_memorias primeiro para achar o ID.

            Args:
                id: o número (ID) da memória a apagar.
            """
            facts = {f["id"]: f["fact"] for f in self._memory.list_facts(user_id)}
            if int(id) not in facts:
                return f"não encontrei a memória #{id}"
            self._memory.delete_fact(user_id, int(id))
            return f"apaguei a memória #{id}: {facts[int(id)]}"

        def apagar_lembrete(id: int) -> str:
            """Cancela/apaga um lembrete do usuário pelo ID (veja em listar_lembretes).

            Args:
                id: o número (ID) do lembrete a apagar.
            """
            ok = self._memory.cancel_reminder(user_id, int(id))
            return f"apaguei o lembrete #{id}" if ok else f"não encontrei o lembrete #{id}"

        def executar_comando(comando: str, argumentos: str = "") -> str:
            """Executa QUALQUER comando da E.V. em nome do usuário — use para fazer
            hands-free (por voz ou texto) o que ele normalmente faria manualmente:
            criar/listar/concluir tarefas, gastos, orçamentos, hábitos, diário,
            links, assinaturas, monitores web, agenda/eventos/e-mail, buscar, etc.
            Também apaga itens (ex: comando 'esquecer', 'gastorm', 'cancelar').

            Comandos disponíveis: tarefa, tarefas, concluir, lembrete, lembretes,
            rotina, cancelar, calendario, lembrar, memorias, esquecer, gasto, gastos,
            gastorm, orcamento, orcamentos, orcamentorm, relatorio, habito, feito,
            habitos, habitorm, diario, diariorm, link, links, linkrm, procurar,
            buscar, noticias, clima, kb, kbrm, kbweb, semana, vigiar, vigias,
            vigiarm, assinatura, assinaturas, assinaturarm, agenda, evento, email,
            emails (ler/resumir e-mails recentes da caixa; sem argumento traz os
            não lidos; com um termo faz busca simples, ex: 'faturas'),
            foco, silenciar, exportar, status, resumir, limparchat, dados, limpar,
            quiz, insights, modelo, documento, transcrever, ajuda, menu.

            Args:
                comando: o nome do comando (ex: 'gasto', 'tarefa', 'foco', 'status').
                argumentos: os argumentos no mesmo formato do comando
                    (ex: '50 mercado #casa' para gasto; 'estudar #faculdade' para tarefa).
            """
            # The model sometimes stuffs the args into `comando`
            # (e.g. comando="tarefa comprar pão", argumentos=""). Split so the
            # command name is just the first token and the rest becomes args.
            raw = (comando or "").strip().lstrip("/")
            tokens = raw.split(None, 1)
            key = (tokens[0] if tokens else "").lower()
            argumentos = (argumentos or "").strip()
            if len(tokens) > 1 and not argumentos:
                argumentos = tokens[1]
            log.info("[executar_comando] comando=%r -> key=%r args=%r",
                     comando, key, argumentos)
            if key in self._commands.runnable():
                out = self._commands.run(user_id, key, argumentos)  # runs now (text)
                log.info("[executar_comando] %s -> %s", key, str(out)[:160])
                return out
            if key in _INTERFACE_COMMANDS:
                # Needs the chat context — queue it for the interface to run.
                self._last_actions.append({"command": key, "args": argumentos})
                return f"ok, executando '{key}' agora"
            out = self._commands.run(user_id, key, argumentos)  # -> "não conheço"
            log.info("[executar_comando] unknown %r -> %s", key, str(out)[:120])
            return out

        def consultar_clima(cidade: str) -> str:
            """Consulta a previsão do tempo real (hoje e próximos dias) de uma cidade.

            Args:
                cidade: nome da cidade (ex: São Paulo).
            """
            return tools_mod.weather_forecast(cidade or cfg.city or "São Paulo", lang=lang)

        def consultar_noticias(assunto: str) -> str:
            """Busca as notícias mais recentes (últimos dias) sobre um assunto.
            Use isto sempre que perguntarem sobre notícias/atualidades.

            Args:
                assunto: tema das notícias (ex: tecnologia, Brasil, futebol).
            """
            return tools_mod.news(assunto or cfg.news_topic or "Brasil", tavily_key=cfg.tavily_api_key, lang=lang)

        def criar_documento(
            conteudo: str,
            titulo: str = "",
            formato: str = "pdf",
            salvar_kb: bool = False,
        ) -> str:
            """Cria um arquivo (txt, md, pdf ou docx/word) com o conteúdo e o
            ENVIA para o usuário no chat. Use quando pedirem algo "em pdf",
            "em word", "num arquivo", "um documento", ou para exportar um texto.

            Args:
                conteudo: o texto completo do documento (já escrito por você).
                titulo: título/nome do documento (ex: "Lista de compras").
                formato: txt, md, pdf ou docx (padrão pdf; "word" vira docx).
                salvar_kb: se True, também guarda o conteúdo na base de conhecimento.
            """
            title = (titulo or "Documento").strip()
            try:
                data, filename = documents_mod.build(formato, title, conteudo)
            except ValueError as exc:
                return str(exc)
            saved_kb = False
            if salvar_kb and (conteudo or "").strip():
                try:
                    knowledge.ingest_text(conteudo, title, cfg, self._memory, user_id)
                    saved_kb = True
                except Exception as exc:  # KB is a bonus — never fail the doc
                    log.warning("criar_documento KB ingest failed (%s)", exc)
            self._last_documents.append({
                "bytes": data, "filename": filename,
                "title": title, "content": conteudo, "saved_kb": saved_kb,
            })
            extra = " e guardei na base de conhecimento" if saved_kb else ""
            return f"documento '{filename}' criado{extra}; será enviado ao usuário agora"

        def anotar_pessoa(nome: str, sobre: str = "", aniversario: str = "") -> str:
            """Registra/atualiza uma pessoa importante do usuário (família, amigo,
            colega): quem é, contexto e aniversário. Use quando ele falar de alguém
            que vale lembrar.

            Args:
                nome: nome da pessoa.
                sobre: nota curta (relação, contexto, preferências).
                aniversario: data de aniversário, ex '12/03' ou '1998-03-12'.
            """
            self._memory.add_person(user_id, nome, sobre, aniversario)
            return f"anotado sobre {nome}"

        def sobre_pessoa(nome: str) -> str:
            """Recupera o que o usuário já registrou sobre uma pessoa, pelo nome.

            Args:
                nome: nome (ou parte) da pessoa.
            """
            p = self._memory.find_person(user_id, nome)
            if not p:
                return f"não tenho nada registrado sobre {nome} ainda"
            parts = [p["name"]]
            if p.get("notes"):
                parts.append(p["notes"])
            if p.get("birthday"):
                parts.append("aniversário: " + p["birthday"])
            return " — ".join(parts)

        def minha_localizacao() -> str:
            """Retorna a última localização conhecida do usuário (do dispositivo, via
            o app web). Use quando ele perguntar 'onde eu estou' ou precisar do
            contexto de local."""
            lat = self._memory.get_setting("loc_lat")
            lng = self._memory.get_setting("loc_lng")
            if not (lat and lng):
                return ("ainda não sei sua localização. Abra a aba Mapa na E.V. e "
                        "toque em 'Onde estou' pra eu passar a saber.")
            addr = self._memory.get_setting("loc_addr") or ""
            link = f"https://www.google.com/maps/@{lat},{lng},16z"
            head = f"você está em {addr} " if addr else ""
            return f"{head}({lat}, {lng}). Ver no mapa: {link}"

        def locais_proximos(tipo: str) -> str:
            """Lista lugares reais de um tipo perto da localização atual do usuário
            (nome + distância), buscando no OpenStreetMap.

            Args:
                tipo: o que procurar, ex 'farmácia', 'mercado', 'restaurante'.
            """
            lat = self._memory.get_setting("loc_lat")
            lng = self._memory.get_setting("loc_lng")
            if not (lat and lng):
                return ("não sei sua localização ainda. Abra a aba Mapa e toque em "
                        "'Onde estou'.")
            flat, flng = float(lat), float(lng)
            places = tools_mod.nearby_places(flat, flng, tipo, limit=6)
            if not places:
                return f"não achei '{tipo}' por perto agora."
            # A map photo of the area with every result pinned, plus a route link
            # per place so the user can navigate straight there.
            img = tools_mod.static_map_url(
                flat, flng, markers=[(p["lat"], p["lng"]) for p in places], zoom=15)
            lines = [f"{tipo.capitalize()} perto de você:", f"![mapa]({img})"]
            for i, p in enumerate(places, 1):
                dl = tools_mod.directions_link(flat, flng, p["lat"], p["lng"])
                lines.append(f"{i}. {p['name']} (~{int(p['dist'])} m) — 🧭 Ir: {dl}")
            return "\n".join(lines)

        def meus_locais() -> str:
            """Lista os pontos de interesse que o usuário salvou no mapa da E.V."""
            places = self._memory.list_places(user_id)
            if not places:
                return "você ainda não salvou nenhum ponto no mapa."
            return "Seus pontos salvos: " + ", ".join(p["name"] for p in places)

        def salvar_local(nome: str, endereco: str = "") -> str:
            """Salva um ponto de interesse no mapa do usuário (ex: Faculdade, Casa).
            Se um endereço for dado, geocodifica; senão usa a localização atual.

            Args:
                nome: apelido do ponto (ex: 'Faculdade').
                endereco: endereço/local a geocodificar (opcional).
            """
            if endereco.strip():
                g = tools_mod.geocode(endereco)
                if not g:
                    return f"não achei o endereço '{endereco}'. Pode detalhar mais?"
                lat, lng = g["lat"], g["lng"]
            else:
                slat = self._memory.get_setting("loc_lat")
                slng = self._memory.get_setting("loc_lng")
                if not (slat and slng):
                    return ("me diz o endereço, ou abra o Mapa e toque em 'Onde estou' "
                            "pra eu salvar na sua posição atual.")
                lat, lng = float(slat), float(slng)
            self._memory.add_place(user_id, nome, lat, lng)
            return f"ponto '{nome}' salvo no seu mapa."

        def criar_automacao(gatilho: str, acao: str, hora: int = -1, minuto: int = 0,
                            dia_semana: int = -1, valor: float = 0.0, categoria: str = "",
                            mensagem: str = "", comando: str = "", playlist: str = "",
                            musica: str = "") -> str:
            """Cria uma automação 'quando X, faça Y' que roda sozinha depois.

            Args:
                gatilho: 'time' (horário recorrente), 'expense_over' (gasto acima de
                    um valor) ou 'task_overdue' (quando uma tarefa vencer).
                acao: 'notify' (avisar), 'command' (rodar um comando), 'reschedule'
                    (remarcar tarefas vencidas; só com task_overdue) ou 'play' (tocar
                    música no Spotify).
                hora: para 'time', hora 0-23.
                minuto: para 'time', minuto 0-59.
                dia_semana: para 'time', 0=segunda..6=domingo, ou -1 para todo dia.
                valor: para 'expense_over', o limite em reais.
                categoria: para 'expense_over', categoria opcional (ex 'comida').
                mensagem: para 'notify', o texto do aviso.
                comando: para 'command', o comando a rodar (ex 'semana', 'relatorio').
                playlist: para 'play', o nome da playlist a tocar.
                musica: para 'play', uma faixa/artista a tocar (se não for playlist).

            Ex: 'toda sexta 18h me manda o resumo' -> gatilho='time', hora=18,
            dia_semana=4, acao='command', comando='semana'. 'toda manhã 8h toca minha
            playlist Foco' -> gatilho='time', hora=8, acao='play', playlist='Foco'.
            """
            aid, msg = self._commands.create_automation(
                user_id, gatilho, acao,
                hour=(None if hora < 0 else hora), minute=minuto, weekday=dia_semana,
                amount=(None if valor <= 0 else valor), category=(categoria or None),
                message=(mensagem or None), command=(comando or None),
                playlist=(playlist or None), musica=(musica or None))
            return ("automação criada: " + msg) if aid else ("não consegui criar: " + msg)

        def tocar_playlist(nome: str) -> str:
            """Toca uma playlist do Spotify do usuário (por nome) no dispositivo
            ativo dele. Requer Spotify conectado e Premium.

            Args:
                nome: nome (ou parte) da playlist.
            """
            from ...providers import spotify as _sp
            tok = _sp.access_token(self._memory, self._config)
            if not tok:
                return "o Spotify não está conectado — conecte na aba Música."
            uri = _sp.find_playlist(tok, nome)
            if not uri:
                return f"não achei uma playlist chamada '{nome}' no seu Spotify."
            r = _sp.api("PUT", "/me/player/play", tok, json={"context_uri": uri})
            if r.status_code == 404:
                return ("não há um dispositivo ativo. Abre o Spotify (ou o player da "
                        "E.V. na aba Música) e tenta de novo.")
            return (f"tocando a playlist '{nome}'." if r.status_code in (200, 202, 204)
                    else "não consegui tocar agora.")

        def tocar_musica(busca: str) -> str:
            """Busca e toca QUALQUER música no Spotify (por nome de faixa/artista).
            Use para 'toca Bohemian Rhapsody', 'bota um som do Djavan'.

            Args:
                busca: o que tocar (faixa e/ou artista).
            """
            from ...providers import spotify as _sp
            tok = _sp.access_token(self._memory, self._config)
            if not tok:
                return "o Spotify não está conectado — conecte na aba Música."
            uri = _sp.first_track_uri(tok, busca)
            if not uri:
                return f"não achei '{busca}' no Spotify."
            r = _sp.api("PUT", "/me/player/play", tok, json={"uris": [uri]})
            if r.status_code == 404:
                return "não há dispositivo ativo. Abre o Spotify ou o player da E.V. e tenta de novo."
            return (f"tocando '{busca}'." if r.status_code in (200, 202, 204)
                    else "não consegui tocar agora.")

        def controlar_musica(acao: str) -> str:
            """Controla o playback do Spotify: pausar, continuar, próxima, anterior.

            Args:
                acao: 'pausar', 'continuar', 'proxima' ou 'anterior'.
            """
            from ...providers import spotify as _sp
            tok = _sp.access_token(self._memory, self._config)
            if not tok:
                return "o Spotify não está conectado."
            a = (acao or "").lower()
            m = {"pausar": ("PUT", "/me/player/pause"), "continuar": ("PUT", "/me/player/play"),
                 "tocar": ("PUT", "/me/player/play"), "proxima": ("POST", "/me/player/next"),
                 "próxima": ("POST", "/me/player/next"), "anterior": ("POST", "/me/player/previous")}
            if a not in m:
                return "diz: pausar, continuar, próxima ou anterior."
            method, path = m[a]
            r = _sp.api(method, path, tok)
            return "feito." if r.status_code in (200, 202, 204) else "não consegui agora (tem algo tocando?)."

        def musica_atual() -> str:
            """O que está tocando agora no Spotify do usuário."""
            from ...providers import spotify as _sp
            tok = _sp.access_token(self._memory, self._config)
            if not tok:
                return "o Spotify não está conectado."
            cur = _sp.current_track(tok)
            return f"tocando agora: {cur}." if cur else "nada tocando no momento."

        def criar_pagina(nome: str, tarefas_categoria: str = "", nota: str = "",
                        conector: str = "", grafico: bool = False, comando: str = "") -> str:
            """Cria uma página/painel personalizado na interface do usuário, montada
            com widgets seguros. Use para 'cria uma página X com ...'.

            Args:
                nome: nome da página (ex 'Faculdade').
                tarefas_categoria: mostra tarefas dessa categoria ('todas' pra todas).
                nota: um texto/nota fixa no painel.
                conector: nome de um conector pra mostrar o valor.
                grafico: True mostra um gráfico de gastos por categoria.
                comando: um comando da E.V. pra virar botão (ex 'semana').
            """
            widgets = []
            if nota.strip():
                widgets.append({"type": "note", "text": nota.strip()})
            if tarefas_categoria.strip():
                cat = tarefas_categoria.strip()
                widgets.append({"type": "tasks",
                                "category": "" if cat.lower() in ("todas", "all", "*") else cat})
            if grafico:
                widgets.append({"type": "chart"})
            if conector.strip():
                widgets.append({"type": "connector", "name": conector.strip()})
            if comando.strip():
                widgets.append({"type": "command", "cmd": comando.strip(), "label": comando.strip()})
            if not widgets:
                return "me diga o que colocar na página (tarefas, nota, gráfico ou um conector)."
            self._memory.add_page(user_id, nome.strip()[:60] or "Página", widgets)
            return (f"pronto — criei a página '{nome.strip()}' com {len(widgets)} "
                    f"widget(s). Ela aparece em 'Páginas' no painel.")

        def consultar_conector(nome: str) -> str:
            """Consulta um conector de API que o usuário criou (pelo nome) e retorna
            o valor atual. Use quando ele perguntar algo que um conector dele cobre
            (ex 'qual a cotação do dólar?' se ele tiver um conector de cotação).

            Args:
                nome: o nome do conector configurado.
            """
            import os as _os
            import re as _re
            import json as _json
            from ...providers import connectors as _cn
            c = self._memory.get_connector(user_id, nome)
            if not c:
                av = [x["name"] for x in self._memory.list_connectors(user_id)]
                return (f"não achei o conector '{nome}'."
                        + (f" Você tem: {', '.join(av)}." if av else
                           " Você ainda não criou conectores (aba Conectores)."))
            def sub(s):
                return _re.sub(r"\{\{\s*([A-Z][A-Z0-9_]{1,39})\s*\}\}",
                               lambda m: _os.environ.get(m.group(1), ""), s or "")
            val, err = _cn.fetch(sub(c["url"]),
                                 {k: sub(v) for k, v in (c["headers"] or {}).items()},
                                 c["path"])
            if err:
                return f"não consegui consultar '{c['name']}': {err}"
            if isinstance(val, (dict, list)):
                val = _json.dumps(val, ensure_ascii=False)[:600]
            return f"{c['name']}: {str(val)[:600]}"

        def planejar_dia() -> str:
            """Monta um plano acionável para o dia do usuário, juntando as tarefas
            abertas, os lembretes, a agenda, o clima e a localização atual, e
            priorizando tudo. Use quando ele pedir 'resolve minha manhã', 'plano do
            dia', 'organiza meu dia', 'o que eu faço hoje'."""
            return self._plan_day_sync(user_id)

        def solicitar_tarefa_local(tipo: str, descricao: str, comando: str = "") -> str:
            """Pede para EXECUTAR algo no computador pessoal do usuário (não no
            servidor da E.V.): rodar um script já cadastrado por ele, abrir um
            app/arquivo, navegar/pesquisar/agir de forma autônoma dentro de um
            navegador de verdade (com sessão de login persistente), ou rodar um
            comando de shell. NUNCA executa nada sozinha — isso só cria um pedido
            pendente que o usuário precisa aprovar manualmente (no console web,
            com fallback pelo Telegram). Use quando ele pedir explicitamente para
            'rodar no meu pc', 'abrir X no computador', 'pesquisa isso no
            navegador pra mim', 'executa esse script pra mim'.

            Se o objetivo envolver WhatsApp Web ou Instagram (ex: responder
            mensagem, enviar DM, postar), a tarefa é marcada como alto risco: além
            desta aprovação, o executor local vai pedir uma SEGUNDA confirmação
            explícita bem antes de clicar em enviar/postar — nunca manda nada
            sozinho, e automatizar essas plataformas pode violar os termos de uso
            delas (risco real de banimento da conta), então avise o usuário disso
            se ele pedir algo do tipo.

            Args:
                tipo: 'script' (um script já cadastrado por nome), 'open' (abrir
                    app/arquivo/pasta), 'browser' (agente autônomo de navegador —
                    descreva o objetivo em linguagem natural, ex: "pesquisar X no
                    Google e resumir os 3 melhores resultados" ou "abrir o
                    WhatsApp Web e responder Fulano com ...") ou 'shell' (comando
                    livre — maior risco, sempre aprovado à mão).
                descricao: frase curta explicando o que a tarefa faz, mostrada ao
                    usuário na hora de aprovar (ex: "abrir o VS Code no projeto X").
                comando: para 'browser', o objetivo em linguagem natural (o
                    executor local decide sozinho os passos de navegação); para os
                    demais tipos, o script/comando/caminho em si.
            """
            kind = (tipo or "").strip().lower()
            if kind not in ("script", "open", "browser", "shell"):
                return "tipo inválido — use script, open, browser ou shell"
            payload = {"command": comando or ""}
            risk = self._memory.classify_local_task_risk(kind, comando or "")
            tid = self._memory.add_local_task(
                user_id, kind, (descricao or comando or "tarefa local")[:200],
                payload, risk=risk,
            )
            aviso = (
                " — como envolve WhatsApp/Instagram, vou pedir uma segunda "
                "confirmação sua bem antes de clicar em enviar/postar qualquer coisa"
                if risk == "high" else ""
            )
            return (f"pedido #{tid} criado — preciso que você aprove pelo console "
                    f"da E.V. (ou pelo Telegram) antes de rodar isso no seu computador"
                    f"{aviso}")

        callables: dict = {
            "modo_serio": modo_serio,
            "executar_comando": executar_comando,
            "planejar_dia": planejar_dia,
            "solicitar_tarefa_local": solicitar_tarefa_local,
            "criar_automacao": criar_automacao,
            "consultar_conector": consultar_conector,
            "criar_pagina": criar_pagina,
            "tocar_playlist": tocar_playlist,
            "tocar_musica": tocar_musica,
            "controlar_musica": controlar_musica,
            "musica_atual": musica_atual,
            "anotar_pessoa": anotar_pessoa,
            "sobre_pessoa": sobre_pessoa,
            "minha_localizacao": minha_localizacao,
            "locais_proximos": locais_proximos,
            "meus_locais": meus_locais,
            "salvar_local": salvar_local,
            "salvar_memoria": salvar_memoria,
            "listar_memorias": listar_memorias,
            "apagar_memoria": apagar_memoria,
            "criar_lembrete": criar_lembrete,
            "listar_lembretes": listar_lembretes,
            "apagar_lembrete": apagar_lembrete,
            "consultar_clima": consultar_clima,
            "consultar_noticias": consultar_noticias,
            "criar_documento": criar_documento,
        }

        if cfg.websearch_enabled:
            def buscar_web(consulta: str) -> str:
                """Busca informação atual na internet.

                Args:
                    consulta: o que pesquisar.
                """
                return tools_mod.web_search(
                    consulta,
                    brave_key=self._config.brave_api_key,
                    tavily_key=self._config.tavily_api_key,
                    lang=lang,
                )

            callables["buscar_web"] = buscar_web

        if cfg.google_oauth_client:
            def ver_agenda() -> str:
                """Lista os próximos eventos da agenda do Google do usuário."""
                return tools_mod.calendar_upcoming(cfg, cfg.default_account, lang=lang)

            def criar_evento(titulo: str, inicio: str, fim: str) -> str:
                """Cria um evento na agenda do Google.

                Args:
                    titulo: título do evento.
                    inicio: início em ISO 8601.
                    fim: fim em ISO 8601.
                """
                return tools_mod.calendar_create(
                    cfg, cfg.default_account, titulo, inicio, fim, lang=lang)

            def enviar_email(para: str, assunto: str, corpo: str) -> str:
                """Envia um e-mail pela conta Gmail do usuário.

                Args:
                    para: endereço de e-mail do destinatário.
                    assunto: assunto do e-mail.
                    corpo: corpo do e-mail.
                """
                return tools_mod.send_email(
                    cfg, cfg.default_account, para, assunto, corpo, lang=lang)

            callables["ver_agenda"] = ver_agenda
            callables["criar_evento"] = criar_evento
            callables["enviar_email"] = enviar_email

        return callables

    def _openai_tools(self) -> list[dict]:
        """OpenAI-format schemas mirroring the enabled tools (for Groq)."""
        cfg = self._config

        def fn(name, desc, props=None, required=None):
            return {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": props or {},
                        "required": required or [],
                    },
                },
            }

        s = "string"
        schemas = [
            fn(
                "modo_serio",
                "Ativa/desativa o modo foco da E.V. (interface azul->vermelha "
                "em alerta + tom direto e tático). Use para 'modo foco', 'fica "
                "séria', 'modo de combate', ou desligar: 'volta ao normal'.",
                {"ativar": {"type": "boolean",
                            "description": "true para ligar, false para desligar"}},
                [],
            ),
            fn(
                "planejar_dia",
                "Monta um plano acionável do dia do usuário juntando tarefas, "
                "lembretes, agenda, clima e localização. Use para 'resolve minha "
                "manhã', 'plano do dia', 'organiza meu dia', 'o que faço hoje'.",
            ),
            fn(
                "solicitar_tarefa_local",
                "Pede para executar algo no computador pessoal do usuário (script "
                "cadastrado, abrir app/arquivo, agente autônomo de navegador de "
                "verdade, ou shell livre). NUNCA executa sozinha — cria um pedido "
                "pendente que o usuário precisa aprovar manualmente (console web, "
                "fallback Telegram). Tarefas de navegador envolvendo WhatsApp/"
                "Instagram pedem uma SEGUNDA confirmação antes de enviar/postar "
                "qualquer coisa. Use para 'roda isso no meu pc', 'abre X no "
                "computador', 'pesquisa isso no navegador pra mim'.",
                {
                    "tipo": {"type": s, "description":
                             "script, open, browser ou shell"},
                    "descricao": {"type": s, "description":
                                  "frase curta do que a tarefa faz"},
                    "comando": {"type": s, "description":
                                "para 'browser', o objetivo em linguagem natural; "
                                "para os demais, o script/comando/caminho em si"},
                },
                ["tipo", "descricao"],
            ),
            fn(
                "tocar_playlist",
                "Toca uma playlist do Spotify do usuário (por nome). Requer Spotify "
                "conectado + Premium. Use para 'toca minha playlist X', 'bota um som'.",
                {"nome": {"type": s, "description": "nome/parte da playlist"}},
                ["nome"],
            ),
            fn(
                "tocar_musica",
                "Busca e toca QUALQUER música no Spotify por nome (faixa/artista). "
                "Use para 'toca Bohemian Rhapsody', 'bota um som do X'. Requer "
                "Spotify conectado + Premium.",
                {"busca": {"type": s, "description": "faixa e/ou artista"}},
                ["busca"],
            ),
            fn(
                "controlar_musica",
                "Controla o Spotify: pausar, continuar, próxima, anterior.",
                {"acao": {"type": s, "description": "pausar|continuar|proxima|anterior"}},
                ["acao"],
            ),
            fn("musica_atual", "O que está tocando agora no Spotify do usuário."),
            fn(
                "criar_pagina",
                "Cria uma página/painel personalizado na interface, com widgets "
                "seguros (tarefas, nota, gráfico de gastos, conector, botão). Use "
                "para 'cria uma página X com minhas tarefas de Y e um gráfico'.",
                {
                    "nome": {"type": s, "description": "nome da página"},
                    "tarefas_categoria": {"type": s, "description": "categoria de tarefas ('todas' p/ todas)"},
                    "nota": {"type": s, "description": "texto fixo no painel"},
                    "conector": {"type": s, "description": "nome de um conector"},
                    "grafico": {"type": "boolean", "description": "mostrar gráfico de gastos"},
                    "comando": {"type": s, "description": "comando pra virar botão"},
                },
                ["nome"],
            ),
            fn(
                "consultar_conector",
                "Consulta um conector de API que o usuário criou (pelo nome) e "
                "retorna o valor atual. Use quando a pergunta dele bate com um "
                "conector configurado.",
                {"nome": {"type": s, "description": "nome do conector"}},
                ["nome"],
            ),
            fn(
                "criar_automacao",
                "Cria uma automação 'quando X, faça Y' que roda sozinha. gatilho: "
                "'time'|'expense_over'|'task_overdue'. acao: 'notify'|'command'|"
                "'reschedule'. Use para 'toda sexta 18h me manda o resumo', 'quando "
                "eu gastar mais de 200 me avisa', 'se uma tarefa vencer, remarca'.",
                {
                    "gatilho": {"type": s, "description": "time|expense_over|task_overdue"},
                    "acao": {"type": s, "description": "notify|command|reschedule"},
                    "hora": {"type": "integer", "description": "para time: 0-23"},
                    "minuto": {"type": "integer", "description": "para time: 0-59"},
                    "dia_semana": {"type": "integer", "description": "0=seg..6=dom, -1=todo dia"},
                    "valor": {"type": "number", "description": "para expense_over: limite em R$"},
                    "categoria": {"type": s, "description": "para expense_over: categoria opcional"},
                    "mensagem": {"type": s, "description": "para notify: texto do aviso"},
                    "comando": {"type": s, "description": "para command: ex 'semana'"},
                    "playlist": {"type": s, "description": "para play: nome da playlist"},
                    "musica": {"type": s, "description": "para play: faixa/artista"},
                },
                ["gatilho", "acao"],
            ),
            fn(
                "executar_comando",
                "Executa QUALQUER comando da E.V. em nome do usuário (hands-free por "
                "voz/texto). CRIAR/EDITAR/APAGAR/CONCLUIR sempre passa por aqui — nunca "
                "afirme que fez sem chamar esta ferramenta. Tarefas: 'tarefa' (criar, ex "
                "args 'comprar leite #mercado'), 'tarefas' (listar), 'concluir' (por id "
                "OU nome, ex 'comprar leite'), 'tarefarm' (apagar por id/nome), "
                "'tarefaeditar' (args '<nome/id> | <novo texto> [#cat]'). Também: lembrete, "
                "lembretes, rotina, cancelar, calendario, lembrar, memorias, esquecer, "
                "gasto, gastos, gastorm (apaga gasto por id OU descrição), gastoeditar "
                "(edita gasto por nome: '<nome/id> | <valor> [descrição] [#cat]'), orcamento, "
                "orcamentos, orcamentorm, relatorio, habito, feito (por nome), habitos, "
                "habitorm (por nome), diario, diariorm, link, links, linkrm (por id OU nome), "
                "cancelar (lembrete por id OU texto), lembreteeditar (edita lembrete por nome: "
                "'<nome/id> | <novo texto> [| <novo tempo>]'), esquecer (memória por id OU conteúdo), "
                "procurar, buscar, noticias, clima, kb, kbrm, kbweb, semana, vigiar, vigias, "
                "vigiarm, assinatura, assinaturas, assinaturarm, agenda, evento, email.",
                {
                    "comando": {"type": s, "description": "nome do comando, ex: 'gasto'"},
                    "argumentos": {"type": s, "description": "argumentos no formato do comando"},
                },
                ["comando"],
            ),
            fn(
                "salvar_memoria",
                "Guarda um fato duradouro sobre o usuário.",
                {"fato": {"type": s, "description": "o fato, em uma frase curta"}},
                ["fato"],
            ),
            fn(
                "anotar_pessoa",
                "Registra/atualiza uma pessoa importante (família, amigo, colega): "
                "quem é, contexto e aniversário.",
                {
                    "nome": {"type": s, "description": "nome da pessoa"},
                    "sobre": {"type": s, "description": "nota curta (relação/contexto)"},
                    "aniversario": {"type": s, "description": "ex '12/03' ou '1998-03-12'"},
                },
                ["nome"],
            ),
            fn(
                "sobre_pessoa",
                "Recupera o que o usuário registrou sobre uma pessoa, pelo nome.",
                {"nome": {"type": s, "description": "nome (ou parte) da pessoa"}},
                ["nome"],
            ),
            fn(
                "minha_localizacao",
                "Última localização conhecida do usuário (do dispositivo). Use para "
                "'onde estou' ou contexto de local.",
            ),
            fn(
                "locais_proximos",
                "Lista lugares reais (nome + distância) de um tipo perto do usuário.",
                {"tipo": {"type": s, "description": "ex: farmácia, mercado, restaurante"}},
                ["tipo"],
            ),
            fn("meus_locais", "Lista os pontos de interesse que o usuário salvou no mapa."),
            fn(
                "salvar_local",
                "Salva um ponto no mapa do usuário (ex: Faculdade). Com endereço, "
                "geocodifica; sem, usa a localização atual.",
                {"nome": {"type": s, "description": "apelido, ex 'Faculdade'"},
                 "endereco": {"type": s, "description": "endereço a geocodificar (opcional)"}},
                ["nome"],
            ),
            fn(
                "criar_lembrete",
                "Cria um lembrete para o usuário.",
                {
                    "texto": {"type": s, "description": "o que lembrar"},
                    "quando": {"type": s, "description": "data/hora em ISO 8601"},
                },
                ["texto"],
            ),
            fn(
                "listar_memorias",
                "Lista as memórias/fatos salvos sobre o usuário, com IDs. "
                "Use antes de apagar para achar o ID certo.",
            ),
            fn(
                "apagar_memoria",
                "Apaga UMA memória/fato do usuário pelo ID.",
                {"id": {"type": "integer", "description": "ID da memória (de listar_memorias)"}},
                ["id"],
            ),
            fn("listar_lembretes", "Lista os lembretes em aberto do usuário."),
            fn(
                "apagar_lembrete",
                "Cancela/apaga um lembrete do usuário pelo ID.",
                {"id": {"type": "integer", "description": "ID do lembrete (de listar_lembretes)"}},
                ["id"],
            ),
            fn(
                "consultar_clima",
                "Consulta a previsão do tempo real (hoje/próximos dias) de uma cidade.",
                {"cidade": {"type": s, "description": "nome da cidade"}},
                ["cidade"],
            ),
            fn(
                "consultar_noticias",
                "Busca notícias recentes (últimos dias) sobre um assunto.",
                {"assunto": {"type": s, "description": "tema das notícias"}},
                ["assunto"],
            ),
            fn(
                "criar_documento",
                "Cria um arquivo (txt, md, pdf ou docx/word) com o conteúdo e o "
                "envia ao usuário. Use quando pedirem algo 'em pdf', 'em word', "
                "'num arquivo' ou 'um documento'.",
                {
                    "conteudo": {"type": s, "description": "o texto completo do documento"},
                    "titulo": {"type": s, "description": "título/nome do documento"},
                    "formato": {"type": s, "description": "txt, md, pdf ou docx (padrão pdf)"},
                    "salvar_kb": {"type": "boolean", "description": "também guardar na base de conhecimento"},
                },
                ["conteudo"],
            ),
        ]
        if cfg.websearch_enabled:
            schemas.append(
                fn(
                    "buscar_web",
                    "Busca informação atual na internet.",
                    {"consulta": {"type": s, "description": "o que pesquisar"}},
                    ["consulta"],
                )
            )
        if cfg.google_oauth_client:
            schemas += [
                fn("ver_agenda", "Lista os próximos eventos da agenda do Google."),
                fn(
                    "criar_evento",
                    "Cria um evento na agenda do Google.",
                    {
                        "titulo": {"type": s},
                        "inicio": {"type": s, "description": "início em ISO 8601"},
                        "fim": {"type": s, "description": "fim em ISO 8601"},
                    },
                    ["titulo", "inicio", "fim"],
                ),
                fn(
                    "enviar_email",
                    "Envia um e-mail pela conta Gmail do usuário.",
                    {
                        "para": {"type": s},
                        "assunto": {"type": s},
                        "corpo": {"type": s},
                    },
                    ["para", "assunto", "corpo"],
                ),
            ]
        return schemas
