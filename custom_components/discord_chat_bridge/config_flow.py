from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
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
    OPTION_CHANNELS,
    OPTION_RECENT_MESSAGE_LIMIT,
)
from .discord_api import (
    DiscordCannotConnectError,
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_validate_discord_credentials,
)

FORM_ENABLED_CHANNELS = "enabled_channels"
FORM_POSTING_CHANNELS = "posting_channels"
FORM_API_CHANNELS = "api_channels"


def _parse_guild_id(value: object) -> int:
    parsed = str(value).strip()
    if not parsed.isdigit():
        raise ValueError("Guild ID must contain only digits.")
    return int(parsed)


def _channel_label(
    channel_id: str,
    channel_data: dict,
    channel_map: dict[str, dict],
) -> str:
    prefix = "#"
    if channel_data.get("kind") == "thread":
        prefix = "Thread"

    label = f"{prefix} {channel_data.get('name', channel_id)}"
    parent_channel_id = channel_data.get("parent_channel_id")
    if parent_channel_id is not None:
        parent = channel_map.get(str(parent_channel_id))
        if parent is not None:
            label = f"{label} ({parent.get('name', parent_channel_id)})"
    return label


def _channel_selector_options(channel_map: dict[str, dict]) -> list[selector.SelectOptionDict]:
    def sort_key(item: tuple[str, dict]) -> tuple[int, str]:
        channel_id, channel_data = item
        return (int(channel_data.get("position", 0)), channel_data.get("name", channel_id))

    return [
        selector.SelectOptionDict(
            value=channel_id,
            label=_channel_label(channel_id, channel_data, channel_map),
        )
        for channel_id, channel_data in sorted(channel_map.items(), key=sort_key)
    ]


def _merge_channel_flag_updates(
    channel_map: dict[str, dict],
    *,
    enabled_channels: list[str],
    posting_channels: list[str],
    api_channels: list[str],
) -> dict[str, dict]:
    enabled_ids = set(enabled_channels)
    posting_ids = set(posting_channels) & enabled_ids
    api_ids = set(api_channels) & enabled_ids

    return {
        channel_id: {
            **channel_data,
            "enabled": channel_id in enabled_ids,
            "allow_posting": channel_id in posting_ids,
            "include_in_api": channel_id in api_ids,
        }
        for channel_id, channel_data in channel_map.items()
    }


class DiscordChatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                guild_id = _parse_guild_id(user_input[CONF_GUILD_ID])
            except ValueError:
                errors[CONF_GUILD_ID] = "invalid_guild_id"
            else:
                normalized_input = {
                    **user_input,
                    CONF_GUILD_ID: guild_id,
                }

                session = async_get_clientsession(self.hass)
                try:
                    bootstrap = await async_validate_discord_credentials(
                        session=session,
                        bot_token=normalized_input[CONF_BOT_TOKEN],
                        guild_id=normalized_input[CONF_GUILD_ID],
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
                            **normalized_input,
                            ENTRY_DATA_GUILD_NAME: bootstrap.guild_name,
                            ENTRY_DATA_BOT_USER_ID: bootstrap.bot_user_id,
                            ENTRY_DATA_BOT_USERNAME: bootstrap.bot_username,
                        },
                        options={
                            OPTION_CHANNELS: {},
                            OPTION_RECENT_MESSAGE_LIMIT: DEFAULT_RECENT_MESSAGE_LIMIT,
                        },
                    )

        default_guild_id = ""
        if user_input is not None:
            default_guild_id = str(user_input.get(CONF_GUILD_ID, "")).strip()

        schema = vol.Schema(
            {
                vol.Required(CONF_BOT_TOKEN): str,
                vol.Required(CONF_GUILD_ID, default=default_guild_id): str,
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
        channel_map = self.config_entry.options.get(OPTION_CHANNELS, {})

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    OPTION_CHANNELS: _merge_channel_flag_updates(
                        channel_map,
                        enabled_channels=user_input[FORM_ENABLED_CHANNELS],
                        posting_channels=user_input[FORM_POSTING_CHANNELS],
                        api_channels=user_input[FORM_API_CHANNELS],
                    ),
                    OPTION_RECENT_MESSAGE_LIMIT: user_input[OPTION_RECENT_MESSAGE_LIMIT],
                },
            )

        channel_options = _channel_selector_options(channel_map)
        schema = vol.Schema(
            {
                vol.Required(
                    OPTION_RECENT_MESSAGE_LIMIT,
                    default=self.config_entry.options.get(
                        OPTION_RECENT_MESSAGE_LIMIT,
                        DEFAULT_RECENT_MESSAGE_LIMIT,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_RECENT_MESSAGE_LIMIT)),
                vol.Required(
                    FORM_ENABLED_CHANNELS,
                    default=[
                        channel_id
                        for channel_id, channel_data in channel_map.items()
                        if channel_data.get("enabled", False)
                    ],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=channel_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    FORM_POSTING_CHANNELS,
                    default=[
                        channel_id
                        for channel_id, channel_data in channel_map.items()
                        if channel_data.get("allow_posting", False)
                    ],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=channel_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    FORM_API_CHANNELS,
                    default=[
                        channel_id
                        for channel_id, channel_data in channel_map.items()
                        if channel_data.get("include_in_api", False)
                    ],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=channel_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
