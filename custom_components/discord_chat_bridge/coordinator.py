from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import CHANNEL_KIND_THREAD, MAX_RECENT_MESSAGE_LIMIT, OPTION_CHANNELS
from .discord_api import DiscordChannelDescription


@dataclass
class ChannelState:
    channel_id: int
    name: str
    kind: str
    parent_channel_id: int | None = None
    enabled: bool = False
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    posting_enabled: bool = False
    api_enabled: bool = False
    recent_messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GuildState:
    guild_id: int
    guild_name: str | None = None
    channels: dict[int, ChannelState] = field(default_factory=dict)


def merge_discovered_channel_settings(
    existing_options: dict,
    discovered_channels: list[DiscordChannelDescription],
) -> dict:
    existing_channels = existing_options.get(OPTION_CHANNELS, {})
    merged_channels: dict[str, dict] = {}
    discovered_ids: set[str] = set()

    for channel in discovered_channels:
        existing = existing_channels.get(str(channel.channel_id), {})
        channel_id = str(channel.channel_id)
        discovered_ids.add(channel_id)
        merged_channels[channel_id] = {
            "name": channel.name,
            "kind": channel.kind,
            "position": channel.position,
            "parent_channel_id": channel.parent_channel_id,
            "archived": channel.archived,
            "enabled": existing.get("enabled", False),
            "allow_posting": existing.get("allow_posting", False),
            "include_in_api": existing.get("include_in_api", False),
        }

    for channel_id, channel_data in existing_channels.items():
        if channel_id in discovered_ids:
            continue
        if not _should_preserve_missing_channel(channel_data):
            continue

        merged_channels[channel_id] = {
            **channel_data,
            "archived": True,
        }

    return {
        **existing_options,
        OPTION_CHANNELS: merged_channels,
    }


def _should_preserve_missing_channel(channel_data: dict) -> bool:
    if channel_data.get("kind") != CHANNEL_KIND_THREAD:
        return False

    return bool(
        channel_data.get("enabled", False)
        or channel_data.get("allow_posting", False)
        or channel_data.get("include_in_api", False)
    )


def build_guild_state(
    guild_id: int,
    guild_name: str,
    options: dict,
) -> GuildState:
    channels: dict[int, ChannelState] = {}
    for channel_id, channel_data in options.get(OPTION_CHANNELS, {}).items():
        enabled = bool(channel_data.get("enabled", False))
        channels[int(channel_id)] = ChannelState(
            channel_id=int(channel_id),
            name=channel_data["name"],
            kind=channel_data["kind"],
            parent_channel_id=channel_data.get("parent_channel_id"),
            enabled=enabled,
            posting_enabled=enabled and bool(channel_data.get("allow_posting", False)),
            api_enabled=enabled and bool(channel_data.get("include_in_api", False)),
        )

    return GuildState(
        guild_id=guild_id,
        guild_name=guild_name,
        channels=channels,
    )


def apply_message_summary(guild_state: GuildState, message: dict) -> None:
    channel_id = int(message["channel_id"])
    channel = guild_state.channels.get(channel_id)
    if channel is None:
        return

    content = (message.get("content") or "").strip()
    if not content and message.get("attachments"):
        content = "<attachment only>"

    channel.last_message_preview = content or "<no text>"
    channel.last_message_at = dt_util.parse_datetime(message["created_at"])


def cache_recent_messages(
    guild_state: GuildState,
    channel_id: int,
    messages: list[dict[str, Any]],
    *,
    limit: int = MAX_RECENT_MESSAGE_LIMIT,
) -> None:
    channel = guild_state.channels.get(channel_id)
    if channel is None or not messages:
        return

    merged_by_id: dict[str, dict[str, Any]] = {}
    for message in [*messages, *channel.recent_messages]:
        merged_by_id.setdefault(_message_cache_key(message), message)

    ordered_messages = sorted(
        merged_by_id.values(),
        key=_message_sort_key,
        reverse=True,
    )
    channel.recent_messages = ordered_messages[:limit]
    apply_message_summary(guild_state, channel.recent_messages[0])


def cache_recent_message(
    guild_state: GuildState,
    message: dict[str, Any],
    *,
    limit: int = MAX_RECENT_MESSAGE_LIMIT,
) -> None:
    cache_recent_messages(
        guild_state,
        int(message["channel_id"]),
        [message],
        limit=limit,
    )


def get_cached_recent_messages(
    guild_state: GuildState,
    channel_id: int,
    *,
    limit: int,
) -> list[dict[str, Any]] | None:
    channel = guild_state.channels.get(channel_id)
    if channel is None or len(channel.recent_messages) < limit:
        return None
    return channel.recent_messages[:limit]


def _message_cache_key(message: dict[str, Any]) -> str:
    if "message_id" in message:
        return str(message["message_id"])

    return (
        f"{message.get('channel_id')}:{message.get('created_at')}:"
        f"{message.get('author_id')}:{message.get('content')}"
    )


def _message_sort_key(message: dict[str, Any]) -> tuple[datetime, str]:
    parsed = dt_util.parse_datetime(str(message.get("created_at", "")))
    if parsed is None:
        parsed = datetime.min.replace(tzinfo=dt_util.UTC)
    return parsed, _message_cache_key(message)
