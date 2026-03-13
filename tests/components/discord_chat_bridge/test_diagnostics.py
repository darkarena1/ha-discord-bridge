from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from custom_components.discord_chat_bridge import DiscordBridgeRuntimeData
from custom_components.discord_chat_bridge.const import (
    CONF_API_KEY,
    CONF_BOT_TOKEN,
    DOMAIN,
)
from custom_components.discord_chat_bridge.coordinator import ChannelState, GuildState
from custom_components.discord_chat_bridge.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.discord_chat_bridge.discord_api import DiscordChannelDescription


class FakeTask:
    def __init__(self, *, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics_redacts_secrets_and_reports_runtime() -> None:
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="KCBN",
        data={
            CONF_BOT_TOKEN: "discord-token",
            CONF_API_KEY: "bridge-key",
            "guild_id": 123,
        },
        options={"channels": {}},
    )
    runtime = DiscordBridgeRuntimeData(
        entry_id=entry.entry_id,
        guild_id=123,
        guild_name="KCBN",
        bot_user_id=42,
        bot_username="KillBot",
        api_key="bridge-key",
        entry_data=entry.data,
        guild_state=GuildState(
            guild_id=123,
            guild_name="KCBN",
            channels={
                100: ChannelState(
                    channel_id=100,
                    name="general",
                    kind="text_channel",
                    category_id=500,
                    category_name="Story",
                    enabled=True,
                    posting_enabled=True,
                    api_enabled=True,
                    last_message_preview="hello",
                    last_message_author="Storyteller",
                    last_message_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
                    recent_messages=[{"message_id": 1}],
                    pinned_messages=[{"message_id": 2}],
                    pinned_messages_refreshed_at=datetime(2026, 3, 13, 12, 5, tzinfo=UTC),
                )
            },
        ),
        discovered_channels=(
            DiscordChannelDescription(
                channel_id=100,
                name="general",
                kind="text_channel",
                position=1,
                category_id=500,
                category_name="Story",
            ),
        ),
        gateway_handle=SimpleNamespace(task=FakeTask(done=False)),
        discovery_refresh_task=FakeTask(done=True),
    )
    hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: runtime}})

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"][CONF_BOT_TOKEN] == "**REDACTED**"
    assert diagnostics["entry"]["data"][CONF_API_KEY] == "**REDACTED**"
    assert diagnostics["runtime"]["gateway_running"] is True
    assert diagnostics["runtime"]["discovery_refresh_pending"] is False
    assert diagnostics["runtime"]["discovered_channels"][0]["category_name"] == "Story"
    assert diagnostics["runtime"]["guild_state"]["100"]["recent_message_cache_count"] == 1
    assert diagnostics["runtime"]["guild_state"]["100"]["last_message_author"] == "Storyteller"
