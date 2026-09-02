"""Cloudy VPS Bot - free VPS hosting from Discord.

Version 1.4 Beta (dev): five regions with live ping, Ubuntu picker, personal
server panels, service status card, a deploy switch for staff and the
anti-abuse guard.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time

import discord
from discord.ext import commands, tasks

import embeds
import statuscard
from config import (
    ANIM_DELAY,
    BOT_BUILD,
    BOT_NAME,
    BOT_VERSION,
    COLOR_ERROR,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    EMOJI,
    LEAVES_ENABLED,
    OWNER_IDS,
    STATUS_IMAGE,
    VPS_EXPIRY_ACTION,
    VPS_EXPIRY_WARN_DAYS,
    VPS_LIFETIME_DAYS,
    is_owner,
)
from deploy_lock import DEPLOY_LOCK
from guard import GUARD
from i18n import LANGUAGES, LangStore, lang_label, normalize
from i18n import rules as rules_for
from i18n import t
from locations import LOCATIONS, tcp_ping, usage_from_records
from locations import plain_title as location_plain
from maintenance import MAINTENANCE
from moderation import BanStore, ModerationError
from plan_store import PLAN_STORE
from slots import MAX_SLOTS, MIN_SLOTS, SLOTS
from views import (
    AdminView,
    DeployView,
    LanguageView,
    ManageView,
    ProfileView,
    ServersView,
    deliver_sshx,
)
from vps_manager import VPSError, VPSManager
from wallet import WALLET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("cloudy.bot")

intents = discord.Intents.default()
intents.message_content = True  # required for prefix commands

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    intents=intents,
    help_command=None,
    activity=discord.Game(name=f"\u2601 Free VPS \u2022 {COMMAND_PREFIX}deploy"),
)

manager: VPSManager | None = None
bans = BanStore()
langs = LangStore()


def lang_of(user: discord.abc.User | int | None) -> str:
    """Language chosen by this user (falls back to DEFAULT_LANG)."""
    uid = user if isinstance(user, int) else getattr(user, "id", None)
    return langs.get(uid)


class Banned(commands.CheckFailure):
    pass


class UnderMaintenance(commands.CheckFailure):
    pass


# Commands that keep working while maintenance mode is ON.
MAINTENANCE_ALLOWED = {
    "about",
    "specs",
    "profile",
    "givevps",
    "rules",
    "lang",
    "help",
    "ping",
    "admin",
    "maintenance",
    "slots",
    "plan",
    "wipe",
    "status",
    "servers",
    "deploylock",
}


@bot.event
async def on_ready() -> None:
    global manager
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    log.info("%s v%s ready | owners: %s | bans: %d", BOT_NAME, BOT_VERSION, OWNER_IDS, bans.count)
    if manager is None:
        try:
            manager = VPSManager()
            await manager.ensure_image()
            log.info("Docker backend ready, VPS image available")
        except Exception as exc:
            log.error("Docker backend unavailable: %s", exc)
    # 1.4 Beta: adopt every guest that already runs on the host, so the
    # servers stay exactly where they were after an update or a rebuild.
    if manager is not None:
        try:
            report = await manager.sync_state()
            log.info(
                "servers restored: %s total (adopted %s, dropped %s, repaired %s)",
                report.get("total"),
                report.get("adopted"),
                report.get("dropped"),
                report.get("repaired"),
            )
        except Exception as exc:  # pragma: no cover
            log.warning("state sync failed: %s", exc)
        GUARD.attach(manager)
    if not presence_loop.is_running():
        presence_loop.start()
    if not locations_loop.is_running():
        locations_loop.start()
    if GUARD.enabled and not guard_loop.is_running():
        guard_loop.change_interval(seconds=max(30, int(GUARD.interval)))
        guard_loop.start()
        log.info("abuse guard on: scanning every %ss", GUARD.interval)
    # Leaves do not limit anything any more, so the billing loop only runs
    # when the old economy is explicitly turned back on (LEAVES_ENABLED=1).
    if WALLET.limits_active():
        if not billing_loop.is_running():
            billing_loop.start()
    else:
        log.info("leaf limits are disabled - uptime is free, billing loop off")
    if VPS_LIFETIME_DAYS > 0 and not expiry_loop.is_running():
        expiry_loop.start()
        log.info(
            "VPS term: %s days per server (expiry action: %s)",
            VPS_LIFETIME_DAYS,
            VPS_EXPIRY_ACTION,
        )


# Counting containers is a Docker round-trip, and the presence loop, !about,
# !slots and the admin panel all want the same numbers - so cache them for a
# few seconds instead of hammering the daemon.
_STATS_TTL = 5.0
_stats_cache: tuple[float, dict] = (0.0, {})


async def _stats(force: bool = False) -> dict:
    """Live counters, or an empty dict when Docker is unavailable."""
    global _stats_cache
    if manager is None:
        return {}
    cached_at, cached = _stats_cache
    now = time.monotonic()
    if not force and cached and now - cached_at < _STATS_TTL:
        return cached
    try:
        stats = await manager.stats()
    except Exception as exc:  # pragma: no cover
        log.warning("could not read VPS stats: %s", exc)
        return {}
    _stats_cache = (now, stats)
    return stats


# Rotating English status lines. Each entry is (ActivityType, template) and may
# use {used} {total} {free} {running} {stopped} {prefix}.
PRESENCE_LINES: list[tuple[discord.ActivityType, str]] = [
    (discord.ActivityType.playing, "\u2601 Free VPS \u2022 {prefix}deploy"),
    (discord.ActivityType.watching, "{used}/{total} slots \u2022 {running} online"),
    (discord.ActivityType.playing, "\u26a1 Free Ubuntu 22.04 VPS \u2022 {free} slots left"),
    (discord.ActivityType.watching, "\u25b8 {running} running \u2022 {stopped} stopped"),
    (discord.ActivityType.playing, "\u2601 Cloudy \u2022 free VPS for everyone"),
]

# Shown while Docker is still starting up or unavailable.
PRESENCE_FALLBACK = (
    discord.ActivityType.playing,
    "\u2601 Free VPS \u2022 {prefix}deploy",
)

_presence_index = 0


async def update_presence(rotate: bool = False) -> None:
    """Pretty English status line with the live slot counters."""
    global _presence_index
    stats = await _stats()
    if stats:
        if rotate:
            _presence_index = (_presence_index + 1) % len(PRESENCE_LINES)
        kind, template = PRESENCE_LINES[_presence_index % len(PRESENCE_LINES)]
        text = template.format(
            used=int(stats.get("used", 0)),
            total=int(stats.get("slots", 0)),
            free=int(stats.get("free", 0)),
            running=int(stats.get("running", 0)),
            stopped=int(stats.get("stopped", 0)),
            prefix=COMMAND_PREFIX,
        )
    else:
        kind, template = PRESENCE_FALLBACK
        text = template.format(prefix=COMMAND_PREFIX)

    try:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=kind, name=text[:128]),
        )
    except discord.HTTPException:
        pass


@tasks.loop(seconds=30)
async def presence_loop() -> None:
    await update_presence(rotate=True)


@presence_loop.before_loop
async def _before_presence_loop() -> None:
    await bot.wait_until_ready()


def _require_manager() -> VPSManager:
    if manager is None:
        raise VPSError(
            "The Docker backend is not available. Check the bot logs and make sure "
            "`/var/run/docker.sock` is mounted."
        )
    return manager


@bot.check
async def _block_banned(ctx: commands.Context) -> bool:
    if bans.is_banned(ctx.author.id):
        raise Banned()
    return True


@bot.check
async def _block_during_maintenance(ctx: commands.Context) -> bool:
    """While maintenance mode is on, only staff can use the hosting commands."""
    if not MAINTENANCE.enabled or is_owner(ctx.author.id):
        return True
    if ctx.command is not None and ctx.command.name in MAINTENANCE_ALLOWED:
        return True
    raise UnderMaintenance()


async def _resolve_user_id(ctx: commands.Context, raw: str) -> tuple[int, str]:
    """Accept a mention, a raw ID, or a name and return (id, display name)."""
    match = re.search(r"\d{15,25}", raw or "")
    if match:
        uid = int(match.group(0))
        user = bot.get_user(uid)
        if user is None:
            try:
                user = await bot.fetch_user(uid)
            except discord.HTTPException:
                user = None
        return uid, (str(user) if user else f"User {uid}")

    try:
        member = await commands.MemberConverter().convert(ctx, raw)
        return member.id, str(member)
    except commands.BadArgument as exc:
        raise ModerationError(
            "Could not find that user. Use a mention or a numeric ID, for example "
            f"`{COMMAND_PREFIX}ban 1264586393594630239 spam`."
        ) from exc


# ---------------------------------------------------------------------------
# Leaf billing: a running VPS costs LEAF_COST_PER_HOUR leaves per hour
# ---------------------------------------------------------------------------
@tasks.loop(minutes=5)
async def billing_loop() -> None:
    """Charge leaves for running servers and stop the ones that ran out.

    Nothing is ever deleted here - the container is only stopped, so the user
    can top up (daily bonus) and start it again from `!manage`.
    """
    if manager is None or not WALLET.limits_active():
        # LEAVES_ENABLED=0 -> uptime is free, there is nothing to charge.
        return
    try:
        records = manager.all_records()
    except Exception as exc:  # pragma: no cover
        log.warning("billing: cannot read state: %s", exc)
        return

    for record in records:
        owner_id = int(record.get("owner_id", 0) or 0)
        if not owner_id:
            continue
        try:
            info = await manager.get_info(owner_id)
        except VPSError:
            await WALLET.stop_billing(owner_id)
            continue
        except Exception as exc:  # pragma: no cover
            log.warning("billing: no info for %s: %s", owner_id, exc)
            continue

        if str(info.get("status", "")).lower() != "running":
            # A stopped VPS costs nothing.
            await WALLET.stop_billing(owner_id)
            continue
        if is_owner(owner_id):
            # Staff servers are free and unlimited.
            continue

        result = await WALLET.charge_due(owner_id, record.get("owner_name", ""))
        if result.get("charged"):
            log.info(
                "billing: charged %s leaves from %s (balance %s)",
                result["charged"],
                owner_id,
                result.get("balance"),
            )
        if not result.get("empty"):
            continue

        try:
            stopped = await manager.stop_if_running(owner_id)
        except Exception as exc:  # pragma: no cover
            log.warning("billing: cannot stop VPS of %s: %s", owner_id, exc)
            continue
        if not stopped:
            continue

        await WALLET.stop_billing(owner_id)
        log.info("billing: stopped VPS of %s (out of leaves)", owner_id)
        try:
            user = bot.get_user(owner_id) or await bot.fetch_user(owner_id)
            if user is not None:
                await user.send(
                    embed=embeds.out_of_leaves_embed(
                        info.get("name", "vps"), lang_of(owner_id)
                    )
                )
        except (discord.HTTPException, AttributeError):
            log.info("could not DM %s about the stopped VPS", owner_id)
        await update_presence()


@billing_loop.before_loop
async def _before_billing_loop() -> None:
    await bot.wait_until_ready()


async def _dm_user(user_id: int, embed: discord.Embed) -> bool:
    """Best-effort DM used by the background loops and by !renew."""
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        if user is None:
            return False
        await user.send(embed=embed)
        return True
    except (discord.HTTPException, AttributeError):
        log.info("could not DM %s", user_id)
        return False


# ---------------------------------------------------------------------------
# 30-day term: remind the owner, then release the slot when the term is over
# ---------------------------------------------------------------------------
@tasks.loop(minutes=30)
async def expiry_loop() -> None:
    """Warn owners before the term ends and clean up expired servers."""
    if manager is None or VPS_LIFETIME_DAYS <= 0:
        return
    try:
        rows = manager.terms()
    except Exception as exc:  # pragma: no cover
        log.warning("expiry: cannot read state: %s", exc)
        return

    marks = sorted({int(d) for d in VPS_EXPIRY_WARN_DAYS if int(d) > 0}, reverse=True)
    for row in rows:
        owner_id = int(row.get("owner_id") or 0)
        if not owner_id or not row.get("expires_ts"):
            continue
        if is_owner(owner_id):
            continue  # staff servers never expire

        lang = lang_of(owner_id)
        name = row.get("name") or "vps"

        if row.get("expired"):
            action = str(VPS_EXPIRY_ACTION or "delete").strip().lower()
            try:
                if action == "stop":
                    await manager.stop_if_running(owner_id)
                else:
                    await manager.delete_vps(owner_id)
            except Exception as exc:  # pragma: no cover
                log.warning("expiry: cannot release VPS of %s: %s", owner_id, exc)
                continue
            await WALLET.stop_billing(owner_id)
            log.info("expiry: %s VPS of %s (term is over)", action, owner_id)
            await _dm_user(
                owner_id,
                embeds.info_embed(
                    f"{EMOJI['clock']} {t(lang, 'expiry.expired_title')}",
                    t(
                        lang,
                        "expiry.stopped_desc"
                        if action == "stop"
                        else "expiry.deleted_desc",
                        name=name,
                        days=VPS_LIFETIME_DAYS,
                        prefix=COMMAND_PREFIX,
                    ),
                    COLOR_WARNING,
                ),
            )
            await update_presence()
            continue

        days_left = int(row.get("days_left") or 0)
        warned = {int(d) for d in (row.get("warned_days") or [])}
        for mark in marks:
            if days_left <= mark and mark not in warned:
                await manager.mark_warned(owner_id, mark)
                await _dm_user(
                    owner_id,
                    embeds.info_embed(
                        f"{EMOJI['clock']} {t(lang, 'expiry.warn_title')}",
                        t(
                            lang,
                            "expiry.warn_desc",
                            name=name,
                            days=max(1, days_left),
                            ts=int(row["expires_ts"]),
                            prefix=COMMAND_PREFIX,
                        ),
                        COLOR_WARNING,
                    ),
                )
                break


@expiry_loop.before_loop
async def _before_expiry_loop() -> None:
    await bot.wait_until_ready()


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------
@bot.command(name="deploy")
@commands.cooldown(1, 15, commands.BucketType.user)
async def deploy(ctx: commands.Context) -> None:
    """Region picker, Ubuntu picker and the live deployment."""
    lang = lang_of(ctx.author)
    # Staff can close !deploy for everyone with !deploylock.
    if DEPLOY_LOCK.closed and not is_owner(ctx.author.id):
        await ctx.reply(
            embed=embeds.deploy_closed_embed(DEPLOY_LOCK.state(), lang),
            mention_author=False,
        )
        return
    try:
        mgr = _require_manager()
        if await mgr.has_vps(ctx.author.id):
            info = await mgr.get_info(ctx.author.id)
            view = ManageView(mgr, ctx.author.id, bans, lang=lang)
            await view.refresh_buttons(info)
            msg = await ctx.reply(
                content=f"{EMOJI['cloud']} {t(lang, 'manage.already_own')}",
                embed=embeds.manage_embed(info, lang),
                view=view,
                mention_author=False,
            )
            view.message = msg
            return
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    # 1.3 Beta: leaves no longer gate anything - the server is granted for
    # VPS_LIFETIME_DAYS days free of charge. The wallet row is still created so
    # the profile card keeps working and so the old economy can be switched
    # back on with LEAVES_ENABLED=1 without any migration.
    await WALLET.ensure(ctx.author.id, str(ctx.author))
    if (
        WALLET.limits_active()
        and not is_owner(ctx.author.id)
        and not WALLET.can_run(ctx.author.id)
    ):
        await ctx.reply(
            embed=embeds.low_leaves_embed(WALLET.balance(ctx.author.id), lang),
            mention_author=False,
        )
        return

    stats = await _stats()
    # Refresh the region board (ping, load, auto-close / auto-reopen) right
    # before the picker is shown.
    try:
        await LOCATIONS.refresh(usage_from_records(mgr.all_records()))
    except Exception as exc:  # pragma: no cover
        log.warning("region refresh failed: %s", exc)
    view = DeployView(mgr, ctx.author.id, bans, lang=lang, stats=stats or None)
    msg = await ctx.reply(
        embed=view.render(ctx.author),
        view=view,
        mention_author=False,
    )
    view.message = msg


@bot.command(name="manage")
@commands.cooldown(1, 5, commands.BucketType.user)
async def manage(ctx: commands.Context) -> None:
    """Server info + power controls."""
    lang = lang_of(ctx.author)
    try:
        mgr = _require_manager()
        info = await mgr.get_info(ctx.author.id)
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    view = ManageView(mgr, ctx.author.id, bans, lang=lang)
    await view.refresh_buttons(info)
    msg = await ctx.reply(
        embed=embeds.manage_embed(info, lang), view=view, mention_author=False
    )
    view.message = msg


@bot.command(
    name="sshx",
    aliases=["web", "browser", "\u0432\u0435\u0431", "\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b"],
)
async def sshx_cmd(ctx: commands.Context) -> None:
    """Second access method: browser terminal link (sshx.io), DM only."""
    lang = lang_of(ctx.author)
    try:
        mgr = _require_manager()
        async with ctx.typing():
            link = await mgr.get_sshx(ctx.author.id, force_new=True, lang=lang)
            info = await mgr.get_info(ctx.author.id)
    except asyncio.TimeoutError:
        await ctx.reply(
            embed=embeds.error_embed(t(lang, "sshx.timeout"), lang=lang),
            mention_author=False,
        )
        return
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    sent = await deliver_sshx(ctx.author, info, link, None, lang)
    if sent:
        await ctx.reply(
            embed=embeds.info_embed(
                f"{EMOJI['mail']} {t(lang, 'sshx.check_dms_title')}",
                t(lang, "sshx.check_dms_desc"),
                COLOR_PRIMARY,
            ),
            mention_author=False,
        )
    else:
        await ctx.reply(embed=embeds.dm_failed_embed(lang), mention_author=False)


# ---------------------------------------------------------------------------
# !specs - username / RAM / disk of the VPS
# ---------------------------------------------------------------------------
@bot.command(
    name="specs",
    aliases=[
        "vps",
        "\u0441\u043f\u0435\u043a\u0438",
        "\u0438\u043d\u0444\u043e",
        "\u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0438",
    ],
)
@commands.cooldown(1, 5, commands.BucketType.user)
async def specs_cmd(ctx: commands.Context, target: str = "") -> None:
    """!specs [@user] - VPS username, RAM, disk, vCPU, uptime and term left."""
    lang = lang_of(ctx.author)
    target_id = ctx.author.id
    target_user: discord.abc.User | None = ctx.author

    if target and is_owner(ctx.author.id):
        try:
            target_id, _name = await _resolve_user_id(ctx, target)
        except ModerationError as exc:
            await ctx.reply(
                embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
            )
            return
        target_user = bot.get_user(target_id)

    try:
        mgr = _require_manager()
        if not await mgr.has_vps(target_id):
            await ctx.reply(
                embed=embeds.error_embed(
                    t(lang, "specs.no_vps", prefix=COMMAND_PREFIX), lang=lang
                ),
                mention_author=False,
            )
            return
        async with ctx.typing():
            info = await mgr.get_info(target_id)
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    await ctx.reply(
        embed=embeds.specs_embed(info, target_user, lang), mention_author=False
    )


@bot.command(name="rules")
async def rules_cmd(ctx: commands.Context) -> None:
    await ctx.reply(embed=embeds.rules_embed(lang_of(ctx.author)), mention_author=False)


@bot.command(name="help")
async def help_cmd(ctx: commands.Context) -> None:
    await ctx.reply(
        embed=embeds.help_embed(
            COMMAND_PREFIX, owner=is_owner(ctx.author.id), lang=lang_of(ctx.author)
        ),
        mention_author=False,
    )


@bot.command(
    name="about",
    aliases=[
        "info",
        "bot",
        "\u043e\u0431\u043e\u0442\u0435",
        "\u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435",
    ],
)
async def about_cmd(ctx: commands.Context) -> None:
    """!about - show what the bot is and what the free VPS includes."""
    stats = await _stats()
    await ctx.reply(
        embed=embeds.about_embed(lang_of(ctx.author), stats=stats or None),
        mention_author=False,
    )


@bot.command(name="lang", aliases=["language", "\u044f\u0437\u044b\u043a", "lang\u0443"])
async def lang_cmd(ctx: commands.Context, choice: str = "") -> None:
    """!lang [ru|en] - switch the bot language, or open the picker."""
    current = lang_of(ctx.author)

    if choice:
        wanted = choice.lower().strip()
        aliases = {
            "ru": "ru",
            "rus": "ru",
            "russian": "ru",
            "\u0440\u0443\u0441": "ru",
            "\u0440\u0443\u0441\u0441\u043a\u0438\u0439": "ru",
            "en": "en",
            "eng": "en",
            "english": "en",
            "\u0430\u043d\u0433": "en",
            "\u0430\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u0438\u0439": "en",
        }
        if wanted not in aliases:
            await ctx.reply(
                embed=embeds.error_embed(
                    f"`{COMMAND_PREFIX}lang ru` \u2022 `{COMMAND_PREFIX}lang en`",
                    lang=current,
                ),
                mention_author=False,
            )
            return
        new_lang = langs.set(ctx.author.id, aliases[wanted])
        await ctx.reply(
            embed=embeds.language_changed_embed(new_lang), mention_author=False
        )
        return

    view = LanguageView(ctx.author.id, langs, current)
    msg = await ctx.reply(
        embed=embeds.language_embed(current), view=view, mention_author=False
    )
    view.message = msg


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    lang = lang_of(ctx.author)
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['spark']} {t(lang, 'ping.title')}",
            t(lang, "ping.desc", ms=round(bot.latency * 1000)),
        ),
        mention_author=False,
    )


@bot.command(name="destroy")
@commands.cooldown(1, 30, commands.BucketType.user)
async def destroy(ctx: commands.Context) -> None:
    """Permanently delete your VPS."""
    lang = lang_of(ctx.author)
    try:
        mgr = _require_manager()
        await mgr.delete_vps(ctx.author.id)
        await WALLET.stop_billing(ctx.author.id)
        await update_presence()
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['check']} {t(lang, 'destroy.title')}",
            t(lang, "destroy.desc", prefix=COMMAND_PREFIX),
        ),
        mention_author=False,
    )


# ---------------------------------------------------------------------------
# Staff commands (owners only)
# ---------------------------------------------------------------------------
def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if not is_owner(ctx.author.id):
            raise commands.CheckFailure("staff_only")
        return True

    return commands.check(predicate)


@bot.command(name="ban")
@owner_only()
async def ban_cmd(ctx: commands.Context, target: str = "", *, reason: str = "") -> None:
    """!ban <@user|id> [reason] - block a user and stop their server."""
    lang = lang_of(ctx.author)
    if not target:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "help.usage_ban", prefix=COMMAND_PREFIX),
                title=t(lang, "help.missing_user"),
                lang=lang,
            ),
            mention_author=False,
        )
        return

    try:
        user_id, user_name = await _resolve_user_id(ctx, target)
        record = await bans.ban(
            user_id=user_id,
            reason=reason.strip(),
            moderator_id=ctx.author.id,
            moderator_name=str(ctx.author),
            user_name=user_name,
        )
    except ModerationError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    stopped = False
    if manager is not None:
        try:
            stopped = await manager.stop_if_running(user_id)
        except Exception as exc:  # pragma: no cover
            log.warning("could not stop server of %s: %s", user_id, exc)

    # Tell the user privately why they lost access (in *their* language).
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(embed=embeds.banned_notice_embed(record, lang_of(user_id)))
    except discord.HTTPException:
        pass

    await ctx.reply(embed=embeds.ban_embed(record, stopped, lang), mention_author=False)


@bot.command(name="unban")
@owner_only()
async def unban_cmd(ctx: commands.Context, target: str = "") -> None:
    """!unban <@user|id> - restore access."""
    lang = lang_of(ctx.author)
    if not target:
        await ctx.reply(
            embed=embeds.error_embed(
                f"`{COMMAND_PREFIX}unban <@user|id>`",
                title=t(lang, "help.missing_user"),
                lang=lang,
            ),
            mention_author=False,
        )
        return

    try:
        user_id, _ = await _resolve_user_id(ctx, target)
        record = await bans.unban(user_id)
    except ModerationError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        ulang = lang_of(user_id)
        await user.send(
            embed=embeds.info_embed(
                f"{EMOJI['check']} {t(ulang, 'mod.unbanned_title')}",
                t(ulang, "help.rules", count=len(rules_for(ulang)))
                + f"\n`{COMMAND_PREFIX}rules`",
            )
        )
    except discord.HTTPException:
        pass

    await ctx.reply(embed=embeds.unban_embed(record, lang), mention_author=False)


@bot.command(name="bans")
@owner_only()
async def bans_cmd(ctx: commands.Context) -> None:
    await ctx.reply(
        embed=embeds.bans_list_embed(bans.all_bans(), lang_of(ctx.author)),
        mention_author=False,
    )


@bot.command(name="servers", aliases=["myvps", "\u043c\u043e\u0438", "\u0441\u0435\u0440\u0432\u0435\u0440\u0430"])
async def servers_cmd(ctx: commands.Context, *, args: str = "") -> None:
    """Your machines: pick one in the menu to open its panel.

    Staff can still see the global list with `!servers all`.
    """
    lang = lang_of(ctx.author)
    try:
        mgr = _require_manager()
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    wants_all = (args or "").strip().lower() in ("all", "\u0432\u0441\u0435", "*")
    if not (wants_all and is_owner(ctx.author.id)):
        stats = await _stats()
        records = mgr.records_of(ctx.author.id)
        view = ServersView(
            mgr,
            ctx.author.id,
            bans,
            lang=lang,
            records=records,
            stats=stats or None,
        )
        msg = await ctx.reply(
            embed=view.render(ctx.author),
            view=view if records else None,
            mention_author=False,
        )
        view.message = msg
        return

    stats = await _stats()
    header = embeds.capacity_line(stats, lang) + "\n" if stats else ""

    records = mgr.all_records()
    if not records:
        await ctx.reply(
            embed=embeds.info_embed(
                f"{EMOJI['cloud']} Servers", header + "No servers deployed yet."
            ),
            mention_author=False,
        )
        return

    lines = [
        f"`{r['name']}` \u2022 <@{r['owner_id']}> \u2022 {r['ram_mb']} MB \u2022 "
        f"<t:{int(r['created_ts'])}:R>"
        for r in records[:25]
    ]
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['cloud']} Servers ({len(records)})", header + "\n".join(lines)
        ),
        mention_author=False,
    )


@bot.command(name="admin", aliases=["panel", "\u0430\u0434\u043c\u0438\u043d", "\u043f\u0430\u043d\u0435\u043b\u044c"])
@owner_only()
async def admin_cmd(ctx: commands.Context) -> None:
    """!admin - staff panel: maintenance switch and VPS slots."""
    lang = lang_of(ctx.author)
    view = AdminView(ctx.author.id, MAINTENANCE, manager, bans, lang=lang, slots=SLOTS)
    embed = await view.build_embed()
    view.sync_buttons()
    msg = await ctx.reply(embed=embed, view=view, mention_author=False)
    view.message = msg


@bot.command(
    name="maintenance",
    aliases=["maint", "\u0442\u0435\u0445\u0440\u0430\u0431\u043e\u0442\u044b", "\u0442\u0435\u0445"],
)
@owner_only()
async def maintenance_cmd(
    ctx: commands.Context, mode: str = "", *, reason: str = ""
) -> None:
    """!maintenance on [reason] | off - close or open the bot for everyone."""
    lang = lang_of(ctx.author)
    choice = (mode or "").lower().strip()

    on_words = {"on", "1", "true", "enable", "\u0432\u043a\u043b", "\u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c", "\u0434\u0430"}
    off_words = {"off", "0", "false", "disable", "\u0432\u044b\u043a\u043b", "\u0432\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c", "\u043d\u0435\u0442"}

    if choice in on_words:
        state = await MAINTENANCE.enable(
            ctx.author.id, str(ctx.author), reason=reason.strip()
        )
    elif choice in off_words:
        state = await MAINTENANCE.disable(ctx.author.id, str(ctx.author))
    elif not choice:
        # No argument: show the panel instead of guessing.
        view = AdminView(
            ctx.author.id, MAINTENANCE, manager, bans, lang=lang, slots=SLOTS
        )
        embed = await view.build_embed()
        view.sync_buttons()
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg
        return
    else:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "admin.usage", prefix=COMMAND_PREFIX), lang=lang
            ),
            mention_author=False,
        )
        return

    await ctx.reply(
        embed=embeds.maintenance_toggled_embed(state, lang), mention_author=False
    )


@bot.command(name="slots", aliases=["capacity", "\u0441\u043b\u043e\u0442\u044b"])
async def slots_cmd(ctx: commands.Context, action: str = "", value: str = "") -> None:
    """!slots - show capacity. Staff: !slots +1 | -1 | set N."""
    lang = lang_of(ctx.author)
    try:
        mgr = _require_manager()
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    raw = (action or "").strip().lower()

    # Everyone may look at the counters.
    if not raw:
        stats = await mgr.stats()
        await ctx.reply(embed=embeds.slots_embed(stats, lang), mention_author=False)
        return

    # Changing the limit is staff only.
    if not is_owner(ctx.author.id):
        raise commands.CheckFailure("staff_only")

    old = SLOTS.total
    target: int | None = None

    if raw in {"set", "=", "\u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c"}:
        try:
            target = int(value)
        except (TypeError, ValueError):
            target = None
    elif raw in {"+", "add", "up", "\u0431\u043e\u043b\u044c\u0448\u0435"}:
        target = old + (int(value) if value.lstrip("+-").isdigit() else 1)
    elif raw in {"-", "remove", "down", "\u043c\u0435\u043d\u044c\u0448\u0435"}:
        target = old - (int(value) if value.lstrip("+-").isdigit() else 1)
    elif raw.lstrip("+-").isdigit():
        # "+1" / "-2" are relative, a bare number is absolute.
        target = old + int(raw) if raw[0] in "+-" else int(raw)

    if target is None:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "slots.usage", prefix=COMMAND_PREFIX), lang=lang
            ),
            mention_author=False,
        )
        return

    if target < MIN_SLOTS or target > MAX_SLOTS:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "slots.limit", min=MIN_SLOTS, max=MAX_SLOTS), lang=lang
            ),
            mention_author=False,
        )
        return

    await SLOTS.set_total(target, ctx.author.id, str(ctx.author))
    stats = await mgr.stats()
    await update_presence()
    await ctx.reply(
        embed=embeds.slots_changed_embed(old, stats, lang), mention_author=False
    )
    await ctx.send(embed=embeds.slots_embed(stats, lang))


@bot.command(
    name="wipe",
    aliases=[
        "delvps",
        "forcedestroy",
        "\u0443\u0434\u0430\u043b\u0438\u0442\u044c",
        "\u0441\u043d\u0435\u0441\u0442\u0438",
    ],
)
@owner_only()
async def wipe_cmd(ctx: commands.Context, target: str = "", *, reason: str = "") -> None:
    """!wipe <@user|id> [reason] - delete somebody else's VPS and free the slot."""
    lang = lang_of(ctx.author)
    if not target:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "wipe.usage", prefix=COMMAND_PREFIX), lang=lang
            ),
            mention_author=False,
        )
        return

    try:
        mgr = _require_manager()
        user_id, _name = await _resolve_user_id(ctx, target)
    except (VPSError, ModerationError) as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    if not await mgr.has_vps(user_id):
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "wipe.none", user=user_id), lang=lang
            ),
            mention_author=False,
        )
        return

    try:
        await mgr.delete_vps(user_id)
        await WALLET.stop_billing(user_id)
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    # Tell the owner what happened, in their own language.
    try:
        victim = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await victim.send(
            embed=embeds.vps_wiped_notice_embed(reason, lang_of(user_id))
        )
    except (discord.HTTPException, AttributeError):
        log.info("could not DM %s about the deleted VPS", user_id)

    stats = await mgr.stats()
    await update_presence()
    await ctx.reply(
        embed=embeds.vps_wiped_embed(user_id, stats, lang), mention_author=False
    )


