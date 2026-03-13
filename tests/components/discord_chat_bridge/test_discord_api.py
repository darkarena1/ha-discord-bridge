from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from custom_components.discord_chat_bridge.discord_api import (
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_fetch_channel_messages,
    async_fetch_discoverable_channels,
    async_post_channel_message,
    async_validate_discord_credentials,
)


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self, content_type=None) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses: Iterator[FakeResponse] = iter(responses)

    def get(self, url: str, headers: dict[str, str], json=None) -> FakeResponse:
        return next(self._responses)

    def post(self, url: str, headers: dict[str, str], json=None) -> FakeResponse:
        return next(self._responses)


@pytest.mark.asyncio
async def test_validate_discord_credentials_success() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {"id": "99", "username": "killbot", "global_name": "Killbot"},
            ),
            FakeResponse(200, {"id": "123", "name": "KCBN"}),
        ]
    )

    result = await async_validate_discord_credentials(
        session=session,
        bot_token="token",
        guild_id=123,
    )

    assert result.guild_id == 123
    assert result.guild_name == "KCBN"
    assert result.bot_user_id == 99
    assert result.bot_username == "Killbot (killbot)"


@pytest.mark.asyncio
async def test_validate_discord_credentials_invalid_auth() -> None:
    session = FakeSession([FakeResponse(401, {})])

    with pytest.raises(DiscordInvalidAuthError):
        await async_validate_discord_credentials(
            session=session,
            bot_token="token",
            guild_id=123,
        )


@pytest.mark.asyncio
async def test_validate_discord_credentials_missing_guild() -> None:
    session = FakeSession(
        [
            FakeResponse(200, {"id": "99", "username": "killbot"}),
            FakeResponse(404, {}),
        ]
    )

    with pytest.raises(DiscordGuildAccessError):
        await async_validate_discord_credentials(
            session=session,
            bot_token="token",
            guild_id=123,
        )


@pytest.mark.asyncio
async def test_fetch_channel_messages_retries_after_rate_limit(monkeypatch) -> None:
    session = FakeSession(
        [
            FakeResponse(429, {"retry_after": 0}),
            FakeResponse(
                200,
                [
                    {
                        "id": "2",
                        "channel_id": "123",
                        "content": "hello",
                        "timestamp": "2026-03-13T12:01:00+00:00",
                        "author": {"id": "99", "username": "killbot"},
                        "attachments": [],
                    }
                ],
            ),
        ]
    )
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("custom_components.discord_chat_bridge.discord_api.asyncio.sleep", _sleep)

    result = await async_fetch_channel_messages(
        session=session,
        bot_token="token",
        channel_id=123,
        limit=1,
    )

    assert sleeps == [0.0]
    assert result[0]["message_id"] == 2


@pytest.mark.asyncio
async def test_fetch_channel_messages_preserves_newest_first_order() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                [
                    {
                        "id": "20",
                        "channel_id": "123",
                        "content": "newest",
                        "timestamp": "2026-03-13T12:02:00+00:00",
                        "author": {"id": "99", "username": "killbot"},
                        "attachments": [],
                    },
                    {
                        "id": "10",
                        "channel_id": "123",
                        "content": "older",
                        "timestamp": "2026-03-13T12:01:00+00:00",
                        "author": {"id": "99", "username": "killbot"},
                        "attachments": [],
                    },
                ],
            )
        ]
    )

    result = await async_fetch_channel_messages(
        session=session,
        bot_token="token",
        channel_id=123,
        limit=2,
    )

    assert [message["message_id"] for message in result] == [20, 10]


@pytest.mark.asyncio
async def test_post_channel_message_retries_after_server_error(monkeypatch) -> None:
    session = FakeSession(
        [
            FakeResponse(502, {"message": "bad gateway"}),
            FakeResponse(
                200,
                {
                    "id": "5",
                    "channel_id": "123",
                    "content": "sent",
                    "timestamp": "2026-03-13T12:01:00+00:00",
                    "author": {"id": "99", "username": "killbot"},
                    "attachments": [],
                },
            ),
        ]
    )
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("custom_components.discord_chat_bridge.discord_api.asyncio.sleep", _sleep)

    result = await async_post_channel_message(
        session=session,
        bot_token="token",
        channel_id=123,
        message="hello",
    )

    assert sleeps == [1.0]
    assert result["message_id"] == 5


@pytest.mark.asyncio
async def test_fetch_discoverable_channels_includes_category_metadata() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                [
                    {
                        "id": "500",
                        "type": 4,
                        "name": "Story",
                        "position": 1,
                    },
                    {
                        "id": "100",
                        "type": 0,
                        "name": "general",
                        "position": 1,
                        "parent_id": "500",
                    },
                ],
            ),
            FakeResponse(
                200,
                {
                    "threads": [
                        {
                            "id": "200",
                            "type": 11,
                            "name": "ops-thread",
                            "position": 0,
                            "parent_id": "100",
                            "thread_metadata": {"archived": False},
                        }
                    ]
                },
            ),
        ]
    )

    result = await async_fetch_discoverable_channels(
        session=session,
        bot_token="token",
        guild_id=123,
    )

    assert result[0].channel_id == 100
    assert result[0].category_id == 500
    assert result[0].category_name == "Story"
    assert result[1].channel_id == 200
    assert result[1].parent_channel_name == "general"
    assert result[1].category_name == "Story"
