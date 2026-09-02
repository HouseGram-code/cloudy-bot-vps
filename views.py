"""Interactive buttons (discord.ui) for Cloudy VPS Bot.

Security: access links are only ever delivered by direct message (with an
ephemeral fallback when DMs are closed). They are never posted in a channel.

Every view carries a `lang` ("en" / "ru") so labels and messages match the
language the user picked with `!lang`.
"""

from __future__ import annotations

import asyncio
import logging
import re

import discord

import embeds
from config import (
    ANIM_DELAY,
    COLOR_PRIMARY,
    COMMAND_PREFIX,
    EMOJI,
    LEAVES_ENABLED,
    VPS_LIFETIME_DAYS,
    is_owner,
)
from i18n import DEFAULT_LANG, LANGUAGES, LangStore, t
from maintenance import MAINTENANCE, MaintenanceStore
from moderation import BanStore
from plan_store import (
    DISK_STEP,
    MAX_DISK_GB,
    MAX_RAM_MB,
    MIN_DISK_GB,
    MIN_RAM_MB,
    PLAN_STORE,
    RAM_STEP,
    PlanStore,
)
from slots import MAX_SLOTS, MIN_SLOTS, SLOTS, SlotStore
from vps_manager import VPSError, VPSManager
from wallet import WALLET, Wallet

log = logging.getLogger("cloudy.views")


async def _deliver_private(
    user: discord.abc.User,
    embed: discord.Embed,
    interaction: discord.Interaction | None = None,
    lang: str = DEFAULT_LANG,
) -> bool:
    """DM one access card, with an ephemeral fallback when DMs are closed."""
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("DM to %s failed: %s", user.id, exc)

    if interaction is not None:
        target = (
            interaction.followup
            if interaction.response.is_done()
            else interaction.response
        )
        try:
            await target.send(embed=embeds.dm_failed_embed(lang), ephemeral=True)
            await target.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass
    return False


async def deliver_sshx(
    user: discord.abc.User,
    info: dict,
    link: str,
    interaction: discord.Interaction | None = None,
    lang: str = DEFAULT_LANG,
) -> bool:
    """Send the sshx link privately. Returns True if the DM was delivered."""
    return await _deliver_private(
        user, embeds.sshx_dm_embed(info, link, lang), interaction, lang
    )


