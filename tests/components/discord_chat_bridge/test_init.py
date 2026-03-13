from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er

import custom_components.discord_chat_bridge as integration
from custom_components.discord_chat_bridge.const import (
    CONF_API_KEY,
    CONF_BOT_TOKEN,
    CONF_GUILD_ID,
    DEFAULT_RECENT_MESSAGE_LIMIT,
    DOMAIN,
    ENTRY_DATA_BOT_USER_ID,
    ENTRY_DATA_BOT_USERNAME,
    ENTRY_DATA_GUILD_NAME,
    OPTION_RECENT_MESSAGE_LIMIT,
    SERVICE_REFRESH_DISCOVERY,
    SERVICE_REFRESH_PINS,
    SERVICE_REFRESH_RECENT_MESSAGES,
)
from custom_components.discord_chat_bridge.coordinator import build_guild_state
from custom_components.discord_chat_bridge.discord_api import (
    DiscordChannelDescription,
    DiscordGuildBootstrap,
    DiscordInvalidAuthError,
)


class FakeServices:
    def __init__(self) -> None:
        self._services: dict[tuple[str, str], dict[str, object]] = {}

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._services

    def async_register(
        self,
        domain: str,
        service: str,
        handler: object,
        *,
        schema: object | None = None,
    ) -> None:
        self._services[(domain, service)] = {
            "handler": handler,
            "schema": schema,
        }


class FakeConfigEntries:
    def __init__(self) -> None:
        self.updated_calls: list[dict[str, object]] = []
        self.forwarded_calls: list[tuple[FakeEntry, list[str]]] = []
        self.unloaded_calls: list[tuple[FakeEntry, list[str]]] = []
        self.reload_calls: list[str] = []
        self.entries_by_domain: dict[str, list[FakeEntry]] = {}

    def async_update_entry(
        self,
        entry: FakeEntry,
        *,
        title: str | None = None,
        data: dict | None = None,
        options: dict | None = None,
    ) -> None:
        if title is not None:
            entry.title = title
        if data is not None:
            entry.data = data
        if options is not None:
            entry.options = options
        self.updated_calls.append(
            {
                "entry": entry,
                "title": title,
                "data": data,
                "options": options,
            }
        )

    async def async_forward_entry_setups(self, entry: FakeEntry, platforms: list[str]) -> None:
        self.forwarded_calls.append((entry, platforms))

    async def async_unload_platforms(self, entry: FakeEntry, platforms: list[str]) -> bool:
        self.unloaded_calls.append((entry, platforms))
        return True

    async def async_reload(self, entry_id: str) -> None:
        self.reload_calls.append(entry_id)

    def async_entries(self, domain: str) -> list[FakeEntry]:
        return list(self.entries_by_domain.get(domain, []))

    def async_get_entry(self, entry_id: str) -> FakeEntry | None:
        for entries in self.entries_by_domain.values():
            for entry in entries:
                if entry.entry_id == entry_id:
                    return entry
        return None


class FakeEntry:
    def __init__(
        self,
        *,
        entry_id: str = "entry-1",
        title: str = "Original Title",
        data: dict | None = None,
        options: dict | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.title = title
        self.data = data or {
            CONF_BOT_TOKEN: "bot-token",
            CONF_GUILD_ID: 1234,
            CONF_API_KEY: "api-key",
        }
        self.options = options or {}
        self.update_listeners: list[object] = []
        self.unload_callbacks: list[object] = []

    def add_update_listener(self, listener: object) -> object:
        self.update_listeners.append(listener)
        return lambda: None

    def async_on_unload(self, callback: object) -> None:
        self.unload_callbacks.append(callback)


class FakeHomeAssistant:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()

    def async_create_background_task(self, coro: object, name: str) -> asyncio.Task[None]:
        return asyncio.create_task(coro, name=name)


class FakeRegistryEntry:
    def __init__(
        self,
        *,
        entity_id: str,
        unique_id: str,
        platform: str = DOMAIN,
    ) -> None:
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.platform = platform


class FakeEntityRegistry:
    def __init__(self, entries: list[FakeRegistryEntry]) -> None:
        self.entries = entries
        self.removed: list[str] = []

    def async_remove(self, entity_id: str) -> None:
        self.removed.append(entity_id)


@pytest.mark.asyncio
async def test_async_setup_registers_views_and_service_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    register_views = MagicMock()
    monkeypatch.setattr(integration, "async_register_views", register_views)

    assert await integration.async_setup(hass, {}) is True
    assert await integration.async_setup(hass, {}) is True

    assert register_views.call_count == 1
    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_DISCOVERY)
    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_RECENT_MESSAGES)
    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_PINS)


