from __future__ import annotations

from custom_components.discord_chat_bridge.coordinator import (
    ChannelState,
    GuildState,
    apply_message_summary,
)


def test_apply_message_summary_updates_channel_state() -> None:
    guild_state = GuildState(
        guild_id=123,
        guild_name="KCBN",
        channels={
            100: ChannelState(
                channel_id=100,
                name="general",
                kind="text_channel",
            )
        },
    )

    apply_message_summary(
        guild_state,
        {
            "channel_id": 100,
            "content": "Hello world",
            "created_at": "2026-03-13T12:00:00+00:00",
            "attachments": (),
        },
    )

    assert guild_state.channels[100].last_message_preview == "Hello world"
    assert guild_state.channels[100].last_message_at is not None
