from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState
from custom_components.discord_chat_bridge.sensor import (
    DiscordLastMessageAuthorSensor,
    DiscordLastMessageSensor,
)


@dataclass
class FakeRuntime:
    entry_id: str
    guild_id: int
    guild_name: str
    guild_state: GuildState


def test_last_message_sensors_expose_text_only_summary() -> None:
    channel_state = ChannelState(
        channel_id=100,
        name="general",
        kind="text_channel",
        last_message_preview="Opening scene",
        last_message_author="Storyteller",
        last_message_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="Guild",
        guild_state=GuildState(guild_id=1),
    )

    message_sensor = DiscordLastMessageSensor(runtime, channel_state)
    author_sensor = DiscordLastMessageAuthorSensor(runtime, channel_state)

    assert message_sensor.native_value == "Opening scene"
    assert author_sensor.native_value == "Storyteller"


def test_last_message_author_sensor_returns_none_when_no_text_message_exists() -> None:
    channel_state = ChannelState(
        channel_id=100,
        name="general",
        kind="text_channel",
        last_message_preview=None,
        last_message_author=None,
        last_message_at=None,
    )
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_id=1,
        guild_name="Guild",
        guild_state=GuildState(guild_id=1),
    )

    author_sensor = DiscordLastMessageAuthorSensor(runtime, channel_state)

    assert author_sensor.native_value is None
