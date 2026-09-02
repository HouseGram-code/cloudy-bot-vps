"""Abuse guard for Cloudy VPS Bot (1.4 Beta · dev).

A free server is the perfect target for crypto miners and DDoS scripts, so
the bot watches its own guests:

* every `GUARD_INTERVAL` seconds each running container is inspected;
* known miner / attack binaries (xmrig, cpuminer, t-rex, mhddos, ...) and
  established connections to typical mining-pool ports are matched;
* offending processes are killed immediately, the owner gets a warning and
  the server is stopped on the next strike;
* mining-pool domains are black-holed in the guest's `/etc/hosts`, and the
  containers themselves are created with dropped Linux capabilities and a
  process limit (see `vps_manager._create_sync`).

The module never imports discord: `scan()` returns plain dicts and the bot
turns them into DMs, log lines and admin notices.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

try:  # keep working even next to a very old config.py
    from config import (
        GUARD_BAN_ON_STRIKE,
        GUARD_CPU_STRIKES,
        GUARD_CPU_WARN,
        GUARD_ENABLED,
        GUARD_FILE,
        GUARD_INTERVAL,
        GUARD_STOP_ON_STRIKE,
        GUARD_STRIKES,
    )
except Exception:  # pragma: no cover
    GUARD_ENABLED = True
    GUARD_INTERVAL = 120
    GUARD_STRIKES = 2
    GUARD_STOP_ON_STRIKE = True
    GUARD_BAN_ON_STRIKE = False
    GUARD_CPU_WARN = 97.0
    GUARD_CPU_STRIKES = 5
    GUARD_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "guard.json"
    )

log = logging.getLogger("cloudy.guard")

# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------
MINER_NAMES = (
    "xmrig",
    "xmr-stak",
    "xmrminer",
    "cpuminer",
    "minerd",
    "cgminer",
    "bfgminer",
    "ethminer",
    "phoenixminer",
    "lolminer",
    "nbminer",
    "t-rex",
    "gminer",
    "teamredminer",
    "srbminer",
    "ccminer",
    "verusminer",
    "randomx",
    "cryptonight",
    "stratum",
    "nicehash",
    "hashvault",
    "supportxmr",
    "moneroocean",
    "nanopool",
    "unmineable",
    "kdevtmpfsi",
    "kinsing",
    "sustes",
    "ddgs",
)
ATTACK_NAMES = (
    "mhddos",
    "hping3",
    "slowloris",
    "pyslowloris",
    "torshammer",
    "goldeneye",
    "loic",
    "hoic",
    "ufonet",
    "raven-storm",
    "xerxes",
    "hulk",
    "synflood",
    "udpflood",
    "ipstresser",
    "saphyra",
)


def _signature(names) -> re.Pattern:
    body = "|".join(re.escape(name) for name in names)
    return re.compile(r"(?<![a-z0-9])(" + body + r")(?![a-z0-9])", re.I)


MINER_RE = _signature(MINER_NAMES)
ATTACK_RE = _signature(ATTACK_NAMES)

# Typical mining-pool ports (an established connection is enough).
POOL_PORTS = {
    3333,
    3334,
    3335,
    4444,
    4445,
    5555,
    5556,
    6666,
    7777,
    8888,
    9999,
    14433,
    14444,
    20580,
    45700,
}

# Pool domains that are black-holed inside every guest.
POOL_HOSTS = (
    "pool.minexmr.com",
    "de.minexmr.com",
    "sg.minexmr.com",
    "pool.supportxmr.com",
    "gulf.moneroocean.stream",
    "xmr.pool.minergate.com",
    "xmr-eu1.nanopool.org",
    "xmr.2miners.com",
    "eth.2miners.com",
    "rx.unmineable.com",
    "unmineable.com",
    "pool.hashvault.pro",
    "randomxmonero.hk.nicehash.com",
    "stratum.slushpool.com",
    "stratum-eth.antpool.com",
)


def hosts_blackhole_script() -> str:
    """Shell snippet that black-holes the pool domains in `/etc/hosts`."""
    body = "\n".join(f"0.0.0.0 {host}" for host in POOL_HOSTS)
    return (
        "grep -q cloudy-guard /etc/hosts 2>/dev/null && exit 0; "
        "cat >> /etc/hosts <<'CLOUDYGUARD'\n"
        "# cloudy-guard: crypto mining pools are black-holed\n"
        f"{body}\n"
        "CLOUDYGUARD\n"
    )


class AbuseGuard:
    """Scans the guests for miners / attack tools and reacts."""

    def __init__(self, manager=None, path: str = GUARD_FILE) -> None:
        self.manager = manager
        self.path = path
        self._lock = asyncio.Lock()
        self._state: dict = {"strikes": {}, "cpu": {}, "events": []}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._state["strikes"] = {
                    str(k): int(v) for k, v in (data.get("strikes") or {}).items()
                }
                self._state["cpu"] = {
                    str(k): int(v) for k, v in (data.get("cpu") or {}).items()
                }
                events = data.get("events")
                self._state["events"] = list(events)[-50:] if isinstance(events, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:  # pragma: no cover
            pass

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(GUARD_ENABLED)

    @property
    def interval(self) -> int:
        return max(30, int(GUARD_INTERVAL))

    def attach(self, manager) -> None:
        self.manager = manager

    def strikes(self, user_id: int) -> int:
        return int(self._state["strikes"].get(str(user_id), 0))

    def recent(self, limit: int = 5) -> list[dict]:
        return list(self._state["events"])[-int(limit) :][::-1]

    def state(self) -> dict:
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "strikes": dict(self._state["strikes"]),
            "events": self.recent(10),
        }

    async def reset(self, user_id: int) -> None:
        async with self._lock:
            self._state["strikes"].pop(str(user_id), None)
            self._save()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------
    async def scan(self) -> list[dict]:
        """Inspect every running guest. Returns the incidents found."""
        if not self.enabled or self.manager is None:
            return []
        async with self._lock:
            try:
                incidents = await asyncio.to_thread(self._scan_sync)
            except Exception as exc:  # pragma: no cover
                log.warning("guard scan failed: %s", exc)
                return []
            if incidents:
                self._save()
            return incidents

    def _containers(self) -> list:
        getter = getattr(self.manager, "guest_containers", None)
        if callable(getter):
            return getter()
        return []

    def _scan_sync(self) -> list[dict]:
        incidents: list[dict] = []
        for container in self._containers():
            try:
                container.reload()
                if container.status != "running":
                    continue
                incident = self._inspect(container)
            except Exception as exc:
                log.debug("guard: cannot inspect %s: %s", getattr(container, "name", "?"), exc)
                continue
            if incident:
                incidents.append(incident)
        return incidents

    @staticmethod
    def _exec(container, script: str) -> tuple[int, str]:
        code, output = container.exec_run(["/bin/sh", "-lc", script], demux=False)
        if isinstance(output, (bytes, bytearray)):
            output = output.decode("utf-8", "replace")
        return int(code or 0), output or ""

    def _ps(self, container) -> list[tuple[int, float, str, str]]:
        _code, out = self._exec(
            container,
            "ps -eo pid,pcpu,comm,args --no-headers 2>/dev/null || ps aux 2>/dev/null",
        )
        rows: list[tuple[int, float, str, str]] = []
        for line in out.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 3 or not parts[0].isdigit():
                continue
            try:
                pid = int(parts[0])
                cpu = float(parts[1])
            except ValueError:
                continue
            name = parts[2]
            args = parts[3] if len(parts) > 3 else ""
            rows.append((pid, cpu, name, args))
        return rows

    def _pool_ports(self, container) -> list[int]:
        _code, out = self._exec(
            container, "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null"
        )
        found: set[int] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4 or ":" not in parts[2]:
                continue
            if parts[3] != "01":  # 01 = ESTABLISHED
                continue
            try:
                port = int(parts[2].rsplit(":", 1)[1], 16)
            except ValueError:
                continue
            if port in POOL_PORTS:
                found.add(port)
        return sorted(found)

    @staticmethod
    def _cpu_quota(container) -> float:
        try:
            nano = float(
                (container.attrs.get("HostConfig") or {}).get("NanoCpus") or 0
            )
        except Exception:  # pragma: no cover
            nano = 0.0
        return max(0.1, nano / 1_000_000_000.0) if nano else 1.0

    def _inspect(self, container) -> dict | None:
        labels = container.labels or {}
        try:
            owner_id = int(labels.get("cloudy.owner") or 0)
        except ValueError:
            owner_id = 0
        owner_name = labels.get("cloudy.owner_name") or ""

        procs = self._ps(container)
        hits: list[dict] = []
        pids: list[int] = []
        for pid, cpu, name, args in procs:
            haystack = f"{name} {args}".lower()
            if MINER_RE.search(haystack):
                kind = "miner"
            elif ATTACK_RE.search(haystack):
                kind = "attack"
            else:
                continue
            hits.append({"kind": kind, "pid": pid, "name": name[:48], "cpu": cpu})
            pids.append(pid)

        pool_ports = self._pool_ports(container)

        if hits or pool_ports:
            killed = self._kill(container, pids)
            strikes = int(self._state["strikes"].get(str(owner_id), 0)) + 1
            self._state["strikes"][str(owner_id)] = strikes
            action = "killed" if killed else "detected"
            if GUARD_STOP_ON_STRIKE and strikes >= max(1, int(GUARD_STRIKES)):
                try:
                    container.stop(timeout=5)
                    action = "stopped"
                except Exception as exc:  # pragma: no cover
                    log.warning("guard: could not stop %s: %s", container.name, exc)
            kind = hits[0]["kind"] if hits else "pool"
            incident = {
                "kind": kind,
                "action": action,
                "owner_id": owner_id,
                "owner_name": owner_name,
                "container": container.name,
                "container_id": container.id[:12],
                "processes": [hit["name"] for hit in hits][:6],
                "pool_ports": pool_ports,
                "strikes": strikes,
                "ban": bool(GUARD_BAN_ON_STRIKE)
                and strikes >= max(1, int(GUARD_STRIKES)),
                "ts": time.time(),
            }
            self._event(incident)
            log.warning(
                "guard: %s in %s (owner %s) -> %s",
                kind,
                container.name,
                owner_id,
                action,
            )
            return incident

        # No signature matched: watch for a server that simply pins its vCPU.
        quota = self._cpu_quota(container)
        total_cpu = sum(cpu for _pid, cpu, _name, _args in procs)
        cpu_percent = min(999.0, total_cpu / (quota * 100.0) * 100.0)
        key = container.id[:12]
        if cpu_percent >= float(GUARD_CPU_WARN):
            count = int(self._state["cpu"].get(key, 0)) + 1
            self._state["cpu"][key] = count
            if count >= max(1, int(GUARD_CPU_STRIKES)):
                self._state["cpu"][key] = 0
                incident = {
                    "kind": "cpu",
                    "action": "warned",
                    "owner_id": owner_id,
                    "owner_name": owner_name,
                    "container": container.name,
                    "container_id": key,
                    "processes": [
                        name
                        for _pid, cpu, name, _args in sorted(
                            procs, key=lambda row: row[1], reverse=True
                        )[:3]
                    ],
                    "pool_ports": [],
                    "cpu_percent": round(cpu_percent, 1),
                    "strikes": self.strikes(owner_id),
                    "ban": False,
                    "ts": time.time(),
                }
                self._event(incident)
                return incident
        else:
            self._state["cpu"].pop(key, None)
        return None

    def _kill(self, container, pids: list[int]) -> bool:
        if not pids:
            return False
        joined = " ".join(str(int(pid)) for pid in pids)
        try:
            self._exec(container, f"kill -9 {joined} 2>/dev/null || true")
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("guard: could not kill %s in %s: %s", joined, container.name, exc)
            return False

    def _event(self, incident: dict) -> None:
        events = self._state.setdefault("events", [])
        events.append(incident)
        del events[:-50]


# Shared instance used by the bot.
GUARD = AbuseGuard()
