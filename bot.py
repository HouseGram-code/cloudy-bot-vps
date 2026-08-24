"""Cloudy VPS Bot - free VPS hosting from Discord.

Version 1.1 Beta (bilingual RU / EN)
"""

from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

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
from views import AdminView, DeployView, LanguageView, ManageView
from vps_manager import VPSError, VPSManager

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
    activity=discord.Game(name=f"{COMMAND_PREFIX}deploy \u2022 free VPS"),
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
MAINTENANCE_ALLOWED = {"rules", "lang", "help", "ping", "admin", "maintenance"}


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

    view = DeployView(mgr, ctx.author.id, bans, lang=lang)
    msg = await ctx.reply(
        embed=embeds.deploy_offer_embed(ctx.author, lang), view=view, mention_author=False
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

    records = mgr.all_records()
    if not records:
        await ctx.reply(
            embed=embeds.info_embed(f"{EMOJI['cloud']} Servers", "No servers deployed yet."),
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
            f"{EMOJI['cloud']} Servers ({len(records)})", "\n".join(lines)
        ),
        mention_author=False,
    )


@bot.command(name="admin", aliases=["panel", "\u0430\u0434\u043c\u0438\u043d", "\u043f\u0430\u043d\u0435\u043b\u044c"])
@owner_only()
async def admin_cmd(ctx: commands.Context) -> None:
    """!admin - staff panel with the maintenance switch."""
    lang = lang_of(ctx.author)
    view = AdminView(ctx.author.id, MAINTENANCE, manager, bans, lang=lang)
    msg = await ctx.reply(embed=view.panel_embed(), view=view, mention_author=False)
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
        view = AdminView(ctx.author.id, MAINTENANCE, manager, bans, lang=lang)
        msg = await ctx.reply(embed=view.panel_embed(), view=view, mention_author=False)
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
