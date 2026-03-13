from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiscordBridgeRuntimeData, DiscordChatBridgeConfigEntry
from .const import DOMAIN
from .entity import DiscordChatBridgeEntity, channel_state_signal


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime: DiscordBridgeRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DiscordDraftText(runtime, channel_state)
            for channel_state in runtime.guild_state.channels.values()
            if channel_state.posting_enabled
        ]
    )


class DiscordDraftText(DiscordChatBridgeEntity, TextEntity):
    _attr_should_poll = False
    _attr_mode = TextMode.TEXT
    _attr_native_max = 2000

    def __init__(
        self, runtime: DiscordBridgeRuntimeData, channel_state
    ) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="draft",
            entity_name="draft",
        )

    @property
    def native_value(self) -> str:
        return self.runtime.drafts.get(self.channel_state.channel_id, "")

    async def async_set_value(self, value: str) -> None:
        self.runtime.drafts[self.channel_state.channel_id] = value
        self.async_write_ha_state()
        async_dispatcher_send(
            self.hass,
            channel_state_signal(self.runtime.entry_id, self.channel_state.channel_id),
        )