# ---------------------------------------------------------------------------
# Profile (leaves are cosmetic since 1.3 Beta)
# ---------------------------------------------------------------------------
@bot.command(
    name="profile",
    aliases=[
        "me",
        "bal",
        "balance",
        "\u043f\u0440\u043e\u0444\u0438\u043b\u044c",
        "\u0431\u0430\u043b\u0430\u043d\u0441",
        "\u043b\u0438\u0441\u0442\u0438\u043a\u0438",
    ],
)
@commands.cooldown(1, 5, commands.BucketType.user)
async def profile_cmd(ctx: commands.Context, target: str = "") -> None:
    """!profile - name, ID, VPS and the (cosmetic) leaf balance."""
    lang = lang_of(ctx.author)
    user: discord.abc.User = ctx.author

    # Staff may look at somebody else's profile: !profile @user
    if target and is_owner(ctx.author.id):
        try:
            user_id, _name = await _resolve_user_id(ctx, target)
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        except (ModerationError, discord.HTTPException) as exc:
            await ctx.reply(
                embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
            )
            return

    await WALLET.ensure(user.id, str(user))
    view = ProfileView(user, manager, lang=lang)
    embed = await view.build_embed()
    view.sync_buttons()
    msg = await ctx.reply(embed=embed, view=view, mention_author=False)
    view.message = msg


