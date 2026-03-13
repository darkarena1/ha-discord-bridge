from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_CHANNEL_STATE_UPDATED
from .coordinator import ChannelState

if TYPE_CHECKING:
    from . import DiscordBridgeRuntimeData


def channel_state_signal(entry_id: str, channel_id: int) -> str:
    return f"{SIGNAL_CHANNEL_STATE_UPDATED}_{entry_id}_{channel_id}"


class DiscordChatBridgeEntity(Entity):
    _attr_has_entity_name = False
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        runtime: DiscordBridgeRuntimeData,
        channel_state: ChannelState,
        *,
        unique_suffix: str,
        entity_name: str,
    ) -> None:
        self.runtime = runtime
        self.channel_state = channel_state
        self._guild_id = runtime.guild_id
        self._guild_name = runtime.guild_name or f"Guild {runtime.guild_id}"
        self._channel_id = channel_state.channel_id
        self._channel_name = channel_state.name
        self._attr_name = f"{self._channel_name} {entity_name}"
        self._attr_unique_id = f"{self._guild_id}_{self._channel_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self._guild_id))},
            name=self._guild_name,
            manufacturer="Discord",
            model="Guild",
        )
        self._attr_translation_key = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                channel_state_signal(
                    self.runtime.entry_id,
                    self.channel_state.channel_id,
                ),
                self.async_write_ha_state,
            )
        )
