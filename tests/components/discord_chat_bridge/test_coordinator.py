from __future__ import annotations

from custom_components.discord_chat_bridge.coordinator import (
    build_guild_state,
    merge_discovered_channel_settings,
)
from custom_components.discord_chat_bridge.discord_api import DiscordChannelDescription


def test_merge_discovered_channel_settings_preserves_flags() -> None:
    discovered = [
        DiscordChannelDescription(
            channel_id=100,
            name="general",
            kind="text_channel",
            position=1,
        ),
        DiscordChannelDescription(
            channel_id=200,
            name="ops-thread",
            kind="thread",
            position=2,
            parent_channel_id=100,
        ),
    ]
    existing_options = {
        "recent_message_limit": 20,
        "channels": {
            "100": {
                "name": "old-general",
                "kind": "text_channel",
                "enabled": True,
                "allow_posting": True,
                "include_in_api": False,
            }
        },
    }

    merged = merge_discovered_channel_settings(existing_options, discovered)

    assert merged["recent_message_limit"] == 20
    assert merged["channels"]["100"]["name"] == "general"
    assert merged["channels"]["100"]["enabled"] is True
    assert merged["channels"]["100"]["allow_posting"] is True
    assert merged["channels"]["100"]["include_in_api"] is False
    assert merged["channels"]["200"]["enabled"] is False
    assert merged["channels"]["200"]["allow_posting"] is False
    assert merged["channels"]["200"]["include_in_api"] is False


def test_build_guild_state_reads_channel_flags() -> None:
    state = build_guild_state(
        guild_id=123,
        guild_name="KCBN",
        options={
            "channels": {
                "100": {
                    "name": "general",
                    "kind": "text_channel",
                    "parent_channel_id": None,
                    "enabled": True,
                    "allow_posting": True,
                    "include_in_api": True,
                }
            }
        },
    )

    assert state.guild_id == 123
    assert state.guild_name == "KCBN"
    assert state.channels[100].enabled is True
    assert state.channels[100].posting_enabled is True
    assert state.channels[100].api_enabled is True
