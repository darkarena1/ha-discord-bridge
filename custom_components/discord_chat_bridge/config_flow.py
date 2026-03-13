from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_API_KEY,
    CONF_BOT_TOKEN,
    CONF_GUILD_ID,
    DEFAULT_RECENT_MESSAGE_LIMIT,
    DOMAIN,
)


class DiscordChatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_GUILD_ID]))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Discord Guild {user_input[CONF_GUILD_ID]}",
                data=user_input,
                options={"recent_message_limit": DEFAULT_RECENT_MESSAGE_LIMIT},
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
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
                vol.Required(
                    "include_archived_threads",
                    default=self.config_entry.options.get("include_archived_threads", False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
