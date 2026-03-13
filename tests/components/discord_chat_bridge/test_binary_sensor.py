from __future__ import annotations

from dataclasses import dataclass

from custom_components.discord_chat_bridge.binary_sensor import (
    DiscordChannelActiveBinarySensor,
)
from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState


@dataclass
class FakeRuntime:
    entry_id: str
    guild_id: int
    guild_name: str
    guild_state: GuildState


def test_channel_active_binary_sensor_reports_active_as_on() -> None:
    sensor = DiscordChannelActiveBinarySensor(
        FakeRuntime(
            entry_id="entry-1",
            guild_id=1,
            guild_name="Guild",
            guild_state=GuildState(guild_id=1),
        ),
        ChannelState(
            channel_id=100,
            name="general",
            kind="text_channel",
            archived=False,
        ),
    )

    assert sensor.available is True
    assert sensor.is_on is True


def test_channel_active_binary_sensor_reports_archived_as_off() -> None:
    sensor = DiscordChannelActiveBinarySensor(
        FakeRuntime(
            entry_id="entry-1",
            guild_id=1,
            guild_name="Guild",
            guild_state=GuildState(guild_id=1),
        ),
        ChannelState(
            channel_id=100,
            name="ops-thread",
            kind="thread",
            archived=True,
        ),
    )

    assert sensor.available is True
    assert sensor.is_on is False
