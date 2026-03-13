from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_BOT_TOKEN, CONF_GUILD_ID
from .coordinator import merge_discovered_channel_settings
from .discord_api import (
    DiscordCannotConnectError,
    DiscordGuildAccessError,
    async_fetch_discoverable_channels,
)

if TYPE_CHECKING:
    from . import DiscordBridgeRuntimeData, DiscordChatBridgeConfigEntry


async def async_refresh_entry_discovery(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
    runtime: DiscordBridgeRuntimeData,
) -> None:
    session = async_get_clientsession(hass)
    discovered_channels = await async_fetch_discoverable_channels(
        session=session,
        bot_token=entry.data[CONF_BOT_TOKEN],
        guild_id=entry.data[CONF_GUILD_ID],
    )
    merged_options = merge_discovered_channel_settings(entry.options, discovered_channels)
    if merged_options != entry.options:
        hass.config_entries.async_update_entry(entry, options=merged_options)


async def async_schedule_discovery_refresh(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
    runtime: DiscordBridgeRuntimeData,
    *,
    immediate: bool = False,
) -> None:
    existing_task = runtime.discovery_refresh_task
    if existing_task is not None and not existing_task.done():
        return

    async def _runner() -> None:
        try:
            if not immediate:
                await asyncio.sleep(1)
            await async_refresh_entry_discovery(hass, entry, runtime)
        except (DiscordCannotConnectError, DiscordGuildAccessError):
            return
        finally:
            runtime.discovery_refresh_task = None

    runtime.discovery_refresh_task = hass.async_create_background_task(
        _runner(),
        f"{runtime.entry_id}_discovery_refresh",
    )