@pytest.mark.asyncio
async def test_async_setup_entry_bootstraps_runtime_and_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry()
    bootstrap = DiscordGuildBootstrap(
        guild_id=1234,
        guild_name="KCBN",
        bot_user_id=42,
        bot_username="KillBot",
    )
    discovered_channels = [
        DiscordChannelDescription(
            channel_id=100,
            name="briefing",
            kind="text_channel",
            position=1,
        ),
        DiscordChannelDescription(
            channel_id=200,
            name="ops-thread",
            kind="thread",
            position=2,
            parent_channel_id=100,
        ),
    ]
    gateway_handle = object()
    fake_registry = FakeEntityRegistry([])

    monkeypatch.setattr(integration, "async_get_clientsession", lambda hass: object())
    monkeypatch.setattr(
        integration,
        "async_validate_discord_credentials",
        AsyncMock(return_value=bootstrap),
    )
    monkeypatch.setattr(
        integration,
        "async_fetch_discoverable_channels",
        AsyncMock(return_value=discovered_channels),
    )
    monkeypatch.setattr(
        integration,
        "async_start_gateway",
        AsyncMock(return_value=gateway_handle),
    )
    monkeypatch.setattr(er, "async_get", lambda hass: fake_registry)
    monkeypatch.setattr(er, "async_entries_for_config_entry", lambda registry, entry_id: [])

    assert await integration.async_setup_entry(hass, entry) is True

    runtime = hass.data[DOMAIN][entry.entry_id]
    assert runtime.guild_id == 1234
    assert runtime.guild_name == "KCBN"
    assert runtime.bot_user_id == 42
    assert runtime.bot_username == "KillBot"
    assert runtime.api_key == "api-key"
    assert runtime.discovered_channels == tuple(discovered_channels)
    assert runtime.gateway_handle is gateway_handle
    assert runtime.guild_state.channels[100].name == "briefing"
    assert runtime.guild_state.channels[200].parent_channel_id == 100

    assert entry.title == "KCBN"
    assert entry.data[ENTRY_DATA_GUILD_NAME] == "KCBN"
    assert entry.data[ENTRY_DATA_BOT_USER_ID] == 42
    assert entry.data[ENTRY_DATA_BOT_USERNAME] == "KillBot"
    assert entry.options["channels"]["100"]["enabled"] is False
    assert entry.update_listeners == [integration.async_reload_entry]
    assert len(entry.unload_callbacks) == 1
    assert hass.config_entries.forwarded_calls == [(entry, integration.PLATFORMS)]
    assert len(hass.config_entries.updated_calls) == 1


@pytest.mark.asyncio
async def test_async_setup_entry_raises_auth_failed_for_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry()

    monkeypatch.setattr(integration, "async_get_clientsession", lambda hass: object())
    monkeypatch.setattr(
        integration,
        "async_validate_discord_credentials",
        AsyncMock(side_effect=DiscordInvalidAuthError("bad token")),
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await integration.async_setup_entry(hass, entry)

    assert hass.data[DOMAIN] == {}


@pytest.mark.asyncio
async def test_async_unload_entry_stops_gateway_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry()
    gateway_handle = object()
    discovery_task = asyncio.create_task(asyncio.sleep(60))
    runtime = integration.DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=1234,
        guild_name="KCBN",
        bot_user_id=42,
        bot_username="KillBot",
        api_key="api-key",
        entry_data=entry.data,
        guild_state=build_guild_state(1234, "KCBN", {}),
        discovered_channels=(),
        gateway_handle=gateway_handle,
        discovery_refresh_task=discovery_task,
    )
    hass.data[DOMAIN] = {entry.entry_id: runtime}
    stop_gateway = AsyncMock()
    monkeypatch.setattr(integration, "async_stop_gateway", stop_gateway)

    assert await integration.async_unload_entry(hass, entry) is True
    await asyncio.sleep(0)

    stop_gateway.assert_awaited_once_with(gateway_handle)
    assert discovery_task.cancelled() is True
    assert hass.config_entries.unloaded_calls == [(entry, integration.PLATFORMS)]
    assert entry.entry_id not in hass.data[DOMAIN]

    with suppress(asyncio.CancelledError):
        await discovery_task


