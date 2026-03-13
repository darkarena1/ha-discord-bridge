from __future__ import annotations

import pytest

from custom_components.discord_chat_bridge.config_flow import (
    DiscordChatBridgeConfigFlow,
    DiscordChatBridgeOptionsFlow,
    _channel_selector_options,
    _merge_channel_flag_updates,
    _parse_guild_id,
)


def test_channel_selector_options_include_thread_parent_labels() -> None:
    channel_map = {
        "100": {
            "name": "general",
            "kind": "text_channel",
            "position": 1,
            "parent_channel_id": None,
        },
        "200": {
            "name": "ops-thread",
            "kind": "thread",
            "position": 2,
            "parent_channel_id": 100,
        },
    }

    options = _channel_selector_options(channel_map)

    assert options == [
        {"value": "100", "label": "# general"},
        {"value": "200", "label": "Thread ops-thread (general)"},
    ]


def test_merge_channel_flag_updates_normalizes_posting_and_api_to_enabled_channels() -> None:
    channel_map = {
        "100": {
            "name": "general",
            "kind": "text_channel",
        },
        "200": {
            "name": "ops-thread",
            "kind": "thread",
        },
    }

    merged = _merge_channel_flag_updates(
        channel_map,
        enabled_channels=["100"],
        posting_channels=["100", "200"],
        api_channels=["200"],
    )

    assert merged["100"]["enabled"] is True
    assert merged["100"]["allow_posting"] is True
    assert merged["100"]["include_in_api"] is False
    assert merged["200"]["enabled"] is False
    assert merged["200"]["allow_posting"] is False
    assert merged["200"]["include_in_api"] is False


def test_parse_guild_id_accepts_digit_strings() -> None:
    assert _parse_guild_id("1352756714700669069") == 1352756714700669069
    assert _parse_guild_id(" 1352756714700669069 ") == 1352756714700669069


@pytest.mark.parametrize("value", ["", "guild", "123abc", "123.45"])
def test_parse_guild_id_rejects_non_digit_values(value: str) -> None:
    with pytest.raises(ValueError):
        _parse_guild_id(value)


def test_async_get_options_flow_returns_options_flow_instance() -> None:
    flow = DiscordChatBridgeConfigFlow.async_get_options_flow(object())

    assert isinstance(flow, DiscordChatBridgeOptionsFlow)
