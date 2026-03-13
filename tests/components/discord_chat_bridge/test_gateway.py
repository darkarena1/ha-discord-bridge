from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState
from custom_components.discord_chat_bridge.entity import channel_state_signal
from custom_components.discord_chat_bridge.gateway import (
    async_handle_gateway_message,
    message_summary_from_gateway_message,
)


@dataclass
class FakeRuntime:
    entry_id: str
    guild_state: GuildState


def test_message_summary_from_gateway_message_serializes_discord_message() -> None:
    message = SimpleNamespace(
        id=123,
        channel=SimpleNamespace(id=200),
        author=SimpleNamespace(id=300, display_name="Killbot", name="killbot"),
        content="Hello world",
        created_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        jump_url="https://discord.example/message/123",
        attachments=[
            SimpleNamespace(
                id=1,
                filename="rules.txt",
                url="https://discord.example/rules.txt",
                content_type="text/plain",
            )
        ],
    )

    summary = message_summary_from_gateway_message(message)

    assert summary == {
        "message_id": 123,
        "channel_id": 200,
        "author_id": 300,
        "author_name": "Killbot",
        "content": "Hello world",
        "created_at": "2026-03-13T12:00:00+00:00",
        "jump_url": "https://discord.example/message/123",
        "attachments": (
            {
                "id": "1",
                "filename": "rules.txt",
                "url": "https://discord.example/rules.txt",
                "content_type": "text/plain",
            },
        ),
    }


async def test_async_handle_gateway_message_updates_matching_channel(monkeypatch) -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_state=GuildState(
            guild_id=1,
            channels={
                200: ChannelState(
                    channel_id=200,
                    name="general",
                    kind="text_channel",
                    enabled=True,
                )
            },
        ),
    )
    hass = object()
    sent_signals: list[str] = []

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.gateway.async_dispatcher_send",
        lambda _hass, signal: sent_signals.append(signal),
    )

    await async_handle_gateway_message(
        hass,
        runtime,
        {
            "channel_id": 200,
            "content": "Live update",
            "created_at": "2026-03-13T12:00:00+00:00",
            "attachments": (),
        },
    )

    assert runtime.guild_state.channels[200].last_message_preview == "Live update"
    assert sent_signals == [channel_state_signal("entry-1", 200)]


async def test_async_handle_gateway_message_ignores_unknown_channel(monkeypatch) -> None:
    runtime = FakeRuntime(
        entry_id="entry-1",
        guild_state=GuildState(guild_id=1, channels={}),
    )
    sent_signals: list[str] = []

    monkeypatch.setattr(
        "custom_components.discord_chat_bridge.gateway.async_dispatcher_send",
        lambda _hass, signal: sent_signals.append(signal),
    )

    await async_handle_gateway_message(
        object(),
        runtime,
        {
            "channel_id": 999,
            "content": "Ignored",
            "created_at": "2026-03-13T12:00:00+00:00",
            "attachments": (),
        },
    )

    assert sent_signals == []
