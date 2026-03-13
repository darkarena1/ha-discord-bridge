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
FORM_CATEGORY_FILTER = "category_filter"
FORM_CHANNEL_KIND_FILTER = "channel_kind_filter"
FORM_SHOW_SELECTED_ONLY = "show_selected_only"

CATEGORY_FILTER_ALL = "__all__"
CATEGORY_FILTER_UNCATEGORIZED = "__uncategorized__"


class EnabledAction(StrEnum):
    NONE = "none"
    SELECT_ALL = "select_all"
    SELECT_ALL_TEXT_CHANNELS = "select_all_text_channels"
    SELECT_ALL_THREADS = "select_all_threads"
    CLEAR_ALL = "clear_all"


class ChannelKindFilter(StrEnum):
    ALL = "all"
    TEXT = "text_channel"
    THREAD = "thread"


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


def _category_selector_options(channel_map: dict[str, dict]) -> list[selector.SelectOptionDict]:
    options = [
        selector.SelectOptionDict(value=CATEGORY_FILTER_ALL, label="All categories"),
        selector.SelectOptionDict(
            value=CATEGORY_FILTER_UNCATEGORIZED,
            label="Uncategorized",
        ),
    ]
    categories = {
        str(channel_data.get("category_id")): channel_data.get("category_name")
        for channel_data in channel_map.values()
        if channel_data.get("category_id") is not None and channel_data.get("category_name")
    }
    for category_id, category_name in sorted(
        categories.items(),
        key=lambda item: str(item[1]).casefold(),
    ):
        options.append(
            selector.SelectOptionDict(
                value=category_id,
                label=str(category_name),
            )
        )
    return options


def _filter_channel_ids(
    channel_map: dict[str, dict],
    *,
    category_filter: str,
    kind_filter: str,
    show_selected_only: bool,
) -> set[str]:
    include_ids: set[str] = set()
    for channel_id, channel_data in channel_map.items():
        if show_selected_only and not channel_data.get("enabled", False):
            continue
        if (
            category_filter != CATEGORY_FILTER_ALL
            and not _matches_category_filter(channel_data, category_filter)
        ):
            continue
        if kind_filter != ChannelKindFilter.ALL.value and channel_data.get("kind") != kind_filter:
            continue
        include_ids.add(channel_id)
    return include_ids


def _matches_category_filter(channel_data: dict, category_filter: str) -> bool:
    category_id = channel_data.get("category_id")
    if category_filter == CATEGORY_FILTER_UNCATEGORIZED:
        return category_id in {None, ""}
    return str(category_id) == category_filter


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
        self._category_filter = CATEGORY_FILTER_ALL
        self._channel_kind_filter = ChannelKindFilter.ALL.value
        self._show_selected_only = False

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        channel_map = self.config_entry.options.get(OPTION_CHANNELS, {})

        if user_input is not None:
            self._recent_message_limit = user_input[OPTION_RECENT_MESSAGE_LIMIT]
            self._category_filter = user_input[FORM_CATEGORY_FILTER]
            self._channel_kind_filter = user_input[FORM_CHANNEL_KIND_FILTER]
            self._show_selected_only = user_input[FORM_SHOW_SELECTED_ONLY]
            return await self.async_step_enabled()

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
                    FORM_CATEGORY_FILTER,
                    default=self._category_filter,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_category_selector_options(channel_map),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    FORM_CHANNEL_KIND_FILTER,
                    default=self._channel_kind_filter,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=ChannelKindFilter.ALL.value,
                                label="All channel types",
                            ),
                            selector.SelectOptionDict(
                                value=ChannelKindFilter.TEXT.value,
                                label="Text channels",
                            ),
                            selector.SelectOptionDict(
                                value=ChannelKindFilter.THREAD.value,
                                label="Threads",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    FORM_SHOW_SELECTED_ONLY,
                    default=self._show_selected_only,
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_enabled(self, user_input: dict | None = None) -> FlowResult:
        channel_map = self.config_entry.options.get(OPTION_CHANNELS, {})
        filtered_ids = _filter_channel_ids(
            channel_map,
            category_filter=self._category_filter,
            kind_filter=self._channel_kind_filter,
            show_selected_only=self._show_selected_only,
        )

        if user_input is not None:
            existing_enabled = {
                channel_id
                for channel_id, channel_data in channel_map.items()
                if channel_data.get("enabled", False)
            }
            resolved_filtered_enabled = set(
                _resolve_enabled_channels(
                    {
                        channel_id: channel_data
                        for channel_id, channel_data in channel_map.items()
                        if channel_id in filtered_ids
                    },
                    selected_channels=user_input[FORM_ENABLED_CHANNELS],
                    enabled_action=user_input[FORM_ENABLED_ACTION],
                )
            )
            self._enabled_channels = sorted(
                (existing_enabled - filtered_ids) | resolved_filtered_enabled
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
                        OPTION_RECENT_MESSAGE_LIMIT: self._recent_message_limit,
                    },
                )

            return await self.async_step_permissions()

        channel_options = _channel_selector_options(channel_map, include_ids=filtered_ids)
        schema = vol.Schema(
            {
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
                        if channel_id in filtered_ids and channel_data.get("enabled", False)
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
        return self.async_show_form(step_id="enabled", data_schema=schema)

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
