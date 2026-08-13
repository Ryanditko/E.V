"""/foco Pomodoro focus timer: start/stop/pause, live card rendering, and the
callback button handler that adjusts the running timer."""

from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

log = logging.getLogger("ev.telegram")


class PomodoroMixin:
    async def cmd_foco(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = self._args(c).strip().lower()
        # /foco parar (or cancelar/stop/fim) -> cancel a running timer.
        if arg in ("parar", "cancelar", "stop", "fim", "off"):
            if self._stop_pomodoro():
                await update.message.reply_text("⏹️ Timer parado.")
            else:
                await update.message.reply_text("Não há nenhum timer rodando agora.")
            return
        # /foco pausar | retomar -> toggle the running timer (also works by voice).
        if arg in ("pausar", "pausa", "pause", "retomar", "retoma", "resume",
                   "continuar", "continua"):
            if not self._pomo:
                await update.message.reply_text(
                    "Não há nenhum timer rodando pra pausar/retomar."
                )
                return
            self._pomo["paused"] = arg in ("pausar", "pausa", "pause")
            await self._render_pomo_card(update.get_bot())
            await update.message.reply_text(
                "⏸️ Foco pausado." if self._pomo["paused"] else "▶️ Foco retomado."
            )
            return
        tokens = self._args(c).split()
        focus, brk = 25, 5
        nums = [t for t in tokens if t.isdigit()]
        if len(nums) >= 1:
            focus = max(1, min(180, int(nums[0])))
        if len(nums) >= 2:
            brk = max(1, min(60, int(nums[1])))
        label = " ".join(t for t in tokens if not t.isdigit()).strip()
        chat_id = update.effective_chat.id
        bot = update.get_bot()
        # Only one live timer at a time — a new /foco replaces the running one.
        self._stop_pomodoro()
        self._bg_tasks = [t for t in self._bg_tasks if not t.done()]  # drop finished
        self._pomodoro_task = asyncio.create_task(
            self._pomodoro(bot, chat_id, focus, brk, label)
        )
        self._bg_tasks.append(self._pomodoro_task)

    def _stop_pomodoro(self) -> bool:
        """Cancel the running timer if any. Returns True if one was running."""
        running = bool(self._pomodoro_task and not self._pomodoro_task.done())
        if self._pomo is not None:
            self._pomo["cancelled"] = True
        if self._pomodoro_task:
            self._pomodoro_task.cancel()
        self._pomo = None
        return running

    async def _render_pomo_card(self, bot) -> None:
        """Re-draw the current timer card (used when pausing/resuming by voice)."""
        s = self._pomo
        if not s or not s.get("message_id"):
            return
        try:
            await bot.edit_message_text(
                chat_id=s["chat_id"], message_id=s["message_id"],
                text=self._focus_card(s["title"], s["remaining"], s["total"], s["paused"]),
                reply_markup=self._pomo_kb(s["paused"]),
            )
        except Exception:
            pass

    def _pomo_kb(self, paused: bool = False) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        toggle = (b("▶️ Retomar", callback_data="pomo:pause") if paused
                  else b("⏸️ Pausar", callback_data="pomo:pause"))
        return InlineKeyboardMarkup([
            [b("⏹️ Parar", callback_data="pomo:stop"), toggle],
            [b("➕5min", callback_data="pomo:add"), b("➖5min", callback_data="pomo:sub")],
        ])

    @staticmethod
    def _focus_card(title: str, remaining: int, total: int, paused: bool = False) -> str:
        """A live progress card: title + bar + mm:ss remaining (or paused)."""
        remaining = max(0, int(remaining))
        frac = 1.0 if total <= 0 else (total - remaining) / total
        frac = max(0.0, min(1.0, frac))  # clamp (remaining may exceed total after +5)
        blocks = max(0, min(10, int(round(frac * 10))))
        bar = "▰" * blocks + "▱" * (10 - blocks)
        m, s = divmod(remaining, 60)
        tail = f"⏸️ pausado — {m:02d}:{s:02d}" if paused else f"⏳ {m:02d}:{s:02d} restantes"
        return f"{title}\n{bar}  {int(frac * 100)}%\n{tail}"

    async def _run_phase(self, bot, chat_id: int, state: dict, interval: int = 10) -> None:
        """Count down `state['remaining']`, editing the card. Reads state live so
        buttons can extend/shrink/cancel mid-run."""
        while state["remaining"] > 0 and not state["cancelled"]:
            step = min(interval, state["remaining"])
            await asyncio.sleep(step)
            if state["cancelled"]:
                break
            if state["paused"]:
                continue  # frozen: don't decrement (handler renders the paused card)
            state["remaining"] -= step
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=state["message_id"],
                    text=self._focus_card(state["title"], state["remaining"], state["total"]),
                    reply_markup=self._pomo_kb(),
                )
            except Exception:
                pass  # ignore rate-limit / not-modified; keep counting

    async def _pomodoro(self, bot, chat_id: int, focus: int, brk: int, label: str) -> None:
        lbl = f" — {label}" if label else ""
        state = {
            "cancelled": False, "paused": False, "chat_id": chat_id,
            "remaining": focus * 60, "total": focus * 60,
            "title": f"🍅 Foco{lbl}", "phase": "focus", "message_id": None,
        }
        self._pomo = state
        try:
            card = await bot.send_message(
                chat_id, self._focus_card(state["title"], state["remaining"], state["total"]),
                reply_markup=self._pomo_kb(),
            )
            state["message_id"] = card.message_id
            await self._run_phase(bot, chat_id, state)
            if state["cancelled"]:
                return
            # focus done -> break
            await bot.edit_message_text(
                chat_id=chat_id, message_id=card.message_id,
                text=f"✅ Foco concluído{lbl}! Hora da pausa de {brk}min. "
                     "Levanta, respira, bebe água. 💧",
            )
            pause = await bot.send_message(
                chat_id, self._focus_card("☕ Pausa", brk * 60, brk * 60),
                reply_markup=self._pomo_kb(),
            )
            state.update(remaining=brk * 60, total=brk * 60, title="☕ Pausa",
                         phase="break", message_id=pause.message_id, paused=False)
            await self._run_phase(bot, chat_id, state)
            if state["cancelled"]:
                return
            await bot.edit_message_text(
                chat_id=chat_id, message_id=pause.message_id,
                text="▶️ Fim da pausa! Bora pro próximo ciclo? Manda /foco. 🍅",
            )
        except asyncio.CancelledError:
            pass  # replaced by a new /foco or stopped
        except Exception:
            log.exception("Pomodoro failed")
        finally:
            if self._pomo is state:
                self._pomo = None

    async def _handle_pomo(self, q, action: str) -> None:
        state = self._pomo
        if not state:
            await q.answer("Nenhum timer ativo agora.", show_alert=True)
            return
        if action == "stop":
            await q.answer("Timer parado.")
            self._stop_pomodoro()
            try:
                await q.edit_message_text("⏹️ Timer cancelado.")
            except Exception:
                pass
            return
        if action == "add":
            state["remaining"] += 300
            state["total"] = max(state["total"], state["remaining"])
            await q.answer("➕ 5 minutos")
        elif action == "sub":
            state["remaining"] = max(10, state["remaining"] - 300)
            await q.answer("➖ 5 minutos")
        elif action == "pause":
            state["paused"] = not state["paused"]
            await q.answer("⏸️ Pausado" if state["paused"] else "▶️ Retomado")
        try:
            await q.edit_message_text(
                self._focus_card(
                    state["title"], state["remaining"], state["total"], state["paused"]
                ),
                reply_markup=self._pomo_kb(state["paused"]),
            )
        except Exception:
            pass
