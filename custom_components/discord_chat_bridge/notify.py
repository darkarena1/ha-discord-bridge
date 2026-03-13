from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DiscordBridgeRuntimeData, DiscordChatBridgeConfigEntry
from .const import CONF_BOT_TOKEN, DOMAIN
from .coordinator import cache_recent_message
from .discord_api import (
    DiscordCannotConnectError,
    DiscordGuildAccessError,
    async_post_channel_message,
)
from .entity import DiscordChatBridgeEntity, channel_state_signal


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DiscordChatBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime: DiscordBridgeRuntimeData = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            DiscordNotifyEntity(runtime, channel_state)
            for channel_state in runtime.guild_state.channels.values()
            if channel_state.enabled
        ]
    )


class DiscordNotifyEntity(DiscordChatBridgeEntity, NotifyEntity):
    _attr_should_poll = False

    def __init__(
        self, runtime: DiscordBridgeRuntimeData, channel_state
    ) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="notify",
            entity_name="notify",
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        if self.channel_state.archived:
            raise RuntimeError("Archived threads are read-only.")

        content = f"{title}\n{message}" if title else message
        session = async_get_clientsession(self.hass)
        try:
            sent_message = await async_post_channel_message(
                session=session,
                bot_token=self.runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=self.channel_state.channel_id,
                message=content,
            )
        except DiscordGuildAccessError as exc:
            raise RuntimeError("Bot cannot post to that channel.") from exc
        except DiscordCannotConnectError as exc:
            raise RuntimeError("Failed to reach Discord.") from exc

        cache_recent_message(self.runtime.guild_state, sent_message)
        async_dispatcher_send(
            self.hass,
            channel_state_signal(self.runtime.entry_id, self.channel_state.channel_id),
        )
