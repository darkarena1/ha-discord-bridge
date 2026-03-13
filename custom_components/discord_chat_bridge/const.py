DOMAIN = "discord_chat_bridge"
API_HEADER = "X-API-Key"

CONF_API_KEY = "api_key"
CONF_BOT_TOKEN = "bot_token"
CONF_GUILD_ID = "guild_id"

DISCORD_API_BASE_URL = "https://discord.com/api/v10"

ENTRY_DATA_GUILD_NAME = "guild_name"
ENTRY_DATA_BOT_USER_ID = "bot_user_id"
ENTRY_DATA_BOT_USERNAME = "bot_username"

OPTION_CHANNELS = "channels"
OPTION_RECENT_MESSAGE_LIMIT = "recent_message_limit"

CHANNEL_KIND_TEXT = "text_channel"
CHANNEL_KIND_THREAD = "thread"

SIGNAL_CHANNEL_STATE_UPDATED = "discord_chat_bridge_channel_state_updated"
SERVICE_REFRESH_DISCOVERY = "refresh_discovery"

DEFAULT_RECENT_MESSAGE_LIMIT = 20
MAX_RECENT_MESSAGE_LIMIT = 50
MAX_PINNED_MESSAGE_LIMIT = 20
PINNED_MESSAGE_CACHE_TTL_SECONDS = 60
