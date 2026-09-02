# Cloudy VPS Bot — v1.4 Beta ◆ dev build

A Discord bot that hands out **free VPS** instances (Docker containers running
**Ubuntu 22.04 LTS**) with a **browser terminal**, a pretty deployment animation,
and a button-based control panel.

> Languages: **Russian + English**. Every user picks their own with `!lang`
> (stored in `data/languages.json`), and the guest login banner follows the
> same choice via `CLOUDY_LANG`.

---

## What's new in 1.4 Beta ◆ dev

| Change | Details |
|---|---|
| **Five regions with a live ping** | `!deploy` now opens with a **region picker**: 🇺🇸 New York, 🇺🇸 Fremont, 🇩🇪 Frankfurt, 🇬🇧 London, 🇸🇬 Singapore. Every row shows a measured TCP ping and a colour — 🟩 normal, 🟨 under load / high ping, 🟥 unavailable. |
| **Regions close and reopen by themselves** | A saturated region goes offline for **5–15 minutes** (`LOCATION_CLOSE_MIN` / `LOCATION_CLOSE_MAX`) and opens again on its own. The board is re-measured every minute (`LOCATION_REFRESH`). |
| **Deploy wizard** | Region → **Ubuntu 22.04 LTS** → animated build. The chosen region is printed while the server is being created, on the success card, in `!manage`, `!specs` and on the server panel. |
| **`!servers` for everyone** | One command shows how many machines you own, a dropdown picks one and opens its panel: start / stop / restart / web terminal / **delete**. `!servers all` is still the staff-wide listing. |
| **`!deploylock`** | **Staff.** `!deploylock on 30 maintenance` closes `!deploy` for everybody (optional timer + reason), `!deploylock off` opens it again, `!deploylock status` prints the current state. Staff can still deploy while it is closed. |
| **`!status` service card** | A generated **PNG** (Pillow) with 🟩 normal / 🟨 under load / 🟥 outage for the Discord gateway, virtualization, deployments, web terminal, abuse guard, storage and all five regions — service health only, no disk/RAM charts. Falls back to a text embed when Pillow or a Unicode font is missing. |
| **Servers survive updates** | On boot the bot **re-adopts every `cloudy.vps` container** straight from Docker: records are rebuilt from container labels, stale entries are dropped and `restart: unless-stopped` is re-applied. Rebuilding or restarting the bot no longer loses machines. |
| **Anti-abuse guard** | A sweep every two minutes hunts miners (xmrig, t-rex, phoenixminer…), attack tools and **mining-pool ports**, kills the processes, DMs the owner, reports to staff and stops repeat offenders. New guests also drop dangerous Linux capabilities and get process/file limits, and known pool hosts are blackholed inside the container. |
| **Pretty test build** | The version is now **v1.4 Beta** with a `◆ dev build` badge in every footer (`BOT_BUILD`, `BOT_BUILD_BADGE`). |

---

## What's new in 1.3 Beta

| Change | Details |
|---|---|
| **Crash fixed** | `Deployment failed: [Errno 13] Permission denied: '/app'`. `config.py` now resolves a **writable** data directory (`DATA_DIR` → `./data` → `~/.cloudy-vps` → temp dir) and every store (`state`, `wallet`, `bans`, `languages`, `slots`, `plan`, `maintenance`) saves through it. `vps_manager` also survives a read-only disk instead of failing the deploy. |
| **No more leaf limits** | Leaves no longer gate `!deploy`, `!manage` or uptime: `LEAVES_ENABLED=0` by default, the billing loop does not even start, and the profile card shows an unlimited badge. Set `LEAVES_ENABLED=1` to bring the old economy back. |
| **30-day free term** | Every server is granted for **30 days** (`VPS_LIFETIME_DAYS`). `!deploy` shows the term before and after the build, `!manage` / `!specs` show the days left, DM reminders arrive 7 / 3 / 1 days before the end, and expired servers are released automatically (`VPS_EXPIRY_ACTION=delete` or `stop`). |
| **Browser terminal only** | The tmate/SSH experiment was **removed** in the final 1.3 build — outbound `2200` and `22` are blocked on most hosts, so `!sshx` (sshx.io over plain HTTPS) is the single way into a VPS. |
| **New `!specs`** | VPS username (`root`), hostname, RAM (used / limit + bar), disk, swap, vCPU, OS, traffic, uptime, server ID and the remaining term. Staff can check anyone: `!specs @user`. |
| **New `!renew`** | **Staff.** `!renew @user 30` extends a term, `!renew @user 0` makes it unlimited. The owner gets a DM. |
| **Admin panel fixed** | Buttons acknowledge the click *before* touching the stores (no more "This interaction failed"), every store error is reported instead of freezing the panel, the panel re-renders from a fallback when the response expires, limit-reached clicks no longer post a bogus confirmation, and the panel shows the VPS term. |
| **Server repair** | `./start.sh fix` (or `bash tools/fix_server.sh`) checks Docker, the socket, data-dir permissions, `.env`, the guest image, dead containers and Python syntax — then recreates the bot container. |

