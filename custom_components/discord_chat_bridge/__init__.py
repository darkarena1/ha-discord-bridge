from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import async_register_views
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
    SERVICE_REFRESH_DISCOVERY,
    SERVICE_REFRESH_PINS,
    SERVICE_REFRESH_RECENT_MESSAGES,
)
from .coordinator import (
    GuildState,
    build_guild_state,
    cache_pinned_messages,
    cache_recent_messages,
    merge_discovered_channel_settings,
)
from .discord_api import (
    DiscordCannotConnectError,
    DiscordChannelDescription,
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_fetch_channel_messages,
    async_fetch_discoverable_channels,
    async_fetch_pinned_messages,
    async_validate_discord_credentials,
)
from .discovery import async_schedule_discovery_refresh
from .entity import channel_state_signal
from .gateway import DiscordGatewayHandle, async_start_gateway, async_stop_gateway

type DiscordChatBridgeConfigEntry = ConfigEntry
PLATFORMS = ["binary_sensor", "sensor", "switch", "text", "button", "notify"]
BASE_ENTITY_UNIQUE_SUFFIXES = (
    "active",
    "last_message",
    "last_message_author",
    "last_message_at",
)
CONFIG_ENTITY_UNIQUE_SUFFIXES = (
    "posting_enabled",
    "api_enabled",
)
POSTING_ENTITY_UNIQUE_SUFFIXES = (
    "draft",
    "send_draft",
    "notify",
)


def _parse_guild_id_filter(value: object | None) -> int | None:
    return _parse_discord_id_filter(value, label="Guild ID")


def _parse_channel_id_filter(value: object | None) -> int | None:
    return _parse_discord_id_filter(value, label="Channel ID")


def _parse_discord_id_filter(value: object | None, *, label: str) -> int | None:
    if value is None:
        return None
    parsed = str(value).strip()
    if not parsed:
        return None
    if not parsed.isdigit():
        raise ValueError(f"{label} must contain only digits.")
    return int(parsed)


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
            schema=vol.Schema({vol.Optional(CONF_GUILD_ID): str}),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_RECENT_MESSAGES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_RECENT_MESSAGES,
            _make_refresh_recent_messages_handler(hass),
            schema=vol.Schema(
                {
                    vol.Optional(CONF_GUILD_ID): str,
                    vol.Optional("channel_id"): str,
                    vol.Optional("limit"): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=1, max=MAX_RECENT_MESSAGE_LIMIT),
                    ),
                }
            ),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_PINS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_PINS,
            _make_refresh_pins_handler(hass),
            schema=vol.Schema(
                {
                    vol.Optional(CONF_GUILD_ID): str,
                    vol.Optional("channel_id"): str,
                }
            ),
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
    await async_preload_recent_message_state(
        session=session,
        entry=entry,
        guild_state=guild_state,
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
    async_cleanup_stale_entities(hass, entry, runtime)

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
        try:
            requested_guild_id = _parse_guild_id_filter(call.data.get(CONF_GUILD_ID))
        except ValueError:
            return
        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if runtime is None:
                continue
            if requested_guild_id is not None and runtime.guild_id != requested_guild_id:
                continue
            await async_schedule_discovery_refresh(hass, entry, runtime, immediate=True)

    return _handler


async def async_preload_recent_message_state(
    *,
    session,
    entry: DiscordChatBridgeConfigEntry,
    guild_state: GuildState,
) -> None:
    limit = _resolve_recent_message_limit(
        None,
        entry.entry_id,
        override=entry.options.get(OPTION_RECENT_MESSAGE_LIMIT),
        entry=entry,
    )
    for channel_id, channel_state in guild_state.channels.items():
        if not channel_state.enabled:
            continue
        try:
            messages = await async_fetch_channel_messages(
                session=session,
                bot_token=entry.data[CONF_BOT_TOKEN],
                channel_id=channel_id,
                limit=limit,
            )
        except (DiscordCannotConnectError, DiscordGuildAccessError):
            continue
        cache_recent_messages(
            guild_state,
            channel_id,
            messages,
            limit=limit,
        )


def _make_refresh_recent_messages_handler(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], Awaitable[None]]:
    async def _handler(call: ServiceCall) -> None:
        try:
            requested_guild_id = _parse_guild_id_filter(call.data.get(CONF_GUILD_ID))
            requested_channel_id = _parse_channel_id_filter(call.data.get("channel_id"))
        except ValueError:
            return

        session = async_get_clientsession(hass)
        for target in _matching_refresh_targets(
            hass,
            requested_guild_id=requested_guild_id,
            requested_channel_id=requested_channel_id,
        ):
            limit = _resolve_recent_message_limit(
                hass,
                target.runtime.entry_id,
                override=call.data.get("limit"),
            )
            try:
                messages = await async_fetch_channel_messages(
                    session=session,
                    bot_token=target.runtime.entry_data[CONF_BOT_TOKEN],
                    channel_id=target.channel_id,
                    limit=limit,
                )
            except (DiscordCannotConnectError, DiscordGuildAccessError):
                continue

            cache_recent_messages(
                target.runtime.guild_state,
                target.channel_id,
                messages,
                limit=limit,
            )
            async_dispatcher_send(
                hass,
                channel_state_signal(target.runtime.entry_id, target.channel_id),
            )

    return _handler


