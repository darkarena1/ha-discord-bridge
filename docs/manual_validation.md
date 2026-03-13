# Manual Validation

Use this checklist once the integration is running in your real Home Assistant instance.

## Discord Setup

Confirm the Discord bot has:

- `Message Content Intent` enabled
- `View Channels`
- `Read Message History`
- `Send Messages`
- `Send Messages in Threads`

## Home Assistant Setup

1. Start Home Assistant with this custom component installed.
2. Add the Discord Chat Bridge integration.
3. Enter:
   - bot token
   - guild ID
   - API key
4. Open the options flow and enable at least:
   - one text channel
   - one thread
5. In the second options step:
   - allow posting for one enabled channel
   - enable API access for the channels you want externally visible

## Entity Validation

For each enabled channel, verify these entities exist:

- `binary_sensor.<channel>_active`
- `sensor.<channel>_last_message`
- `sensor.<channel>_last_message_author`
- `sensor.<channel>_last_message_at`
- `text.<channel>_draft`
- `button.<channel>_send_draft`
- `notify.<channel>`

## Runtime Validation

1. Send a Discord message in an enabled channel.
2. Confirm the last-message sensor and timestamp update.
3. Confirm attachment-only messages do not replace the text summary entities.
4. Restart Home Assistant and confirm the last text message is preloaded back into:
   - `sensor.<channel>_last_message`
   - `sensor.<channel>_last_message_author`
   - `sensor.<channel>_last_message_at`
5. Post from Home Assistant through:
   - the draft text + send button
   - the notify entity
6. Confirm the message appears in Discord and cache counts increase.

## Archive Validation

1. Archive an enabled thread.
2. Confirm:
   - `binary_sensor.<thread>_active` is `off`
   - message/post actions are blocked
   - the thread still appears in API metadata if `include_in_api` is enabled

## API Validation

Use the external Home Assistant URL plus `X-API-Key`.

Verify:

- `GET /api/discord_chat_bridge/health`
- `GET /api/discord_chat_bridge/channels`
- `GET /api/discord_chat_bridge/channels/{channel_id}`
- `GET /api/discord_chat_bridge/channels/{channel_id}/messages`
- `GET /api/discord_chat_bridge/channels/{channel_id}/pins`
- `POST /api/discord_chat_bridge/channels/{channel_id}/messages`

Then verify cache bypass:

- `GET /api/discord_chat_bridge/channels/{channel_id}/messages?refresh=true`
- `GET /api/discord_chat_bridge/channels/{channel_id}/pins?refresh=true`

## Service Validation

In Home Assistant developer tools, call:

- `discord_chat_bridge.refresh_discovery`
- `discord_chat_bridge.refresh_recent_messages`
- `discord_chat_bridge.refresh_pins`

Validate:

1. `refresh_discovery` picks up a newly created thread or channel.
2. `refresh_recent_messages` updates:
   - `sensor.<channel>_last_message`
   - `sensor.<channel>_last_message_at`
   - `recent_message_cache_count`
3. `refresh_pins` updates:
   - `pinned_message_cache_count`
   - `pinned_messages_refreshed_at`

Optional targeted calls:

- `guild_id`: refresh only one guild
- `channel_id`: refresh only one enabled channel
- `limit`: override the recent-message fetch size for `refresh_recent_messages`

## Diagnostics Validation

Download the Home Assistant diagnostics bundle for the config entry and confirm it includes:

- redacted `bot_token`
- redacted `api_key`
- guild metadata
- discovered channel metadata
- per-channel enabled, posting, and API flags
- recent and pinned cache counts
