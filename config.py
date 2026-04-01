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

# System prompt
SYSTEM_PROMPT_FILE = "system_prompt.txt"
