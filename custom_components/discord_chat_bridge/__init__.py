from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import async_register_views
from .const import (
    CONF_API_KEY,
    CONF_BOT_TOKEN,
    CONF_GUILD_ID,
    DOMAIN,
    ENTRY_DATA_BOT_USER_ID,
    ENTRY_DATA_BOT_USERNAME,
    ENTRY_DATA_GUILD_NAME,
    SERVICE_REFRESH_DISCOVERY,
)
from .coordinator import GuildState, build_guild_state, merge_discovered_channel_settings
from .discord_api import (
    DiscordCannotConnectError,
    DiscordChannelDescription,
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_fetch_discoverable_channels,
    async_validate_discord_credentials,
)
from .discovery import async_schedule_discovery_refresh
from .gateway import DiscordGatewayHandle, async_start_gateway, async_stop_gateway

type DiscordChatBridgeConfigEntry = ConfigEntry
PLATFORMS = ["binary_sensor", "sensor", "text", "button", "notify"]


@dataclass
class DiscordBridgeRuntimeData:
    entry_id: str
    guild_id: int
    guild_name: str
    bot_user_id: int
    bot_username: str
    api_key: str
    entry_data: dict
    guild_state: GuildState
    discovered_channels: tuple[DiscordChannelDescription, ...]
    drafts: dict[int, str] = field(default_factory=dict)
    gateway_handle: DiscordGatewayHandle | None = None
    discovery_refresh_task: asyncio.Task[None] | None = None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("_views_registered"):
        async_register_views(hass)
        hass.data[DOMAIN]["_views_registered"] = True
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_DISCOVERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_DISCOVERY,
            _make_refresh_discovery_handler(hass),
            schema=vol.Schema({vol.Optional(CONF_GUILD_ID): int}),
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DiscordChatBridgeConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    session = async_get_clientsession(hass)

    try:
        bootstrap = await async_validate_discord_credentials(
            session=session,
            bot_token=entry.data[CONF_BOT_TOKEN],
            guild_id=entry.data[CONF_GUILD_ID],
        )
    except DiscordInvalidAuthError as exc:
        raise ConfigEntryAuthFailed("Discord bot token is invalid.") from exc
    except DiscordGuildAccessError as exc:
        raise ConfigEntryAuthFailed("Discord guild is not accessible to this bot.") from exc
    except DiscordCannotConnectError as exc:
        raise ConfigEntryNotReady("Could not connect to Discord during setup.") from exc

    try:
        discovered_channels = await async_fetch_discoverable_channels(
            session=session,
            bot_token=entry.data[CONF_BOT_TOKEN],
            guild_id=entry.data[CONF_GUILD_ID],
        )
    except DiscordGuildAccessError as exc:
        raise ConfigEntryAuthFailed(
            "Discord guild channels are not accessible to this bot."
        ) from exc
    except DiscordCannotConnectError as exc:
        raise ConfigEntryNotReady("Could not discover Discord channels during setup.") from exc

    merged_options = merge_discovered_channel_settings(entry.options, discovered_channels)
    guild_state = build_guild_state(
        guild_id=bootstrap.guild_id,
        guild_name=bootstrap.guild_name,
        options=merged_options,
    )

    runtime = DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=bootstrap.guild_id,
        guild_name=bootstrap.guild_name,
        bot_user_id=bootstrap.bot_user_id,
        bot_username=bootstrap.bot_username,
        api_key=entry.data[CONF_API_KEY],
        entry_data=entry.data,
        guild_state=guild_state,
        discovered_channels=tuple(discovered_channels),
    )
    hass.data[DOMAIN][entry.entry_id] = runtime

    updated_data = {
        **entry.data,
        ENTRY_DATA_GUILD_NAME: bootstrap.guild_name,
        ENTRY_DATA_BOT_USER_ID: bootstrap.bot_user_id,
        ENTRY_DATA_BOT_USERNAME: bootstrap.bot_username,
    }
    if (
        entry.title != bootstrap.guild_name
        or entry.data != updated_data
        or entry.options != merged_options
    ):
        hass.config_entries.async_update_entry(
            entry,
            title=bootstrap.guild_name,
            data=updated_data,
            options=merged_options,
        )
    runtime.gateway_handle = await async_start_gateway(hass, runtime)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DiscordChatBridgeConfigEntry) -> bool:
    runtime = hass.data[DOMAIN].get(entry.entry_id)
    if runtime is not None and runtime.gateway_handle is not None:
        await async_stop_gateway(runtime.gateway_handle)
    if runtime is not None and runtime.discovery_refresh_task is not None:
        runtime.discovery_refresh_task.cancel()
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_reload_entry(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _make_refresh_discovery_handler(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], Awaitable[None]]:
    async def _handler(call: ServiceCall) -> None:
        requested_guild_id = call.data.get(CONF_GUILD_ID)
        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if runtime is None:
                continue
            if requested_guild_id is not None and runtime.guild_id != requested_guild_id:
                continue
            await async_schedule_discovery_refresh(hass, entry, runtime, immediate=True)

    return _handler
