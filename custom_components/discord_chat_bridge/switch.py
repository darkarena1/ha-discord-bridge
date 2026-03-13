from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import (
    DiscordBridgeRuntimeData,
    DiscordChatBridgeConfigEntry,
    async_update_channel_capability,
)
from .const import DOMAIN
from .entity import DiscordChatBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiscordChatBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime: DiscordBridgeRuntimeData = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    for channel_state in runtime.guild_state.channels.values():
        if not channel_state.enabled:
            continue
        entities.append(DiscordPostingEnabledSwitch(runtime, channel_state))
        entities.append(DiscordApiEnabledSwitch(runtime, channel_state))
    async_add_entities(entities)


class DiscordChannelCapabilitySwitch(DiscordChatBridgeEntity, SwitchEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        return True


class DiscordPostingEnabledSwitch(DiscordChannelCapabilitySwitch):
    def __init__(self, runtime: DiscordBridgeRuntimeData, channel_state) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="posting_enabled",
            entity_name="posting enabled",
        )
        self._attr_icon = "mdi:message-text"

    @property
    def is_on(self) -> bool:
        return self.channel_state.posting_enabled

    async def async_turn_on(self, **kwargs) -> None:
        async_update_channel_capability(
            self.hass,
            self.runtime.entry_id,
            self.channel_state.channel_id,
            capability_key="allow_posting",
            enabled=True,
        )

    async def async_turn_off(self, **kwargs) -> None:
        async_update_channel_capability(
            self.hass,
            self.runtime.entry_id,
            self.channel_state.channel_id,
            capability_key="allow_posting",
            enabled=False,
        )


class DiscordApiEnabledSwitch(DiscordChannelCapabilitySwitch):
    def __init__(self, runtime: DiscordBridgeRuntimeData, channel_state) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="api_enabled",
            entity_name="api enabled",
        )
        self._attr_icon = "mdi:api"

    @property
    def is_on(self) -> bool:
        return self.channel_state.api_enabled

    async def async_turn_on(self, **kwargs) -> None:
        async_update_channel_capability(
            self.hass,
            self.runtime.entry_id,
            self.channel_state.channel_id,
            capability_key="include_in_api",
            enabled=True,
        )

    async def async_turn_off(self, **kwargs) -> None:
        async_update_channel_capability(
            self.hass,
            self.runtime.entry_id,
            self.channel_state.channel_id,
            capability_key="include_in_api",
            enabled=False,
        )
