import logging
import config
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I'm having trouble thinking right now. Try again in a moment!"

client = AsyncOpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url=config.OPENROUTER_BASE_URL,
)


def load_system_prompt() -> str:
    try:
        with open(config.SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return (
            "You are a friendly, casual chat companion in a Discord server. "
            "Keep responses concise (1-3 paragraphs max)."
        )


async def generate_reply(user_message: str, memory_context: str, channel_name: str) -> str:
    system_content = load_system_prompt() + "\n\n## Recent Memory\n" + memory_context
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]
    try:
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating reply: {e}")
        return FALLBACK_REPLY


async def summarize(log_content: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Summarize this conversation log concisely, preserving key topics, names, "
                "and any promises or commitments made. Keep it under 500 words."
            ),
        },
        {"role": "user", "content": log_content},
    ]
    try:
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error summarizing log: {e}")
        return log_content
