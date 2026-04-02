import os
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# LLM
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

# Memory
MEMORY_DIR = "memory"
SUMMARIZE_THRESHOLD = int(os.getenv("SUMMARIZE_THRESHOLD", "50"))

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
