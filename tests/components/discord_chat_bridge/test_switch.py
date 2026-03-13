from __future__ import annotations

from dataclasses import dataclass

from homeassistant.const import EntityCategory

from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState
from custom_components.discord_chat_bridge.switch import (
    DiscordApiEnabledSwitch,
    DiscordPostingEnabledSwitch,
)


@dataclass
class FakeRuntime:
    entry_id: str
    guild_id: int
    guild_name: str
    guild_state: GuildState


def test_posting_switch_reports_channel_posting_state() -> None:
    switch = DiscordPostingEnabledSwitch(
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
            posting_enabled=False,
        ),
    )

    assert switch.available is True
    assert switch.entity_category is EntityCategory.CONFIG
    assert switch.icon == "mdi:message-text"
    assert switch.is_on is False


def test_api_switch_reports_channel_api_state() -> None:
    switch = DiscordApiEnabledSwitch(
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
            api_enabled=True,
            archived=True,
        ),
    )

    assert switch.available is True
    assert switch.entity_category is EntityCategory.CONFIG
    assert switch.icon == "mdi:api"
    assert switch.is_on is True
