from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import DISCORD_API_BASE_URL


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
) -> tuple[int, dict[str, Any]]:
    url = f"{DISCORD_API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "User-Agent": "HomeAssistantDiscordChatBridge/0.1.0",
    }

    try:
        async with session.get(url, headers=headers) as response:
            payload = await response.json(content_type=None)
            if isinstance(payload, dict):
                return response.status, payload
            return response.status, {}
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
