from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import OPTION_CHANNELS
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

    for channel in discovered_channels:
        existing = existing_channels.get(str(channel.channel_id), {})
        merged_channels[str(channel.channel_id)] = {
            "name": channel.name,
            "kind": channel.kind,
            "position": channel.position,
            "parent_channel_id": channel.parent_channel_id,
            "archived": channel.archived,
            "enabled": existing.get("enabled", False),
            "allow_posting": existing.get("allow_posting", False),
            "include_in_api": existing.get("include_in_api", False),
        }

    return {
        **existing_options,
        OPTION_CHANNELS: merged_channels,
    }


def build_guild_state(
    guild_id: int,
    guild_name: str,
    options: dict,
) -> GuildState:
    channels = {
        int(channel_id): ChannelState(
            channel_id=int(channel_id),
            name=channel_data["name"],
            kind=channel_data["kind"],
            parent_channel_id=channel_data.get("parent_channel_id"),
            enabled=bool(channel_data.get("enabled", False)),
            posting_enabled=bool(channel_data.get("allow_posting", False)),
            api_enabled=bool(channel_data.get("include_in_api", False)),
        )
        for channel_id, channel_data in options.get(OPTION_CHANNELS, {}).items()
    }

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
