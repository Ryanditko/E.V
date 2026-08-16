# E.V. in Telegram groups

You can run E.V. in several topic groups (Faculdade, Finanças, Estudos, Jogos,
Pessoal...) to keep things decentralized from the main private chat. Each group
keeps its **own conversation thread**, while your data (memories, tasks, reminders,
expenses...) stays **shared** — she knows who you are everywhere.

## Setup (one time per group)

1. Create the group in Telegram (e.g. "E.V. — Finanças").
2. Add your bot to the group (group → Add members → search your bot's @username).
3. That's it. **No BotFather change needed** — privacy mode stays ON, so E.V. only
   sees messages that call her (mentions, replies, commands). She does **not** read
   everything in the group.

> If you ever want her to read/respond to every message in a group, you'd disable
> privacy mode in BotFather (`/setprivacy` → Disable). Not recommended — noisy and
> she'd read all group content.

## How to call her in a group

She answers only when explicitly called:

- **Mention:** `@your_bot qual a fórmula de bhaskara?`
- **Reply:** reply to any message she sent and type your follow-up.
- **Command:** `/ev resume os pontos principais disso`

Plus every slash command works in groups too (`/gasto`, `/tarefa`, `/lembrete`,
`/foco`, `/status`, ...), addressed to the group.

## What's separate vs shared

| Separate per group | Shared across all chats |
|--------------------|--------------------------|
| Conversation thread / context | Your memories (facts about you) |
| (each group has its own history) | Tasks, reminders, expenses, budgets, habits, journal, links, knowledge base |

So a chat in **Finanças** won't carry over the context of **Faculdade**, but if you
say "anota um gasto" in any group, it lands in the same (shared) ledger.

## Access

Only **you** (the `EV_OWNER_ID`) are answered — even if other people are in the
group, E.V. ignores their messages. To change this, adjust `_authorized` in
`ev/interfaces/telegram_bot/routing.py`.

## Tip: one supergroup with Topics

Instead of many groups, Telegram supergroups support **Topics** (tabs like
Faculdade, Finanças...). Enable Topics in one group and E.V. lives in a single
place, organized by tab. Each topic is still the same chat id, so the conversation
context is shared within that supergroup (unlike separate groups).
