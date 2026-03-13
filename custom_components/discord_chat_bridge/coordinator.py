from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChannelState:
    channel_id: int
    name: str
    kind: str
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    posting_enabled: bool = False
    api_enabled: bool = False


@dataclass
class GuildState:
    guild_id: int
    guild_name: str | None = None
    channels: dict[int, ChannelState] = field(default_factory=dict)
