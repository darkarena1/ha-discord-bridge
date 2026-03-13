from __future__ import annotations

from collections.abc import Iterator

import pytest

from custom_components.discord_chat_bridge.discord_api import (
    DiscordGuildAccessError,
    DiscordInvalidAuthError,
    async_validate_discord_credentials,
)


class FakeResponse:
    def __init__(self, status: int, payload: dict) -> None:
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

    def get(self, url: str, headers: dict[str, str]) -> FakeResponse:
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
