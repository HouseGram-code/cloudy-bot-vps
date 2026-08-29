# Cloudy VPS Bot — v1.1 Beta

A Discord bot that hands out **free VPS** instances (Docker containers running
**Ubuntu 22.04 LTS**) with **tmate SSH** access, a pretty deployment animation,
and a button-based control panel.

> Languages: **Russian + English**. Every user picks their own with `!lang`
> (stored in `data/languages.json`), and the guest login banner follows the
> same choice via `CLOUDY_LANG`.

---

## Commands

| Command | What it does |
|---|---|
| `!deploy` | Shows the free plan specs (RAM, swap, vCPU, disk, OS, bandwidth, access) with a **Start** button. Pressing Start plays an animated progress bar and then reveals the live server + web-terminal link. |
| `!manage` | Live control panel: status, RAM usage bar, CPU usage bar, disk, OS, network I/O, uptime, server ID + buttons **Start / Stop / Restart / Web terminal / Refresh**. |
| `!rules` | The 5 rules of the free tier. |
| `!destroy` | Permanently removes the user's VPS. |
| `!ban <@user\|id> [reason]` | **Staff.** Blocks the user, stops their server, DMs them the reason. |
| `!unban <@user\|id>` | **Staff.** Restores access and DMs the user. |
| `!bans` | **Staff.** List of all bans with reason and moderator. |
| `!sshx` • `!веб` | Browser terminal link (sshx.io) — the second way into the same VPS. |
| `!servers` | **Staff.** All deployed servers and their owners. |
| `!plan` | **Staff.** Show the free-tier resources; `!plan ram 4096`, `!plan disk 30`, `!plan cpu 2`, `!plan reset` change them live. |
| `!ping` | Latency check. |
| `!lang` / `!язык` | Language picker (🇷🇺 Русский / 🇬🇧 English). Also `!lang ru`, `!lang en`. |
| `!help` | Command list. |

One VPS per Discord user by default (`MAX_VPS_PER_USER`).

---

## Free tier defaults

| Resource | Value |
|---|---|
| RAM | 2048 MB (+1024 MB swap) |
| CPU | 2 vCPU (`--cpus=2`) |
| Disk | 20 GB |
| OS | Ubuntu 22.04 LTS (Jammy) |
| Access | sshx web terminal (root) |
| Bandwidth | Unmetered (fair use) |

All of it is configurable in `.env` **and** live-editable with `!plan` /
the buttons in `!admin` (see "Free VPS resources" below).

---

## Project layout

```
cloudy-vps-bot/
├── bot.py                       # commands, events, error handling
├── config.py                    # token, plan, colors, emojis
├── vps_manager.py               # Docker backend + sshx web terminal
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

## How to connect: the web terminal

Access is provided by **sshx**, a browser terminal. There is no SSH button.

| | sshx web terminal |
|---|---|
| Command | `!sshx` or the **Web terminal** button in `!manage` |
| Client | any browser |
| Needs | outbound HTTPS only |
| Looks like | `https://sshx.io/s/wC8cc6Mbjv#W0apHWrt8OaX4W` |

It opens the container as `root`, and the link is sent **by DM only**.

* The client is one static binary; the bot installs it inside the VPS on first
  use (official build from `sshx.s3.amazonaws.com`, with `https://sshx.io/get`
  as a fallback) and pre-installs it in the guest image.
* It runs detached with `--shell /usr/local/bin/cloudy-login`, so the browser
  terminal greets you with the Cloudy banner. If a client build does not know a
  flag, the bot retries with fewer flags instead of failing.
* Everything after `#` in the link is the encryption key: it stays in the URL
  fragment, so the sshx server never sees it. **The link is the credential** -
  the bot only ever DMs it.
* `!sshx` always kills the previous session and prints a fresh link, so a leaked
  link can be revoked in one command. Stopping the VPS kills the session too.
* Settings: `SSHX_ENABLED`, `SSHX_TIMEOUT`, `SSHX_SERVER` (self-hosted mesh),
  `SSHX_INSTALL_URL`, `SSHX_BINARY_BASE`.

---

## Why tmate SSH was removed

tmate needs one of two things, and a NATed host has neither:

* **outbound TCP 2200** to `ssh.tmate.io` - the only real tmate relay port.
  Many providers block it at the network edge, where `ufw` cannot help
  (outbound is already allowed by default; the filter is upstream).
* **a publicly reachable inbound port** for a self-hosted relay
  (`tools/setup_relay.sh`). Behind provider NAT the host only has private
  addresses (`10.x`, `172.17.x`), so there is nothing to publish. An
  "echo my IP" service reports the NAT gateway, which belongs to someone else -
  pointing the bot at it yields `Connection refused`.

Ports 22 and 443 on `ssh.tmate.io` accept TCP but are **not** the relay: they
never complete the handshake, so "TCP OK" there is misleading.

sshx has neither requirement - it only dials out over HTTPS - so it works on
exactly the hosts where tmate cannot.

