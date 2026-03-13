from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from aiohttp.test_utils import make_mocked_request

from custom_components.discord_chat_bridge.api import (
    DiscordBridgeChannelDetailView,
    DiscordBridgeChannelMessagesView,
    DiscordBridgePinnedMessagesView,
    _matching_runtimes_for_api_key,
    _runtime_for_channel,
    _serialize_channel,
    _should_refresh,
)
from custom_components.discord_chat_bridge.const import CONF_BOT_TOKEN
from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState


@dataclass(frozen=True)
class FakeRuntime:
    entry_id: str
    guild_id: int
    guild_name: str
    api_key: str
    entry_data: dict
    guild_state: GuildState


class FakeHass:
    def __init__(self, runtimes: dict) -> None:
        self.data = {"discord_chat_bridge": runtimes}


def test_matching_runtimes_for_api_key_filters_results() -> None:
    runtime_a = FakeRuntime(
        entry_id="a",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(guild_id=1),
    )
    runtime_b = FakeRuntime(
        entry_id="b",
        guild_id=2,
        guild_name="B",
        api_key="key-b",
        entry_data={CONF_BOT_TOKEN: "token-b"},
        guild_state=GuildState(guild_id=2),
    )
    hass = FakeHass({"a": runtime_a, "b": runtime_b})

    results = _matching_runtimes_for_api_key(hass, "key-a")

    assert results == [runtime_a]


def test_runtime_for_channel_returns_matching_runtime() -> None:
    runtime = FakeRuntime(
        entry_id="a",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=True,
                )
            },
        ),
    )
    hass = FakeHass({"a": runtime})

    result = _runtime_for_channel(hass, "key-a", 100)

    assert result is runtime


def test_serialize_channel_includes_archived_flag() -> None:
    runtime = FakeRuntime(
        entry_id="a",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(guild_id=1),
    )
    channel_state = ChannelState(
        channel_id=100,
        name="ops-thread",
        kind="thread",
        parent_channel_id=50,
        archived=True,
        enabled=True,
        api_enabled=True,
    )

    result = _serialize_channel(runtime, channel_state)

    assert result["archived"] is True
    assert result["parent_channel_id"] == 50


def test_serialize_channel_includes_cache_metadata() -> None:
    runtime = FakeRuntime(
        entry_id="a",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(guild_id=1),
    )
    channel_state = ChannelState(
        channel_id=100,
        name="general",
        kind="text_channel",
        last_message_author="Storyteller",
        recent_messages=[{"message_id": 1}, {"message_id": 2}],
        pinned_messages=[{"message_id": 10}],
        pinned_messages_refreshed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    result = _serialize_channel(runtime, channel_state)

    assert result["recent_message_cache_count"] == 2
    assert result["pinned_message_cache_count"] == 1
    assert result["pinned_messages_refreshed_at"] == "2026-03-13T12:00:00+00:00"
    assert result["last_message_author"] == "Storyteller"


def test_should_refresh_parses_truthy_values() -> None:
    class FakeRequest:
        def __init__(self, query: dict[str, str]) -> None:
            self.query = query

    assert _should_refresh(FakeRequest({"refresh": "true"})) is True
    assert _should_refresh(FakeRequest({"refresh": "1"})) is True
    assert _should_refresh(FakeRequest({"refresh": "yes"})) is True
    assert _should_refresh(FakeRequest({})) is False
    assert _should_refresh(FakeRequest({"refresh": "false"})) is False


def _json_shape(value):
    return json.loads(json.dumps(value))


async def test_channel_detail_view_returns_single_channel_payload() -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=True,
                    recent_messages=[{"message_id": 1}],
                )
            },
        ),
    )
    hass = FakeHass({"entry-1": runtime})
    view = DiscordBridgeChannelDetailView(hass)
    request = make_mocked_request(
        "GET",
        "/api/discord_chat_bridge/channels/100",
        headers={"X-API-Key": "key-a"},
    )

    response = await view.get(request, "100")

    assert response.status == 200
    assert json.loads(response.text) == _json_shape(
        _serialize_channel(runtime, runtime.guild_state.channels[100])
    )


async def test_channel_detail_view_rejects_non_api_channel() -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=False,
                )
            },
        ),
    )
    hass = FakeHass({"entry-1": runtime})
    view = DiscordBridgeChannelDetailView(hass)
    request = make_mocked_request(
        "GET",
        "/api/discord_chat_bridge/channels/100",
        headers={"X-API-Key": "key-a"},
    )

    response = await view.get(request, "100")

    assert response.status == 403


