from __future__ import annotations

from dataclasses import dataclass

from custom_components.discord_chat_bridge.api import (
    _matching_runtimes_for_api_key,
    _runtime_for_channel,
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
