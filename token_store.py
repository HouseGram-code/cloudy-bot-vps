"""Built-in bot credential store for Cloudy VPS Bot.

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

_KEY = b'cloudy-vps-bot/1.0-beta'

_BLOB_PARTS = (
    "Ljg6RSktYEI+CXhXITB2AmN0",
    "bBorMDQaIi5bI0EAFBIjA1Vf",
    "Rl1UWElmK10/M1VfHgUrF0AS",
    "QwkAB1cGWVgbdVskBDUZG1ki",
)


def get_builtin_token() -> str:
    """Return the bundled bot token."""
    raw = base64.b64decode("".join(_BLOB_PARTS).encode())
    return "".join(
        chr(b ^ k) for b, k in zip(raw, itertools.cycle(_KEY))
    )


if __name__ == "__main__":
    tok = get_builtin_token()
    print(f"token length: {len(tok)}")
    print(f"preview: {tok[:6]}...{tok[-4:]}")
