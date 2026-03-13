from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    OPTION_INCLUDE_ARCHIVED_THREADS,
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

type DiscordChatBridgeConfigEntry = ConfigEntry
PLATFORMS = ["sensor", "text", "button", "notify"]


@dataclass(frozen=True)
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
    drafts: dict[int, str]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("_views_registered"):
        async_register_views(hass)
        hass.data[DOMAIN]["_views_registered"] = True
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

    include_archived_threads = bool(
        entry.options.get(OPTION_INCLUDE_ARCHIVED_THREADS, False)
    )

    try:
        discovered_channels = await async_fetch_discoverable_channels(
            session=session,
            bot_token=entry.data[CONF_BOT_TOKEN],
            guild_id=entry.data[CONF_GUILD_ID],
            include_archived_threads=include_archived_threads,
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
        drafts={},
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
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DiscordChatBridgeConfigEntry) -> bool:
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_reload_entry(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
