from __future__ import annotations

from custom_components.discord_chat_bridge.coordinator import (
    ChannelState,
    GuildState,
    apply_message_summary,
    cache_recent_message,
    cache_recent_messages,
    get_cached_recent_messages,
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


def test_cache_recent_messages_keeps_newest_message_summary() -> None:
    guild_state = GuildState(
        guild_id=123,
        channels={
            100: ChannelState(channel_id=100, name="general", kind="text_channel")
        },
    )

    cache_recent_messages(
        guild_state,
        100,
        [
            {
                "message_id": 2,
                "channel_id": 100,
                "content": "Newest",
                "created_at": "2026-03-13T12:01:00+00:00",
                "attachments": (),
            },
            {
                "message_id": 1,
                "channel_id": 100,
                "content": "Older",
                "created_at": "2026-03-13T12:00:00+00:00",
                "attachments": (),
            },
        ],
    )

    assert guild_state.channels[100].last_message_preview == "Newest"
    assert [
        message["message_id"] for message in guild_state.channels[100].recent_messages
    ] == [2, 1]


def test_cache_recent_message_deduplicates_by_message_id() -> None:
    guild_state = GuildState(
        guild_id=123,
        channels={
            100: ChannelState(channel_id=100, name="general", kind="text_channel")
        },
    )

    cache_recent_message(
        guild_state,
        {
            "message_id": 1,
            "channel_id": 100,
            "content": "Hello",
            "created_at": "2026-03-13T12:00:00+00:00",
            "attachments": (),
        },
    )
    cache_recent_message(
        guild_state,
        {
            "message_id": 1,
            "channel_id": 100,
            "content": "Hello updated",
            "created_at": "2026-03-13T12:00:00+00:00",
            "attachments": (),
        },
    )

    assert len(guild_state.channels[100].recent_messages) == 1
    assert guild_state.channels[100].recent_messages[0]["content"] == "Hello updated"


def test_get_cached_recent_messages_returns_none_when_cache_is_short() -> None:
    guild_state = GuildState(
        guild_id=123,
        channels={
            100: ChannelState(channel_id=100, name="general", kind="text_channel")
        },
    )
    cache_recent_message(
        guild_state,
        {
            "message_id": 1,
            "channel_id": 100,
            "content": "Hello",
            "created_at": "2026-03-13T12:00:00+00:00",
            "attachments": (),
        },
    )

    assert get_cached_recent_messages(guild_state, 100, limit=2) is None
    assert get_cached_recent_messages(guild_state, 100, limit=1) is not None
