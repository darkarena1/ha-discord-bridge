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

## Entity Validation

For each enabled channel, verify these entities exist:

- `binary_sensor.<channel>_active`
- `sensor.<channel>_last_message`
- `sensor.<channel>_last_message_at`
- `text.<channel>_draft`
- `button.<channel>_send_draft`
- `notify.<channel>`

## Runtime Validation

1. Send a Discord message in an enabled channel.
2. Confirm the last-message sensor and timestamp update.
3. Post from Home Assistant through:
   - the draft text + send button
   - the notify entity
4. Confirm the message appears in Discord and cache counts increase.

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
