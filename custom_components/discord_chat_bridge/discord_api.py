from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import CHANNEL_KIND_TEXT, CHANNEL_KIND_THREAD, DISCORD_API_BASE_URL


class DiscordBridgeError(Exception):
    """Base error for Discord bridge failures."""


class DiscordCannotConnectError(DiscordBridgeError):
    """Raised when Discord cannot be reached."""


class DiscordInvalidAuthError(DiscordBridgeError):
    """Raised when the bot token is invalid."""


class DiscordGuildAccessError(DiscordBridgeError):
    """Raised when the configured guild is not accessible."""


@dataclass(frozen=True)
class DiscordGuildBootstrap:
    guild_id: int
    guild_name: str
    bot_user_id: int
    bot_username: str


@dataclass(frozen=True)
class DiscordChannelDescription:
    channel_id: int
    name: str
    kind: str
    position: int
    parent_channel_id: int | None = None
    archived: bool = False


@dataclass(frozen=True)
class DiscordMessageSummary:
    message_id: int
    channel_id: int
    author_id: int
    author_name: str
    content: str
    created_at: str
    jump_url: str
    attachments: tuple[dict[str, str | None], ...]


def _bot_display_name(payload: dict[str, Any]) -> str:
    global_name = payload.get("global_name")
    username = payload.get("username", "Unknown Bot")
    if global_name:
        return f"{global_name} ({username})"
    return username


async def _discord_get(
    session: ClientSession,
    bot_token: str,
    path: str,
) -> tuple[int, Any]:
    url = f"{DISCORD_API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "HomeAssistantDiscordChatBridge/0.1.0",
    }

    try:
        async with session.get(url, headers=headers) as response:
            payload = await response.json(content_type=None)
            return response.status, payload
    except ClientError as exc:
        raise DiscordCannotConnectError("Could not connect to Discord.") from exc


async def async_validate_discord_credentials(
    session: ClientSession,
    bot_token: str,
    guild_id: int,
) -> DiscordGuildBootstrap:
    user_status, user_payload = await _discord_get(session, bot_token, "/users/@me")
    if user_status == 401:
        raise DiscordInvalidAuthError("Discord bot token is invalid.")
    if user_status >= 400:
        raise DiscordCannotConnectError("Discord rejected the user lookup request.")

    guild_status, guild_payload = await _discord_get(session, bot_token, f"/guilds/{guild_id}")
    if guild_status in {401, 403}:
        raise DiscordGuildAccessError(
            f"Bot does not have access to guild {guild_id}."
        )
    if guild_status == 404:
        raise DiscordGuildAccessError(f"Guild {guild_id} was not found.")
    if guild_status >= 400:
        raise DiscordCannotConnectError("Discord rejected the guild lookup request.")

    return DiscordGuildBootstrap(
        guild_id=int(guild_payload["id"]),
        guild_name=guild_payload["name"],
        bot_user_id=int(user_payload["id"]),
        bot_username=_bot_display_name(user_payload),
    )


def _channel_kind_from_type(channel_type: int) -> str | None:
    if channel_type in {0, 5}:
        return CHANNEL_KIND_TEXT
    if channel_type in {10, 11, 12}:
        return CHANNEL_KIND_THREAD
    return None


def _channel_from_payload(payload: dict[str, Any]) -> DiscordChannelDescription | None:
    channel_type = payload.get("type")
    if not isinstance(channel_type, int):
        return None

    kind = _channel_kind_from_type(channel_type)
    if kind is None:
        return None

    return DiscordChannelDescription(
        channel_id=int(payload["id"]),
        name=payload.get("name") or f"channel-{payload['id']}",
        kind=kind,
        position=int(payload.get("position", 0)),
        parent_channel_id=(
            int(payload["parent_id"])
            if payload.get("parent_id") not in {None, ""}
            else None
        ),
        archived=bool(payload.get("thread_metadata", {}).get("archived", False)),
    )


def _message_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    attachments = tuple(
        {
            "id": str(attachment.get("id", "")),
            "filename": attachment.get("filename"),
            "url": attachment.get("url"),
            "content_type": attachment.get("content_type"),
        }
        for attachment in payload.get("attachments", [])
        if isinstance(attachment, dict)
    )
    author = payload.get("author", {})
    author_name = author.get("global_name") or author.get("username", "Unknown")

    return {
        "message_id": int(payload["id"]),
        "channel_id": int(payload["channel_id"]),
        "author_id": int(author.get("id", 0)),
        "author_name": author_name,
        "content": payload.get("content", ""),
        "created_at": payload.get("timestamp", datetime.utcnow().isoformat()),
        "jump_url": (
            f"https://discord.com/channels/"
            f"{payload.get('guild_id', '@me')}/{payload['channel_id']}/{payload['id']}"
        ),
        "attachments": attachments,
    }