# ---------------------------------------------------------------------------
# VPS term (staff)
# ---------------------------------------------------------------------------
@bot.command(
    name="renew",
    aliases=["extend", "\u043f\u0440\u043e\u0434\u043b\u0438\u0442\u044c"],
)
@owner_only()
async def renew_cmd(
    ctx: commands.Context, target: str = "", days: str = ""
) -> None:
    """!renew <@user|id> [days] - extend a VPS term (`0` makes it unlimited)."""
    lang = lang_of(ctx.author)
    usage = embeds.error_embed(
        t(lang, "renew.usage", prefix=COMMAND_PREFIX, days=VPS_LIFETIME_DAYS),
        lang=lang,
    )
    if not target:
        await ctx.reply(embed=usage, mention_author=False)
        return

    try:
        user_id, _name = await _resolve_user_id(ctx, target)
    except ModerationError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    amount: float | None = None
    if days:
        parsed = _plan_number(days)
        if parsed is None or parsed < 0:
            await ctx.reply(embed=usage, mention_author=False)
            return
        amount = parsed

    try:
        mgr = _require_manager()
        expires = await mgr.renew(user_id, amount)
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    granted = int(VPS_LIFETIME_DAYS if amount is None else amount)
    body = (
        t(lang, "renew.done", user=user_id, days=granted, ts=int(expires))
        if expires > 0
        else t(lang, "renew.unlimited", user=user_id)
    )
    await ctx.reply(
        embed=embeds.info_embed(
            f"{EMOJI['gift']} {t(lang, 'renew.title')}", body, COLOR_PRIMARY
        ),
        mention_author=False,
    )

    if expires > 0:
        user_lang = lang_of(user_id)
        await _dm_user(
            user_id,
            embeds.info_embed(
                f"{EMOJI['gift']} {t(user_lang, 'renew.notice_title')}",
                t(user_lang, "renew.notice", days=granted, ts=int(expires)),
                COLOR_PRIMARY,
            ),
        )


