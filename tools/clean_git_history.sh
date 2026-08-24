#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cloudy VPS Bot - remove the leaked token from git history
#
# GitHub push protection scans EVERY commit in a push, not just the current
# files. Even after fixing .env / config.py, the old commits still contain the
# raw token, so the push keeps getting rejected. This script rewrites history
# so no commit contains the secret.
#
# Usage:
#     bash tools/clean_git_history.sh            # squash into one clean commit
#     bash tools/clean_git_history.sh --push     # ...and force-push to origin
# ---------------------------------------------------------------------------
set -euo pipefail

BRANCH="${BRANCH:-main}"
DO_PUSH=0
[[ "${1:-}" == "--push" ]] && DO_PUSH=1

cd "$(dirname "$0")/.."

if [[ ! -d .git ]]; then
  echo "No .git here yet - initializing a clean repository."
  git init -b "$BRANCH"
  git add -A
  git commit -m "Cloudy VPS Bot v1.0 Beta"
  echo "Done. Add your remote and push:"
  echo "  git remote add origin <your-repo-url>"
  echo "  git push -u origin $BRANCH"
  exit 0
fi

echo "==> 1/5 Making sure .env is untracked"
git rm --cached .env       >/dev/null 2>&1 || true
git rm --cached .env.local >/dev/null 2>&1 || true

echo "==> 2/5 Verifying the working tree is clean of secrets"
if ! python3 tools/scan_secrets.py --tree; then
  echo "Secrets still present in files. Fix them before rewriting history." >&2
  exit 1
fi

echo "==> 3/5 Rewriting history into a single clean commit"
CURRENT="$(git rev-parse --abbrev-ref HEAD)"
git checkout --orphan __cloudy_clean >/dev/null 2>&1
git add -A
git commit -m "Cloudy VPS Bot v1.0 Beta" >/dev/null
git branch -D "$CURRENT" >/dev/null 2>&1 || true
git branch -m "$BRANCH"

echo "==> 4/5 Dropping old objects"
git reflog expire --expire=now --all >/dev/null 2>&1 || true
git gc --prune=now --aggressive >/dev/null 2>&1 || true

echo "==> 5/5 Scanning the new history"
python3 tools/scan_secrets.py --history

if [[ "$DO_PUSH" == "1" ]]; then
  if git remote get-url origin >/dev/null 2>&1; then
    echo "==> Force-pushing $BRANCH to origin"
    git push -f -u origin "$BRANCH"
  else
    echo "No 'origin' remote configured. Add one, then: git push -f -u origin $BRANCH"
  fi
else
  echo
  echo "History is clean. Push with:"
  echo "  git push -f -u origin $BRANCH"
fi
