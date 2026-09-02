"""Datacenter locations for Cloudy VPS Bot (1.4 Beta · dev).

`!deploy` starts with a region picker. Every region carries a health signal
that a user can read at a glance:

    green   normal        low latency, capacity free
    yellow  under load    higher latency or the region is filling up
    red     unavailable   saturated - it opens again automatically after
                          5-15 minutes

Latency is measured for real (a TCP handshake against a well known host in
that region). When the probe is blocked - many hosts firewall outbound
traffic - the value falls back to a smooth synthetic one, so the picker never
looks broken.

Everything is stored in `data/locations.json`, so restarts and updates keep
the region a server was deployed in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import socket
import threading
import time

try:  # keep working even next to a very old config.py
    from config import LOCATIONS_FILE as _CONFIG_LOCATIONS_FILE
except Exception:  # pragma: no cover
    _CONFIG_LOCATIONS_FILE = ""

LOCATIONS_FILE = (
    _CONFIG_LOCATIONS_FILE
    or os.getenv("LOCATIONS_FILE")
    or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "locations.json"
    )
)

log = logging.getLogger("cloudy.locations")

# ---------------------------------------------------------------------------
# Status vocabulary (green / yellow / red)
# ---------------------------------------------------------------------------
OK = "ok"
LOAD = "load"
DOWN = "down"

STATUS_EMOJI = {
    OK: "\U0001F7E9",
    LOAD: "\U0001F7E8",
    DOWN: "\U0001F7E5",
}
STATUS_KEY = {
    OK: "loc.status_ok",
    LOAD: "loc.status_load",
    DOWN: "loc.status_down",
}
STATUS_COLOR = {
    OK: 0x57F287,
    LOAD: 0xFEE75C,
    DOWN: 0xED4245,
}
STATUS_ORDER = {OK: 0, LOAD: 1, DOWN: 2}

# Thresholds. Ping is in milliseconds, load is 0.0 - 1.0.
PING_OK = int(os.getenv("LOCATION_PING_OK", "120") or 120)
PING_LOAD = int(os.getenv("LOCATION_PING_LOAD", "220") or 220)
LOAD_OK = float(os.getenv("LOCATION_LOAD_OK", "0.65") or 0.65)
LOAD_FULL = float(os.getenv("LOCATION_LOAD_FULL", "0.9") or 0.9)

# How many guests one region advertises.
DEFAULT_CAPACITY = int(os.getenv("LOCATION_CAPACITY", "12") or 12)

# A saturated region is closed for 5-15 minutes and then opens by itself.
CLOSE_MIN_MINUTES = int(os.getenv("LOCATION_CLOSE_MIN", "5") or 5)
CLOSE_MAX_MINUTES = int(os.getenv("LOCATION_CLOSE_MAX", "15") or 15)

REFRESH_SECONDS = int(os.getenv("LOCATION_REFRESH", "60") or 60)
PROBE_TIMEOUT = float(os.getenv("LOCATION_PROBE_TIMEOUT", "1.5") or 1.5)
PROBE_ENABLED = (os.getenv("LOCATION_PROBE", "1") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)

# ---------------------------------------------------------------------------
# The five pickable regions
# ---------------------------------------------------------------------------
LOCATION_DEFS: list[dict] = [
    {
        "id": "us-east",
        "code": "US-EAST-1",
        "flag": "\U0001F1FA\U0001F1F8",
        "country": "USA",
        "country_ru": "\u0421\u0428\u0410",
        "city": "New York",
        "city_ru": "\u041d\u044c\u044e-\u0419\u043e\u0440\u043a",
        "probe": ["speedtest.newark.linode.com", 80],
        "base_ping": 104,
        "capacity": DEFAULT_CAPACITY,
    },
    {
        "id": "us-west",
        "code": "US-WEST-1",
        "flag": "\U0001F1FA\U0001F1F8",
        "country": "USA",
        "country_ru": "\u0421\u0428\u0410",
        "city": "Fremont",
        "city_ru": "\u0424\u0440\u0438\u043c\u043e\u043d\u0442",
        "probe": ["speedtest.fremont.linode.com", 80],
        "base_ping": 158,
        "capacity": DEFAULT_CAPACITY,
    },
    {
        "id": "eu-central",
        "code": "EU-CENTRAL-1",
        "flag": "\U0001F1E9\U0001F1EA",
        "country": "Germany",
        "country_ru": "\u0413\u0435\u0440\u043c\u0430\u043d\u0438\u044f",
        "city": "Frankfurt",
        "city_ru": "\u0424\u0440\u0430\u043d\u043a\u0444\u0443\u0440\u0442",
        "probe": ["speedtest.frankfurt.linode.com", 80],
        "base_ping": 42,
        "capacity": DEFAULT_CAPACITY,
    },
    {
        "id": "eu-west",
        "code": "EU-WEST-1",
        "flag": "\U0001F1EC\U0001F1E7",
        "country": "United Kingdom",
        "country_ru": "\u0412\u0435\u043b\u0438\u043a\u043e\u0431\u0440\u0438\u0442\u0430\u043d\u0438\u044f",
        "city": "London",
        "city_ru": "\u041b\u043e\u043d\u0434\u043e\u043d",
        "probe": ["speedtest.london.linode.com", 80],
        "base_ping": 58,
        "capacity": DEFAULT_CAPACITY,
    },
    {
        "id": "asia-se",
        "code": "AP-SOUTHEAST-1",
        "flag": "\U0001F1F8\U0001F1EC",
        "country": "Singapore",
        "country_ru": "\u0421\u0438\u043d\u0433\u0430\u043f\u0443\u0440",
        "city": "Singapore",
        "city_ru": "\u0421\u0438\u043d\u0433\u0430\u043f\u0443\u0440",
        "probe": ["speedtest.singapore.linode.com", 80],
        "base_ping": 186,
        "capacity": DEFAULT_CAPACITY,
    },
]

LOCATION_BY_ID: dict[str, dict] = {item["id"]: item for item in LOCATION_DEFS}
LOCATION_IDS: list[str] = [item["id"] for item in LOCATION_DEFS]
DEFAULT_LOCATION_ID = os.getenv("DEFAULT_LOCATION", "eu-central").strip() or "eu-central"
if DEFAULT_LOCATION_ID not in LOCATION_BY_ID:
    DEFAULT_LOCATION_ID = LOCATION_IDS[0]


def title(loc: dict | str, lang: str = "en") -> str:
    """"\U0001F1FA\U0001F1F8 USA \u2022 New York" / "\U0001F1FA\U0001F1F8 \u0421\u0428\u0410 \u2022 \u041d\u044c\u044e-\u0419\u043e\u0440\u043a"."""
    data = LOCATION_BY_ID.get(loc) if isinstance(loc, str) else (loc or {})
    data = data or LOCATION_BY_ID[DEFAULT_LOCATION_ID]
    russian = str(lang or "").startswith("ru")
    country = data.get("country_ru" if russian else "country") or data.get("country", "")
    city = data.get("city_ru" if russian else "city") or data.get("city", "")
    return f"{data.get('flag', '')} {country} \u2022 {city}".strip()


def plain_title(loc: dict | str, lang: str = "en") -> str:
    """Same as `title()` but without the flag (for images and logs)."""
    data = LOCATION_BY_ID.get(loc) if isinstance(loc, str) else (loc or {})
    data = data or LOCATION_BY_ID[DEFAULT_LOCATION_ID]
    russian = str(lang or "").startswith("ru")
    country = data.get("country_ru" if russian else "country") or data.get("country", "")
    city = data.get("city_ru" if russian else "city") or data.get("city", "")
    return f"{country} \u2022 {city}".strip()


def usage_from_records(records) -> dict[str, int]:
    """How many servers live in each region right now."""
    used: dict[str, int] = {}
    for record in records or []:
        loc_id = str((record or {}).get("location_id") or DEFAULT_LOCATION_ID)
        if loc_id not in LOCATION_BY_ID:
            loc_id = DEFAULT_LOCATION_ID
        used[loc_id] = used.get(loc_id, 0) + 1
    return used


class LocationStore:
    """Live health of the five regions, persisted between restarts."""

    def __init__(self, path: str = LOCATIONS_FILE) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._io_lock = threading.Lock()
        self._state: dict = {"locations": {}, "updated": 0.0}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("locations"), dict):
                self._state = {
                    "locations": {
                        str(k): dict(v)
                        for k, v in data["locations"].items()
                        if isinstance(v, dict)
                    },
                    "updated": float(data.get("updated") or 0.0),
                }
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            self._state = {"locations": {}, "updated": 0.0}

    def _save(self) -> None:
        with self._io_lock:
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self._state, fh, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
            except OSError as exc:  # pragma: no cover
                log.warning("could not save %s: %s", self.path, exc)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def _merged(self, definition: dict) -> dict:
        entry = dict(self._state["locations"].get(definition["id"]) or {})
        now = time.time()
        closed_until = float(entry.get("closed_until") or 0.0)
        if closed_until and closed_until <= now:
            # The 5-15 minute window is over: the region is open again.
            closed_until = 0.0
        status = str(entry.get("status") or OK)
        if closed_until:
            status = DOWN
        elif status == DOWN:
            status = LOAD
        load = float(entry.get("load") or 0.0)
        data = dict(definition)
        data.update(
            {
                "status": status,
                "emoji": STATUS_EMOJI.get(status, STATUS_EMOJI[OK]),
                "status_key": STATUS_KEY.get(status, STATUS_KEY[OK]),
                "color": STATUS_COLOR.get(status, STATUS_COLOR[OK]),
                "ping": int(entry.get("ping") or definition.get("base_ping") or 0),
                "load": load,
                "load_percent": int(round(min(1.0, max(0.0, load)) * 100)),
                "used": int(entry.get("used") or 0),
                "capacity": int(definition.get("capacity") or DEFAULT_CAPACITY),
                "probe_ok": bool(entry.get("probe_ok")),
                "closed_until": closed_until,
                "reopen_in": int(max(0.0, closed_until - now)) if closed_until else 0,
                "reopen_minutes": (
                    max(1, int((closed_until - now) // 60 + 1)) if closed_until else 0
                ),
                "available": not closed_until,
                "reason": str(entry.get("reason") or ""),
                "updated": float(entry.get("updated") or 0.0),
            }
        )
        return data

    def all(self) -> list[dict]:
        return [self._merged(item) for item in LOCATION_DEFS]

    def get(self, loc_id: str | None) -> dict:
        definition = LOCATION_BY_ID.get(str(loc_id or "")) or LOCATION_BY_ID[
            DEFAULT_LOCATION_ID
        ]
        return self._merged(definition)

    def exists(self, loc_id: str | None) -> bool:
        return str(loc_id or "") in LOCATION_BY_ID

    def available(self, loc_id: str | None) -> bool:
        return bool(self.get(loc_id).get("available"))

    def free_count(self) -> int:
        return sum(1 for item in self.all() if item["available"])

    def overall(self) -> str:
        """Worst status across the regions (used by the status card)."""
        worst = OK
        for item in self.all():
            if STATUS_ORDER[item["status"]] > STATUS_ORDER[worst]:
                worst = item["status"]
        return worst

    def pick_best(self) -> dict:
        """The healthiest open region (used as the pre-selected option)."""
        open_ones = [item for item in self.all() if item["available"]]
        if not open_ones:
            return self.get(DEFAULT_LOCATION_ID)
        open_ones.sort(key=lambda item: (STATUS_ORDER[item["status"]], item["ping"]))
        return open_ones[0]

    def record_fields(self, loc_id: str | None) -> dict:
        """The location keys stored on a VPS record."""
        loc = self.get(loc_id)
        return {
            "location_id": loc["id"],
            "location": f"{loc['flag']} {loc['country']} \u2022 {loc['city']}",
            "location_code": loc["code"],
            "location_ping": int(loc["ping"]),
        }

    def state(self) -> dict:
        return {"updated": float(self._state.get("updated") or 0.0), "locations": self.all()}

    # ------------------------------------------------------------------
    # Refreshing
    # ------------------------------------------------------------------
    @staticmethod
    def _tcp_ping(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> float | None:
        """Milliseconds of a TCP handshake, or None when it is blocked."""
        try:
            started = time.perf_counter()
            with socket.create_connection((host, int(port)), timeout=timeout):
                pass
            return (time.perf_counter() - started) * 1000.0
        except OSError:
            return None

    def _probe_all(self) -> dict[str, float | None]:
        results: dict[str, float | None] = {}
        for definition in LOCATION_DEFS:
            if not PROBE_ENABLED:
                results[definition["id"]] = None
                continue
            probe = definition.get("probe") or []
            if len(probe) != 2:
                results[definition["id"]] = None
                continue
            results[definition["id"]] = self._tcp_ping(probe[0], probe[1])
        return results

    @staticmethod
    def _bucket(loc_id: str, index: int) -> float:
        return random.Random(f"{loc_id}:{index}").random()

    def _drift(self, loc_id: str, span: float = 300.0) -> float:
        """Smooth 0..1 value that changes slowly (5 minute buckets)."""
        now = time.time()
        index = int(now // span)
        frac = (now % span) / span
        start = self._bucket(loc_id, index)
        end = self._bucket(loc_id, index + 1)
        return start + (end - start) * frac

    def _recompute(self, pings: dict, usage: dict) -> None:
        now = time.time()
        for definition in LOCATION_DEFS:
            loc_id = definition["id"]
            entry = dict(self._state["locations"].get(loc_id) or {})
            capacity = int(definition.get("capacity") or DEFAULT_CAPACITY)
            used = int(usage.get(loc_id, 0))
            occupancy = min(1.0, used / float(max(1, capacity)))
            drift = self._drift(loc_id)
            load = min(1.0, round(0.55 * drift + 0.8 * occupancy, 3))

            measured = pings.get(loc_id)
            if measured is not None:
                ping = int(round(measured))
                probe_ok = True
            else:
                ping = int(round(definition["base_ping"] * (0.85 + 0.45 * drift)))
                probe_ok = False
            ping = int(min(999, max(1, ping + round(load * 70))))

            closed_until = float(entry.get("closed_until") or 0.0)
            reason = str(entry.get("reason") or "")
            if closed_until and closed_until <= now:
                closed_until = 0.0
                reason = ""
                log.info("location %s is open again", loc_id)
            if not closed_until and (load >= LOAD_FULL or ping >= PING_LOAD):
                minutes = random.randint(
                    min(CLOSE_MIN_MINUTES, CLOSE_MAX_MINUTES),
                    max(CLOSE_MIN_MINUTES, CLOSE_MAX_MINUTES),
                )
                closed_until = now + minutes * 60.0
                reason = "load" if load >= LOAD_FULL else "ping"
                log.info(
                    "location %s closed for %s min (load %.0f%%, ping %s ms)",
                    loc_id,
                    minutes,
                    load * 100,
                    ping,
                )

            if closed_until:
                status = DOWN
            elif load >= LOAD_OK or ping >= PING_OK:
                status = LOAD
            else:
                status = OK

            self._state["locations"][loc_id] = {
                "status": status,
                "ping": ping,
                "load": load,
                "used": used,
                "probe_ok": probe_ok,
                "closed_until": closed_until,
                "reason": reason,
                "updated": now,
            }

    async def refresh(
        self, usage: dict | None = None, force: bool = False
    ) -> list[dict]:
        """Re-measure every region (at most once per REFRESH_SECONDS)."""
        async with self._lock:
            now = time.time()
            age = now - float(self._state.get("updated") or 0.0)
            if not force and self._state["locations"] and age < REFRESH_SECONDS:
                return self.all()
            try:
                pings = await asyncio.to_thread(self._probe_all)
            except Exception as exc:  # pragma: no cover
                log.warning("location probe failed: %s", exc)
                pings = {}
            self._recompute(pings, usage or {})
            self._state["updated"] = now
            await asyncio.to_thread(self._save)
            return self.all()

    async def set_closed(
        self, loc_id: str, minutes: int = 10, reason: str = "staff"
    ) -> dict:
        """Staff / tests: close one region by hand."""
        async with self._lock:
            if loc_id not in LOCATION_BY_ID:
                return self.get(loc_id)
            entry = dict(self._state["locations"].get(loc_id) or {})
            entry.update(
                {
                    "status": DOWN,
                    "closed_until": time.time() + max(1, int(minutes)) * 60.0,
                    "reason": reason,
                    "updated": time.time(),
                }
            )
            self._state["locations"][loc_id] = entry
            await asyncio.to_thread(self._save)
            return self.get(loc_id)

    async def open_all(self) -> list[dict]:
        async with self._lock:
            for loc_id, entry in list(self._state["locations"].items()):
                entry["closed_until"] = 0.0
                entry["reason"] = ""
                if entry.get("status") == DOWN:
                    entry["status"] = LOAD
                self._state["locations"][loc_id] = entry
            await asyncio.to_thread(self._save)
            return self.all()


def tcp_ping(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> float | None:
    """Public TCP probe (milliseconds) used by the `!status` card."""
    return LocationStore._tcp_ping(host, port, timeout)


# Shared instance used by the bot, the views and the VPS manager.
LOCATIONS = LocationStore()
