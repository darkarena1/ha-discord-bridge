from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from custom_components.discord_chat_bridge.api import (
    _matching_runtimes_for_api_key,
    _runtime_for_channel,
    _serialize_channel,
    _should_refresh,
)
from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState


@dataclass(frozen=True)
class FakeRuntime:
    guild_id: int
    guild_name: str
    api_key: str
    guild_state: GuildState


class FakeHass:
    def __init__(self, runtimes: dict) -> None:
        self.data = {"discord_chat_bridge": runtimes}


def test_matching_runtimes_for_api_key_filters_results() -> None:
    runtime_a = FakeRuntime(
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        guild_state=GuildState(guild_id=1),
    )
    runtime_b = FakeRuntime(
        guild_id=2,
        guild_name="B",
        api_key="key-b",
        guild_state=GuildState(guild_id=2),
    )
    hass = FakeHass({"a": runtime_a, "b": runtime_b})

    results = _matching_runtimes_for_api_key(hass, "key-a")

    assert results == [runtime_a]


def test_runtime_for_channel_returns_matching_runtime() -> None:
    runtime = FakeRuntime(
        guild_id=1,
        guild_name="A",
        api_key="key-a",
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
        guild_id=1,
        guild_name="A",
        api_key="key-a",
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
        guild_id=1,
        guild_name="A",
        api_key="key-a",
        guild_state=GuildState(guild_id=1),
    )
    channel_state = ChannelState(
        channel_id=100,
        name="general",
        kind="text_channel",
        recent_messages=[{"message_id": 1}, {"message_id": 2}],
        pinned_messages=[{"message_id": 10}],
        pinned_messages_refreshed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    result = _serialize_channel(runtime, channel_state)

    assert result["recent_message_cache_count"] == 2
    assert result["pinned_message_cache_count"] == 1
    assert result["pinned_messages_refreshed_at"] == "2026-03-13T12:00:00+00:00"


def test_should_refresh_parses_truthy_values() -> None:
    class FakeRequest:
        def __init__(self, query: dict[str, str]) -> None:
            self.query = query

    assert _should_refresh(FakeRequest({"refresh": "true"})) is True
    assert _should_refresh(FakeRequest({"refresh": "1"})) is True
    assert _should_refresh(FakeRequest({"refresh": "yes"})) is True
    assert _should_refresh(FakeRequest({})) is False
    assert _should_refresh(FakeRequest({"refresh": "false"})) is False