def _make_refresh_pins_handler(
    hass: HomeAssistant,
) -> Callable[[ServiceCall], Awaitable[None]]:
    async def _handler(call: ServiceCall) -> None:
        try:
            requested_guild_id = _parse_guild_id_filter(call.data.get(CONF_GUILD_ID))
            requested_channel_id = _parse_channel_id_filter(call.data.get("channel_id"))
        except ValueError:
            return

        session = async_get_clientsession(hass)
        for target in _matching_refresh_targets(
            hass,
            requested_guild_id=requested_guild_id,
            requested_channel_id=requested_channel_id,
        ):
            try:
                messages = await async_fetch_pinned_messages(
                    session=session,
                    bot_token=target.runtime.entry_data[CONF_BOT_TOKEN],
                    channel_id=target.channel_id,
                )
            except (DiscordCannotConnectError, DiscordGuildAccessError):
                continue

            cache_pinned_messages(target.runtime.guild_state, target.channel_id, messages)
            async_dispatcher_send(
                hass,
                channel_state_signal(target.runtime.entry_id, target.channel_id),
            )

    return _handler


@dataclass(frozen=True)
class _RefreshTarget:
    runtime: DiscordBridgeRuntimeData
    channel_id: int


def _matching_refresh_targets(
    hass: HomeAssistant,
    *,
    requested_guild_id: int | None,
    requested_channel_id: int | None,
) -> list[_RefreshTarget]:
    targets: list[_RefreshTarget] = []
    runtimes = hass.data.get(DOMAIN, {})
    for runtime in runtimes.values():
        if not isinstance(runtime, DiscordBridgeRuntimeData):
            continue
        if requested_guild_id is not None and runtime.guild_id != requested_guild_id:
            continue

        for channel_id, channel_state in runtime.guild_state.channels.items():
            if not channel_state.enabled:
                continue
            if requested_channel_id is not None and channel_id != requested_channel_id:
                continue
            targets.append(
                _RefreshTarget(
                    runtime=runtime,
                    channel_id=channel_id,
                )
            )

    return targets


def _resolve_recent_message_limit(
    hass: HomeAssistant | None,
    entry_id: str,
    *,
    override: object | None,
    entry: DiscordChatBridgeConfigEntry | None = None,
) -> int:
    if isinstance(override, int):
        return max(1, min(override, MAX_RECENT_MESSAGE_LIMIT))

    if entry is None:
        if hass is None:
            return DEFAULT_RECENT_MESSAGE_LIMIT
        entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        return DEFAULT_RECENT_MESSAGE_LIMIT

    configured = entry.options.get(OPTION_RECENT_MESSAGE_LIMIT, DEFAULT_RECENT_MESSAGE_LIMIT)
    if not isinstance(configured, int):
        return DEFAULT_RECENT_MESSAGE_LIMIT
    return max(1, min(configured, MAX_RECENT_MESSAGE_LIMIT))


@callback
def async_cleanup_stale_entities(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
    runtime: DiscordBridgeRuntimeData,
) -> None:
    registry = er.async_get(hass)
    expected_unique_ids = {
        f"{runtime.guild_id}_{channel_state.channel_id}_{suffix}"
        for channel_state in runtime.guild_state.channels.values()
        if channel_state.enabled
        for suffix in (
            BASE_ENTITY_UNIQUE_SUFFIXES
            + CONFIG_ENTITY_UNIQUE_SUFFIXES
            + (POSTING_ENTITY_UNIQUE_SUFFIXES if channel_state.posting_enabled else ())
        )
    }

    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.platform != DOMAIN:
            continue
        if registry_entry.unique_id in expected_unique_ids:
            continue
        registry.async_remove(registry_entry.entity_id)


@callback
def async_update_channel_capability(
    hass: HomeAssistant,
    entry_id: str,
    channel_id: int,
    *,
    capability_key: str,
    enabled: bool,
) -> None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        return

    channel_map = entry.options.get(OPTION_CHANNELS, {})
    channel_id_str = str(channel_id)
    channel_data = channel_map.get(channel_id_str)
    if channel_data is None or not channel_data.get("enabled", False):
        return

    normalized_enabled = bool(enabled)
    existing_value = bool(channel_data.get(capability_key, False))
    if existing_value == normalized_enabled:
        return

    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            OPTION_CHANNELS: {
                **channel_map,
                channel_id_str: {
                    **channel_data,
                    capability_key: normalized_enabled,
                },
            },
        },
    )
