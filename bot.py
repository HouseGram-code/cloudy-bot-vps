"""Cloudy VPS Bot - free VPS hosting from Discord.

Version 1.2 Beta (bilingual RU / EN, leaf economy)
"""

from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands, tasks

import embeds
from config import (
    BOT_NAME,
    BOT_VERSION,
    COMMAND_PREFIX,
    DISCORD_TOKEN,
    EMOJI,
    OWNER_IDS,
    is_owner,
)
from i18n import LANGUAGES, LangStore, lang_label, normalize
from i18n import rules as rules_for
from i18n import t
from maintenance import MAINTENANCE
from moderation import BanStore, ModerationError
from plan_store import PLAN_STORE
from slots import MAX_SLOTS, MIN_SLOTS, SLOTS
from views import AdminView, DeployView, LanguageView, ManageView, ProfileView
from vps_manager import VPSError, VPSManager
from wallet import MAX_GRANT, WALLET

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
    "profile",
    "bonus",
    "give",
    "rules",
    "lang",
    "help",
    "ping",
    "admin",
    "maintenance",
    "slots",
    "plan",
    "wipe",
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
    if not presence_loop.is_running():
        presence_loop.start()
    if not billing_loop.is_running():
        billing_loop.start()


async def _stats() -> dict:
    """Live counters, or an empty dict when Docker is unavailable."""
    if manager is None:
        return {}
    try:
        return await manager.stats()
    except Exception as exc:  # pragma: no cover
        log.warning("could not read VPS stats: %s", exc)
        return {}


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
    if manager is None:
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


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------
@bot.command(name="deploy")
@commands.cooldown(1, 15, commands.BucketType.user)
async def deploy(ctx: commands.Context) -> None:
    """Show the free plan specs and deploy a VPS."""
    lang = lang_of(ctx.author)
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

    # A free VPS still needs leaves to stay online.
    await WALLET.ensure(ctx.author.id, str(ctx.author))
    if not is_owner(ctx.author.id) and not WALLET.can_run(ctx.author.id):
        await ctx.reply(
            embed=embeds.low_leaves_embed(WALLET.balance(ctx.author.id), lang),
            mention_author=False,
        )
        return

    stats = await _stats()
    view = DeployView(mgr, ctx.author.id, bans, lang=lang)
    msg = await ctx.reply(
        embed=embeds.deploy_offer_embed(ctx.author, lang, stats=stats or None),
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


@bot.command(name="servers")
@owner_only()
async def servers_cmd(ctx: commands.Context) -> None:
    lang = lang_of(ctx.author)
    try:
        mgr = _require_manager()
    except VPSError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
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
# Profile, daily bonus and leaves
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
    """!profile - name, ID, leaf balance and the daily bonus button."""
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


@bot.command(name="bonus", aliases=["daily", "\u0431\u043e\u043d\u0443\u0441"])
@commands.cooldown(1, 5, commands.BucketType.user)
async def bonus_cmd(ctx: commands.Context) -> None:
    """!bonus - claim the daily leaves."""
    lang = lang_of(ctx.author)
    result = await WALLET.claim_bonus(ctx.author.id, str(ctx.author))
    await ctx.reply(
        embed=embeds.bonus_claimed_embed(result, lang), mention_author=False
    )


@bot.command(
    name="give",
    aliases=[
        "grant",
        "leaves",
        "\u0432\u044b\u0434\u0430\u0442\u044c",
        "\u0432\u044b\u0434\u0430\u0442\u044c\u043b\u0438\u0441\u0442\u0438\u043a",
    ],
)
@owner_only()
async def give_cmd(
    ctx: commands.Context, target: str = "", amount: str = ""
) -> None:
    """!give <@user|id> <amount> - hand out leaves (negative takes them away)."""
    lang = lang_of(ctx.author)
    if not target or not amount:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "grant.usage", prefix=COMMAND_PREFIX), lang=lang
            ),
            mention_author=False,
        )
        return

    try:
        user_id, name = await _resolve_user_id(ctx, target)
    except ModerationError as exc:
        await ctx.reply(
            embed=embeds.error_embed(str(exc), lang=lang), mention_author=False
        )
        return

    try:
        value = int(str(amount).strip().replace("+", ""))
    except (TypeError, ValueError):
        value = 0
    if value == 0 or abs(value) > MAX_GRANT:
        await ctx.reply(
            embed=embeds.error_embed(
                t(lang, "grant.bad_amount", max=MAX_GRANT), lang=lang
            ),
            mention_author=False,
        )
        return

    balance = await WALLET.add(user_id, value, name)
    await ctx.reply(
        embed=embeds.leaves_granted_embed(user_id, value, balance, lang),
        mention_author=False,
    )

    if value > 0:
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            if user is not None:
                await user.send(
                    embed=embeds.leaves_notice_embed(
                        value, balance, lang_of(user_id)
                    )
                )
        except (discord.HTTPException, AttributeError):
            log.info("could not DM %s about the new leaves", user_id)


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


def main() -> None:
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set.")
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