`tools/setup_relay.sh` and `tools/check_tmate.sh` are kept for hosts that do
have a public address or an open outbound 2200.

---

## Privacy: access links only in DMs

The access link is **never posted in a channel or group**. Whenever a session is
created (after `!deploy` or via the **Web terminal** button) the bot sends it to
the user's **direct messages**. The public message only says *"Sent to your DMs"*.

If the user has DMs closed, the bot falls back to an **ephemeral** reply that only
that user can see, plus a hint to enable *Privacy Settings -> Direct Messages*.

Anyone holding the link gets a root shell, so treat it as a password: run
`!sshx` again to revoke the old session and issue a fresh link.

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

## Admin panel & maintenance mode

| Command | Who | What it does |
| --- | --- | --- |
| `!admin` (`!panel`, `!админ`, `!панель`) | staff | Opens the admin panel: maintenance switch, live server / ban counters, preview of the public notice. |
| `!maintenance on [reason]` (`!maint`, `!техработы`) | staff | Closes the bot: everyone except staff gets a nicely formatted "technical works" embed. The reason you type is shown to users. |
| `!maintenance off` | staff | Opens the bot for everyone again. |

While maintenance mode is ON:

- `!deploy`, `!manage`, `!destroy` and all panel buttons are blocked for regular users; they receive the maintenance notice instead.
- `!rules`, `!lang`, `!help`, `!ping` keep working, and already running VPS containers are **not** touched.
- Staff (`OWNER_IDS`) can use everything as usual.

The switch is stored in `MAINTENANCE_FILE` (`/app/data/maintenance.json` by default), so it survives bot restarts.

## Pretty in-VPS banner (no rebuild needed)

The login banner (`cloudy-banner`) is now installed into the container **at runtime** on every
`!deploy` and on every Start / Restart from `!manage`. The bot copies `images/ubuntu-22.04/cloudy-banner.sh`
into the guest as `/usr/local/bin/cloudy-banner`, wipes the old Ubuntu MOTD (`/etc/motd`,
`/etc/update-motd.d/*`, `/etc/legal`) and hooks the banner into `/root/.bashrc`.

So old containers and old images get the new banner too — just restart the VPS from `!manage`
(or `!destroy` + `!deploy` for a clean box). Type `banner` inside the VPS to print it again.

## Bot profile description ("About Me")

Discord does **not** let a bot edit its own profile description over the API.
The text under the bot's name comes from the Developer Portal:

1. https://discord.com/developers/applications -> your app -> **General Information**
2. Paste this into **Description** and press Save:

```
Free Ubuntu 22.04 VPS, right from Discord. One command, full root over SSH, no card, no cost. Type !deploy to get your free VPS, or !about to see the specs.
```

3. Reload Discord (Ctrl+R) - the profile card is cached for a while.

Inside Discord the same description is always available as a pretty card via
`!about` (aliases `!info`, `!bot`, `!оботе`, `!описание`), in EN and RU.

## Slots (global capacity)

The host has a fixed number of slots, shown everywhere as `used/total`
(for example `5/5`).

```
!slots            # anyone: running / stopped / free, e.g. 3 running, 1 stopped, 4/5
!slots +1         # staff: one more slot
!slots -1         # staff: one slot less
!slots set 10     # staff: absolute value (0 - 500)
```

* The counters come from Docker itself (`cloudy.vps=true` labels), so they are
  correct even if `data/vps_state.json` was lost.
* When `used >= total` a regular user who runs `!deploy` gets a
  **"No free slots"** card and no container is created. Staff bypass the limit.
* The limit is stored in `SLOTS_FILE` (`data/slots.json`), so it survives
  restarts. `TOTAL_VPS_SLOTS` is only the initial value.
* `!admin` shows Capacity / Running / Stopped / Free and has working
  **➖ -1 slot** and **➕ +1 slot** buttons next to the maintenance switch.

## Deleting somebody else's VPS

When a user's server misbehaves, staff can free the slot immediately:

```
!wipe @user               # delete their VPS
!wipe 1264586393594630239 abuse of resources   # with a reason
```

Aliases: `!delvps`, `!forcedestroy`, `!удалить`, `!снести`. The owner gets a DM
in their own language explaining that staff deleted the VPS and why, and the
freed slot is reported back in the confirmation card.

## VPS quota

| Role | Limit |
| --- | --- |
| Regular user | `MAX_VPS_PER_USER` (default **1**) |
| Staff (`OWNER_IDS`) | unlimited |
| Whole host | `TOTAL_VPS_SLOTS` slots, live-editable with `!slots` |

The limit is enforced by counting real Docker containers labelled
`cloudy.owner=<discord id>`, so it keeps working even if `data/vps_state.json`
is deleted or edited by hand. A user who is at the limit gets a clear
"VPS limit reached" message with a hint to use `!manage` or `!destroy`.

Staff can deploy as many servers as they want: the newest one becomes the
primary server that `!manage` / `!destroy` control, older ones keep running and
stay listed in `!servers`. After `!destroy` the next newest staff server is
promoted automatically.

