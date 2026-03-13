from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers import http
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import API_HEADER, CONF_BOT_TOKEN, DOMAIN, FRONTEND_API_VERSION
from .coordinator import (
    cache_pinned_messages,
    cache_recent_message,
    cache_recent_messages,
    get_cached_pinned_messages,
    get_cached_recent_messages,
)
from .discord_api import (
    DiscordCannotConnectError,
    DiscordGuildAccessError,
    async_fetch_channel_messages,
    async_fetch_pinned_messages,
    async_post_channel_message,
)
from .entity import channel_state_signal


def _matching_runtimes_for_api_key(hass: HomeAssistant, api_key: str) -> list[Any]:
    runtimes = hass.data.get(DOMAIN, {}).values()
    return [
        runtime
        for runtime in runtimes
        if hasattr(runtime, "api_key") and runtime.api_key == api_key
    ]


def _runtime_for_channel(hass: HomeAssistant, api_key: str, channel_id: int) -> Any | None:
    for runtime in _matching_runtimes_for_api_key(hass, api_key):
        channel_state = runtime.guild_state.channels.get(channel_id)
        if channel_state is not None:
            return runtime
    return None


def _runtime_for_enabled_channel(hass: HomeAssistant, channel_id: int) -> Any | None:
    runtimes = hass.data.get(DOMAIN, {}).values()
    for runtime in runtimes:
        if not hasattr(runtime, "guild_state"):
            continue
        channel_state = runtime.guild_state.channels.get(channel_id)
        if channel_state is not None and channel_state.enabled:
            return runtime
    return None


def _serialize_channel(runtime: Any, channel_state: Any) -> dict[str, Any]:
    return {
        "guild_id": runtime.guild_id,
        "guild_name": runtime.guild_name,
        "channel_id": channel_state.channel_id,
        "name": channel_state.name,
        "kind": channel_state.kind,
        "parent_channel_id": channel_state.parent_channel_id,
        "parent_channel_name": channel_state.parent_channel_name,
        "category_id": channel_state.category_id,
        "category_name": channel_state.category_name,
        "archived": channel_state.archived,
        "enabled": channel_state.enabled,
        "allow_posting": channel_state.posting_enabled,
        "include_in_api": channel_state.api_enabled,
        "last_message_preview": channel_state.last_message_preview,
        "last_message_author": channel_state.last_message_author,
        "last_message_at": (
            channel_state.last_message_at.isoformat()
            if channel_state.last_message_at is not None
            else None
        ),
        "recent_message_cache_count": len(channel_state.recent_messages),
        "pinned_message_cache_count": len(channel_state.pinned_messages),
        "pinned_messages_refreshed_at": (
            channel_state.pinned_messages_refreshed_at.isoformat()
            if channel_state.pinned_messages_refreshed_at is not None
            else None
        ),
    }


def _extract_api_key(request: web.Request) -> str | None:
    value = request.headers.get(API_HEADER)
    if not value:
        return None
    return value.strip()