# ---------------------------------------------------------------------------
# Hand out a ready VPS (staff)
# ---------------------------------------------------------------------------
GRANT_MIN_RAM_MB = 128
GRANT_MAX_RAM_MB = 262_144
GRANT_MAX_DISK_GB = 4_096
GRANT_MAX_DAYS = 3_650
GRANT_MAX_CPU = 64

_AMOUNT_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([a-z\u0430-\u044f\u0451]*)$")


def _parse_amount(raw: str) -> tuple[float, str] | None:
    """Split `4gb` / `40 \u0413\u0411` / `60` into (value, unit)."""
    match = _AMOUNT_RE.match(str(raw or "").strip().lower())
    if match is None:
        return None
    return float(match.group(1).replace(",", ".")), match.group(2)


def _parse_ram_mb(raw: str, default: int) -> int | None:
    if not str(raw or "").strip():
        return default
    parsed = _parse_amount(raw)
    if parsed is None:
        return None
    value, unit = parsed
    if unit.startswith(("t", "\u0442")):
        value *= 1024 * 1024
    elif unit.startswith(("g", "\u0433")):
        value *= 1024
    elif not unit and value <= 64:
        # "!givevps @user alex 4 40 30" - 4 obviously means 4 GB, not 4 MB.
        value *= 1024
    return int(round(value))