async def test_channel_messages_view_uses_cache_when_not_forced(monkeypatch) -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=True,
                    recent_messages=[
                        {
                            "message_id": 2,
                            "channel_id": 100,
                            "content": "cached 2",
                            "created_at": "2026-03-13T12:01:00+00:00",
                            "attachments": (),
                        },
                        {
                            "message_id": 1,
                            "channel_id": 100,
                            "content": "cached 1",
                            "created_at": "2026-03-13T12:00:00+00:00",
                            "attachments": (),
                        },
                    ],
                )
            },
        ),
    )
    hass = FakeHass({"entry-1": runtime})
    view = DiscordBridgeChannelMessagesView(hass)
    request = make_mocked_request(
        "GET",
        "/api/discord_chat_bridge/channels/100/messages?limit=2",
        headers={"X-API-Key": "key-a"},
    )

    async def _unexpected_fetch(*args, **kwargs):
        raise AssertionError("Discord fetch should not run when cache satisfies request")

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.api.async_fetch_channel_messages",
        _unexpected_fetch,
    )

    response = await view.get(request, "100")

    assert response.status == 200
    assert json.loads(response.text) == _json_shape(
        runtime.guild_state.channels[100].recent_messages
    )


async def test_channel_messages_view_refresh_bypasses_cache(monkeypatch) -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=True,
                    recent_messages=[
                        {
                            "message_id": 1,
                            "channel_id": 100,
                            "content": "stale",
                            "created_at": "2026-03-13T12:00:00+00:00",
                            "attachments": (),
                        }
                    ],
                )
            },
        ),
    )
    hass = FakeHass({"entry-1": runtime})
    view = DiscordBridgeChannelMessagesView(hass)
    request = make_mocked_request(
        "GET",
        "/api/discord_chat_bridge/channels/100/messages?limit=1&refresh=true",
        headers={"X-API-Key": "key-a"},
    )
    fetched_messages = [
        {
            "message_id": 2,
            "channel_id": 100,
            "content": "fresh",
            "created_at": "2026-03-13T12:01:00+00:00",
            "attachments": (),
        }
    ]

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.api.async_get_clientsession",
        lambda hass: object(),
    )
    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.api.async_dispatcher_send",
        lambda *args, **kwargs: None,
    )

    async def _fetch(*args, **kwargs):
        return fetched_messages

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.api.async_fetch_channel_messages",
        _fetch,
    )

    response = await view.get(request, "100")

    assert response.status == 200
    assert json.loads(response.text) == _json_shape(fetched_messages)
    assert runtime.guild_state.channels[100].recent_messages[0] == fetched_messages[0]
    assert len(runtime.guild_state.channels[100].recent_messages) == 2


async def test_pinned_messages_view_uses_cache_when_not_forced() -> None:
    refreshed_at = datetime.now(UTC)
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=True,
                    pinned_messages=[
                        {
                            "message_id": 10,
                            "channel_id": 100,
                            "content": "cached pin",
                            "created_at": "2026-03-13T12:01:00+00:00",
                            "attachments": (),
                        }
                    ],
                    pinned_messages_refreshed_at=refreshed_at,
                )
            },
        ),
    )
    hass = FakeHass({"entry-1": runtime})
    view = DiscordBridgePinnedMessagesView(hass)
    request = make_mocked_request(
        "GET",
        "/api/discord_chat_bridge/channels/100/pins",
        headers={"X-API-Key": "key-a"},
    )

    response = await view.get(request, "100")

    assert response.status == 200
    assert json.loads(response.text) == _json_shape(
        runtime.guild_state.channels[100].pinned_messages
    )


async def test_pinned_messages_view_refresh_bypasses_cache(monkeypatch) -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        entry_data={CONF_BOT_TOKEN: "token-a"},
        guild_state=GuildState(
            guild_id=1,
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    api_enabled=True,
                    pinned_messages=[
                        {
                            "message_id": 10,
                            "channel_id": 100,
                            "content": "stale pin",
                            "created_at": "2026-03-13T12:00:00+00:00",
                            "attachments": (),
                        }
                    ],
                    pinned_messages_refreshed_at=datetime(
                        2026, 3, 13, 12, 2, tzinfo=UTC
                    ),
                )
            },
        ),
    )
    hass = FakeHass({"entry-1": runtime})
    view = DiscordBridgePinnedMessagesView(hass)
    request = make_mocked_request(
        "GET",
        "/api/discord_chat_bridge/channels/100/pins?refresh=true",
        headers={"X-API-Key": "key-a"},
    )
    fetched_messages = [
        {
            "message_id": 11,
            "channel_id": 100,
            "content": "fresh pin",
            "created_at": "2026-03-13T12:01:00+00:00",
            "attachments": (),
        }
    ]

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.api.async_get_clientsession",
        lambda hass: object(),
    )

    async def _fetch(*args, **kwargs):
        return fetched_messages

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.api.async_fetch_pinned_messages",
        _fetch,
    )

    response = await view.get(request, "100")

    assert response.status == 200
    assert json.loads(response.text) == _json_shape(fetched_messages)
    assert runtime.guild_state.channels[100].pinned_messages == fetched_messages
