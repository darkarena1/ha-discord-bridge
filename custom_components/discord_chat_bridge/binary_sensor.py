from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiscordBridgeRuntimeData, DiscordChatBridgeConfigEntry
from .const import DOMAIN
from .entity import DiscordChatBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime: DiscordBridgeRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DiscordChannelActiveBinarySensor(runtime, channel_state)
            for channel_state in runtime.guild_state.channels.values()
            if channel_state.enabled
        ]
    )


class DiscordChannelActiveBinarySensor(DiscordChatBridgeEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(
        self, runtime: DiscordBridgeRuntimeData, channel_state
    ) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="active",
            entity_name="active",
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return not self.channel_state.archived