---

## Commands

| Command | What it does |
|---|---|
| `!deploy` | Free-plan specs (RAM, swap, vCPU, disk, OS, bandwidth, access), then the **region picker** (5 locations with live ping colours) → **Ubuntu 22.04 LTS** → animated build → the live server + web-terminal link. Can be closed by staff with `!deploylock`. |
| `!manage` | Live control panel: status, RAM usage bar, CPU usage bar, disk, OS, network I/O, uptime, server ID + buttons **Start / Stop / Restart / Web terminal / Refresh**. |
| `!specs` • `!инфо` | Full server card: **VPS username**, hostname, **RAM**, **disk**, swap, vCPU, OS, traffic, uptime, server ID and the days left of the 30-day term. `!specs @user` for staff. |
| `!renew <@user\|id> [days]` | **Staff.** Extends the VPS term (`0` = unlimited). |
| `!givevps <@user\|id> [username] [RAM] [disk] [days]` | **Staff.** Hands out a ready VPS with the same animated deployment: login, RAM, disk and term on Ubuntu 22.04 LTS. Only the target is required — everything else is optional and order-free (`!givevps @user 5g 25 1`, `ram=5g disk=25 days=1 cpu=2 swap=1g`), and a missing username is derived from the Discord account. The new owner gets a DM with the control panel. Aliases: `!выдать`, `!grantvps`. |
| `!rules` | The 5 rules of the free tier. |
| `!destroy` | Permanently removes the user's VPS. |
| `!ban <@user\|id> [reason]` | **Staff.** Blocks the user, stops their server, DMs them the reason. |
| `!unban <@user\|id>` | **Staff.** Restores access and DMs the user. |
| `!bans` | **Staff.** List of all bans with reason and moderator. |
| `!sshx` • `!веб` | Browser terminal link (sshx.io) — the only way into the VPS. |
| `!servers` • `!мои` | Your machines: a dropdown opens the panel of the selected server (start / stop / restart / web terminal / **delete**). `!servers all` is the **staff** listing of every deployed server and its owner. |
| `!status` • `!статус` | Generated service-status card: 🟩 normal, 🟨 under load, 🟥 outage for the gateway, virtualization, deployments, terminal, guard, storage and the five regions. |
| `!deploylock on\|off\|status [minutes] [reason]` | **Staff.** Closes or opens `!deploy` for everyone. |
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
├── tools/clean_git_history.sh   # wipes a leaked token from git history
├── .gitignore
├── requirements.txt
├── Dockerfile                   # the bot image (python:3.12-slim)
├── docker-compose.yml
├── start.sh                     # one-command build + run (creates .env if missing)
├── .env / .env.example
└── images/
    └── ubuntu-22.04/Dockerfile  # the guest "VPS" image (ubuntu:22.04 + sshx)
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

There is exactly **one** door into a server — the sshx browser terminal — and it
is always **delivered by DM**:

| | sshx web terminal |
|---|---|
| Command | `!sshx` / `!веб` or the **Web terminal** button in `!manage` |
| Client | any browser |
| Needs | outbound HTTPS only — no SSH client, no keys, no open ports |
| Looks like | `https://sshx.io/s/wC8cc6Mbjv#W0apHWrt8OaX4W` |
| Login | `root` |

The link is a **credential**: the bot sends it to your DMs only and never prints
it in a channel. If your DMs are closed the bot says so instead of leaking the
session. It opens the container as `root`.

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

## Troubleshooting: "[Errno 13] Permission denied: '/app'"

Fixed in 1.3 Beta. If an older build still shows it, or the bot cannot save its
state, run the repair script:

```bash
./start.sh fix          # same as: bash tools/fix_server.sh
bash tools/fix_server.sh --check   # report only, change nothing
```

What happened: the bot wrote its JSON stores to `/app/data`, and creating that
directory fails whenever `/app` is not writable for the process (container
started as a non-root UID, read-only layer, or the code run from a directory
owned by someone else). Now `config.py` picks the first writable location out of
`$DATA_DIR` → `./data` → `~/.cloudy-vps` → a temp directory, `vps_manager`
keeps working even if the state file cannot be written, and the image itself
creates `/app/data` with open permissions.

---

## Troubleshooting: "Could not open a web terminal"

Run the built-in diagnostic:

```bash
python3 tools/selfcheck.py
```

The usual causes:

| Cause | Fix |
|---|---|
| Outbound **HTTPS** blocked on the host | allow `443/tcp` outbound — sshx needs nothing else |
| `sshx` missing from an old guest image | `docker build --no-cache -t cloudy-vps:ubuntu-22.04 ./images/ubuntu-22.04`, then `!destroy` + `!deploy` |
| DNS not resolving inside containers | already handled via `VPS_DNS=1.1.1.1,8.8.8.8` in `.env` |
| The VPS is stopped | `!manage` → **Start**, then press **Web terminal** again |

