"""Diagnostics support for Discord Chat Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_BOT_TOKEN, DOMAIN

TO_REDACT = {
    CONF_API_KEY,
    CONF_BOT_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    runtime_data: dict[str, Any] | None = None
    if runtime is not None:
        runtime_data = {
            "guild_id": runtime.guild_id,
            "guild_name": runtime.guild_name,
            "bot_user_id": runtime.bot_user_id,
            "bot_username": runtime.bot_username,
            "gateway_running": (
                runtime.gateway_handle is not None and not runtime.gateway_handle.task.done()
            ),
            "discovery_refresh_pending": (
                runtime.discovery_refresh_task is not None
                and not runtime.discovery_refresh_task.done()
            ),
            "discovered_channels": [
                {
                    "channel_id": channel.channel_id,
                    "name": channel.name,
                    "kind": channel.kind,
                    "parent_channel_id": channel.parent_channel_id,
                    "parent_channel_name": channel.parent_channel_name,
                    "category_id": channel.category_id,
                    "category_name": channel.category_name,
                    "archived": channel.archived,
                }
                for channel in runtime.discovered_channels
            ],
            "guild_state": {
                str(channel_id): {
                    "name": channel_state.name,
                    "kind": channel_state.kind,
                    "parent_channel_id": channel_state.parent_channel_id,
                    "parent_channel_name": channel_state.parent_channel_name,
                    "category_id": channel_state.category_id,
                    "category_name": channel_state.category_name,
                    "archived": channel_state.archived,
                    "enabled": channel_state.enabled,
                    "posting_enabled": channel_state.posting_enabled,
                    "api_enabled": channel_state.api_enabled,
                    "last_message_preview": channel_state.last_message_preview,
                    "last_message_at": (
                        channel_state.last_message_at.isoformat()
                        if channel_state.last_message_at is not None
                        else None
                    ),
                    "recent_message_cache_count": len(channel_state.recent_messages),
                    "pinned_message_cache_count": len(channel_state.pinned_messages),
                    "pinned_messages_refreshed_at": (
                        channel_state.pinned_messages_refreshed_at.isoformat()
                        if channel_state.pinned_messages_refreshed_at is not None
                        else None
                    ),
                }
                for channel_id, channel_state in runtime.guild_state.channels.items()
            },
        }

    return {
        "entry": async_redact_data(
            {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        "runtime": runtime_data,
    }