def _parse_disk_gb(raw: str, default: int) -> int | None:
    if not str(raw or "").strip():
        return default
    parsed = _parse_amount(raw)
    if parsed is None:
        return None
    value, unit = parsed
    if unit.startswith(("m", "\u043c")):
        value /= 1024
    elif unit.startswith(("t", "\u0442")):
        value *= 1024
    return int(round(value))


def _parse_days(raw: str, default: int) -> int | None:
    if not str(raw or "").strip():
        return default
    parsed = _parse_amount(raw)
    if parsed is None:
        return None
    value, unit = parsed
    if unit.startswith(("y", "\u0433")):  # years / \u0433\u043e\u0434
        value *= 365
    elif unit.startswith(("m", "\u043c")):  # months / \u043c\u0435\u0441\u044f\u0446
        value *= 30
    elif unit.startswith(("w", "\u043d")):  # weeks / \u043d\u0435\u0434\u0435\u043b\u044f
        value *= 7
    return int(round(value))


# Optional argument names for !givevps, so staff can be explicit when the
# order is not obvious: `!givevps @user ram=5g disk=25 days=1 cpu=2`.
_GRANT_KEYS: dict[str, str] = {
    "user": "login",
    "login": "login",
    "username": "login",
    "name": "login",
    "\u044e\u0437\u0435\u0440": "login",
    "\u044e\u0437\u0435\u0440\u043d\u0435\u0439\u043c": "login",
    "\u043b\u043e\u0433\u0438\u043d": "login",
    "\u0438\u043c\u044f": "login",
    "ram": "ram",
    "mem": "ram",
    "memory": "ram",
    "\u043e\u0437\u0443": "ram",
    "\u0440\u0430\u043c": "ram",
    "\u043f\u0430\u043c\u044f\u0442\u044c": "ram",
    "disk": "disk",
    "hdd": "disk",
    "ssd": "disk",
    "storage": "disk",
    "\u0434\u0438\u0441\u043a": "disk",
    "days": "days",
    "day": "days",
    "term": "days",
    "\u0434\u043d\u0435\u0439": "days",
    "\u0434\u043d\u0438": "days",
    "\u0434\u0435\u043d\u044c": "days",
    "\u0441\u0440\u043e\u043a": "days",
    "cpu": "cpu",
    "vcpu": "cpu",
    "cores": "cpu",
    "\u044f\u0434\u0440\u0430": "cpu",
    "swap": "swap",
    "\u0441\u0432\u043e\u043f": "swap",
}