@pytest.mark.asyncio
async def test_async_reload_entry_calls_home_assistant_reload() -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry(entry_id="reload-me")

    await integration.async_reload_entry(hass, entry)

    assert hass.config_entries.reload_calls == ["reload-me"]


@pytest.mark.asyncio
async def test_refresh_discovery_service_handler_filters_by_guild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry_one = FakeEntry(entry_id="entry-1", data={
        CONF_BOT_TOKEN: "token-1",
        CONF_GUILD_ID: 111,
        CONF_API_KEY: "shared-key",
    })
    entry_two = FakeEntry(entry_id="entry-2", data={
        CONF_BOT_TOKEN: "token-2",
        CONF_GUILD_ID: 222,
        CONF_API_KEY: "shared-key",
    })
    hass.config_entries.entries_by_domain[DOMAIN] = [entry_one, entry_two]

    runtime_one = integration.DiscordBridgeRuntimeData(
        entry_id=entry_one.entry_id,
        guild_id=111,
        guild_name="Guild One",
        bot_user_id=1,
        bot_username="Bot One",
        api_key="shared-key",
        entry_data=entry_one.data,
        guild_state=build_guild_state(111, "Guild One", {}),
        discovered_channels=(),
    )
    runtime_two = integration.DiscordBridgeRuntimeData(
        entry_id=entry_two.entry_id,
        guild_id=222,
        guild_name="Guild Two",
        bot_user_id=2,
        bot_username="Bot Two",
        api_key="shared-key",
        entry_data=entry_two.data,
        guild_state=build_guild_state(222, "Guild Two", {}),
        discovered_channels=(),
    )
    hass.data[DOMAIN] = {
        entry_one.entry_id: runtime_one,
        entry_two.entry_id: runtime_two,
    }

    schedule_refresh = AsyncMock()
    monkeypatch.setattr(integration, "async_schedule_discovery_refresh", schedule_refresh)
    handler = integration._make_refresh_discovery_handler(hass)

    await handler(SimpleNamespace(data={}))

    schedule_refresh.assert_has_awaits(
        [
            call(hass, entry_one, runtime_one, immediate=True),
            call(hass, entry_two, runtime_two, immediate=True),
        ]
    )

    schedule_refresh.reset_mock()
    await handler(SimpleNamespace(data={CONF_GUILD_ID: "222"}))

    schedule_refresh.assert_awaited_once_with(hass, entry_two, runtime_two, immediate=True)


