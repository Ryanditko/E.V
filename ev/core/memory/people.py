"""People / relationships — who's who, birthdays."""

from __future__ import annotations

import re


class PeopleMixin:
    @staticmethod
    def _norm_bday(bday: str) -> str:
        """Normalize a birthday to 'MM-DD' (year kept if given as YYYY-MM-DD)."""
        b = (bday or "").strip()
        if not b:
            return ""
        # accept DD/MM, DD/MM/YYYY, YYYY-MM-DD, MM-DD
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", b)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            mmdd = f"{int(mo):02d}-{int(d):02d}"
            return f"{y}-{mmdd}" if y and len(y) == 4 else mmdd
        m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", b)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return b

    def add_person(self, user_id: str, name: str, notes: str = "",
                   birthday: str = "") -> int:
        """Add or update a person (matched by name, case-insensitive). Notes are
        appended; a new birthday overwrites the old one."""
        name = (name or "").strip()
        bday = self._norm_bday(birthday)
        row = self._conn.execute(
            "SELECT id, notes FROM people WHERE user_id = ? AND lower(name) = lower(?)",
            (user_id, name),
        ).fetchone()
        if row:
            notes_new = (row["notes"] or "").strip()
            if notes and notes not in notes_new:
                notes_new = (notes_new + " • " + notes).strip(" •")
            self._conn.execute(
                "UPDATE people SET notes = ?, birthday = COALESCE(NULLIF(?, ''), birthday) "
                "WHERE id = ?", (notes_new, bday, row["id"]))
            self._conn.commit()
            return int(row["id"])
        cur = self._conn.execute(
            "INSERT INTO people (user_id, name, notes, birthday, created) "
            "VALUES (?, ?, ?, ?, ?)", (user_id, name, notes, bday, self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_people(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, notes, birthday FROM people WHERE user_id = ? "
            "ORDER BY lower(name)", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def find_person(self, user_id: str, name: str) -> dict | None:
        n = (name or "").strip()
        row = self._conn.execute(
            "SELECT id, name, notes, birthday FROM people WHERE user_id = ? "
            "AND lower(name) LIKE lower(?) ORDER BY length(name) LIMIT 1",
            (user_id, f"%{n}%")).fetchone()
        return dict(row) if row else None

    def delete_person(self, user_id: str, name: str) -> bool:
        p = self.find_person(user_id, name)
        if not p:
            return False
        self._conn.execute("DELETE FROM people WHERE id = ?", (p["id"],))
        self._conn.commit()
        return True

    def delete_person_by_id(self, user_id: str, person_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM people WHERE id = ? AND user_id = ?", (person_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    def birthdays_on(self, user_id: str, mmdd: str) -> list[dict]:
        """People whose birthday falls on the given 'MM-DD' (year ignored)."""
        out = []
        for p in self.list_people(user_id):
            b = p.get("birthday") or ""
            if b and b[-5:] == mmdd:
                out.append(p)
        return out

    def update_person(self, u, i, name):
        return self._update("people", u, i, {"name": name})