def _parse_grant_args(args: tuple[str, ...]) -> dict[str, str]:
    """Order-free parsing for !givevps - only the target is required.

    A token that looks like a number (with or without a unit) is a resource
    value, anything else is the login. That is why `!givevps @user 5g 25 1`
    now means "5 GB RAM, 25 GB disk, 1 day" instead of trying to create an
    account called `5g`. Named values work too, in any order:
    `!givevps @user disk=25 ram=5g days=1`.
    """
    parsed: dict[str, str] = {}
    numbers: list[str] = []
    for raw in args:
        token = str(raw or "").strip().strip(",")
        if not token:
            continue

        field = ""
        value = token
        for sep in ("=", ":"):
            if sep in token:
                head, _, tail = token.partition(sep)
                field = _GRANT_KEYS.get(head.strip().lower(), "")
                if field and tail.strip():
                    value = tail.strip()
                else:
                    field = ""
                break
        if field:
            parsed[field] = value
            continue

        if _parse_amount(token) is not None:
            numbers.append(token)
        elif "login" not in parsed:
            parsed["login"] = token

    # Bare numbers keep the documented order: RAM, disk, days - skipping
    # whatever was already given by name.
    free = [field for field in ("ram", "disk", "days") if field not in parsed]
    for field, value in zip(free, numbers):
        parsed[field] = value
    return parsed


def _grant_stages(login: str, ram_mb: int, disk_gb: int) -> list[tuple[str, int, str]]:
    """Deployment animation with the granted numbers in the log."""
    return [
        ("stage.alloc", 8, f"\u001b[0;36m[cloudy]\u001b[0m reserving {ram_mb} MB RAM"),
        ("stage.image", 22, "\u001b[0;36m[image]\u001b[0m ubuntu:22.04 \u2192 ok"),
        ("stage.disk", 36, f"\u001b[0;36m[disk]\u001b[0m formatting {disk_gb} GB volume"),
        ("stage.boot", 52, "\u001b[0;36m[boot]\u001b[0m kernel handoff \u2192 init"),
        ("stage.net", 66, "\u001b[0;36m[net]\u001b[0m bridge attached, DNS ready"),
        ("stage.apt", 78, "\u001b[0;36m[apt]\u001b[0m curl git htop python3 tmux"),
        ("stage.user", 89, f"\u001b[0;36m[user]\u001b[0m useradd {login} \u2192 sudo"),
        ("stage.health", 97, "\u001b[0;32m[ok]\u001b[0m all services healthy"),
    ]


@bot.command(
    name="givevps",
    aliases=[
        "grantvps",
        "vpsgive",
        "\u0432\u044b\u0434\u0430\u0442\u044c",
        "\u0432\u044b\u0434\u0430\u0442\u044cvps",
        "\u0432\u044b\u0434\u0430\u0442\u044c\u0432\u043f\u0441",
    ],
)
@owner_only()
async def givevps_cmd(ctx: commands.Context, target: str = "", *args: str) -> None:
    """!givevps <@user|id> [username] [RAM] [disk] [days] - hand out a VPS.

    Only the target is required. `!givevps @user 5g 25 1` grants 5 GB RAM,
    25 GB disk and one day, and the login is taken from the Discord account.
    """
    lang = lang_of(ctx.author)
    plan = PLAN_STORE.plan()
    usage = embeds.error_embed(
        t(
            lang,
            "givevps.usage",
            prefix=COMMAND_PREFIX,
            ram=int(plan["ram_mb"]),
            disk=int(plan["disk_gb"]),
            days=int(VPS_LIFETIME_DAYS),
        ),
        lang=lang,
    )
    if not target:
        await ctx.reply(embed=usage, mention_author=False)
        return

    try:
        mgr = _require_manager()
        user_id, name = await _resolve_user_id(ctx, target)
    except (ModerationError, VPSError) as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    # Everything after the target is optional and order-free, so a missing
    # username no longer turns the RAM value into a login.
    opts = _parse_grant_args(args)

    login = ""
    if opts.get("login"):
        login = VPSManager.normalize_login(opts["login"], fallback="")
        if not login:
            await ctx.reply(
                embed=embeds.error_embed(t(lang, "givevps.bad_login"), lang=lang),
                mention_author=False,
            )
            return

    ram_mb = _parse_ram_mb(opts.get("ram", ""), int(plan["ram_mb"]))
    if ram_mb is None or not GRANT_MIN_RAM_MB <= ram_mb <= GRANT_MAX_RAM_MB:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "givevps.bad_ram", max=GRANT_MAX_RAM_MB), lang=lang
            ),
            mention_author=False,
        )
        return

    disk_gb = _parse_disk_gb(opts.get("disk", ""), int(plan["disk_gb"]))
    if disk_gb is None or not 1 <= disk_gb <= GRANT_MAX_DISK_GB:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "givevps.bad_disk", max=GRANT_MAX_DISK_GB), lang=lang
            ),
            mention_author=False,
        )
        return

    term = _parse_days(opts.get("days", ""), int(VPS_LIFETIME_DAYS))
    if term is None or not 0 <= term <= GRANT_MAX_DAYS:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "givevps.bad_days", max=GRANT_MAX_DAYS), lang=lang
            ),
            mention_author=False,
        )
        return

    cpu_cores: float | None = None
    if opts.get("cpu"):
        parsed_cpu = _parse_amount(opts["cpu"])
        if parsed_cpu is None or not 0.1 <= parsed_cpu[0] <= GRANT_MAX_CPU:
            await ctx.reply(
                embed=embeds.error_embed(
                    t(lang, "givevps.bad_cpu", max=GRANT_MAX_CPU), lang=lang
                ),
                mention_author=False,
            )
            return
        cpu_cores = round(parsed_cpu[0], 2)

    swap_mb: int | None = None
    if opts.get("swap"):
        swap_mb = _parse_ram_mb(opts["swap"], 0)
        if swap_mb is None or not 0 <= swap_mb <= GRANT_MAX_RAM_MB:
            await ctx.reply(
                embed=embeds.error_embed(
                    t(lang, "givevps.bad_swap", max=GRANT_MAX_RAM_MB), lang=lang
                ),
                mention_author=False,
            )
            return

    target_user: discord.abc.User | None = bot.get_user(user_id)
    if target_user is None:
        try:
            target_user = await bot.fetch_user(user_id)
        except discord.HTTPException:
            target_user = None
    owner_name = str(target_user) if target_user is not None else name
    target_lang = lang_of(user_id)

    if not login:
        # No username given: build a valid Linux login out of the Discord
        # account instead of bothering the staff about it.
        login = VPSManager.suggest_login(
            getattr(target_user, "name", ""), name, f"cloudy{user_id % 10000}"
        )

    # Same look as !deploy: a live progress card while the container boots.
    message = await ctx.reply(
        embed=embeds.deploy_progress_embed(t(lang, "progress.init"), 3, [], lang),
        mention_author=False,
    )
    task = asyncio.create_task(
        mgr.create_custom(
            user_id,
            owner_name,
            login=login,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            cpu_cores=cpu_cores,
            swap_mb=swap_mb,
            days=term,
            lang=target_lang,
        )
    )

    log_lines: list[str] = []
    record: dict = {}
    try:
        for stage_key, percent, line in _grant_stages(login, ram_mb, disk_gb):
            log_lines.append(line)
            await message.edit(
                embed=embeds.deploy_progress_embed(
                    t(lang, stage_key), percent, log_lines, lang
                )
            )
            await asyncio.sleep(ANIM_DELAY)
        record = await task
    except VPSError as exc:
        await message.edit(embed=embeds.error_embed(str(exc), lang=lang))
        return
    except Exception as exc:  # pragma: no cover
        log.exception("givevps failed")
        await message.edit(
            embed=embeds.error_embed(
                t(lang, "givevps.failed", error=str(exc)[:400]), lang=lang
            )
        )
        return

    info = await mgr.get_info(user_id)
    granted_login = str(record.get("login") or info.get("login") or "root")
    await message.edit(
        embed=embeds.deploy_progress_embed(
            t(lang, "progress.finishing"), 100, log_lines, lang
        )
    )
    await asyncio.sleep(0.6)
    await message.edit(
        embed=embeds.grant_vps_embed(info, user_id, granted_login, lang)
    )
    await update_presence()

    # The new owner gets their own control panel, in DMs.
    if target_user is None:
        return
    try:
        view = ManageView(mgr, user_id, bans, lang=target_lang)
        await view.refresh_buttons(info)
        dm = await target_user.send(
            embed=embeds.grant_vps_notice_embed(info, granted_login, target_lang),
            view=view,
        )
        view.message = dm
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        log.info("could not DM %s about the granted VPS", user_id)
        await ctx.send(
            embed=embeds.info_embed(
                f"{EMOJI['mail']} {t(lang, 'givevps.title')}",
                t(lang, "givevps.no_dm"),
                COLOR_WARNING,
            )
        )


