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

The integration is functional end to end.

Implemented:
- Discord credential validation and guild bootstrap
- text-channel and active-thread discovery
- category-aware options flow with searchable channel selection
- per-channel enablement, posting, and API exposure flags
- channel entities for active status, latest message, latest message author, timestamp, draft, send-draft, and notify
- live Discord gateway updates for enabled channels
- startup preload of recent messages for enabled channels so entity summaries are populated immediately
- authenticated bridge API endpoints for health, channels, channel detail, messages, pins, and posting
- in-memory message and pin caching with `refresh=true` cache bypass
- diagnostics export for config entry and runtime state
- manual refresh services for discovery, recent messages, and pins
- stale entity cleanup when channels are disabled
- local Home Assistant config directory trimmed for lower-noise development

## Repository Layout

- `custom_components/discord_chat_bridge/`: Home Assistant integration
- `docs/architecture.md`: architecture, entities, API, and roadmap
- `docs/chatgpt_actions.md`: Custom GPT Actions setup guide
- `config/`: local Home Assistant configuration for development
- `tests/`: integration tests
- `openapi.yaml`: OpenAPI schema for Custom GPT Actions

## Installation

### HACS

1. Push this repository to GitHub.
2. In Home Assistant, open HACS.
3. Add this repository as a custom repository:
   - repository type: `Integration`
4. Install `Discord Chat Bridge`.
5. Restart Home Assistant.
6. Add the integration from `Settings > Devices & Services`.

After the repository is added in HACS, HACS will download the integration into Home Assistant for you. It does not complete configuration automatically:
- you still need to restart Home Assistant after install or upgrade
- you still need to add/configure the integration from `Devices & Services`

### Manual

1. Copy [custom_components/discord_chat_bridge](/Users/scottobryan/Source/ha-discord-bridge/custom_components/discord_chat_bridge) into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings > Devices & Services`.

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

## Discord Requirements

Your Discord application should have:

- a bot user created in the Discord Developer Portal
- the `Message Content Intent` enabled

Minimum bot permissions for this integration:

- `View Channels`
- `Read Message History`
- `Send Messages`

Recommended if you want thread behavior to be reliable:

- `Create Public Threads`
- `Create Private Threads`
- `Send Messages in Threads`
- `Manage Webhooks` is not required for the current implementation

## Operator Workflow

1. Add the `Discord Chat Bridge` integration in Home Assistant.
2. Enter:
   - Discord bot token
   - Discord guild ID
   - bridge API key
3. Open the integration options flow.
4. Filter by category or channel kind if needed.
5. Enable only the channels or threads you want managed.
6. In the second step, choose which enabled channels:
   - allow posting
   - are exposed through the external API
7. Save options and verify the entities created for those channels.

Notes:
- all discovered channels start disabled
- posting and API access are only configurable for enabled channels
- threads are labeled as `parent / thread` in the selector

## External API

The integration exposes authenticated HTTP endpoints under your Home Assistant base URL:

- `/api/discord_chat_bridge/channels`
- `/api/discord_chat_bridge/channels/{channel_id}`
- `/api/discord_chat_bridge/channels/{channel_id}/messages`
- `/api/discord_chat_bridge/channels/{channel_id}/pins`
- `/api/discord_chat_bridge/channels/{channel_id}/messages` `POST`
- `/api/discord_chat_bridge/health`

Use the `X-API-Key` header with the bridge API key stored in the config entry.

Example:

```bash
curl \
  -H 'X-API-Key: your_bridge_api_key' \
  'https://your-home-assistant-url/api/discord_chat_bridge/channels'
```

### Cache Control

Read endpoints support `refresh=true` to bypass cache and force a Discord fetch:

- `/api/discord_chat_bridge/channels/{channel_id}/messages?limit=20&refresh=true`
- `/api/discord_chat_bridge/channels/{channel_id}/pins?refresh=true`

Channel metadata returned by `/api/discord_chat_bridge/channels` includes:

- `recent_message_cache_count`
- `pinned_message_cache_count`
- `pinned_messages_refreshed_at`

Single-channel metadata is available at:

- `/api/discord_chat_bridge/channels/{channel_id}`

This returns the same metadata shape as the channel list, scoped to one API-enabled channel.

## ChatGPT Actions

The repo now includes an OpenAPI schema for Custom GPT Actions:

- [openapi.yaml](/Users/scottobryan/Source/ha-discord-bridge/openapi.yaml#L1)

Setup guide:

- [chatgpt_actions.md](/Users/scottobryan/Source/ha-discord-bridge/docs/chatgpt_actions.md#L1)

Use API key auth with:
- header: `X-API-Key`
- value: your bridge API key

## Home Assistant Services

The integration also registers manual refresh services:

- `discord_chat_bridge.refresh_discovery`
- `discord_chat_bridge.refresh_recent_messages`
- `discord_chat_bridge.refresh_pins`

Supported fields:
- `guild_id`: optional Discord guild ID string
- `channel_id`: optional Discord channel ID string for channel-scoped refresh
- `limit`: optional message limit for `refresh_recent_messages`

These only operate on channels already enabled in the integration.

## Diagnostics

Home Assistant diagnostics for the config entry include:
- redacted config-entry data and options
- gateway task state
- discovery refresh task state
- discovered channel metadata
- per-channel runtime flags and cache counts

Use this before debugging API or gateway issues.

## Manual Validation

Use this checklist in a real Home Assistant instance with your Discord bot:

1. Add the integration and confirm the config entry succeeds.
2. Open the options flow and enable one text channel and one thread.
3. Verify these entities appear:
   - `binary_sensor.<channel>_active`
   - `sensor.<channel>_last_message`
   - `sensor.<channel>_last_message_author`
   - `sensor.<channel>_last_message_at`
   - `text.<channel>_draft`
   - `button.<channel>_send_draft`
   - `notify.<channel>`
4. Send a message in Discord and confirm the last-message sensor updates.
5. Archive an enabled thread and confirm:
   - `binary_sensor.<thread>_active` turns `off`
   - posting is rejected through the API and HA entities
6. Call the external API with your `X-API-Key` and verify:
   - `GET /health`
   - `GET /channels`
   - `GET /channels/{channel_id}`
   - `GET /channels/{channel_id}/messages`
   - `GET /channels/{channel_id}/pins`
   - `POST /channels/{channel_id}/messages` for a posting-enabled channel
7. Verify `refresh=true` bypasses cache for messages and pins.
8. Call Home Assistant services and verify cache refresh works:
   - `discord_chat_bridge.refresh_discovery`
   - `discord_chat_bridge.refresh_recent_messages`
   - `discord_chat_bridge.refresh_pins`
9. Create a new thread in Discord and confirm discovery refresh picks it up.

## Notes

- This design is intentionally independent of the Home Assistant OpenAI integration.
- If you later want native Assist/LLM tool support inside Home Assistant too, that can be added on top.
- Local secrets belong in `.env`, not in committed files.
- The Discord bot should have the Message Content intent enabled if you want live message previews.
- Entity summaries ignore attachment-only and non-text messages. `last_message`, `last_message_author`, and `last_message_at` track the latest text-bearing message instead.
- `manifest.json` currently assumes the eventual GitHub repo path will be `darkarena1/ha-discord-bridge`. Update those URLs if you publish elsewhere.
