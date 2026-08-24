"""Global VPS capacity ("slots") for Cloudy VPS Bot.

The host can only run a limited number of guests, so the bot keeps a global
slot counter (e.g. 5/5). When every slot is taken, regular users cannot deploy
a new VPS anymore - staff can raise or lower the limit at runtime from the
admin panel or with `!slots +1` / `!slots -1` / `!slots set 8`.

The value lives in a small JSON file so it survives restarts.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

from config import SLOTS_FILE, TOTAL_VPS_SLOTS

MIN_SLOTS = 0
MAX_SLOTS = 500


class SlotStore:
    """Persistent global slot limit."""

    def __init__(self, path: str = SLOTS_FILE, default: int = TOTAL_VPS_SLOTS) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._state: dict = {
            "total": int(default),
            "changed_ts": 0.0,
            "by_id": 0,
            "by_name": "",
        }
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._state.update({k: data.get(k, v) for k, v in self._state.items()})
                self._state["total"] = self._clamp(self._state.get("total", 0))
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    @staticmethod
    def _clamp(value) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = TOTAL_VPS_SLOTS
        return max(MIN_SLOTS, min(MAX_SLOTS, number))

    # ------------------------------------------------------------------
    @property
    def total(self) -> int:
        """How many VPS may exist on the host in total."""
        return int(self._state.get("total", TOTAL_VPS_SLOTS))

    def state(self) -> dict:
        return dict(self._state)

    def has_free(self, used: int) -> bool:
        return int(used) < self.total

    def free(self, used: int) -> int:
        return max(0, self.total - int(used))

    # ------------------------------------------------------------------
    async def set_total(
        self, value: int, moderator_id: int = 0, moderator_name: str = ""
    ) -> int:
        """Set the absolute slot count. Returns the new value."""
        async with self._lock:
            self._state.update(
                {
                    "total": self._clamp(value),
                    "changed_ts": time.time(),
                    "by_id": int(moderator_id),
                    "by_name": moderator_name,
                }
            )
            self._save()
            return self.total

    async def add(
        self, delta: int, moderator_id: int = 0, moderator_name: str = ""
    ) -> int:
        """Increase / decrease the slot count. Returns the new value."""
        return await self.set_total(self.total + int(delta), moderator_id, moderator_name)


# Shared instance used by the bot, the views and the VPS manager.
SLOTS = SlotStore()
