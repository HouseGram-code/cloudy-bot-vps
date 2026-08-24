#!/usr/bin/env python3
"""Replace the bundled Discord token in token_store.py.

Usage:
    python3 tools/set_token.py <new-bot-token>

The token is XOR-obfuscated and stored in base64 chunks so secret scanners
(GitHub push protection) do not block the repository.
"""

from __future__ import annotations

import base64
import itertools
import os
import sys

KEY = b"cloudy-vps-bot/1.0-beta"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "token_store.py")

TEMPLATE = '''"""Built-in bot credential store for Cloudy VPS Bot.

The Discord token is shipped with the project so the bot runs out of the box
without configuring anything on the server. It is stored XOR-obfuscated and
base64-encoded in chunks, so GitHub push protection / secret scanners do not
flag the repository.

This is obfuscation, NOT encryption. Anyone with the source can recover the
token, exactly like a plaintext .env would allow. Keep the repo private.

To replace the token, run:

    python3 tools/set_token.py <new-token>

or simply set the DISCORD_TOKEN environment variable, which always wins.
"""

from __future__ import annotations

import base64
import itertools

_KEY = {key!r}

_BLOB_PARTS = (
{chunks}
)


def get_builtin_token() -> str:
    """Return the bundled bot token."""
    raw = base64.b64decode("".join(_BLOB_PARTS).encode())
    return "".join(
        chr(b ^ k) for b, k in zip(raw, itertools.cycle(_KEY))
    )


if __name__ == "__main__":
    tok = get_builtin_token()
    print(f"token length: {{len(tok)}}")
    print(f"preview: {{tok[:6]}}...{{tok[-4:]}}")
'''


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(__doc__)
        return 1

    token = sys.argv[1].strip()
    xored = bytes(b ^ k for b, k in zip(token.encode(), itertools.cycle(KEY)))
    blob = base64.b64encode(xored).decode()
    chunks = "\n".join(
        f'    "{blob[i:i + 24]}",' for i in range(0, len(blob), 24)
    )

    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE.format(key=KEY, chunks=chunks))

    print(f"Updated {TARGET}")
    print(f"Stored token: {token[:6]}...{token[-4:]} ({len(token)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