@pytest.mark.asyncio
async def test_refresh_discovery_service_handler_ignores_invalid_guild_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry(entry_id="entry-1", data={
        CONF_BOT_TOKEN: "token-1",
        CONF_GUILD_ID: 111,
        CONF_API_KEY: "shared-key",
    })
    hass.config_entries.entries_by_domain[DOMAIN] = [entry]
    runtime = integration.DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=111,
        guild_name="Guild One",
        bot_user_id=1,
        bot_username="Bot One",
        api_key="shared-key",
        entry_data=entry.data,
        guild_state=build_guild_state(111, "Guild One", {}),
        discovered_channels=(),
    )
    hass.data[DOMAIN] = {entry.entry_id: runtime}

    schedule_refresh = AsyncMock()
    monkeypatch.setattr(integration, "async_schedule_discovery_refresh", schedule_refresh)
    handler = integration._make_refresh_discovery_handler(hass)

    await handler(SimpleNamespace(data={CONF_GUILD_ID: "not-a-number"}))

    schedule_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_recent_messages_service_updates_enabled_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry(
        entry_id="entry-1",
        data={
            CONF_BOT_TOKEN: "token-1",
            CONF_GUILD_ID: 111,
            CONF_API_KEY: "shared-key",
        },
        options={
            OPTION_RECENT_MESSAGE_LIMIT: 7,
            "channels": {
                "100": {
                    "name": "briefing",
                    "kind": "text_channel",
                    "enabled": True,
                    "allow_posting": False,
                    "include_in_api": True,
                },
                "200": {
                    "name": "ignored",
                    "kind": "text_channel",
                    "enabled": False,
                    "allow_posting": False,
                    "include_in_api": False,
                },
            },
        },
    )
    hass.config_entries.entries_by_domain[DOMAIN] = [entry]
    runtime = integration.DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=111,
        guild_name="Guild One",
        bot_user_id=1,
        bot_username="Bot One",
        api_key="shared-key",
        entry_data=entry.data,
        guild_state=build_guild_state(111, "Guild One", entry.options),
        discovered_channels=(),
    )
    hass.data[DOMAIN] = {entry.entry_id: runtime}

    fetch_messages = AsyncMock(
        return_value=[
            {
                "message_id": 999,
                "channel_id": 100,
                "author_id": 5,
                "author_name": "GM",
                "content": "Fresh cache",
                "created_at": "2026-03-13T12:00:00+00:00",
                "jump_url": "https://discord.example/messages/999",
                "attachments": (),
            }
        ]
    )
    send_signal = MagicMock()
    session = object()
    monkeypatch.setattr(integration, "async_get_clientsession", lambda hass: session)
    monkeypatch.setattr(integration, "async_fetch_channel_messages", fetch_messages)
    monkeypatch.setattr(integration, "async_dispatcher_send", send_signal)
    handler = integration._make_refresh_recent_messages_handler(hass)

    await handler(SimpleNamespace(data={}))

    fetch_messages.assert_awaited_once_with(
        session=session,
        bot_token="token-1",
        channel_id=100,
        limit=7,
    )
    assert runtime.guild_state.channels[100].last_message_preview == "Fresh cache"
    assert len(runtime.guild_state.channels[100].recent_messages) == 1
    assert runtime.guild_state.channels[200].recent_messages == []
    send_signal.assert_called_once_with(
        hass,
        "discord_chat_bridge_channel_state_updated_entry-1_100",
    )


@pytest.mark.asyncio
async def test_refresh_recent_messages_service_honors_filters_and_limit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry(
        entry_id="entry-1",
        data={
            CONF_BOT_TOKEN: "token-1",
            CONF_GUILD_ID: 111,
            CONF_API_KEY: "shared-key",
        },
        options={
            OPTION_RECENT_MESSAGE_LIMIT: DEFAULT_RECENT_MESSAGE_LIMIT,
            "channels": {
                "100": {
                    "name": "briefing",
                    "kind": "text_channel",
                    "enabled": True,
                    "allow_posting": False,
                    "include_in_api": True,
                }
            },
        },
    )
    other_entry = FakeEntry(
        entry_id="entry-2",
        data={
            CONF_BOT_TOKEN: "token-2",
            CONF_GUILD_ID: 222,
            CONF_API_KEY: "shared-key",
        },
        options={
            "channels": {
                "300": {
                    "name": "ops",
                    "kind": "text_channel",
                    "enabled": True,
                    "allow_posting": False,
                    "include_in_api": True,
                }
            },
        },
    )
    hass.config_entries.entries_by_domain[DOMAIN] = [entry, other_entry]
    hass.data[DOMAIN] = {
        entry.entry_id: integration.DiscordBridgeRuntimeData(
            entry_id=entry.entry_id,
            guild_id=111,
            guild_name="Guild One",
            bot_user_id=1,
            bot_username="Bot One",
            api_key="shared-key",
            entry_data=entry.data,
            guild_state=build_guild_state(111, "Guild One", entry.options),
            discovered_channels=(),
        ),
        other_entry.entry_id: integration.DiscordBridgeRuntimeData(
            entry_id=other_entry.entry_id,
            guild_id=222,
            guild_name="Guild Two",
            bot_user_id=2,
            bot_username="Bot Two",
            api_key="shared-key",
            entry_data=other_entry.data,
            guild_state=build_guild_state(222, "Guild Two", other_entry.options),
            discovered_channels=(),
        ),
    }

    fetch_messages = AsyncMock(return_value=[])
    session = object()
    monkeypatch.setattr(integration, "async_get_clientsession", lambda hass: session)
    monkeypatch.setattr(integration, "async_fetch_channel_messages", fetch_messages)
    monkeypatch.setattr(integration, "async_dispatcher_send", MagicMock())
    handler = integration._make_refresh_recent_messages_handler(hass)

    await handler(SimpleNamespace(data={CONF_GUILD_ID: "111", "channel_id": "100", "limit": 3}))

    fetch_messages.assert_awaited_once()
    assert fetch_messages.await_args.kwargs["bot_token"] == "token-1"
    assert fetch_messages.await_args.kwargs["channel_id"] == 100
    assert fetch_messages.await_args.kwargs["limit"] == 3


