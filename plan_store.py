"""Runtime resource plan for the free VPS tier.

The amount of RAM / disk / vCPU a free VPS gets used to be baked into
`config.PLAN` (env only), which meant every change required editing `.env` and
restarting the bot. Staff can now raise or lower the resources at runtime from
the admin panel (buttons) or with `!plan ram 2048` / `!plan disk 20`.

The values live in a small JSON file so they survive restarts. Changing them
only affects VPS created afterwards - Docker cannot resize a running guest's
disk, so existing servers keep the limits they were created with.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import config

PLAN = config.PLAN
# A half-updated deployment (new modules + an old config.py) used to crash
# with `ImportError: cannot import name 'PLAN_FILE'`. Never hard-fail on a
# missing setting - fall back to the environment and then to the default.
PLAN_FILE = getattr(config, "PLAN_FILE", None) or os.getenv(
    "PLAN_FILE", "/app/data/plan.json"
)

# Safety rails: the host cannot hand out more than it has.
MIN_RAM_MB = 256
MAX_RAM_MB = 16384
MIN_DISK_GB = 5
MAX_DISK_GB = 200
MIN_CPU = 0.5
MAX_CPU = 8.0

# How much one button press changes.
RAM_STEP = 512
DISK_STEP = 5
CPU_STEP = 0.5


def _clamp_int(value, low: int, high: int, default: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = int(default)
    return max(low, min(high, number))


def _clamp_float(value, low: float, high: float, default: float) -> float:
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError):
        number = float(default)
    return max(low, min(high, number))


class PlanStore:
    """Persistent, editable copy of the free-tier resource plan."""

    def __init__(self, path: str = PLAN_FILE, base: dict | None = None) -> None:
        self.path = path
        self.base = dict(base or PLAN)
        self._lock = asyncio.Lock()
        self._state: dict = {
            "ram_mb": _clamp_int(self.base.get("ram_mb", 1024), MIN_RAM_MB, MAX_RAM_MB, 1024),
            "swap_mb": _clamp_int(self.base.get("swap_mb", 512), 0, MAX_RAM_MB, 512),
            "cpu_cores": _clamp_float(self.base.get("cpu_cores", 1), MIN_CPU, MAX_CPU, 1.0),
            "disk_gb": _clamp_int(self.base.get("disk_gb", 10), MIN_DISK_GB, MAX_DISK_GB, 10),
            "changed_ts": 0.0,
            "by_id": 0,
            "by_name": "",
        }
        self._defaults = {
            "ram_mb": self._state["ram_mb"],
            "swap_mb": self._state["swap_mb"],
            "cpu_cores": self._state["cpu_cores"],
            "disk_gb": self._state["disk_gb"],
        }
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key in list(self._state):
            if key in data:
                self._state[key] = data[key]
        self._normalize()

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _normalize(self) -> None:
        self._state["ram_mb"] = _clamp_int(
            self._state.get("ram_mb"), MIN_RAM_MB, MAX_RAM_MB, self._defaults["ram_mb"]
        )
        self._state["disk_gb"] = _clamp_int(
            self._state.get("disk_gb"), MIN_DISK_GB, MAX_DISK_GB, self._defaults["disk_gb"]
        )
        self._state["cpu_cores"] = _clamp_float(
            self._state.get("cpu_cores"), MIN_CPU, MAX_CPU, self._defaults["cpu_cores"]
        )
        self._state["swap_mb"] = _clamp_int(
            self._state.get("swap_mb"), 0, MAX_RAM_MB, self._defaults["swap_mb"]
        )
        try:
            self._state["changed_ts"] = float(self._state.get("changed_ts") or 0.0)
        except (TypeError, ValueError):
            self._state["changed_ts"] = 0.0
        try:
            self._state["by_id"] = int(self._state.get("by_id") or 0)
        except (TypeError, ValueError):
            self._state["by_id"] = 0
        self._state["by_name"] = str(self._state.get("by_name") or "")

    # ------------------------------------------------------------------
    @property
    def ram_mb(self) -> int:
        return int(self._state["ram_mb"])

    @property
    def swap_mb(self) -> int:
        return int(self._state["swap_mb"])

    @property
    def cpu_cores(self) -> float:
        return float(self._state["cpu_cores"])

    @property
    def disk_gb(self) -> int:
        return int(self._state["disk_gb"])

    def plan(self) -> dict:
        """The full plan dict (static text from config + live resources)."""
        merged = dict(self.base)
        merged.update(
            {
                "ram_mb": self.ram_mb,
                "swap_mb": self.swap_mb,
                "cpu_cores": self.cpu_cores,
                "disk_gb": self.disk_gb,
            }
        )
        return merged

    def state(self) -> dict:
        return dict(self._state)

    def is_default(self) -> bool:
        return all(self._state[k] == v for k, v in self._defaults.items())

    def defaults(self) -> dict:
        return dict(self._defaults)

    # ------------------------------------------------------------------
    async def update(
        self,
        ram_mb: int | float | None = None,
        disk_gb: int | float | None = None,
        cpu_cores: float | None = None,
        swap_mb: int | float | None = None,
        moderator_id: int = 0,
        moderator_name: str = "",
    ) -> dict:
        """Set absolute values. Returns the new plan."""
        async with self._lock:
            if ram_mb is not None:
                self._state["ram_mb"] = ram_mb
                if swap_mb is None:
                    # Keep a sane swap size next to the new RAM amount.
                    self._state["swap_mb"] = max(256, int(float(ram_mb)) // 2)
            if swap_mb is not None:
                self._state["swap_mb"] = swap_mb
            if disk_gb is not None:
                self._state["disk_gb"] = disk_gb
            if cpu_cores is not None:
                self._state["cpu_cores"] = cpu_cores
            self._normalize()
            self._state["changed_ts"] = time.time()
            self._state["by_id"] = int(moderator_id)
            self._state["by_name"] = str(moderator_name)
            self._save()
            return self.plan()

    async def add_ram(self, delta: int, moderator_id: int = 0, moderator_name: str = "") -> dict:
        return await self.update(
            ram_mb=self.ram_mb + int(delta),
            moderator_id=moderator_id,
            moderator_name=moderator_name,
        )

    async def add_disk(self, delta: int, moderator_id: int = 0, moderator_name: str = "") -> dict:
        return await self.update(
            disk_gb=self.disk_gb + int(delta),
            moderator_id=moderator_id,
            moderator_name=moderator_name,
        )

    async def add_cpu(self, delta: float, moderator_id: int = 0, moderator_name: str = "") -> dict:
        return await self.update(
            cpu_cores=self.cpu_cores + float(delta),
            moderator_id=moderator_id,
            moderator_name=moderator_name,
        )

    async def reset(self, moderator_id: int = 0, moderator_name: str = "") -> dict:
        """Back to the values from config / .env."""
        return await self.update(
            ram_mb=self._defaults["ram_mb"],
            swap_mb=self._defaults["swap_mb"],
            disk_gb=self._defaults["disk_gb"],
            cpu_cores=self._defaults["cpu_cores"],
            moderator_id=moderator_id,
            moderator_name=moderator_name,
        )


# Shared instance used by the bot, the views, the embeds and the VPS manager.
PLAN_STORE = PlanStore()


def live_plan() -> dict:
    """Shortcut used by embeds / manager so they always read fresh values."""
    return PLAN_STORE.plan()