# ---------------------------------------------------------------------------
# Free VPS resources (staff)
# ---------------------------------------------------------------------------
def _plan_number(value: str) -> float | None:
    """Parse "2048", "2gb", "1,5" into a number (None when it is not one)."""
    raw = str(value or "").strip().lower().replace(",", ".")
    for junk in ("mib", "gib", "mb", "gb", "vcpu", "cpu", "g", "m"):
        if raw.endswith(junk):
            raw = raw[: -len(junk)].strip()
            break
    try:
        return float(raw)
    except ValueError:
        return None


@bot.command(
    name="plan",
    aliases=[
        "resources",
        "\u0440\u0435\u0441\u0443\u0440\u0441\u044b",
        "\u0442\u0430\u0440\u0438\u0444",
    ],
)
@owner_only()
async def plan_cmd(ctx: commands.Context, action: str = "", value: str = "") -> None:
    """!plan - show the free plan. !plan ram 2048 | disk 20 | cpu 2 | reset."""
    lang = lang_of(ctx.author)
    raw = (action or "").strip().lower()

    if not raw:
        await ctx.reply(embed=embeds.plan_embed(lang), mention_author=False)
        return

    old = PLAN_STORE.plan()

    if raw in {"reset", "default", "\u0441\u0431\u0440\u043e\u0441"}:
        new = await PLAN_STORE.reset(ctx.author.id, str(ctx.author))
    else:
        number = _plan_number(value)
        if number is None:
            await ctx.reply(
                embed=embeds.error_embed(
                    t(lang, "plan.bad_value", prefix=COMMAND_PREFIX), lang=lang
                ),
                mention_author=False,
            )
            return

        moderator = {"moderator_id": ctx.author.id, "moderator_name": str(ctx.author)}
        if raw in {
            "ram",
            "memory",
            "mem",
            "\u043e\u0437\u0443",
            "\u043f\u0430\u043c\u044f\u0442\u044c",
        }:
            new = await PLAN_STORE.update(ram_mb=number, **moderator)
        elif raw in {"disk", "storage", "\u0434\u0438\u0441\u043a"}:
            new = await PLAN_STORE.update(disk_gb=number, **moderator)
        elif raw in {
            "cpu",
            "cores",
            "vcpu",
            "\u043f\u0440\u043e\u0446\u0435\u0441\u0441\u043e\u0440",
        }:
            new = await PLAN_STORE.update(cpu_cores=number, **moderator)
        elif raw == "swap":
            new = await PLAN_STORE.update(swap_mb=number, **moderator)
        else:
            await ctx.reply(
                embed=embeds.error_embed(
                    t(lang, "plan.usage", prefix=COMMAND_PREFIX), lang=lang
                ),
                mention_author=False,
            )
            return

    await ctx.reply(
        embed=embeds.plan_changed_embed(old, new, lang), mention_author=False
    )
    await ctx.send(embed=embeds.plan_embed(lang))


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return

    lang = lang_of(ctx.author)

    if isinstance(error, Banned):
        record = bans.get(ctx.author.id) or {}
        try:
            await ctx.author.send(embed=embeds.banned_notice_embed(record, lang))
        except discord.HTTPException:
            await ctx.reply(
                embed=embeds.error_embed(
                    t(lang, "mod.you_banned_desc"),
                    title=t(lang, "mod.you_banned_title"),
                    lang=lang,
                ),
                mention_author=False,
            )
        return

    if isinstance(error, UnderMaintenance):
        await ctx.reply(
            embed=embeds.maintenance_embed(MAINTENANCE.state(), lang),
            mention_author=False,
        )
        return

    if isinstance(error, commands.CheckFailure):
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "help.staff"), title=t(lang, "generic.error_title"), lang=lang
            ),
            mention_author=False,
        )
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(
            embed=embeds.error_embed(
                f"\u23F3 **{error.retry_after:.0f}s**", lang=lang
            ),
            mention_author=False,
        )
        return

    log.exception("command error", exc_info=error)
    await ctx.reply(embed=embeds.error_embed(f"`{error}`", lang=lang), mention_author=False)


# ---------------------------------------------------------------------------
# 1.4 Beta (dev): deploy switch, service status card, background loops
# ---------------------------------------------------------------------------
@bot.command(
    name="deploylock",
    aliases=["deploytoggle", "\u0437\u0430\u043c\u043e\u043a"],
)
@owner_only()
async def deploylock_cmd(ctx: commands.Context, *, args: str = "") -> None:
    """`!deploylock on|off|status [minutes] [reason]` - close or open !deploy."""
    lang = lang_of(ctx.author)
    parts = (args or "").split()
    action = parts[0].lower() if parts else "toggle"
    rest = parts[1:]
    minutes = 0
    if rest and rest[0].isdigit():
        minutes = max(0, min(int(rest[0]), 7 * 24 * 60))
        rest = rest[1:]
    reason = " ".join(rest).strip()

    if action in ("status", "state", "\u0441\u0442\u0430\u0442\u0443\u0441"):
        await ctx.reply(
            embed=embeds.deploy_lock_embed(DEPLOY_LOCK.state(), lang),
            mention_author=False,
        )
        return

    if action in (
        "off",
        "open",
        "\u043e\u0442\u043a\u0440\u044b\u0442\u044c",
        "\u043e\u0442\u043a\u0440\u043e\u0439",
    ):
        state = await DEPLOY_LOCK.reopen(ctx.author.id, str(ctx.author))
    elif action in (
        "on",
        "close",
        "\u0437\u0430\u043a\u0440\u044b\u0442\u044c",
        "\u0437\u0430\u043a\u0440\u043e\u0439",
    ):
        state = await DEPLOY_LOCK.close(
            ctx.author.id, str(ctx.author), reason, minutes
        )
    else:
        state = await DEPLOY_LOCK.toggle(
            ctx.author.id, str(ctx.author), reason, minutes
        )

    log.info(
        "deploy is now %s (by %s)",
        "closed" if state.get("closed") else "open",
        ctx.author,
    )
    await ctx.reply(embed=embeds.deploy_lock_embed(state, lang), mention_author=False)


def _health(status: str, label: str, lang: str, detail: str = "") -> dict:
    """One row of the status card: green = ok, yellow = load, red = outage."""
    return {
        "label": label,
        "status": status,
        "text": t(lang, "status." + status),
        "detail": detail,
    }