def _should_refresh(request: web.Request) -> bool:
    value = request.query.get("refresh")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class DiscordBridgeBaseView(http.HomeAssistantView):
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _authorized_runtimes(self, request: web.Request) -> list[Any] | web.Response:
        api_key = _extract_api_key(request)
        if not api_key:
            return self.json_message(
                "Missing API key.",
                status_code=HTTPStatus.UNAUTHORIZED,
            )

        runtimes = _matching_runtimes_for_api_key(self.hass, api_key)
        if not runtimes:
            return self.json_message(
                "Invalid API key.",
                status_code=HTTPStatus.UNAUTHORIZED,
            )
        return runtimes

    def _authorized_runtime_for_channel(
        self,
        request: web.Request,
        channel_id: int,
    ) -> Any | web.Response:
        api_key = _extract_api_key(request)
        if not api_key:
            return self.json_message(
                "Missing API key.",
                status_code=HTTPStatus.UNAUTHORIZED,
            )

        runtime = _runtime_for_channel(self.hass, api_key, channel_id)
        if runtime is None:
            return self.json_message(
                "Channel not found for this API key.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return runtime


class DiscordBridgeHealthView(DiscordBridgeBaseView):
    url = "/api/discord_chat_bridge/health"
    name = "api:discord_chat_bridge:health"

    async def get(self, request: web.Request) -> web.Response:
        runtimes = self._authorized_runtimes(request)
        if isinstance(runtimes, web.Response):
            return runtimes

        return self.json(
            {
                "status": "ok",
                "guilds": [
                    {
                        "guild_id": runtime.guild_id,
                        "guild_name": runtime.guild_name,
                        "bot_user_id": runtime.bot_user_id,
                        "bot_username": runtime.bot_username,
                    }
                    for runtime in runtimes
                ],
            }
        )


class DiscordBridgeChannelsView(DiscordBridgeBaseView):
    url = "/api/discord_chat_bridge/channels"
    name = "api:discord_chat_bridge:channels"

    async def get(self, request: web.Request) -> web.Response:
        runtimes = self._authorized_runtimes(request)
        if isinstance(runtimes, web.Response):
            return runtimes

        channels: list[dict[str, Any]] = []
        for runtime in runtimes:
            for channel_state in runtime.guild_state.channels.values():
                if not channel_state.api_enabled:
                    continue
                channels.append(_serialize_channel(runtime, channel_state))

        channels.sort(key=lambda item: (item["guild_name"], item["kind"], item["name"]))
        return self.json(channels)


class DiscordBridgeChannelDetailView(DiscordBridgeBaseView):
    url = "/api/discord_chat_bridge/channels/{channel_id}"
    name = "api:discord_chat_bridge:channel_detail"

    async def get(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._authorized_runtime_for_channel(request, parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        channel_state = runtime.guild_state.channels[parsed_channel_id]
        if not channel_state.api_enabled:
            return self.json_message(
                "Channel is not enabled for API access.",
                status_code=HTTPStatus.FORBIDDEN,
            )

        return self.json(_serialize_channel(runtime, channel_state))


class DiscordBridgeChannelMessagesView(DiscordBridgeBaseView):
    url = "/api/discord_chat_bridge/channels/{channel_id}/messages"
    name = "api:discord_chat_bridge:channel_messages"

    async def get(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._authorized_runtime_for_channel(request, parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        channel_state = runtime.guild_state.channels[parsed_channel_id]
        if not channel_state.api_enabled:
            return self.json_message(
                "Channel is not enabled for API access.",
                status_code=HTTPStatus.FORBIDDEN,
            )

        limit = request.query.get("limit")
        if limit is None:
            limit_value = 20
        else:
            try:
                limit_value = max(1, min(int(limit), 50))
            except ValueError:
                return self.json_message(
                    "Invalid limit.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

        if not _should_refresh(request):
            cached_messages = get_cached_recent_messages(
                runtime.guild_state,
                parsed_channel_id,
                limit=limit_value,
            )
            if cached_messages is not None:
                return self.json(cached_messages)

        session = async_get_clientsession(self.hass)
        try:
            messages = await async_fetch_channel_messages(
                session=session,
                bot_token=runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=parsed_channel_id,
                limit=limit_value,
            )
        except DiscordGuildAccessError:
            return self.json_message(
                "Bot cannot access that channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        except DiscordCannotConnectError:
            return self.json_message(
                "Failed to reach Discord.",
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        if messages:
            cache_recent_messages(
                runtime.guild_state,
                parsed_channel_id,
                messages,
            )
            async_dispatcher_send(
                self.hass,
                channel_state_signal(runtime.entry_id, parsed_channel_id),
            )

        return self.json(messages)

    async def post(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._authorized_runtime_for_channel(request, parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        channel_state = runtime.guild_state.channels[parsed_channel_id]
        if not channel_state.posting_enabled:
            return self.json_message(
                "Posting is disabled for this channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        if channel_state.archived:
            return self.json_message(
                "Archived threads are read-only.",
                status_code=HTTPStatus.FORBIDDEN,
            )

        try:
            payload = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON body.", status_code=HTTPStatus.BAD_REQUEST)

        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, str) or not message.strip():
            return self.json_message(
                "Body must include a non-empty 'message' field.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        session = async_get_clientsession(self.hass)
        try:
            sent_message = await async_post_channel_message(
                session=session,
                bot_token=runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=parsed_channel_id,
                message=message,
            )
        except DiscordGuildAccessError:
            return self.json_message(
                "Bot cannot post to that channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        except DiscordCannotConnectError:
            return self.json_message(
                "Failed to reach Discord.",
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        cache_recent_message(runtime.guild_state, sent_message)
        async_dispatcher_send(
            self.hass,
            channel_state_signal(runtime.entry_id, parsed_channel_id),
        )

        return self.json(sent_message, status_code=HTTPStatus.CREATED)


class DiscordBridgePinnedMessagesView(DiscordBridgeBaseView):
    url = "/api/discord_chat_bridge/channels/{channel_id}/pins"
    name = "api:discord_chat_bridge:pinned_messages"

    async def get(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._authorized_runtime_for_channel(request, parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        channel_state = runtime.guild_state.channels[parsed_channel_id]
        if not channel_state.api_enabled:
            return self.json_message(
                "Channel is not enabled for API access.",
                status_code=HTTPStatus.FORBIDDEN,
            )

        if not _should_refresh(request):
            cached_messages = get_cached_pinned_messages(
                runtime.guild_state,
                parsed_channel_id,
            )
            if cached_messages is not None:
                return self.json(cached_messages)

        session = async_get_clientsession(self.hass)
        try:
            messages = await async_fetch_pinned_messages(
                session=session,
                bot_token=runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=parsed_channel_id,
            )
        except DiscordGuildAccessError:
            return self.json_message(
                "Bot cannot access that channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        except DiscordCannotConnectError:
            return self.json_message(
                "Failed to reach Discord.",
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        cache_pinned_messages(runtime.guild_state, parsed_channel_id, messages)
        return self.json(messages)


class DiscordBridgeFrontendBaseView(http.HomeAssistantView):
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _runtime_for_enabled_channel(
        self,
        channel_id: int,
    ) -> Any | web.Response:
        runtime = _runtime_for_enabled_channel(self.hass, channel_id)
        if runtime is None:
            return self.json_message(
                "Enabled channel not found.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return runtime


class DiscordBridgeFrontendInfoView(DiscordBridgeFrontendBaseView):
    url = "/api/discord_chat_bridge/frontend/info"
    name = "api:discord_chat_bridge:frontend_info"

    async def get(self, request: web.Request) -> web.Response:
        guild_count = 0
        enabled_channel_count = 0
        for runtime in self.hass.data.get(DOMAIN, {}).values():
            if not hasattr(runtime, "guild_state"):
                continue
            guild_count += 1
            enabled_channel_count += sum(
                1
                for channel_state in runtime.guild_state.channels.values()
                if channel_state.enabled
            )

        return self.json(
            {
                "domain": DOMAIN,
                "frontend_api_version": FRONTEND_API_VERSION,
                "guild_count": guild_count,
                "enabled_channel_count": enabled_channel_count,
            }
        )


class DiscordBridgeFrontendChannelsView(DiscordBridgeFrontendBaseView):
    url = "/api/discord_chat_bridge/frontend/channels"
    name = "api:discord_chat_bridge:frontend_channels"

    async def get(self, request: web.Request) -> web.Response:
        channels: list[dict[str, Any]] = []
        for runtime in self.hass.data.get(DOMAIN, {}).values():
            if not hasattr(runtime, "guild_state"):
                continue
            for channel_state in runtime.guild_state.channels.values():
                if not channel_state.enabled:
                    continue
                channels.append(_serialize_channel(runtime, channel_state))

        channels.sort(key=lambda item: (item["guild_name"], item["kind"], item["name"]))
        return self.json(channels)


class DiscordBridgeFrontendChannelDetailView(DiscordBridgeFrontendBaseView):
    url = "/api/discord_chat_bridge/frontend/channels/{channel_id}"
    name = "api:discord_chat_bridge:frontend_channel_detail"

    async def get(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._runtime_for_enabled_channel(parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        return self.json(
            _serialize_channel(runtime, runtime.guild_state.channels[parsed_channel_id])
        )


class DiscordBridgeFrontendChannelMessagesView(DiscordBridgeFrontendBaseView):
    url = "/api/discord_chat_bridge/frontend/channels/{channel_id}/messages"
    name = "api:discord_chat_bridge:frontend_channel_messages"

    async def get(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._runtime_for_enabled_channel(parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        limit = request.query.get("limit")
        if limit is None:
            limit_value = 20
        else:
            try:
                limit_value = max(1, min(int(limit), 50))
            except ValueError:
                return self.json_message(
                    "Invalid limit.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

        if not _should_refresh(request):
            cached_messages = get_cached_recent_messages(
                runtime.guild_state,
                parsed_channel_id,
                limit=limit_value,
            )
            if cached_messages is not None:
                return self.json(cached_messages)

        session = async_get_clientsession(self.hass)
        try:
            messages = await async_fetch_channel_messages(
                session=session,
                bot_token=runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=parsed_channel_id,
                limit=limit_value,
            )
        except DiscordGuildAccessError:
            return self.json_message(
                "Bot cannot access that channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        except DiscordCannotConnectError:
            return self.json_message(
                "Failed to reach Discord.",
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        if messages:
            cache_recent_messages(
                runtime.guild_state,
                parsed_channel_id,
                messages,
            )
            async_dispatcher_send(
                self.hass,
                channel_state_signal(runtime.entry_id, parsed_channel_id),
            )

        return self.json(messages)

    async def post(self, request: web.Request, channel_id: str) -> web.Response:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            return self.json_message("Invalid channel id.", status_code=HTTPStatus.BAD_REQUEST)

        runtime = self._runtime_for_enabled_channel(parsed_channel_id)
        if isinstance(runtime, web.Response):
            return runtime

        channel_state = runtime.guild_state.channels[parsed_channel_id]
        if not channel_state.posting_enabled:
            return self.json_message(
                "Posting is disabled for this channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        if channel_state.archived:
            return self.json_message(
                "Archived threads are read-only.",
                status_code=HTTPStatus.FORBIDDEN,
            )

        try:
            payload = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON body.", status_code=HTTPStatus.BAD_REQUEST)

        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, str) or not message.strip():
            return self.json_message(
                "Body must include a non-empty 'message' field.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        session = async_get_clientsession(self.hass)
        try:
            sent_message = await async_post_channel_message(
                session=session,
                bot_token=runtime.entry_data[CONF_BOT_TOKEN],
                channel_id=parsed_channel_id,
                message=message,
            )
        except DiscordGuildAccessError:
            return self.json_message(
                "Bot cannot post to that channel.",
                status_code=HTTPStatus.FORBIDDEN,
            )
        except DiscordCannotConnectError:
            return self.json_message(
                "Failed to reach Discord.",
                status_code=HTTPStatus.BAD_GATEWAY,
            )

        cache_recent_message(runtime.guild_state, sent_message)
        async_dispatcher_send(
            self.hass,
            channel_state_signal(runtime.entry_id, parsed_channel_id),
        )

        return self.json(sent_message, status_code=HTTPStatus.CREATED)


def async_register_views(hass: HomeAssistant) -> None:
    hass.http.register_view(DiscordBridgeHealthView(hass))
    hass.http.register_view(DiscordBridgeChannelsView(hass))
    hass.http.register_view(DiscordBridgeChannelDetailView(hass))
    hass.http.register_view(DiscordBridgeChannelMessagesView(hass))
    hass.http.register_view(DiscordBridgePinnedMessagesView(hass))
    hass.http.register_view(DiscordBridgeFrontendInfoView(hass))
    hass.http.register_view(DiscordBridgeFrontendChannelsView(hass))
    hass.http.register_view(DiscordBridgeFrontendChannelDetailView(hass))
    hass.http.register_view(DiscordBridgeFrontendChannelMessagesView(hass))