async def async_fetch_discoverable_channels(
    session: ClientSession,
    bot_token: str,
    guild_id: int,
    *,
    include_archived_threads: bool = False,
) -> list[DiscordChannelDescription]:
    channels_status, channels_payload = await _discord_get(
        session,
        bot_token,
        f"/guilds/{guild_id}/channels",
    )
    if channels_status in {401, 403, 404}:
        raise DiscordGuildAccessError(
            f"Bot cannot access channels for guild {guild_id}."
        )
    if channels_status >= 400:
        raise DiscordCannotConnectError("Discord rejected the guild channels request.")

    active_threads_status, active_threads_payload = await _discord_get(
        session,
        bot_token,
        f"/guilds/{guild_id}/threads/active",
    )
    if active_threads_status in {401, 403, 404}:
        raise DiscordGuildAccessError(
            f"Bot cannot access threads for guild {guild_id}."
        )
    if active_threads_status >= 400:
        raise DiscordCannotConnectError("Discord rejected the active threads request.")

    discovered: dict[int, DiscordChannelDescription] = {}

    raw_channels = channels_payload if isinstance(channels_payload, list) else []
    for payload in raw_channels:
        if not isinstance(payload, dict):
            continue
        channel = _channel_from_payload(payload)
        if channel is None:
            continue
        if channel.archived and not include_archived_threads:
            continue
        discovered[channel.channel_id] = channel

    raw_threads = active_threads_payload.get("threads", [])
    if isinstance(raw_threads, list):
        for payload in raw_threads:
            if not isinstance(payload, dict):
                continue
            channel = _channel_from_payload(payload)
            if channel is None:
                continue
            if channel.archived and not include_archived_threads:
                continue
            discovered[channel.channel_id] = channel

    return sorted(
        discovered.values(),
        key=lambda item: (item.kind != CHANNEL_KIND_TEXT, item.position, item.name.lower()),
    )


async def async_fetch_channel_messages(
    session: ClientSession,
    bot_token: str,
    channel_id: int,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    status, payload = await _discord_get(
        session,
        bot_token,
        f"/channels/{channel_id}/messages?limit={limit}",
    )
    if status in {401, 403, 404}:
        raise DiscordGuildAccessError(f"Bot cannot access channel {channel_id}.")
    if status >= 400:
        raise DiscordCannotConnectError("Discord rejected the channel messages request.")

    if not isinstance(payload, list):
        return []

    messages = [
        _message_summary_from_payload(message)
        for message in payload
        if isinstance(message, dict)
    ]
    messages.reverse()
    return messages


async def async_fetch_pinned_messages(
    session: ClientSession,
    bot_token: str,
    channel_id: int,
) -> list[dict[str, Any]]:
    status, payload = await _discord_get(
        session,
        bot_token,
        f"/channels/{channel_id}/pins",
    )
    if status in {401, 403, 404}:
        raise DiscordGuildAccessError(f"Bot cannot access channel {channel_id}.")
    if status >= 400:
        raise DiscordCannotConnectError("Discord rejected the pinned messages request.")

    if not isinstance(payload, list):
        return []

    return [
        _message_summary_from_payload(message)
        for message in payload
        if isinstance(message, dict)
    ]


async def async_post_channel_message(
    session: ClientSession,
    bot_token: str,
    channel_id: int,
    *,
    message: str,
) -> dict[str, Any]:
    url = f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "HomeAssistantDiscordChatBridge/0.1.0",
    }
    body = {"content": message}

    try:
        async with session.post(url, headers=headers, json=body) as response:
            payload = await response.json(content_type=None)
    except ClientError as exc:
        raise DiscordCannotConnectError("Could not connect to Discord.") from exc

    if response.status in {401, 403, 404}:
        raise DiscordGuildAccessError(f"Bot cannot post to channel {channel_id}.")
    if response.status >= 400:
        raise DiscordCannotConnectError("Discord rejected the send message request.")

    if not isinstance(payload, dict):
        raise DiscordCannotConnectError("Discord returned an unexpected send response.")
    return _message_summary_from_payload(payload)
