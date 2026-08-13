"""Health & routine tracking (water, sleep, mood). Named health_log to avoid
clashing with the top-level ev/core/health.py module."""

from __future__ import annotations


class HealthLogMixin:
    def health_day(self, user_id: str, day: str) -> dict:
        r = self._conn.execute(
            "SELECT water, sleep, mood FROM health WHERE user_id = ? AND day = ?",
            (user_id, day)).fetchone()
        return dict(r) if r else {"water": 0, "sleep": None, "mood": None}

    def health_set(self, user_id: str, day: str, field: str, value) -> None:
        if field not in ("water", "sleep", "mood"):
            return
        self._conn.execute(
            "INSERT INTO health (user_id, day, water) VALUES (?, ?, 0) "
            "ON CONFLICT(user_id, day) DO NOTHING", (user_id, day))
        self._conn.execute(
            f"UPDATE health SET {field} = ? WHERE user_id = ? AND day = ?",
            (value, user_id, day))
        self._conn.commit()

    def health_water_inc(self, user_id: str, day: str, delta: int = 1) -> int:
        self._conn.execute(
            "INSERT INTO health (user_id, day, water) VALUES (?, ?, 0) "
            "ON CONFLICT(user_id, day) DO NOTHING", (user_id, day))
        self._conn.execute(
            "UPDATE health SET water = MAX(0, water + ?) WHERE user_id = ? AND day = ?",
            (delta, user_id, day))
        self._conn.commit()
        return self.health_day(user_id, day)["water"]

    def health_history(self, user_id: str, limit: int = 7) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT day, water, sleep, mood FROM health WHERE user_id = ? "
            "ORDER BY day DESC LIMIT ?", (user_id, limit)).fetchall()]
