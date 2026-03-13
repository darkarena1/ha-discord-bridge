from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class DiscordChatBridgeEntity(Entity):
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        guild_id: int,
        guild_name: str | None,
        channel_id: int,
        channel_name: str,
    ) -> None:
        self._guild_id = guild_id
        self._guild_name = guild_name or f"Guild {guild_id}"
        self._channel_id = channel_id
        self._channel_name = channel_name
        self._attr_unique_id = f"{guild_id}_{channel_id}_{self.__class__.__name__.lower()}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(guild_id))},
            name=self._guild_name,
            manufacturer="Discord",
            model="Guild",
        )
        self._attr_translation_key = None

    @property
    def name(self) -> str:
        return self._channel_name