@pytest.mark.asyncio
async def test_refresh_pins_service_updates_target_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry(
        entry_id="entry-1",
        data={
            CONF_BOT_TOKEN: "token-1",
            CONF_GUILD_ID: 111,
            CONF_API_KEY: "shared-key",
        },
        options={
            "channels": {
                "100": {
                    "name": "briefing",
                    "kind": "text_channel",
                    "enabled": True,
                    "allow_posting": False,
                    "include_in_api": True,
                },
                "200": {
                    "name": "ops",
                    "kind": "text_channel",
                    "enabled": True,
                    "allow_posting": False,
                    "include_in_api": True,
                },
            },
        },
    )
    hass.config_entries.entries_by_domain[DOMAIN] = [entry]
    runtime = integration.DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=111,
        guild_name="Guild One",
        bot_user_id=1,
        bot_username="Bot One",
        api_key="shared-key",
        entry_data=entry.data,
        guild_state=build_guild_state(111, "Guild One", entry.options),
        discovered_channels=(),
    )
    hass.data[DOMAIN] = {entry.entry_id: runtime}

    fetch_pins = AsyncMock(
        return_value=[
            {
                "message_id": 700,
                "channel_id": 200,
                "author_id": 8,
                "author_name": "GM",
                "content": "Pinned rule",
                "created_at": "2026-03-13T13:00:00+00:00",
                "jump_url": "https://discord.example/messages/700",
                "attachments": (),
            }
        ]
    )
    send_signal = MagicMock()
    session = object()
    monkeypatch.setattr(integration, "async_get_clientsession", lambda hass: session)
    monkeypatch.setattr(integration, "async_fetch_pinned_messages", fetch_pins)
    monkeypatch.setattr(integration, "async_dispatcher_send", send_signal)
    handler = integration._make_refresh_pins_handler(hass)

    await handler(SimpleNamespace(data={"channel_id": "200"}))

    fetch_pins.assert_awaited_once()
    assert fetch_pins.await_args.kwargs["channel_id"] == 200
    assert len(runtime.guild_state.channels[200].pinned_messages) == 1
    assert runtime.guild_state.channels[100].pinned_messages == []
    send_signal.assert_called_once_with(
        hass,
        "discord_chat_bridge_channel_state_updated_entry-1_200",
    )


def test_async_cleanup_stale_entities_removes_disabled_channel_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = FakeHomeAssistant()
    entry = FakeEntry()
    runtime = integration.DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=1234,
        guild_name="KCBN",
        bot_user_id=42,
        bot_username="KillBot",
        api_key="api-key",
        entry_data=entry.data,
        guild_state=build_guild_state(
            1234,
            "KCBN",
            {
                "channels": {
                    "100": {
                        "name": "enabled-channel",
                        "kind": "text_channel",
                        "enabled": True,
                        "allow_posting": False,
                        "include_in_api": False,
                    },
                    "200": {
                        "name": "disabled-channel",
                        "kind": "text_channel",
                        "enabled": False,
                        "allow_posting": False,
                        "include_in_api": False,
                    },
                }
            },
        ),
        discovered_channels=(),
    )
    fake_registry = FakeEntityRegistry(
        [
            FakeRegistryEntry(
                entity_id="sensor.enabled_channel_last_message",
                unique_id="1234_100_last_message",
            ),
            FakeRegistryEntry(
                entity_id="sensor.disabled_channel_last_message",
                unique_id="1234_200_last_message",
            ),
            FakeRegistryEntry(
                entity_id="text.disabled_channel_draft",
                unique_id="1234_200_draft",
            ),
            FakeRegistryEntry(
                entity_id="sensor.other_platform",
                unique_id="1234_200_last_message",
                platform="other_integration",
            ),
        ]
    )

    monkeypatch.setattr(er, "async_get", lambda hass: fake_registry)
    monkeypatch.setattr(
        er,
        "async_entries_for_config_entry",
        lambda registry, entry_id: list(fake_registry.entries),
    )

    integration.async_cleanup_stale_entities(hass, entry, runtime)

    assert fake_registry.removed == [
        "sensor.disabled_channel_last_message",
        "text.disabled_channel_draft",
    ]
