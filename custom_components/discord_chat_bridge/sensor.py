from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    entities: list[SensorEntity] = []
    for channel_state in runtime.guild_state.channels.values():
        if not channel_state.enabled:
            continue
        entities.append(DiscordLastMessageSensor(runtime, channel_state))
        entities.append(DiscordLastMessageAtSensor(runtime, channel_state))
    async_add_entities(entities)


class DiscordLastMessageSensor(DiscordChatBridgeEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self, runtime: DiscordBridgeRuntimeData, channel_state
    ) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="last_message",
            entity_name="last message",
        )

    @property
    def native_value(self) -> str | None:
        return self.channel_state.last_message_preview


class DiscordLastMessageAtSensor(DiscordChatBridgeEntity, SensorEntity):
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, runtime: DiscordBridgeRuntimeData, channel_state
    ) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="last_message_at",
            entity_name="last message at",
        )

    @property
    def native_value(self):
        return self.channel_state.last_message_at
