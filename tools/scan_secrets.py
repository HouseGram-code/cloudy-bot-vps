#!/usr/bin/env python3
"""Check that no Discord token appears in the working tree or in git history.

Run this BEFORE pushing to GitHub:

    python3 tools/scan_secrets.py            # files + git history
    python3 tools/scan_secrets.py --tree     # files only
    python3 tools/scan_secrets.py --history  # git history only

Exit code 0 = clean, 1 = a secret was found.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# GitHub's "Discord Bot Token" pattern: base64(user id).base64(timestamp).hmac
TOKEN_RE = re.compile(
    r"[MNO][A-Za-z\d_-]{23,27}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,40}"
)

SKIP_DIRS = {".git", "__pycache__", "data", ".venv", "venv", "node_modules"}
SKIP_FILES = {"scan_secrets.py"}


def _report(where: str, line_no: int | str, match: str) -> None:
    masked = f"{match[:8]}...{match[-4:]}"
    print(f"  [!] {where}:{line_no} -> {masked}")


def scan_tree() -> int:
    print("Scanning working tree...")
    hits = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES or name.endswith((".pyc", ".zip", ".png")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh, 1):
                        for m in TOKEN_RE.finditer(line):
                            _report(os.path.relpath(path, ROOT), i, m.group(0))
                            hits += 1
            except OSError:
                continue
    print("  clean" if not hits else f"  {hits} problem(s) found")
    return hits


def scan_history() -> int:
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        print("Scanning git history...\n  no git repository yet - nothing to scan")
        return 0

    print("Scanning git history (all commits, all blobs)...")
    try:
        blobs = subprocess.run(
            ["git", "rev-list", "--objects", "--all"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"  could not read history: {exc}")
        return 0

    hits = 0
    for entry in blobs:
        parts = entry.split(" ", 1)
        sha = parts[0]
        name = parts[1] if len(parts) > 1 else "(commit/tree)"
        if name.endswith((".pyc", ".zip", ".png")):
            continue
        try:
            content = subprocess.run(
                ["git", "cat-file", "-p", sha],
                cwd=ROOT,
                capture_output=True,
                check=False,
            ).stdout.decode("utf-8", "ignore")
        except OSError:
            continue
        for m in TOKEN_RE.finditer(content):
            _report(f"{name} (blob {sha[:8]})", "?", m.group(0))
            hits += 1

    if hits:
        print(f"  {hits} problem(s) found in history")
        print("  -> run: bash tools/clean_git_history.sh")
    else:
        print("  clean")
    return hits


def main() -> int:
    args = sys.argv[1:]
    do_tree = not args or "--tree" in args
    do_hist = not args or "--history" in args

    total = 0
    if do_tree:
        total += scan_tree()
    if do_hist:
        total += scan_history()

    print()
    if total:
        print("RESULT: secrets found - GitHub push protection WILL reject this push.")
        return 1
    print("RESULT: clean - safe to push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
