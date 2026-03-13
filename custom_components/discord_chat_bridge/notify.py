from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_service(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    discovery_info=None,
) -> list[NotifyEntity]:
    return []
