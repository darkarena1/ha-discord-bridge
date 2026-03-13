from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_BOT_TOKEN,
    CONF_GUILD_ID,
    DEFAULT_RECENT_MESSAGE_LIMIT,
    DOMAIN,
    ENTRY_DATA_BOT_USER_ID,
    ENTRY_DATA_BOT_USERNAME,
    ENTRY_DATA_GUILD_NAME,
    MAX_RECENT_MESSAGE_LIMIT,
)
from .discord_api import (
    DiscordCannotConnectError,
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_validate_discord_credentials,
)


class DiscordChatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                bootstrap = await async_validate_discord_credentials(
                    session=session,
                    bot_token=user_input[CONF_BOT_TOKEN],
                    guild_id=user_input[CONF_GUILD_ID],
                )
            except DiscordInvalidAuthError:
                errors["base"] = "invalid_auth"
            except DiscordGuildAccessError:
                errors["base"] = "guild_not_found"
            except DiscordCannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(bootstrap.guild_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=bootstrap.guild_name,
                    data={
                        **user_input,
                        ENTRY_DATA_GUILD_NAME: bootstrap.guild_name,
                        ENTRY_DATA_BOT_USER_ID: bootstrap.bot_user_id,
                        ENTRY_DATA_BOT_USERNAME: bootstrap.bot_username,
                    },
                    options={
                        "recent_message_limit": DEFAULT_RECENT_MESSAGE_LIMIT,
                        "include_archived_threads": False,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BOT_TOKEN): str,
                vol.Required(CONF_GUILD_ID): int,
                vol.Required(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return DiscordChatBridgeOptionsFlow(config_entry)


class DiscordChatBridgeOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    "recent_message_limit",
                    default=self.config_entry.options.get(
                        "recent_message_limit",
                        DEFAULT_RECENT_MESSAGE_LIMIT,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_RECENT_MESSAGE_LIMIT)),
                vol.Required(
                    "include_archived_threads",
                    default=self.config_entry.options.get("include_archived_threads", False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
