from __future__ import annotations

from dataclasses import dataclass

from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState
from custom_components.discord_chat_bridge.sensor import DiscordChannelStatusSensor


@dataclass
class FakeRuntime:
    entry_id: str
    guild_id: int
    guild_name: str
    guild_state: GuildState


def test_channel_status_sensor_reports_active() -> None:
    sensor = DiscordChannelStatusSensor(
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
    assert sensor.native_value == "active"


def test_channel_status_sensor_reports_archived_but_stays_available() -> None:
    sensor = DiscordChannelStatusSensor(
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
    assert sensor.native_value == "archived"
