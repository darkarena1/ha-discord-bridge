from __future__ import annotations

from enum import StrEnum

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
FORM_ENABLED_ACTION = "enabled_action"


class EnabledAction(StrEnum):
    NONE = "none"
    SELECT_ALL = "select_all"
    SELECT_ALL_TEXT_CHANNELS = "select_all_text_channels"
    SELECT_ALL_THREADS = "select_all_threads"
    CLEAR_ALL = "clear_all"


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
    if channel_data.get("kind") == "thread":
        parent_channel_id = channel_data.get("parent_channel_id")
        parent = channel_map.get(str(parent_channel_id)) if parent_channel_id is not None else None
        if parent is not None:
            parent_name = parent.get("name", parent_channel_id)
            channel_name = channel_data.get("name", channel_id)
            return f"{parent_name} / {channel_name}"
        return f"Thread / {channel_data.get('name', channel_id)}"

    return channel_data.get("name", channel_id)


def _channel_selector_options(
    channel_map: dict[str, dict],
    *,
    include_ids: set[str] | None = None,
) -> list[selector.SelectOptionDict]:
    filtered_channel_map = {
        channel_id: channel_data
        for channel_id, channel_data in channel_map.items()
        if include_ids is None or channel_id in include_ids
    }

    text_channels: list[tuple[str, dict]] = []
    threads_by_parent: dict[str, list[tuple[str, dict]]] = {}
    orphan_threads: list[tuple[str, dict]] = []

    for channel_id, channel_data in filtered_channel_map.items():
        if channel_data.get("kind") == "thread":
            parent_channel_id = str(channel_data.get("parent_channel_id"))
            if parent_channel_id in filtered_channel_map:
                threads_by_parent.setdefault(parent_channel_id, []).append(
                    (channel_id, channel_data)
                )
            else:
                orphan_threads.append((channel_id, channel_data))
            continue
        text_channels.append((channel_id, channel_data))

    def sort_key(item: tuple[str, dict]) -> tuple[str, str]:
        channel_id, channel_data = item
        return (channel_data.get("name", channel_id).casefold(), channel_id)

    options: list[selector.SelectOptionDict] = []
    for channel_id, channel_data in sorted(text_channels, key=sort_key):
        options.append(
            selector.SelectOptionDict(
                value=channel_id,
                label=_channel_label(channel_id, channel_data, channel_map),
            )
        )
        for thread_id, thread_data in sorted(threads_by_parent.get(channel_id, []), key=sort_key):
            options.append(
                selector.SelectOptionDict(
                    value=thread_id,
                    label=_channel_label(thread_id, thread_data, channel_map),
                )
            )

    for thread_id, thread_data in sorted(orphan_threads, key=sort_key):
        options.append(
            selector.SelectOptionDict(
                value=thread_id,
                label=_channel_label(thread_id, thread_data, channel_map),
            )
        )

    return options


def _resolve_enabled_channels(
    channel_map: dict[str, dict],
    *,
    selected_channels: list[str],
    enabled_action: str,
) -> list[str]:
    all_channel_ids = list(channel_map)
    text_channel_ids = [
        channel_id
        for channel_id, channel_data in channel_map.items()
        if channel_data.get("kind") != "thread"
    ]
    thread_ids = [
        channel_id
        for channel_id, channel_data in channel_map.items()
        if channel_data.get("kind") == "thread"
    ]

    match EnabledAction(enabled_action):
        case EnabledAction.SELECT_ALL:
            return all_channel_ids
        case EnabledAction.SELECT_ALL_TEXT_CHANNELS:
            return text_channel_ids
        case EnabledAction.SELECT_ALL_THREADS:
            return thread_ids
        case EnabledAction.CLEAR_ALL:
            return []
        case EnabledAction.NONE:
            return selected_channels


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
        return DiscordChatBridgeOptionsFlow()


class DiscordChatBridgeOptionsFlow(config_entries.OptionsFlow):
    def __init__(self) -> None:
        self._enabled_channels: list[str] | None = None
        self._recent_message_limit = DEFAULT_RECENT_MESSAGE_LIMIT

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        channel_map = self.config_entry.options.get(OPTION_CHANNELS, {})

        if user_input is not None:
            self._enabled_channels = _resolve_enabled_channels(
                channel_map,
                selected_channels=user_input[FORM_ENABLED_CHANNELS],
                enabled_action=user_input[FORM_ENABLED_ACTION],
            )

            if not self._enabled_channels:
                return self.async_create_entry(
                    title="",
                    data={
                        OPTION_CHANNELS: _merge_channel_flag_updates(
                            channel_map,
                            enabled_channels=[],
                            posting_channels=[],
                            api_channels=[],
                        ),
                        OPTION_RECENT_MESSAGE_LIMIT: user_input[OPTION_RECENT_MESSAGE_LIMIT],
                    },
                )

            self._recent_message_limit = user_input[OPTION_RECENT_MESSAGE_LIMIT]
            return await self.async_step_permissions()

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
                    FORM_ENABLED_ACTION,
                    default=EnabledAction.NONE.value,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=EnabledAction.NONE.value,
                                label="Use manual selection",
                            ),
                            selector.SelectOptionDict(
                                value=EnabledAction.SELECT_ALL.value,
                                label="Select all channels",
                            ),
                            selector.SelectOptionDict(
                                value=EnabledAction.SELECT_ALL_TEXT_CHANNELS.value,
                                label="Select all text channels",
                            ),
                            selector.SelectOptionDict(
                                value=EnabledAction.SELECT_ALL_THREADS.value,
                                label="Select all threads",
                            ),
                            selector.SelectOptionDict(
                                value=EnabledAction.CLEAR_ALL.value,
                                label="Clear all selections",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_permissions(self, user_input: dict | None = None) -> FlowResult:
        channel_map = self.config_entry.options.get(OPTION_CHANNELS, {})
        enabled_channels = self._enabled_channels or [
            channel_id
            for channel_id, channel_data in channel_map.items()
            if channel_data.get("enabled", False)
        ]

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    OPTION_CHANNELS: _merge_channel_flag_updates(
                        channel_map,
                        enabled_channels=enabled_channels,
                        posting_channels=user_input[FORM_POSTING_CHANNELS],
                        api_channels=user_input[FORM_API_CHANNELS],
                    ),
                    OPTION_RECENT_MESSAGE_LIMIT: self._recent_message_limit,
                },
            )

        enabled_channel_ids = set(enabled_channels)
        channel_options = _channel_selector_options(channel_map, include_ids=enabled_channel_ids)
        schema = vol.Schema(
            {
                vol.Required(
                    FORM_POSTING_CHANNELS,
                    default=[
                        channel_id
                        for channel_id, channel_data in channel_map.items()
                        if channel_id in enabled_channel_ids
                        and channel_data.get("allow_posting", False)
                    ],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=channel_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    FORM_API_CHANNELS,
                    default=[
                        channel_id
                        for channel_id, channel_data in channel_map.items()
                        if channel_id in enabled_channel_ids
                        and channel_data.get("include_in_api", False)
                    ],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=channel_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="permissions", data_schema=schema)
