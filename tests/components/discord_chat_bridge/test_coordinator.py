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
            category_id=500,
            category_name="Story",
        ),
        DiscordChannelDescription(
            channel_id=200,
            name="ops-thread",
            kind="thread",
            position=2,
            parent_channel_id=100,
            parent_channel_name="general",
            category_id=500,
            category_name="Story",
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
    assert merged["channels"]["100"]["category_name"] == "Story"
    assert merged["channels"]["100"]["enabled"] is True
    assert merged["channels"]["100"]["allow_posting"] is True
    assert merged["channels"]["100"]["include_in_api"] is False
    assert merged["channels"]["200"]["enabled"] is False
    assert merged["channels"]["200"]["parent_channel_name"] == "general"
    assert merged["channels"]["200"]["allow_posting"] is False
    assert merged["channels"]["200"]["include_in_api"] is False


def test_merge_discovered_channel_settings_defaults_enabled_channel_to_posting_and_api() -> None:
    discovered = [
        DiscordChannelDescription(
            channel_id=100,
            name="general",
            kind="text_channel",
            position=1,
        )
    ]
    existing_options = {
        "channels": {
            "100": {
                "name": "general",
                "kind": "text_channel",
                "enabled": True,
            }
        }
    }

    merged = merge_discovered_channel_settings(existing_options, discovered)

    assert merged["channels"]["100"]["enabled"] is True
    assert merged["channels"]["100"]["allow_posting"] is True
    assert merged["channels"]["100"]["include_in_api"] is True


def test_merge_discovered_channel_settings_preserves_enabled_thread_that_went_missing() -> None:
    existing_options = {
        "channels": {
            "200": {
                "name": "ops-thread",
                "kind": "thread",
                "position": 2,
                "parent_channel_id": 100,
                "enabled": True,
                "allow_posting": True,
                "include_in_api": True,
                "archived": False,
            }
        }
    }

    merged = merge_discovered_channel_settings(existing_options, [])

    assert merged["channels"]["200"]["enabled"] is True
    assert merged["channels"]["200"]["allow_posting"] is True
    assert merged["channels"]["200"]["include_in_api"] is True
    assert merged["channels"]["200"]["archived"] is True


def test_merge_discovered_channel_settings_drops_unconfigured_missing_thread() -> None:
    existing_options = {
        "channels": {
            "200": {
                "name": "ops-thread",
                "kind": "thread",
                "position": 2,
                "enabled": False,
                "allow_posting": False,
                "include_in_api": False,
                "archived": False,
            }
        }
    }

    merged = merge_discovered_channel_settings(existing_options, [])

    assert merged["channels"] == {}


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
                    "parent_channel_name": None,
                    "category_id": 500,
                    "category_name": "Story",
                    "archived": False,
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
    assert state.channels[100].category_name == "Story"
    assert state.channels[100].archived is False
    assert state.channels[100].posting_enabled is True
    assert state.channels[100].api_enabled is True


def test_build_guild_state_disables_posting_and_api_for_disabled_channels() -> None:
    state = build_guild_state(
        guild_id=123,
        guild_name="KCBN",
        options={
            "channels": {
                "100": {
                    "name": "general",
                    "kind": "text_channel",
                    "parent_channel_id": None,
                    "archived": False,
                    "enabled": False,
                    "allow_posting": True,
                    "include_in_api": True,
                }
            }
        },
    )

    assert state.channels[100].enabled is False
    assert state.channels[100].posting_enabled is False
    assert state.channels[100].api_enabled is False


def test_build_guild_state_defaults_enabled_channel_to_posting_and_api() -> None:
    state = build_guild_state(
        guild_id=123,
        guild_name="KCBN",
        options={
            "channels": {
                "100": {
                    "name": "general",
                    "kind": "text_channel",
                    "enabled": True,
                }
            }
        },
    )

    assert state.channels[100].enabled is True
    assert state.channels[100].posting_enabled is True
    assert state.channels[100].api_enabled is True
