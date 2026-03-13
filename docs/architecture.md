# Architecture

## Scope

Custom Home Assistant integration for Discord guild access through a Discord bot application.

The integration will:
- connect to one guild per config entry,
- create one Home Assistant device representing that guild,
- surface selected channels and threads as entities,
- expose an authenticated HTTP API for AI agents to read and post messages.

## Design Decisions

### Config entry model

- One config entry per guild
- Setup flow asks for:
  - `bot_token`
  - `guild_id`
  - integration API key for external calls

For local development, the repo also provides a `.env.example` template with:
- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID`
- `DISCORD_CHAT_BRIDGE_API_KEY`

These are developer conveniences only. Runtime configuration should live in the
Home Assistant config entry, not in source-controlled files.

### Device model

- One Home Assistant device per guild
- Channels and threads are entities attached to that device

### Channel model

Both text channels and threads are first-class channels.

Each channel has:
- a stable Discord ID
- a display name
- a kind: `text_channel` or `thread`
- channel-level feature flags

### Entity model

Per enabled channel, plan to create:

- `notify.<channel_slug>`
  - send a message to the channel
- `binary_sensor.<channel_slug>_active`
  - `on` when active
- `sensor.<channel_slug>_last_message`
  - last message preview
- `sensor.<channel_slug>_last_message_at`
  - timestamp of the most recent message
- `text.<channel_slug>_draft`
  - draft message input
- `button.<channel_slug>_send_draft`
  - sends the draft text to the channel

Entity behavior:
- channel entities should default to disabled in the entity registry
- channels are enabled selectively by the user
- posting can be enabled or disabled separately from read access

### Why not store full message lists on entities

Recent-message lists and pinned-message lists should not live in entity state or large attributes.

Instead:
- entities expose small summaries for dashboards and automations
- the external HTTP API returns richer structured message lists on demand

## Channel Enablement Model

Recommended configuration state per channel:

- `enabled`: whether the channel gets entities
- `allow_posting`: whether send operations are permitted
- `include_in_api`: whether the external API may access the channel

Recommended default:
- all discovered channels disabled initially
- posting disabled until the channel is explicitly enabled
- threads follow the same rules as channels

This gives a conservative and reviewable security posture.

## Retrieval Limits

Recommended default recent-message limit: `20`

Reasoning:
- enough context for summarization or operational questions
- not so large that latency and token cost become noisy
- still manageable for threads and busy channels

Recommended defaults:
- recent messages default: `20`
- recent messages maximum: `50`
- pinned messages default: all currently pinned, capped at `20`

## External API Model

The integration should expose authenticated HTTP endpoints under Home Assistant.

Proposed endpoints:

- `GET /api/discord_chat_bridge/health`
- `GET /api/discord_chat_bridge/channels`
- `GET /api/discord_chat_bridge/channels/{channel_id}`
- `GET /api/discord_chat_bridge/channels/{channel_id}/messages?limit=20`
- `GET /api/discord_chat_bridge/channels/{channel_id}/pins`
- `POST /api/discord_chat_bridge/channels/{channel_id}/messages`

Authentication:
- integration-specific API key in `X-API-Key`
- do not require a full Home Assistant long-lived access token for AI use

Authorization rules:
- only channels marked `include_in_api` are readable
- only channels marked `allow_posting` accept posting

## Runtime Model

Discord is primarily push-based.

Current runtime:
- maintain one long-lived Discord client per config entry
- subscribe to message events
- cache:
  - guild metadata
  - channel metadata
  - latest message summary

Current behavior:
- Home Assistant entities read latest-message state from the in-memory cache
- the external API still reads messages and pins directly from Discord REST
- gateway updates currently apply to already-discovered channels and threads
- channel and thread lifecycle events trigger rediscovery refreshes
- configured threads are preserved if they disappear from active discovery after archiving
- recent-message cache counts and pinned-message cache metadata are exposed on entities
- API callers can bypass cached reads with `refresh=true`

Planned additions:

Initial implementation note:
- channel and active-thread discovery is persisted in config entry options first
- the gateway-backed live cache builds on top of the discovered channel map

## Options Flow

The options flow should manage:
- channel enablement
- posting enablement
- API exposure enablement
- recent-message default limit

## Initial Roadmap

### Phase 1

- scaffold integration
- set up local Home Assistant development environment
- add config flow

### Phase 2

- add Discord client runtime
- discover guild channels and threads
- persist channel settings in entry options

### Phase 3

- add sensors, text entities, button entities, and notify entities
- default all channel entities to disabled

### Phase 4

- add authenticated HTTP API views
- add per-channel authorization checks

### Phase 5

- add tests for config flow, entity creation, API, and posting rules
