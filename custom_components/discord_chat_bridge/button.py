from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    entry: DiscordChatBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime: DiscordBridgeRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DiscordSendDraftButton(runtime, channel_state)
            for channel_state in runtime.guild_state.channels.values()
            if channel_state.enabled
        ]
    )


class DiscordSendDraftButton(DiscordChatBridgeEntity, ButtonEntity):
    _attr_should_poll = False

    def __init__(
        self, runtime: DiscordBridgeRuntimeData, channel_state
    ) -> None:
        super().__init__(
            runtime,
            channel_state,
            unique_suffix="send_draft",
            entity_name="send draft",
        )

    async def async_press(self) -> None:
        message = self.runtime.drafts.get(self.channel_state.channel_id, "").strip()
        if not message:
            raise HomeAssistantError("Draft is empty.")

        session = async_get_clientsession(self.hass)
        try:
            sent_message = await async_post_channel_message(
                session=session,
                bot_token=self.runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=self.channel_state.channel_id,
                message=message,
            )
        except DiscordGuildAccessError as exc:
            raise HomeAssistantError("Bot cannot post to that channel.") from exc
        except DiscordCannotConnectError as exc:
            raise HomeAssistantError("Failed to reach Discord.") from exc

        self.runtime.drafts[self.channel_state.channel_id] = ""
        cache_recent_message(self.runtime.guild_state, sent_message)
        async_dispatcher_send(
            self.hass,
            channel_state_signal(self.runtime.entry_id, self.channel_state.channel_id),
        )
