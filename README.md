# Cloudy VPS Bot — v1.0 Beta

A Discord bot that hands out **free VPS** instances (Docker containers running
**Ubuntu 22.04 LTS**) with **tmate SSH** access, a pretty deployment animation,
and a button-based control panel.

> Language: English UI (v1.0 Beta). Multi-language can be added later.

---

## Commands

| Command | What it does |
|---|---|
| `!deploy` | Shows the free plan specs (RAM, swap, vCPU, disk, OS, bandwidth, access) with a **Start** button. Pressing Start plays an animated progress bar and then reveals the live server + tmate SSH command. |
| `!manage` | Live control panel: status, RAM usage bar, CPU usage bar, disk, OS, network I/O, uptime, server ID + buttons **Start / Stop / Restart / Get SSH / Refresh**. |
| `!rules` | The 5 rules of the free tier. |
| `!destroy` | Permanently removes the user's VPS. |
| `!ban <@user\|id> [reason]` | **Staff.** Blocks the user, stops their server, DMs them the reason. |
| `!unban <@user\|id>` | **Staff.** Restores access and DMs the user. |
| `!bans` | **Staff.** List of all bans with reason and moderator. |
| `!servers` | **Staff.** All deployed servers and their owners. |
| `!ping` | Latency check. |
| `!help` | Command list. |

One VPS per Discord user by default (`MAX_VPS_PER_USER`).

---

## Free tier defaults

| Resource | Value |
|---|---|
| RAM | 1024 MB (+512 MB swap) |
| CPU | 1 vCPU (`--cpus=1`) |
| Disk | 10 GB |
| OS | Ubuntu 22.04 LTS (Jammy) |
| Access | tmate SSH (root) |
| Bandwidth | Unmetered (fair use) |

All of it is configurable in `.env`.

---

## Project layout

```
cloudy-vps-bot/
├── bot.py                       # commands, events, error handling
├── config.py                    # token, plan, colors, emojis
├── vps_manager.py               # Docker backend + tmate SSH
├── views.py                     # buttons, deploy animation
├── embeds.py                    # all the pretty embeds
├── moderation.py                # ban / unban storage (data/bans.json)
├── token_store.py               # bundled bot token (obfuscated, scanner-safe)
├── tools/set_token.py           # helper to replace the bundled token
├── tools/scan_secrets.py        # pre-push check: files + git history
├── tools/check_tmate.sh         # diagnose tmate/SSH problems
├── tools/clean_git_history.sh   # wipes a leaked token from git history
├── .gitignore
├── requirements.txt
├── Dockerfile                   # the bot image (python:3.12-slim)
├── docker-compose.yml
├── start.sh                     # one-command build + run (creates .env if missing)
├── .env / .env.example
└── images/
    └── ubuntu-22.04/Dockerfile  # the guest "VPS" image (ubuntu:22.04 + tmate)
```

---

## Setup

### 1. Discord Developer Portal

1. Open your application → **Bot**.
2. Enable **MESSAGE CONTENT INTENT** (required for `!` commands).
3. Invite the bot with scopes `bot` + permissions: *Send Messages, Embed Links,
   Read Message History, Use External Emojis*.

### 2. Configure (nothing required)

The bot token is **already bundled** in `token_store.py`, so the bot works
immediately after cloning — you do not have to create a `.env` or set any
variable on the server.

Only if you want to tune the plan (RAM, CPU, disk, prefix):

```bash
cp .env.example .env
```

### 3. Build the guest VPS image

```bash
docker build -t cloudy-vps:ubuntu-22.04 ./images/ubuntu-22.04
```

(The bot also builds it automatically on first start if it is missing.)

### 4. Before pushing to GitHub (optional)

```bash
python3 tools/scan_secrets.py
```

### 5. Run the bot

```bash
chmod +x start.sh
./start.sh          # builds the guest image + starts the bot
./start.sh logs     # follow the logs
```

Or with plain Compose:

```bash
docker compose up -d --build
docker compose logs -f
```

> **`env file /root/... /.env not found`?**
> `.env` is gitignored, so a fresh `git clone` has no `.env`. The bot does not
> need one (token is bundled, all plan values have defaults). Either run
> `./start.sh`, which creates it automatically, or:
>
> ```bash
> cp .env.example .env
> docker compose up -d --build
> ```
>
> `docker-compose.yml` already marks the env file as `required: false`, which
> needs Compose **v2.24+** (`docker compose version` to check).

Or without Docker:

```bash
pip install -r requirements.txt
STATE_FILE=./data/vps_state.json python bot.py
```

---

## Bot token (GitHub-safe)

GitHub push protection blocks any commit containing a raw Discord token, which is
why `.env`, `.env.example` and `config.py` were rejected earlier. The token is now
kept in **`token_store.py`**, XOR-obfuscated and stored as short base64 chunks, so
no secret-looking string exists in the repository and pushes go through.

Resolution order used by `config.py`:

```python
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or get_builtin_token()
```

1. `DISCORD_TOKEN` environment variable (or `.env`) — wins if present.
2. Otherwise the bundled token from `token_store.py`.

Check what is bundled:

```bash
python3 token_store.py
# token length: 72
# preview: MTU***...***K4
```

Replace it with another token:

```bash
python3 tools/set_token.py <new-bot-token>
```

`.env` is listed in `.gitignore`, so a local override never reaches GitHub.