class OwnerOnlyView(discord.ui.View):
    """Base view that only reacts to the user who ran the command."""

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        timeout: float | None = 300,
        lang: str = DEFAULT_LANG,
    ):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.owner_id = owner_id
        self.bans = bans
        self.lang = lang
        self.message: discord.Message | None = None
        self.localize_labels()

    # Button labels are class-level in discord.py, so translate them per instance.
    LABEL_KEYS: dict[str, str] = {}

    def localize_labels(self) -> None:
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            key = self.LABEL_KEYS.get(child.custom_id or "") or self.LABEL_KEYS.get(
                (child.label or "").lower()
            )
            if key:
                child.label = t(self.lang, key)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "panel.not_yours"),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return False
        if self.bans is not None and self.bans.is_banned(interaction.user.id):
            record = self.bans.get(interaction.user.id) or {}
            await interaction.response.send_message(
                embed=embeds.banned_notice_embed(record, self.lang), ephemeral=True
            )
            return False
        # Maintenance mode: buttons are frozen for everyone except staff.
        if MAINTENANCE.enabled and not is_owner(interaction.user.id):
            await interaction.response.send_message(
                embed=embeds.maintenance_embed(MAINTENANCE.state(), self.lang),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# !deploy
# ---------------------------------------------------------------------------
# (stage key, percent, ansi log line)
DEPLOY_STAGES: list[tuple[str, int, str]] = [
    ("stage.alloc", 8, "\u001b[0;36m[cloudy]\u001b[0m reserving 1 vCPU / RAM slice"),
    ("stage.image", 22, "\u001b[0;36m[image]\u001b[0m ubuntu:22.04 \u2192 ok"),
    ("stage.disk", 36, "\u001b[0;36m[disk]\u001b[0m formatting 10 GB volume"),
    ("stage.boot", 52, "\u001b[0;36m[boot]\u001b[0m kernel handoff \u2192 init"),
    ("stage.net", 66, "\u001b[0;36m[net]\u001b[0m bridge attached, DNS ready"),
    ("stage.apt", 78, "\u001b[0;36m[apt]\u001b[0m curl git htop python3 tmux"),
    ("stage.terminal", 90, "\u001b[0;36m[shell]\u001b[0m terminal service ready"),
    ("stage.health", 97, "\u001b[0;32m[ok]\u001b[0m all services healthy"),
]


# ---------------------------------------------------------------------------
# !manage
# ---------------------------------------------------------------------------
class ManageView(OwnerOnlyView):
    LABEL_KEYS = {
        "vps_start": "btn.start",
        "vps_stop": "btn.stop",
        "vps_restart": "btn.restart",
        "vps_sshx": "btn.sshx",
        "vps_refresh": "btn.refresh",
        "vps_rules": "btn.rules",
    }

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
    ):
        super().__init__(manager, owner_id, bans, timeout=600, lang=lang)

    async def refresh_buttons(self, info: dict) -> None:
        running = info["status"] == "running"
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "vps_start":
                child.disabled = running
            elif child.custom_id in (
                "vps_stop",
                "vps_restart",
                "vps_sshx",
            ):
                # The web terminal needs a running guest.
                child.disabled = not running
            else:
                child.disabled = False

    async def _do(self, interaction: discord.Interaction, action: str, verb_key: str):
        lang = self.lang
        await interaction.response.defer()
        try:
            await self.manager.power_action(interaction.user.id, action)
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return
        except Exception as exc:  # pragma: no cover
            log.exception("%s failed", action)
            await interaction.followup.send(
                embed=embeds.error_embed(f"`{exc}`", lang=lang), ephemeral=True
            )
            return

        await asyncio.sleep(1.5)  # let the container settle before reading stats
        info = await self.manager.get_info(interaction.user.id)
        await self.refresh_buttons(info)
        await interaction.edit_original_response(
            embed=embeds.manage_embed(info, lang), view=self
        )
        await interaction.followup.send(
            embed=embeds.info_embed(
                f"{EMOJI['check']} {t(lang, verb_key)}",
                t(lang, "manage.now_status", name=info["name"], status=info["status"])
                + (
                    t(lang, "manage.session_closed")
                    if action in ("stop", "restart")
                    else ""
                ),
                COLOR_PRIMARY,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Start", style=discord.ButtonStyle.success, emoji="\u25B6\ufe0f", custom_id="vps_start"
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "start", "manage.started")

    @discord.ui.button(
        label="Stop", style=discord.ButtonStyle.danger, emoji="\u23F9\ufe0f", custom_id="vps_stop"
    )
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "stop", "manage.stopped")

    @discord.ui.button(
        label="Restart",
        style=discord.ButtonStyle.primary,
        emoji="\U0001F504",
        custom_id="vps_restart",
    )
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, "restart", "manage.restarted")

    @discord.ui.button(
        label="Web terminal",
        style=discord.ButtonStyle.primary,
        emoji="\U0001F310",
        custom_id="vps_sshx",
        row=1,
    )
    async def sshx(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Second access method: a browser terminal link from sshx.io."""
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        try:
            link = await self.manager.get_sshx(
                interaction.user.id, force_new=True, lang=lang
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                embed=embeds.error_embed(t(lang, "sshx.timeout"), lang=lang),
                ephemeral=True,
            )
            return
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return

        info = await self.manager.get_info(interaction.user.id)
        sent = await deliver_sshx(interaction.user, info, link, interaction, lang)
        if sent:
            await interaction.followup.send(
                embed=embeds.info_embed(
                    f"{EMOJI['mail']} {t(lang, 'sshx.check_dms_title')}",
                    t(lang, "sshx.check_dms_desc"),
                    COLOR_PRIMARY,
                ),
                ephemeral=True,
            )


    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F501",
        custom_id="vps_refresh",
        row=1,
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            info = await self.manager.get_info(interaction.user.id)
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=self.lang), ephemeral=True
            )
            return
        await self.refresh_buttons(info)
        await interaction.edit_original_response(
            embed=embeds.manage_embed(info, self.lang), view=self
        )

    @discord.ui.button(
        label="Rules",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F4DC",
        custom_id="vps_rules",
        row=1,
    )
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embeds.rules_embed(self.lang), ephemeral=True
        )


# ---------------------------------------------------------------------------
# !lang - language picker
# ---------------------------------------------------------------------------
class LanguageSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(
                label=meta["name"],
                value=code,
                emoji=meta["flag"],
                default=(code == current),
                description={"ru": "\u0418\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441 \u0431\u043e\u0442\u0430 \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c", "en": "Bot interface in English"}[code],
            )
            for code, meta in LANGUAGES.items()
        ]
        super().__init__(
            placeholder=t(current, "lang.select_placeholder"),
            min_values=1,
            max_values=1,
            options=options,
            custom_id="lang_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: LanguageView = self.view  # type: ignore[assignment]
        new_lang = view.store.set(interaction.user.id, self.values[0])
        view.lang = new_lang
        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=embeds.language_changed_embed(new_lang), view=view
        )
        view.stop()


class LanguageView(discord.ui.View):
    """Small select menu so the user can pick Russian or English."""

    def __init__(self, owner_id: int, store: LangStore, current: str = DEFAULT_LANG):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.store = store
        self.lang = current
        self.message: discord.Message | None = None
        self.add_item(LanguageSelect(current))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "panel.not_yours"),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# !admin - staff panel with the maintenance switch
# ---------------------------------------------------------------------------
class ProfileView(discord.ui.View):
    """Profile card with the daily bonus button (owner of the profile only)."""

    def __init__(
        self,
        user: discord.abc.User,
        manager: VPSManager | None = None,
        wallet: Wallet = WALLET,
        lang: str = DEFAULT_LANG,
    ):
        super().__init__(timeout=300)
        self.profile_user = user
        self.owner_id = user.id
        self.manager = manager
        self.wallet = wallet
        self.lang = lang
        self.message: discord.Message | None = None
        self.sync_buttons()

    # ---- helpers ----
    async def _vps_info(self) -> dict | None:
        if self.manager is None:
            return None
        try:
            if await self.manager.has_vps(self.owner_id):
                return await self.manager.get_info(self.owner_id)
        except Exception as exc:  # pragma: no cover
            log.warning("profile: could not read VPS info: %s", exc)
        return None

    async def build_embed(self) -> discord.Embed:
        state = self.wallet.state(self.owner_id, str(self.profile_user))
        return embeds.profile_embed(
            self.profile_user, state, await self._vps_info(), self.lang
        )

    def sync_buttons(self) -> None:
        # 1.3 Beta: the daily-bonus button is gone together with !bonus.
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "profile_refresh":
                child.label = t(self.lang, "btn.profile_refresh")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "panel.not_yours", prefix=COMMAND_PREFIX),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # ---- buttons ----
    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F501",
        custom_id="profile_refresh",
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await self.build_embed()
        self.sync_buttons()
        await interaction.edit_original_response(embed=embed, view=self)


# ---------------------------------------------------------------------------
# !admin
# ---------------------------------------------------------------------------
class AdminView(discord.ui.View):
    """Owner-only panel: turn maintenance mode on/off and see live counters."""

    def __init__(
        self,
        owner_id: int,
        maintenance: MaintenanceStore = MAINTENANCE,
        manager: VPSManager | None = None,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
        slots: SlotStore = SLOTS,
        wallet: Wallet = WALLET,
        plan: PlanStore = PLAN_STORE,
    ):
        super().__init__(timeout=600)
        self.wallet = wallet
        self.plan = plan
        self.owner_id = owner_id
        self.maintenance = maintenance
        self.manager = manager
        self.bans = bans
        self.lang = lang
        self.slots = slots
        self.stats: dict = {}
        self.message: discord.Message | None = None
        self.sync_buttons()

    # ---- helpers ----
    def _counts(self) -> tuple[int, int]:
        servers = 0
        if self.manager is not None:
            try:
                servers = len(self.manager.all_records())
            except Exception:  # pragma: no cover
                servers = 0
        ban_count = self.bans.count if self.bans is not None else 0
        return servers, ban_count

    async def refresh_stats(self) -> dict:
        """Live running / stopped / slot counters from Docker."""
        if self.manager is not None:
            try:
                self.stats = await self.manager.stats()
            except Exception as exc:  # pragma: no cover
                log.warning("could not read VPS stats: %s", exc)
                self.stats = {}
        return self.stats

    def panel_embed(self) -> discord.Embed:
        servers, ban_count = self._counts()
        return embeds.admin_panel_embed(
            self.maintenance.state(),
            servers,
            ban_count,
            self.lang,
            stats=self.stats or None,
        )

    async def build_embed(self) -> discord.Embed:
        """Panel embed with fresh counters (use this instead of panel_embed)."""
        await self.refresh_stats()
        return self.panel_embed()

    def sync_buttons(self) -> None:
        on = self.maintenance.enabled
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "maint_toggle":
                child.label = t(self.lang, "admin.btn_off" if on else "admin.btn_on")
                child.style = (
                    discord.ButtonStyle.success if on else discord.ButtonStyle.danger
                )
                child.emoji = "\u2705" if on else "\U0001F6A7"
            elif child.custom_id == "maint_preview":
                child.label = t(self.lang, "admin.btn_preview")
            elif child.custom_id == "maint_refresh":
                child.label = t(self.lang, "admin.btn_refresh")
            elif child.custom_id == "slot_plus":
                child.label = t(self.lang, "admin.btn_slot_plus")
                child.disabled = self.slots.total >= MAX_SLOTS
            elif child.custom_id == "slot_minus":
                child.label = t(self.lang, "admin.btn_slot_minus")
                child.disabled = self.slots.total <= MIN_SLOTS
            elif child.custom_id == "admin_plan":
                child.label = t(self.lang, "admin.btn_plan")
            elif child.custom_id == "admin_ram_plus":
                child.label = t(self.lang, "admin.btn_ram_plus")
                child.disabled = self.plan.ram_mb >= MAX_RAM_MB
            elif child.custom_id == "admin_ram_minus":
                child.label = t(self.lang, "admin.btn_ram_minus")
                child.disabled = self.plan.ram_mb <= MIN_RAM_MB
            elif child.custom_id == "admin_disk_plus":
                child.label = t(self.lang, "admin.btn_disk_plus")
                child.disabled = self.plan.disk_gb >= MAX_DISK_GB
            elif child.custom_id == "admin_disk_minus":
                child.label = t(self.lang, "admin.btn_disk_minus")
                child.disabled = self.plan.disk_gb <= MIN_DISK_GB

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not is_owner(interaction.user.id):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "admin.only_staff"),
                    title=t(self.lang, "panel.not_yours_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # ---- interaction plumbing -------------------------------------------
    # Every button used to run its store update BEFORE acknowledging the
    # interaction; a slow disk or a raised exception left Discord showing
    # "This interaction failed" and the panel frozen. Now we always defer
    # first, then work, then re-render - and errors are reported instead of
    # killing the panel.
    async def _safe_defer(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except discord.HTTPException:
                pass

    async def _rerender(self, interaction: discord.Interaction) -> None:
        """Rebuild the panel embed and push fresh button states."""
        try:
            embed = await self.build_embed()
        except Exception as exc:  # pragma: no cover
            log.warning("admin panel: could not rebuild the embed: %s", exc)
            return
        self.sync_buttons()
        try:
            await interaction.edit_original_response(embed=embed, view=self)
            return
        except discord.HTTPException as exc:
            log.warning("admin panel: could not edit the response: %s", exc)
        if self.message is not None:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    async def _panel_error(
        self, interaction: discord.Interaction, exc: Exception
    ) -> None:
        try:
            await interaction.followup.send(
                embed=embeds.error_embed(f"`{exc}`", lang=self.lang), ephemeral=True
            )
        except discord.HTTPException:
            pass

    # ---- buttons ----
    @discord.ui.button(
        label="Maintenance",
        style=discord.ButtonStyle.danger,
        emoji="\U0001F6A7",
        custom_id="maint_toggle",
    )
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_defer(interaction)
        try:
            state = await self.maintenance.toggle(
                interaction.user.id, str(interaction.user)
            )
        except Exception as exc:  # pragma: no cover
            log.exception("admin panel: maintenance toggle failed")
            await self._panel_error(interaction, exc)
            return
        await self._rerender(interaction)
        await interaction.followup.send(
            embed=embeds.maintenance_toggled_embed(state, self.lang), ephemeral=True
        )

    @discord.ui.button(
        label="Preview",
        style=discord.ButtonStyle.primary,
        emoji="\U0001F441\ufe0f",
        custom_id="maint_preview",
    )
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show exactly what regular users see while maintenance is on."""
        await interaction.response.send_message(
            embed=embeds.maintenance_embed(self.maintenance.state(), self.lang),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F501",
        custom_id="maint_refresh",
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_defer(interaction)
        await self._rerender(interaction)

    # ---- capacity buttons ----
    async def _change_slots(self, interaction: discord.Interaction, delta: int) -> None:
        await self._safe_defer(interaction)
        old = self.slots.total
        try:
            await self.slots.add(delta, interaction.user.id, str(interaction.user))
        except Exception as exc:  # pragma: no cover
            log.exception("admin panel: slot change failed")
            await self._panel_error(interaction, exc)
            return
        await self._rerender(interaction)
        if self.slots.total == old:
            return  # already at the limit, the buttons now show it
        await interaction.followup.send(
            embed=embeds.slots_changed_embed(old, self.stats or {}, self.lang),
            ephemeral=True,
        )

    @discord.ui.button(
        label="-1 slot",
        style=discord.ButtonStyle.secondary,
        emoji="\u2796",
        custom_id="slot_minus",
        row=1,
    )
    async def slot_minus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_slots(interaction, -1)

    @discord.ui.button(
        label="+1 slot",
        style=discord.ButtonStyle.success,
        emoji="\u2795",
        custom_id="slot_plus",
        row=1,
    )
    async def slot_plus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_slots(interaction, +1)

    # ---- free VPS resources (RAM / disk) ----
    async def _change_plan(
        self,
        interaction: discord.Interaction,
        ram_delta: int = 0,
        disk_delta: int = 0,
    ) -> None:
        await self._safe_defer(interaction)
        old = self.plan.plan()
        try:
            if ram_delta:
                new = await self.plan.add_ram(
                    ram_delta, interaction.user.id, str(interaction.user)
                )
            else:
                new = await self.plan.add_disk(
                    disk_delta, interaction.user.id, str(interaction.user)
                )
        except Exception as exc:  # pragma: no cover
            log.exception("admin panel: plan change failed")
            await self._panel_error(interaction, exc)
            return
        await self._rerender(interaction)
        await interaction.followup.send(
            embed=embeds.plan_changed_embed(old, new, self.lang), ephemeral=True
        )

    @discord.ui.button(
        label="Resources",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F4E6",
        custom_id="admin_plan",
        row=2,
    )
    async def show_plan(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            embed=embeds.plan_embed(self.lang), ephemeral=True
        )

    @discord.ui.button(
        label="-RAM",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F9E9",
        custom_id="admin_ram_minus",
        row=3,
    )
    async def ram_minus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_plan(interaction, ram_delta=-RAM_STEP)

    @discord.ui.button(
        label="+RAM",
        style=discord.ButtonStyle.success,
        emoji="\U0001F9E9",
        custom_id="admin_ram_plus",
        row=3,
    )
    async def ram_plus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_plan(interaction, ram_delta=RAM_STEP)

    @discord.ui.button(
        label="-disk",
        style=discord.ButtonStyle.secondary,
        emoji="\U0001F4BD",
        custom_id="admin_disk_minus",
        row=3,
    )
    async def disk_minus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_plan(interaction, disk_delta=-DISK_STEP)

    @discord.ui.button(
        label="+disk",
        style=discord.ButtonStyle.success,
        emoji="\U0001F4BD",
        custom_id="admin_disk_plus",
        row=3,
    )
    async def disk_plus(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_plan(interaction, disk_delta=DISK_STEP)


# ---------------------------------------------------------------------------
# 1.4 Beta (dev): !deploy wizard - region -> Ubuntu -> live progress
# ---------------------------------------------------------------------------
from config import DEFAULT_OS_ID, OS_BY_ID, OS_CHOICES  # noqa: E402
from locations import LOCATIONS, usage_from_records  # noqa: E402
from locations import plain_title as location_plain  # noqa: E402
from locations import title as location_title  # noqa: E402


def _records_list(manager: VPSManager) -> list:
    """All VPS records as a plain list (the store may return a dict)."""
    try:
        records = manager.all_records()
    except Exception:  # pragma: no cover
        return []
    if isinstance(records, dict):
        return list(records.values())
    return list(records or [])


def _region_stages(loc: dict) -> list[tuple[str, int, str]]:
    """DEPLOY_STAGES with the chosen region woven into the build log."""
    code = str(loc.get("code") or "-")
    ping = int(loc.get("ping") or 0)
    stages = list(DEPLOY_STAGES)
    stages[0] = (
        stages[0][0],
        stages[0][1],
        f"\u001b[0;36m[cloudy]\u001b[0m region {code} \u00b7 reserving vCPU / RAM slice",
    )
    stages[4] = (
        stages[4][0],
        stages[4][1],
        f"\u001b[0;36m[net]\u001b[0m {code} bridge attached \u00b7 rtt {ping} ms \u00b7 DNS ready",
    )
    return stages


class _LocationSelect(discord.ui.Select):
    """Step 1: five regions with live ping and a colored status."""

    def __init__(self, wizard: "DeployView"):
        self.wizard = wizard
        lang = wizard.lang
        options = []
        for item in wizard.locations:
            capacity = int(item.get("capacity") or 0)
            free = max(0, capacity - int(item.get("used") or 0))
            tail = (
                t(lang, "loc.free", free=free, total=capacity)
                if item.get("available")
                else t(lang, "loc.reopen", minutes=int(item.get("reopen_minutes") or 5))
            )
            description = (
                f"{item.get('emoji', '')} {int(item.get('ping') or 0)} ms \u00b7 "
                f"{t(lang, item.get('status_key') or 'loc.status_ok')} \u00b7 {tail}"
            )
            options.append(
                discord.SelectOption(
                    label=location_plain(item, lang)[:100],
                    value=str(item["id"]),
                    description=description[:100],
                    emoji=item.get("flag") or None,
                    default=str(item["id"]) == str(wizard.location_id or ""),
                )
            )
        super().__init__(
            placeholder=t(lang, "loc.picker"),
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.wizard.choose_location(interaction, self.values[0])


class _OSSelect(discord.ui.Select):
    """Step 2: the Ubuntu release."""

    def __init__(self, wizard: "DeployView"):
        self.wizard = wizard
        lang = wizard.lang
        options = []
        for item in OS_CHOICES:
            note = (
                t(lang, "os.recommended")
                if item.get("available") and item.get("recommended")
                else ("" if item.get("available") else t(lang, "os.soon"))
            )
            description = f"{item.get('codename', '')}"
            if note:
                description = f"{description} \u00b7 {note}"
            options.append(
                discord.SelectOption(
                    label=str(item.get("label") or item["id"])[:100],
                    value=str(item["id"]),
                    description=description[:100],
                    emoji=item.get("emoji") or None,
                    default=str(item["id"]) == str(wizard.os_id or ""),
                )
            )
        super().__init__(
            placeholder=t(lang, "os.picker"),
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.wizard.choose_os(interaction, self.values[0])


class _WizardButton(discord.ui.Button):
    def __init__(
        self,
        wizard: "DeployView",
        action: str,
        label: str,
        style: discord.ButtonStyle,
        emoji: str | None = None,
        row: int = 1,
    ):
        super().__init__(label=label, style=style, emoji=emoji, row=row)
        self.wizard = wizard
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.wizard.handle(interaction, self.action)


class DeployView(OwnerOnlyView):
    """`!deploy` wizard: pick a region, pick Ubuntu, watch it being built."""

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
        stats: dict | None = None,
    ):
        super().__init__(manager, owner_id, bans, timeout=300, lang=lang)
        self.stats = stats or {}
        self.locations = LOCATIONS.all()
        best = LOCATIONS.pick_best()
        self.location_id = best["id"] if best.get("available") else None
        self.os_id = DEFAULT_OS_ID
        self.step = "location"
        self._build()

    # ------------------------------------------------------------------
    @property
    def location(self) -> dict:
        return LOCATIONS.get(self.location_id)

    @property
    def os_choice(self) -> dict:
        return OS_BY_ID.get(self.os_id) or OS_BY_ID[DEFAULT_OS_ID]

    def _build(self) -> None:
        """Rebuild the buttons for the current step."""
        self.clear_items()
        lang = self.lang
        if self.step == "location":
            self.add_item(_LocationSelect(self))
            self.add_item(
                _WizardButton(
                    self,
                    "refresh",
                    t(lang, "btn.refresh_loc"),
                    discord.ButtonStyle.secondary,
                    "\U0001F503",
                    1,
                )
            )
            self.add_item(
                _WizardButton(
                    self, "rules", t(lang, "btn.rules"), discord.ButtonStyle.primary, "\U0001F4DC", 1
                )
            )
            self.add_item(
                _WizardButton(
                    self,
                    "cancel",
                    t(lang, "btn.cancel"),
                    discord.ButtonStyle.secondary,
                    "\u2716\ufe0f",
                    1,
                )
            )
            return
        if self.step == "os":
            self.add_item(_OSSelect(self))
            self.add_item(
                _WizardButton(
                    self,
                    "back_location",
                    t(lang, "btn.back"),
                    discord.ButtonStyle.secondary,
                    "\u2B05\ufe0f",
                    1,
                )
            )
            self.add_item(
                _WizardButton(
                    self,
                    "cancel",
                    t(lang, "btn.cancel"),
                    discord.ButtonStyle.secondary,
                    "\u2716\ufe0f",
                    1,
                )
            )
            return
        self.add_item(
            _WizardButton(
                self, "deploy", t(lang, "btn.deploy"), discord.ButtonStyle.success, "\U0001F680", 0
            )
        )
        self.add_item(
            _WizardButton(
                self, "back_os", t(lang, "btn.back"), discord.ButtonStyle.secondary, "\u2B05\ufe0f", 0
            )
        )
        self.add_item(
            _WizardButton(
                self, "rules", t(lang, "btn.rules"), discord.ButtonStyle.primary, "\U0001F4DC", 1
            )
        )
        self.add_item(
            _WizardButton(
                self,
                "cancel",
                t(lang, "btn.cancel"),
                discord.ButtonStyle.secondary,
                "\u2716\ufe0f",
                1,
            )
        )

    def render(self, user: discord.abc.User) -> discord.Embed:
        """Embed of the current step."""
        if self.step == "location":
            return embeds.deploy_location_embed(user, self.lang, self.locations, self.stats)
        if self.step == "os":
            return embeds.deploy_os_embed(self.location, self.lang)
        return embeds.deploy_confirm_embed(
            self.location, self.os_choice, self.lang, self.stats
        )

    # ------------------------------------------------------------------
    async def choose_location(self, interaction: discord.Interaction, loc_id: str) -> None:
        loc = LOCATIONS.get(loc_id)
        if not loc.get("available"):
            # Saturated region: it reopens by itself within 5-15 minutes.
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(
                        self.lang,
                        "loc.unavailable",
                        loc=location_title(loc, self.lang),
                        minutes=int(loc.get("reopen_minutes") or 5),
                    ),
                    title=t(self.lang, "loc.unavailable_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return
        self.location_id = loc["id"]
        self.step = "os"
        self._build()
        await interaction.response.edit_message(
            embed=self.render(interaction.user), view=self
        )

    async def choose_os(self, interaction: discord.Interaction, os_id: str) -> None:
        choice = OS_BY_ID.get(os_id) or {}
        if not choice.get("available"):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    t(self.lang, "os.unavailable", os=choice.get("label") or os_id),
                    title=t(self.lang, "os.unavailable_title"),
                    lang=self.lang,
                ),
                ephemeral=True,
            )
            return
        self.os_id = str(os_id)
        self.step = "confirm"
        self._build()
        await interaction.response.edit_message(
            embed=self.render(interaction.user), view=self
        )

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        lang = self.lang
        if action == "rules":
            await interaction.response.send_message(
                embed=embeds.rules_embed(lang), ephemeral=True
            )
            return
        if action == "cancel":
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                embed=embeds.info_embed(
                    f"{EMOJI['cloud']} {t(lang, 'cancel.title')}",
                    t(lang, "cancel.desc", prefix=COMMAND_PREFIX),
                    COLOR_PRIMARY,
                ),
                view=None,
            )
            self.stop()
            return
        if action == "refresh":
            await interaction.response.defer()
            self.locations = await LOCATIONS.refresh(
                usage_from_records(_records_list(self.manager)), force=True
            )
            if self.location_id and not LOCATIONS.available(self.location_id):
                self.location_id = None
            self.step = "location"
            self._build()
            await interaction.edit_original_response(
                embed=self.render(interaction.user), view=self
            )
            return
        if action in ("back_location", "back_os"):
            self.step = "location" if action == "back_location" else "os"
            if self.step == "location":
                self.locations = LOCATIONS.all()
            self._build()
            await interaction.response.edit_message(
                embed=self.render(interaction.user), view=self
            )
            return
        if action == "deploy":
            await self._deploy(interaction)

    # ------------------------------------------------------------------
    async def _deploy(self, interaction: discord.Interaction) -> None:
        lang = self.lang
        loc = self.location
        if not loc.get("available"):
            self.step = "location"
            self.locations = LOCATIONS.all()
            self._build()
            await interaction.response.edit_message(
                embed=self.render(interaction.user), view=self
            )
            return

        for child in self.children:
            child.disabled = True
        label = f"{loc.get('emoji', '')} {location_title(loc, lang)}"
        await interaction.response.edit_message(
            embed=embeds.deploy_progress_embed(
                t(lang, "stage.region", loc=location_title(loc, lang)),
                3,
                [],
                lang,
                location=label,
            ),
            view=self,
        )
        message = interaction.message

        # Real work runs in the background while the animation plays.
        task = asyncio.create_task(
            self.manager.create_vps(
                interaction.user.id,
                str(interaction.user),
                lang,
                location_id=loc["id"],
                os_id=self.os_id,
            )
        )

        log_lines: list[str] = []
        try:
            for stage_key, percent, line in _region_stages(loc):
                log_lines.append(line)
                await message.edit(
                    embed=embeds.deploy_progress_embed(
                        t(lang, stage_key), percent, log_lines, lang, location=label
                    ),
                    view=self,
                )
                await asyncio.sleep(ANIM_DELAY)
            await task
        except VPSError as exc:
            await message.edit(embed=embeds.error_embed(str(exc), lang=lang), view=None)
            return
        except Exception as exc:  # pragma: no cover
            log.exception("deploy failed")
            await message.edit(
                embed=embeds.error_embed(t(lang, "deploy.failed", error=exc), lang=lang),
                view=None,
            )
            return

        info = await self.manager.get_info(interaction.user.id)
        access_status = t(lang, "access.press_button")

        await message.edit(
            embed=embeds.deploy_progress_embed(
                t(lang, "progress.finishing"), 100, log_lines, lang, location=label
            ),
            view=self,
        )
        await asyncio.sleep(0.6)

        manage_view = ManageView(self.manager, interaction.user.id, self.bans, lang=lang)
        await manage_view.refresh_buttons(info)
        await message.edit(
            embed=embeds.deploy_success_embed(info, access_status, lang),
            view=manage_view,
        )
        manage_view.message = message
        self.stop()


# ---------------------------------------------------------------------------
# 1.4 Beta (dev): !servers - how many machines you have + per-server panel
# ---------------------------------------------------------------------------
class _ServerSelect(discord.ui.Select):
    def __init__(self, listing: "ServersView"):
        self.listing = listing
        lang = listing.lang
        options = []
        for index, (key, record) in enumerate(listing.records[:25], start=1):
            loc = LOCATIONS.get(record.get("location_id"))
            description = (
                f"{location_plain(loc, lang)} \u00b7 {int(record.get('ram_mb') or 0)} MB "
                f"\u00b7 {int(record.get('disk_gb') or 0)} GB"
            )
            options.append(
                discord.SelectOption(
                    label=str(record.get("name") or f"server {index}")[:100],
                    value=str(key),
                    description=description[:100],
                    emoji=loc.get("flag") or None,
                )
            )
        super().__init__(
            placeholder=t(lang, "servers.picker"),
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.listing.open_panel(interaction, self.values[0])


class ServersView(OwnerOnlyView):
    """`!servers`: pick one of your machines and open its panel."""

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
        records: list | None = None,
        stats: dict | None = None,
    ):
        super().__init__(manager, owner_id, bans, timeout=300, lang=lang)
        self.records = list(records or [])
        self.stats = stats or {}
        if self.records:
            self.add_item(_ServerSelect(self))

    def render(self, user: discord.abc.User) -> discord.Embed:
        return embeds.servers_list_embed(
            user, [record for _key, record in self.records], self.lang, self.stats
        )

    async def reload(self) -> None:
        self.records = list(self.manager.records_of(self.owner_id))
        self.clear_items()
        if self.records:
            self.add_item(_ServerSelect(self))

    async def open_panel(self, interaction: discord.Interaction, key: str) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            info = await self.manager.get_info(interaction.user.id, key=key)
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return
        panel = ServerPanelView(
            self.manager, interaction.user.id, self.bans, lang=lang, key=key, parent=self
        )
        await panel.refresh_buttons(info)
        await interaction.edit_original_response(
            embed=embeds.manage_embed(info, lang), view=panel
        )
        panel.message = interaction.message


class _PanelButton(discord.ui.Button):
    def __init__(
        self,
        panel: "ServerPanelView",
        action: str,
        label: str,
        style: discord.ButtonStyle,
        emoji: str | None = None,
        row: int = 0,
        custom_id: str | None = None,
    ):
        super().__init__(label=label, style=style, emoji=emoji, row=row, custom_id=custom_id)
        self.panel = panel
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.panel.handle(interaction, self.action)


class ServerPanelView(OwnerOnlyView):
    """Panel of one selected server: power, web terminal, delete."""

    def __init__(
        self,
        manager: VPSManager,
        owner_id: int,
        bans: BanStore | None = None,
        lang: str = DEFAULT_LANG,
        key: str = "",
        parent: ServersView | None = None,
    ):
        super().__init__(manager, owner_id, bans, timeout=600, lang=lang)
        self.key = str(key)
        self.parent_view = parent
        self.confirm = False
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.clear_items()
        lang = self.lang
        if self.confirm:
            self.add_item(
                _PanelButton(
                    self,
                    "delete_yes",
                    t(lang, "btn.delete_yes"),
                    discord.ButtonStyle.danger,
                    "\U0001F5D1\ufe0f",
                    0,
                    "panel_delete_yes",
                )
            )
            self.add_item(
                _PanelButton(
                    self,
                    "delete_no",
                    t(lang, "btn.cancel"),
                    discord.ButtonStyle.secondary,
                    "\u2716\ufe0f",
                    0,
                    "panel_delete_no",
                )
            )
            return
        self.add_item(
            _PanelButton(
                self, "start", t(lang, "btn.start"), discord.ButtonStyle.success, "\u25B6\ufe0f", 0, "panel_start"
            )
        )
        self.add_item(
            _PanelButton(
                self, "stop", t(lang, "btn.stop"), discord.ButtonStyle.danger, "\u23F9\ufe0f", 0, "panel_stop"
            )
        )
        self.add_item(
            _PanelButton(
                self,
                "restart",
                t(lang, "btn.restart"),
                discord.ButtonStyle.primary,
                "\U0001F504",
                0,
                "panel_restart",
            )
        )
        self.add_item(
            _PanelButton(
                self, "sshx", t(lang, "btn.sshx"), discord.ButtonStyle.primary, "\U0001F310", 1, "panel_sshx"
            )
        )
        self.add_item(
            _PanelButton(
                self,
                "refresh",
                t(lang, "btn.refresh"),
                discord.ButtonStyle.secondary,
                "\U0001F501",
                1,
                "panel_refresh",
            )
        )
        self.add_item(
            _PanelButton(
                self,
                "delete",
                t(lang, "btn.delete"),
                discord.ButtonStyle.danger,
                "\U0001F5D1\ufe0f",
                2,
                "panel_delete",
            )
        )
        if self.parent_view is not None:
            self.add_item(
                _PanelButton(
                    self,
                    "back",
                    t(lang, "btn.back"),
                    discord.ButtonStyle.secondary,
                    "\u2B05\ufe0f",
                    2,
                    "panel_back",
                )
            )

    async def refresh_buttons(self, info: dict) -> None:
        running = info.get("status") == "running"
        primary = self.key == str(self.owner_id)
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "panel_start":
                child.disabled = running
            elif child.custom_id in ("panel_stop", "panel_restart"):
                child.disabled = not running
            elif child.custom_id == "panel_sshx":
                # The terminal helper works on the user's primary server.
                child.disabled = (not running) or (not primary)
            else:
                child.disabled = False

    async def _info(self, interaction: discord.Interaction) -> dict | None:
        try:
            return await self.manager.get_info(interaction.user.id, key=self.key)
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=self.lang), ephemeral=True
            )
            return None

    # ------------------------------------------------------------------
    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        lang = self.lang
        if action == "sshx":
            await self._open_terminal(interaction)
            return

        if action == "back" and self.parent_view is not None:
            await interaction.response.defer()
            await self.parent_view.reload()
            await interaction.edit_original_response(
                embed=self.parent_view.render(interaction.user), view=self.parent_view
            )
            self.parent_view.message = interaction.message
            self.stop()
            return

        await interaction.response.defer()

        if action == "refresh":
            info = await self._info(interaction)
            if info is None:
                return
            await self.refresh_buttons(info)
            await interaction.edit_original_response(
                embed=embeds.manage_embed(info, lang), view=self
            )
            return

        if action == "delete":
            info = await self._info(interaction)
            if info is None:
                return
            self.confirm = True
            self._build()
            await interaction.edit_original_response(
                embed=embeds.server_delete_confirm_embed(info, lang), view=self
            )
            return

        if action == "delete_no":
            self.confirm = False
            self._build()
            info = await self._info(interaction)
            if info is None:
                return
            await self.refresh_buttons(info)
            await interaction.edit_original_response(
                embed=embeds.manage_embed(info, lang), view=self
            )
            await interaction.followup.send(
                embed=embeds.info_embed(
                    f"{EMOJI['check']} {t(lang, 'servers.delete_cancelled')}",
                    t(lang, "servers.hint"),
                    COLOR_PRIMARY,
                ),
                ephemeral=True,
            )
            return

        if action == "delete_yes":
            info = await self._info(interaction)
            name = (info or {}).get("name", "-")
            try:
                await self.manager.delete_vps(interaction.user.id, key=self.key)
            except VPSError as exc:
                await interaction.followup.send(
                    embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
                )
                return
            except Exception as exc:  # pragma: no cover
                log.exception("panel delete failed")
                await interaction.followup.send(
                    embed=embeds.error_embed(f"`{exc}`", lang=lang), ephemeral=True
                )
                return
            await interaction.edit_original_response(
                embed=embeds.server_deleted_embed(name, lang), view=None
            )
            self.stop()
            return

        # start / stop / restart
        verb_keys = {
            "start": "manage.started",
            "stop": "manage.stopped",
            "restart": "manage.restarted",
        }
        if action not in verb_keys:
            return
        try:
            await self.manager.power_action(interaction.user.id, action, key=self.key)
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return
        except Exception as exc:  # pragma: no cover
            log.exception("panel %s failed", action)
            await interaction.followup.send(
                embed=embeds.error_embed(f"`{exc}`", lang=lang), ephemeral=True
            )
            return

        await asyncio.sleep(1.5)
        info = await self._info(interaction)
        if info is None:
            return
        await self.refresh_buttons(info)
        await interaction.edit_original_response(
            embed=embeds.manage_embed(info, lang), view=self
        )
        await interaction.followup.send(
            embed=embeds.info_embed(
                f"{EMOJI['check']} {t(lang, verb_keys[action])}",
                t(lang, "manage.now_status", name=info["name"], status=info["status"]),
                COLOR_PRIMARY,
            ),
            ephemeral=True,
        )

    async def _open_terminal(self, interaction: discord.Interaction) -> None:
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        try:
            link = await self.manager.get_sshx(
                interaction.user.id, force_new=True, lang=lang
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                embed=embeds.error_embed(t(lang, "sshx.timeout"), lang=lang),
                ephemeral=True,
            )
            return
        except VPSError as exc:
            await interaction.followup.send(
                embed=embeds.error_embed(str(exc), lang=lang), ephemeral=True
            )
            return
        info = await self.manager.get_info(interaction.user.id)
        sent = await deliver_sshx(interaction.user, info, link, interaction, lang)
        if sent:
            await interaction.followup.send(
                embed=embeds.info_embed(
                    f"{EMOJI['mail']} {t(lang, 'sshx.check_dms_title')}",
                    t(lang, "sshx.check_dms_desc"),
                    COLOR_PRIMARY,
                ),
                ephemeral=True,
            )