async def _status_rows(lang: str) -> list[dict]:
    """Real checks: gateway, Docker, deploy, terminal, guard, storage, regions."""
    rows: list[dict] = [{"section": t(lang, "status.core")}]

    # 1. Discord gateway - our own websocket latency (NaN before the first
    #    heartbeat, so compare the value with itself).
    raw = bot.latency
    latency = raw * 1000.0 if raw == raw else 0.0
    if latency <= 0:
        rows.append(_health("load", t(lang, "status.gateway"), lang, "-"))
    else:
        level = "ok" if latency < 250 else "load" if latency < 600 else "down"
        rows.append(
            _health(level, t(lang, "status.gateway"), lang, f"{latency:.0f} ms")
        )

    # 2. Virtualization - is the Docker daemon answering?
    stats = await _stats()
    docker_ok = False
    if manager is not None:
        try:
            docker_ok = bool(await asyncio.to_thread(manager.client.ping))
        except Exception:
            docker_ok = False
    rows.append(
        _health(
            "ok" if docker_ok else "down",
            t(lang, "status.docker"),
            lang,
            (
                f"{int(stats.get('running', 0))}/{int(stats.get('used', 0))}"
                if docker_ok
                else t(lang, "status.docker_down")
            ),
        )
    )

    # 3. Deployments - staff lock first, then free slots.
    free = int(stats.get("free", 0)) if stats else 0
    total = int(stats.get("slots", SLOTS.total)) if stats else SLOTS.total
    slot_detail = t(lang, "status.slots_value", free=free, total=total)
    if DEPLOY_LOCK.closed:
        rows.append(
            _health(
                "down",
                t(lang, "status.deploy"),
                lang,
                t(lang, "status.deploy_closed"),
            )
        )
    elif not docker_ok:
        rows.append(
            _health(
                "down", t(lang, "status.deploy"), lang, t(lang, "status.docker_down")
            )
        )
    else:
        rows.append(
            _health(
                "ok" if free > 0 else "load",
                t(lang, "status.deploy"),
                lang,
                slot_detail,
            )
        )

    # 4. Web terminal - real TCP handshake with sshx.io.
    try:
        rtt = await asyncio.to_thread(tcp_ping, "sshx.io", 443, 1.5)
    except Exception:  # pragma: no cover
        rtt = None
    if rtt is None:
        rows.append(_health("down", t(lang, "status.terminal"), lang, "sshx.io:443"))
    else:
        rows.append(
            _health(
                "ok" if rtt < 400 else "load",
                t(lang, "status.terminal"),
                lang,
                f"{rtt:.0f} ms",
            )
        )

    # 5. Abuse guard.
    if GUARD.enabled:
        rows.append(
            _health(
                "ok",
                t(lang, "status.guard"),
                lang,
                t(lang, "status.guard_on", count=int(stats.get("used", 0))),
            )
        )
    else:
        rows.append(
            _health(
                "load", t(lang, "status.guard"), lang, t(lang, "status.guard_off")
            )
        )

    # 6. Storage - can we still write the state files?
    folder = os.path.dirname(os.path.abspath(DEPLOY_LOCK.path)) or "."
    rows.append(
        _health(
            "ok" if os.access(folder, os.W_OK) else "down",
            t(lang, "status.storage"),
            lang,
            "data/",
        )
    )

    # 7. The five regions (ping, load, and the 5-15 minute auto-close).
    rows.append({"section": t(lang, "status.regions")})
    try:
        await LOCATIONS.refresh(
            usage_from_records(manager.all_records() if manager is not None else [])
        )
    except Exception as exc:  # pragma: no cover
        log.warning("region refresh failed: %s", exc)
    for item in LOCATIONS.all():
        detail = (
            f"{item['ping']} ms"
            if item["available"]
            else f"{item['reopen_minutes']} min"
        )
        rows.append(
            _health(item["status"], location_plain(item, lang), lang, detail)
        )
    return rows


@bot.command(
    name="status",
    aliases=[
        "\u0441\u0442\u0430\u0442\u0443\u0441",
        "health",
        "\u0441\u0435\u0440\u0432\u0438\u0441",
    ],
)
@commands.cooldown(1, 10, commands.BucketType.user)
async def status_cmd(ctx: commands.Context) -> None:
    """Service status card: green = normal, yellow = load, red = outage."""
    lang = lang_of(ctx.author)
    async with ctx.typing():
        rows = await _status_rows(lang)
        overall = statuscard.overall_status(rows)

        png: bytes | None = None
        if STATUS_IMAGE and statuscard.HAS_PILLOW and statuscard.has_unicode_font():
            legend = [
                ("ok", t(lang, "status.ok")),
                ("load", t(lang, "status.load")),
                ("down", t(lang, "status.down")),
            ]
            footer = (
                f"{t(lang, 'status.updated')}: "
                f"{time.strftime('%H:%M UTC', time.gmtime())}"
            )
            try:
                png = await asyncio.to_thread(
                    statuscard.render_status_card,
                    t(lang, "status.title"),
                    f"{BOT_NAME} \u2022 v{BOT_VERSION} \u2022 {BOT_BUILD}",
                    rows,
                    legend,
                    footer,
                    overall,
                )
            except Exception as exc:
                log.warning("status card failed: %s", exc)
                png = None

    if png:
        embed = embeds.status_embed(rows, overall, lang, True)
        embed.set_image(url="attachment://cloudy-status.png")
        await ctx.reply(
            embed=embed,
            file=discord.File(io.BytesIO(png), filename="cloudy-status.png"),
            mention_author=False,
        )
        return

    await ctx.reply(
        embed=embeds.status_embed(rows, overall, lang, False), mention_author=False
    )


@tasks.loop(seconds=60)
async def locations_loop() -> None:
    """Keep the region board live: ping, load, auto-close and auto-reopen."""
    if manager is None:
        return
    try:
        await LOCATIONS.refresh(usage_from_records(manager.all_records()))
    except Exception as exc:  # pragma: no cover
        log.warning("region loop failed: %s", exc)


@locations_loop.before_loop
async def _before_locations_loop() -> None:
    await bot.wait_until_ready()


@tasks.loop(seconds=120)
async def guard_loop() -> None:
    """Anti-abuse sweep: miners, attack tools, pool sockets, pinned CPU."""
    incidents = await GUARD.scan()
    for incident in incidents:
        owner_id = int(incident.get("owner_id") or 0)
        log.warning(
            "abuse guard: %s in %s (owner %s, action %s, strikes %s)",
            incident.get("kind"),
            incident.get("container"),
            owner_id,
            incident.get("action"),
            incident.get("strikes"),
        )

        if owner_id:
            user = bot.get_user(owner_id)
            if user is None:
                try:
                    user = await bot.fetch_user(owner_id)
                except discord.HTTPException:
                    user = None
            if user is not None:
                try:
                    await user.send(
                        embed=embeds.guard_warning_embed(incident, lang_of(owner_id))
                    )
                except discord.HTTPException:
                    pass

        # Repeat offenders can be banned automatically (GUARD_BAN_ON_STRIKE=1).
        if incident.get("ban") and owner_id:
            try:
                await bans.ban(
                    owner_id,
                    f"abuse guard: {incident.get('kind') or 'miner'}",
                    0,
                    "Abuse guard",
                    str(incident.get("owner_name") or ""),
                )
            except Exception as exc:  # pragma: no cover
                log.info("guard ban skipped: %s", exc)

        for staff_id in OWNER_IDS:
            staff = bot.get_user(int(staff_id))
            if staff is None:
                continue
            try:
                await staff.send(
                    embed=embeds.guard_report_embed(incident, lang_of(int(staff_id)))
                )
            except discord.HTTPException:
                pass


@guard_loop.before_loop
async def _before_guard_loop() -> None:
    await bot.wait_until_ready()


def main() -> None:
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set.")
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
