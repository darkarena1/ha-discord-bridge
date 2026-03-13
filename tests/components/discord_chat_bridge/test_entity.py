from __future__ import annotations

from dataclasses import dataclass

from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState
from custom_components.discord_chat_bridge.entity import DiscordChatBridgeEntity


@dataclass
class FakeRuntime:
    entry_id: str
    guild_id: int
    guild_name: str
    guild_state: GuildState


def test_entity_marks_archived_thread_unavailable_and_exposes_attributes() -> None:
    channel_state = ChannelState(
        channel_id=100,
        name="ops-thread",
        kind="thread",
        parent_channel_id=50,
        archived=True,
    )
    entity = DiscordChatBridgeEntity(
        FakeRuntime(
            entry_id="entry-1",
            guild_id=1,
            guild_name="Guild",
            guild_state=GuildState(guild_id=1),
        ),
        channel_state,
        unique_suffix="test",
        entity_name="state",
    )

    assert entity.available is False
    assert entity.extra_state_attributes == {
        "channel_id": 100,
        "channel_kind": "thread",
        "parent_channel_id": 50,
        "archived": True,
    }
