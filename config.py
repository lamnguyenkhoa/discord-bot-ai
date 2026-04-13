import os
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# LLM backend — works with OpenRouter, Ollama, or any OpenAI-compatible API
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY")

# Backward-compat aliases
OPENROUTER_API_KEY = LLM_API_KEY
OPENROUTER_BASE_URL = LLM_BASE_URL

# LLM
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"

# Attachments
ATTACHMENT_MAX_BYTES = int(os.getenv("ATTACHMENT_MAX_BYTES", str(512 * 1024)))  # 512 KB
ATTACHMENT_MAX_CHARS = int(os.getenv("ATTACHMENT_MAX_CHARS", "8000"))
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB
PDF_MAX_PAGES = int(os.getenv("PDF_MAX_PAGES", "20"))

# Memory
MEMORY_BASE_PATH = os.getenv("MEMORY_BASE_PATH", "./memory")

# Search index
INDEX_PATH = os.getenv("INDEX_PATH", "./index/memory.sqlite")

# Embeddings (optional — falls back to FTS5-only if unavailable)
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or LLM_API_KEY
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Channels to silently observe (comma-separated names, e.g. "general,announcements")
WATCH_CHANNELS = [c.strip() for c in os.getenv("WATCH_CHANNELS", "").split(",") if c.strip()]

# System prompt
SYSTEM_PROMPT_FILE = "system_prompt.txt"

# Kill word - stops the bot process when sent by an allowed user
KILL_WORD = os.getenv("KILL_WORD", "")
KILL_WORD_ALLOWED_USER_ID = os.getenv("KILL_WORD_ALLOWED_USER_ID", "")

# Status messages
ONLINE_MESSAGE = os.getenv("ONLINE_MESSAGE", "I'm back online!")
OFFLINE_MESSAGE = os.getenv("OFFLINE_MESSAGE", "Going offline now. Goodbye!")
STATUS_CHANNEL = os.getenv("STATUS_CHANNEL", "")

# Auto-post feature
AUTO_POST_ENABLED = os.getenv("AUTO_POST_ENABLED", "false").lower() in ("1", "true", "yes")
AUTO_POST_TRIGGER_MIN = int(os.getenv("AUTO_POST_TRIGGER_MIN", "3"))
AUTO_POST_TRIGGER_MAX = int(os.getenv("AUTO_POST_TRIGGER_MAX", "10"))
AUTO_POST_COOLDOWN_SECONDS = int(os.getenv("AUTO_POST_COOLDOWN_SECONDS", "60"))
AUTO_POST_MAX_LENGTH = int(os.getenv("AUTO_POST_MAX_LENGTH", "500"))
