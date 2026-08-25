#!/usr/bin/env python3
"""Pre-flight check for Cloudy VPS Bot.

Run it after an update (inside the container or next to the sources) to catch a
half-applied upgrade *before* the bot crash-loops:

    docker compose exec bot python tools/selfcheck.py
    # or on the host, from the project folder:
    python3 tools/selfcheck.py

It verifies that every module file is present, that config.py knows every
setting the newer modules expect, that the language table is complete and that
all modules import cleanly. Exit code 0 = healthy, 1 = something is off.
"""
from __future__ import annotations

import ast
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OK = "\033[92mOK\033[0m"
BAD = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

MODULES = [
    "config",
    "i18n",
    "moderation",
    "maintenance",
    "slots",
    "plan_store",
    "wallet",
    "token_store",
    "vps_manager",
    "embeds",
    "views",
    "bot",
]

# Settings introduced by newer features. A stale config.py is the #1 cause of
# "cannot import name ... from 'config'" crashes after copying new files over.
REQUIRED_SETTINGS = [
    "BOT_NAME",
    "BOT_VERSION",
    "COMMAND_PREFIX",
    "PLAN",
    "PLAN_FILE",
    "SLOTS_FILE",
    "STATE_FILE",
    "BAN_FILE",
    "WALLET_FILE",
    "MAINTENANCE_FILE",
    "START_LEAVES",
    "LEAF_COST_PER_HOUR",
    "BONUS_LEAVES",
    "BONUS_COOLDOWN_HOURS",
    "TOTAL_VPS_SLOTS",
    "MAX_VPS_PER_USER",
    "TMATE_PORTS",
]

failures: list[str] = []


def line(status: str, text: str) -> None:
    print(f"  [{status}] {text}")


def check_files() -> None:
    print("files")
    for name in MODULES:
        path = os.path.join(ROOT, name + ".py")
        if os.path.isfile(path):
            line(OK, f"{name}.py")
        else:
            line(BAD, f"{name}.py is missing")
            failures.append(f"missing file {name}.py")


def check_config() -> None:
    print("config.py")
    try:
        cfg = importlib.import_module("config")
    except Exception as exc:
        line(BAD, f"cannot import config: {exc}")
        failures.append("config import")
        return
    for name in REQUIRED_SETTINGS:
        if hasattr(cfg, name):
            continue
        line(BAD, f"{name} is not defined - copy the new config.py / .env")
        failures.append(f"config.{name}")
    plan = getattr(cfg, "PLAN", {})
    for key in ("ram_mb", "swap_mb", "cpu_cores", "disk_gb", "os", "os_short"):
        if key not in plan:
            line(BAD, f"PLAN['{key}'] is missing")
            failures.append(f"PLAN.{key}")
    if not failures:
        line(
            OK,
            "plan: {ram} MB RAM (+{swap} swap) / {cpu} vCPU / {disk} GB".format(
                ram=plan.get("ram_mb"),
                swap=plan.get("swap_mb"),
                cpu=plan.get("cpu_cores"),
                disk=plan.get("disk_gb"),
            ),
        )
    token = getattr(cfg, "TOKEN", "") or ""
    line(OK if token else WARN, "bot token present" if token else "bot token is empty")


def check_i18n() -> None:
    print("i18n.py")
    path = os.path.join(ROOT, "i18n.py")
    if not os.path.isfile(path):
        return
    source = open(path, encoding="utf-8").read()
    strings = None
    for node in ast.parse(source).body:
        target = None
        if isinstance(node, ast.Assign):
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        if isinstance(target, ast.Name) and target.id == "STRINGS":
            strings = ast.literal_eval(node.value)
    if not strings:
        line(BAD, "STRINGS table not found")
        failures.append("i18n.STRINGS")
        return
    line(OK, f"{len(strings)} keys")
    partial = [k for k, v in strings.items() if set(v) != {"en", "ru"}]
    if partial:
        line(BAD, f"not translated: {', '.join(partial[:5])}")
        failures.append("i18n translations")
    pattern = re.compile(
        r"t\(\s*(?:lang|current|DEFAULT_LANG|guest|guest_lang|l|self\.lang)"
        r"[^,]*,\s*[\"']([\w.]+)[\"']"
    )
    used: set[str] = set()
    for name in ("bot.py", "embeds.py", "views.py", "vps_manager.py"):
        file_path = os.path.join(ROOT, name)
        if os.path.isfile(file_path):
            used |= set(pattern.findall(open(file_path, encoding="utf-8").read()))
    unknown = sorted(used - set(strings))
    if unknown:
        line(BAD, f"unknown keys used: {', '.join(unknown[:5])}")
        failures.append("i18n missing keys")
    else:
        line(OK, "every key used by the code exists")


def check_imports() -> None:
    print("imports")
    for name in MODULES:
        if name == "bot":
            continue  # importing bot.py would build the client
        try:
            importlib.import_module(name)
            line(OK, name)
        except Exception as exc:
            line(BAD, f"{name}: {type(exc).__name__}: {exc}")
            failures.append(f"import {name}")


def main() -> int:
    print("Cloudy VPS Bot - self check")
    print(f"project: {ROOT}\n")
    check_files()
    check_config()
    check_i18n()
    check_imports()
    print()
    if failures:
        print(f"{BAD} {len(failures)} problem(s): " + ", ".join(failures[:8]))
        print("Hint: copy ALL files from the archive (config.py included), then")
        print("      ./start.sh restart")
        return 1
    print(f"{OK} everything looks good - ./start.sh up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
