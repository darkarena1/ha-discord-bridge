from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC
from typing import Any

import discord
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_BOT_TOKEN
from .coordinator import cache_recent_message
from .discovery import async_schedule_discovery_refresh
from .entity import channel_state_signal

_LOGGER = logging.getLogger(__name__)


def message_summary_from_gateway_message(message: discord.Message) -> dict[str, Any]:
    author_name = message.author.display_name or message.author.name
    return {
        "message_id": int(message.id),
        "channel_id": int(message.channel.id),
        "author_id": int(message.author.id),
        "author_name": author_name,
        "content": message.content,
        "created_at": message.created_at.astimezone(UTC).isoformat(),
        "jump_url": message.jump_url,
        "attachments": tuple(
            {
                "id": str(attachment.id),
                "filename": attachment.filename,
                "url": attachment.url,
                "content_type": attachment.content_type,
            }
            for attachment in message.attachments
        ),
    }


async def async_handle_gateway_message(
    hass: HomeAssistant,
    runtime: Any,
    message_summary: dict[str, Any],
) -> None:
    channel_id = int(message_summary["channel_id"])
    if channel_id not in runtime.guild_state.channels:
        return

    cache_recent_message(runtime.guild_state, message_summary)
    async_dispatcher_send(
        hass,
        channel_state_signal(runtime.entry_id, channel_id),
    )


class DiscordGatewayClient(discord.Client):
    def __init__(self, hass: HomeAssistant, runtime: Any) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(intents=intents)
        self._hass = hass
        self._runtime = runtime

    async def on_ready(self) -> None:
        if self.user is None:
            return
        _LOGGER.info(
            "Discord gateway connected for guild %s as %s",
            self._runtime.guild_name,
            self.user,
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != self._runtime.guild_id:
            return

        if message.channel.id not in self._runtime.guild_state.channels:
            return

        await async_handle_gateway_message(
            self._hass,
            self._runtime,
            message_summary_from_gateway_message(message),
        )

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != self._runtime.guild_id:
            return
        await self._schedule_refresh()

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != self._runtime.guild_id:
            return
        await self._schedule_refresh()

    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        if after.guild.id != self._runtime.guild_id:
            return
        await self._schedule_refresh()

    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.guild is None or thread.guild.id != self._runtime.guild_id:
            return
        await self._schedule_refresh()

    async def on_thread_delete(self, thread: discord.Thread) -> None:
        if thread.guild is None or thread.guild.id != self._runtime.guild_id:
            return
        await self._schedule_refresh()

    async def on_thread_update(
        self,
        before: discord.Thread,
        after: discord.Thread,
    ) -> None:
        if after.guild is None or after.guild.id != self._runtime.guild_id:
            return
        await self._schedule_refresh()

    async def _schedule_refresh(self) -> None:
        entry = self._hass.config_entries.async_get_entry(self._runtime.entry_id)
        if entry is None:
            return
        await async_schedule_discovery_refresh(self._hass, entry, self._runtime)


async def _run_gateway_client(
    client: DiscordGatewayClient,
    *,
    bot_token: str,
    guild_name: str,
) -> None:
    try:
        await client.start(bot_token)
    except asyncio.CancelledError:
        raise
    except Exception:
        _LOGGER.exception("Discord gateway client stopped for guild %s", guild_name)


@dataclass
class DiscordGatewayHandle:
    client: DiscordGatewayClient
    task: asyncio.Task[None]


async def async_start_gateway(
    hass: HomeAssistant,
    runtime: Any,
) -> DiscordGatewayHandle:
    client = DiscordGatewayClient(hass, runtime)
    task = hass.async_create_background_task(
        _run_gateway_client(
            client,
            bot_token=runtime.entry_data[CONF_BOT_TOKEN],
            guild_name=runtime.guild_name,
        ),
        f"{runtime.entry_id}_discord_gateway",
    )
    return DiscordGatewayHandle(client=client, task=task)


async def async_stop_gateway(handle: DiscordGatewayHandle) -> None:
    await handle.client.close()
    try:
        await handle.task
    except asyncio.CancelledError:
        pass
