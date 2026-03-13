# Home Assistant Discord Bridge

Custom Home Assistant integration that connects to Discord as a bot application and exposes selected guild channels as Home Assistant entities plus an authenticated HTTP API.

## Goals

- One config entry per Discord guild
- One Home Assistant device per guild
- Text channels and threads treated as first-class channels
- Channel entities disabled by default and enabled selectively
- Dedicated tools/endpoints for recent messages and pinned messages
- Optional posting controls per channel
- AI-agnostic external API reachable through your Home Assistant base URL

## Current Status

Project scaffold and development environment are in place.

Implemented so far:
- repository structure for a Home Assistant custom integration
- initial config flow skeleton
- initial manifest and component files
- architecture and API design docs
- local Home Assistant config directory

## Repository Layout

- `custom_components/discord_chat_bridge/`: Home Assistant integration
- `docs/architecture.md`: architecture, entities, API, and roadmap
- `config/`: local Home Assistant configuration for development
- `tests/`: integration tests

## Development Environment

### 1. Create the virtual environment

```bash
cd /Users/scottobryan/Source/ha-discord-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. Create local environment values

```bash
cp .env.example .env
```

Fill in:
- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID`
- `DISCORD_CHAT_BRIDGE_API_KEY`

Notes:
- `.env` is ignored by git
- `.env.example` is the committed template
- the integration will ultimately store production values in Home Assistant config entries
- this file is for local development, scripts, and manual testing
### 3. Run Home Assistant locally

```bash
source .venv/bin/activate
hass -c ./config
```

### 4. Open Home Assistant

By default:

```text
http://127.0.0.1:8123
```

## Planned External API

The integration is designed to expose authenticated HTTP endpoints under the Home Assistant instance, for example:

- `/api/discord_chat_bridge/channels`
- `/api/discord_chat_bridge/channels/{channel_id}/messages`
- `/api/discord_chat_bridge/channels/{channel_id}/pins`
- `/api/discord_chat_bridge/channels/{channel_id}/messages` `POST`

These will be callable through your Home Assistant external URL once implemented.

## Notes

- This design is intentionally independent of the Home Assistant OpenAI integration.
- If you later want native Assist/LLM tool support inside Home Assistant too, that can be added on top.
- Local secrets belong in `.env`, not in committed files.