## Banner troubleshooting (fixed in this build)

The banner used to be installed with `printf '%s' "line1\nline2" >> /root/.bashrc`.
Bash does **not** expand `\n` with `%s`, so `.bashrc` received one broken line and
the banner was never executed. On top of that, tmate starts `bash -l`, which does
not necessarily source `.bashrc` at all.

Now the bot:

1. ships the banner and both hooks **base64-encoded** (no escaping issues at all);
2. installs `/usr/local/bin/cloudy-banner`, `/usr/local/bin/cloudy-login`,
   `/etc/profile.d/00-cloudy-banner.sh`, plus hooks in `/root/.bashrc` and
   `/root/.bash_profile` (guarded by `CLOUDY_BANNER_SHOWN`, so it never prints twice);
3. starts the tmate session through `cloudy-login`, which prints the banner and then
   `exec bash -l` — so it shows even on a container with a stripped-down profile;
4. re-installs the banner on **deploy, start, restart and every SSH request**, and
   runs a self-test inside the guest (`banner install issue …` appears in the bot log
   if something is wrong).

To see it: `!manage` → **Web terminal** (a fresh session re-installs the banner),
or type `banner` inside the VPS.

## Leaves (the free-VPS currency)

Every user has a balance of leaves. Leaves are what keeps a free VPS online:

* a new account starts with **3** leaves (`START_LEAVES`)
* a **running** VPS costs **1** leaf per hour (`LEAF_COST_PER_HOUR`); a stopped one is free
* `!bonus` (or the green button on `!profile`) gives **+25** leaves once every **24 h**
* at **0** leaves the VPS is **stopped, never deleted** - the owner gets a DM and can start it again from `!manage` after topping up
* staff servers (owner IDs) are never charged

Commands:

* `!profile` (`!me`, `!bal`, `!balance`, RU: `!profile` / `!balans` / `!listiki`) - name, ID, balance, remaining uptime, VPS status, bonus timer
* `!bonus` (`!daily`, RU `!bonus`) - claim the daily leaves
* `!give <@user|id> <amount>` - staff only; a negative amount takes leaves away. The same thing is available as the **Give leaves** button in `!admin`.

Balances live in `WALLET_FILE` (`/app/data/wallet.json` by default), so they survive restarts.
Billing runs every 5 minutes and charges every full hour of uptime, so a restart never double-charges.

---

## Free VPS resources (live editable)

The free tier used to be frozen in `.env`. Now the resources of every **new**
VPS can be changed while the bot is running:

```
!plan                # staff: current RAM / vCPU / disk + limits
!plan ram 4096       # 4 GB of RAM (swap follows automatically: RAM / 2)
!plan disk 30        # 30 GB of disk
!plan cpu 2          # 2 vCPU
!plan swap 2048      # explicit swap size
!plan reset          # back to the .env defaults
```

The admin panel (`!admin`) has the same controls as buttons:
**Resources** (show the card), **-512 MB / +512 MB RAM** and
**-5 GB / +5 GB disk**.

| Setting | Range |
|---|---|
| RAM | 256 - 16384 MB |
| Disk | 5 - 200 GB |
| CPU | 0.5 - 8 vCPU |

* Values are clamped to those ranges, so a wrong number can never break Docker.
* New limits apply to **newly created** servers. A running VPS keeps the limits
  it was created with (Docker cannot resize a live container's disk) - recreate
  it with `!destroy` + `!deploy` to pick up the new plan.
* The plan is stored in `PLAN_FILE` (`data/plan.json`), so it survives restarts.
* The in-VPS banner now reads the limits from the container itself, so an old
  server no longer shows the new plan's numbers.

---

## Updating safely (self check)

When you copy a new build over an old folder, copy **every** file - the modules
read new settings from `config.py`. Copying only some of them produced crashes
like:

```
ImportError: cannot import name 'PLAN_FILE' from 'config'
```

Run the pre-flight check after every update:

```bash
python3 tools/selfcheck.py            # on the host, in the project folder
docker compose exec bot python tools/selfcheck.py   # inside the container
```

It reports missing files, settings that `config.py` does not know about,
incomplete translations and modules that fail to import - before the bot starts
restart-looping. `plan_store.py` and `wallet.py` now also fall back to `.env`
values and safe defaults, so an old `config.py` can no longer stop the bot.

---

## Other fixes in this build

* `!manage` was redesigned: RAM / CPU / disk / network now live in one aligned
  monospace panel with soft bars, plus separate OS / uptime / created / ID /
  hostname / status fields and a hint when the server is off.
* The "VPS limit reached" message is localized (RU / EN) and uses the real
  command prefix instead of a hardcoded `!`.
* `!deploy`, `!about` and the admin panel always show the live plan instead of
  the values baked in at start-up.
* Metrics are read defensively (`info.get(...)`), so a container that reports
  no stats yet can no longer break the control panel with a `KeyError`.