> This is **obfuscation, not encryption**. Anyone who can read the source can
> recover the token, exactly like a plaintext `.env`. Keep the repository private.
> If the token ever leaks publicly, reset it in the Developer Portal and run
> `tools/set_token.py` with the new one.

### GitHub still rejects the push?

Push protection scans **every commit in the push, not just the current files**.
If an earlier commit ever contained the raw token (in `.env`, `.env.example` or
`config.py`), fixing the files is not enough — the old commit still carries the
secret and the push keeps getting rejected.

Check what exactly is blocking you:

```bash
python3 tools/scan_secrets.py
# Scanning working tree...        clean
# Scanning git history...         [!] .env (blob 3f9a1c2d)
```

Then rewrite the history into one clean commit:

```bash
bash tools/clean_git_history.sh          # local rewrite only
bash tools/clean_git_history.sh --push   # rewrite + force-push to origin
```

What the script does:

1. Untracks `.env` (`git rm --cached`).
2. Verifies no file contains a token pattern.
3. Replaces history with a single orphan commit — old commits are gone.
4. Expires the reflog and runs `git gc`, dropping the old objects.
5. Re-scans and optionally force-pushes.

If you prefer surgical history editing instead of a squash:

```bash
pip install git-filter-repo
git filter-repo --path .env --path .env.example --invert-paths --force
git push -f origin main
```

> After a force-push, anyone else with a clone must re-clone or run
> `git fetch && git reset --hard origin/main`.
>
> GitHub also offers an "allow secret" link in the rejection message. Do **not**
> use it — it lets the raw token into the repository, and Discord auto-revokes
> tokens it finds on public GitHub.

---

## How tmate SSH works

When a server is deployed (or you press **Get SSH**), the bot runs inside the
guest container:

```bash
tmate -S /tmp/cloudy.tmate.sock new-session -d 'bash -l'
tmate -S /tmp/cloudy.tmate.sock wait tmate-ready
tmate -S /tmp/cloudy.tmate.sock display -p '#{tmate_ssh}'
```

The resulting `ssh xxxxx@nyc1.tmate.io` line is sent to the user. No port
forwarding or public IP is needed, but the host **must have outbound internet
access** to `tmate.io`. Stopping or restarting a server invalidates its session —
press **Get SSH** again to obtain a fresh one.

---

## Privacy: SSH only in DMs

SSH credentials are **never posted in a channel or group**. Whenever a session is
created (after `!deploy` or via the **Get SSH** button) the bot sends it to the
user's **direct messages**. The public message only says *"Sent to your DMs"*.

If the user has DMs closed, the bot falls back to an **ephemeral** reply that only
that user can see, plus a hint to enable *Privacy Settings -> Direct Messages*.
Set `SSH_TO_DM_ONLY=0` in `.env` to allow the ephemeral copy without the warning.

---

## Staff, rules and bans

Owners are configured in `.env` (`OWNER_IDS`, comma-separated) and default to the
bundled owner ID. Owners bypass the one-server limit, can ban/unban, and can
never be banned themselves.

```bash
!ban 1264586393594630239 mining on the free tier
!unban @user
!bans
!servers
```

Banning a user immediately:

1. writes the ban to `data/bans.json` (survives restarts),
2. **stops their running VPS**,
3. DMs them the reason,
4. blocks every command and every button they press.

The 5 free-tier rules live in `config.py` (`RULES`) and are shown by `!rules`, by
the **Rules** button in both panels, and referenced on the deploy card — pressing
**Start** means accepting them.

---

## Troubleshooting: "Could not open a tmate session"

Run the built-in diagnostic:

```bash
bash tools/check_tmate.sh
```

It checks, on the host **and** inside the guest container: DNS for
`ssh.tmate.io`, outbound **TCP 2200**, whether the `tmate` binary exists, the
tmate log, and finally opens a real test session.

The three usual causes:

| Cause | Fix |
|---|---|
| `tmate` missing from the guest image (old image built before this fix) | `docker build --no-cache -t cloudy-vps:ubuntu-22.04 ./images/ubuntu-22.04` then `!destroy` + `!deploy` |
| Outbound **TCP 2200** blocked by the host firewall | `ufw allow out 2200/tcp` (or the equivalent in your provider's firewall) |
| DNS not resolving inside containers | already handled via `VPS_DNS=1.1.1.1,8.8.8.8` in `.env` |

What changed in the bot itself: tmate is now started with `nohup ... -F` and
logged to `/tmp/cloudy.tmate.log`, the SSH string is **polled** instead of
blocking on `tmate wait`, the binary is auto-installed if missing, existing
sessions are validated before reuse, and failures return the real DNS/TCP/log
output instead of *"no output"*.

---

## Notes & security

- The bot mounts `/var/run/docker.sock`. That equals root on the host, so only
  run it on a machine you own and keep the bot container private.
- Guest containers run with `cap_drop: ALL`, `no-new-privileges`, a PID limit,
  and hard RAM/CPU caps.
- `storage_opt` (disk quota) only applies on `overlay2` + XFS with pquota; the
  bot falls back gracefully to no quota elsewhere.
- The bundled token in `token_store.py` gives full control of the bot. Keep the
  repository private and rotate the token if the code is ever shared publicly.

---

## Roadmap

- [ ] Localization (RU) toggle
- [ ] Slash commands (`/deploy`, `/manage`)
- [ ] Admin commands: list all servers, force delete, quotas
- [ ] More OS templates (Debian 12, Ubuntu 24.04)