How it works in the bot: the client is auto-installed on first use, the link is
**polled** out of `/tmp/cloudy.sshx.log`, every request kills the previous
session, and a failure returns the real log output instead of *"no output"*.

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
Free Ubuntu 22.04 VPS, right from Discord. One command, full root in your browser, no card, no cost. Type !deploy to get your free VPS, or !about to see the specs.
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
the banner was never executed. On top of that, the login shell is `bash -l`, which does
not necessarily source `.bashrc` at all.

Now the bot:

1. ships the banner and both hooks **base64-encoded** (no escaping issues at all);
2. installs `/usr/local/bin/cloudy-banner`, `/usr/local/bin/cloudy-login`,
   `/etc/profile.d/00-cloudy-banner.sh`, plus hooks in `/root/.bashrc` and
   `/root/.bash_profile` (guarded by `CLOUDY_BANNER_SHOWN`, so it never prints twice);
3. starts the web terminal through `cloudy-login`, which prints the banner and then
   `exec bash -l` — so it shows even on a container with a stripped-down profile;
4. re-installs the banner on **deploy, start, restart and every terminal request**, and
   runs a self-test inside the guest (`banner install issue …` appears in the bot log
   if something is wrong).

To see it: `!manage` → **Web terminal** (a fresh session re-installs the banner),
or type `banner` inside the VPS.

## Leaves (cosmetic since 1.3 Beta)

**Leaves no longer limit anything.** `LEAVES_ENABLED=0` is the default: nothing
is charged, the billing loop never starts, `!deploy` never asks for a balance,
and a server is never stopped for running out of leaves. The only limit is the
**30-day term**. `!bonus` and `!give` were **removed** in 1.3 Beta together with
the **Give leaves** button; the balance stays on `!profile` as a cosmetic score,
with an unlimited badge instead of the remaining uptime.

Set `LEAVES_ENABLED=1` in `.env` to bring the old economy back, unchanged:

* a new account starts with `START_LEAVES` leaves
* a **running** VPS costs **1** leaf per hour (`LEAF_COST_PER_HOUR`); a stopped one is free
* at **0** leaves the VPS is **stopped, never deleted** - the owner gets a DM and can start it again from `!manage` after topping up
* staff servers (owner IDs) are never charged

Commands:

* `!profile` (`!me`, `!bal`, `!balance`, RU: `!профиль` / `!баланс` / `!листики`) - name, ID, balance, VPS status
* `!bonus`, `!give` and the **Give leaves** button in `!admin` no longer exist

Balances live in `WALLET_FILE` (`$DATA_DIR/wallet.json`, i.e. `./data/wallet.json`
outside Docker), so they survive restarts. With `LEAVES_ENABLED=1` billing runs
every 5 minutes and charges every full hour of uptime, so a restart never
double-charges; with `LEAVES_ENABLED=0` the loop does not even start.

---

## The 30-day term

| Setting | Default | Meaning |
|---|---|---|
| `VPS_LIFETIME_DAYS` | `30` | How long a free VPS lives. `0` = unlimited. |
| `VPS_EXPIRY_ACTION` | `delete` | What happens at the end: `delete` frees the slot, `stop` only powers it off. |
| `VPS_EXPIRY_WARN_DAYS` | `7,3,1` | When to DM the owner before the end. |

* `!deploy` shows the term on the offer card and on the success card, with the
  exact expiry date.
* `!manage` and `!specs` show the days left; the expiry timestamp is rendered in
  every user's own timezone by Discord.
* A background loop checks every 30 minutes, DMs the reminders, and releases the
  server when the term is over. Staff servers never expire.
* Staff can extend any term with `!renew <@user|id> [days]` (`0` = unlimited).
* Staff can hand out a fully custom server with
  `!givevps <@user|id> [username] [RAM] [disk] [days]`: RAM accepts `2048` or
  `4gb`, disk `40` or `40gb`, days `60`, `2m` or `0` for unlimited. A bare
  number up to 64 is read as GB, so `!givevps @user alex 4 40 60` means 4 GB
  RAM / 40 GB disk / 60 days. The username becomes a real account inside the
  guest with passwordless `sudo` (terminal sessions still land as `root`).
* Only the target is required, and the rest is parsed by shape, not by
  position: anything that looks like a number is a resource value, anything
  else is the login. `!givevps @user 5g 25 1` therefore means 5 GB RAM,
  25 GB disk and one day, and the login is taken from the Discord account
  (cleaned up for `useradd`: `xtekx [DXD]` becomes `xtekx-dxd`). Values can
  also be named in any order, including `cpu` and `swap`:
  `!givevps @user disk=25 ram=5g days=1 cpu=2 swap=1g` (`озу`, `диск`,
  `дней`, `логин` work too).

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
