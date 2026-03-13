from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_BOT_TOKEN,
    CONF_GUILD_ID,
    DOMAIN,
    ENTRY_DATA_BOT_USER_ID,
    ENTRY_DATA_BOT_USERNAME,
    ENTRY_DATA_GUILD_NAME,
)
from .discord_api import (
    DiscordCannotConnectError,
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_validate_discord_credentials,
)

type DiscordChatBridgeConfigEntry = ConfigEntry


@dataclass(frozen=True)
class DiscordBridgeRuntimeData:
    guild_id: int
    guild_name: str
    bot_user_id: int
    bot_username: str
    api_key: str


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
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

    runtime = DiscordBridgeRuntimeData(
        guild_id=bootstrap.guild_id,
        guild_name=bootstrap.guild_name,
        bot_user_id=bootstrap.bot_user_id,
        bot_username=bootstrap.bot_username,
        api_key=entry.data[CONF_API_KEY],
    )
    hass.data[DOMAIN][entry.entry_id] = runtime

    hass.config_entries.async_update_entry(
        entry,
        title=bootstrap.guild_name,
        data={
            **entry.data,
            ENTRY_DATA_GUILD_NAME: bootstrap.guild_name,
            ENTRY_DATA_BOT_USER_ID: bootstrap.bot_user_id,
            ENTRY_DATA_BOT_USERNAME: bootstrap.bot_username,
        },
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DiscordChatBridgeConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
