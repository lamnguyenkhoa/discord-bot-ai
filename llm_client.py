import logging
import config
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I'm having trouble thinking right now. Try again in a moment!"

client = AsyncOpenAI(
    api_key=config.LLM_API_KEY or "ollama",
    base_url=config.LLM_BASE_URL,
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


# TODO: Add conversation history of a few last message instead of
# just today context / summary (for client.chat.completions.create)


async def generate_reply(
    user_message: str,
    memory_context: str,
    channel_name: str,
    image_urls: list | None = None,
    temperature: float = 0.9,
    system_prompt: str | None = None,
) -> str:
    base_system_prompt = load_system_prompt()
    if system_prompt:
        system_content = system_prompt + "\n\n## Recent Memory\n" + memory_context
    else:
        system_content = base_system_prompt + "\n\n## Recent Memory\n" + memory_context
    if image_urls:
        user_content = [{"type": "text", "text": user_message}]
        for url in image_urls:
            user_content.append({"type": "image_url", "image_url": {"url": url}})
    else:
        user_content = user_message
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    try:
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
            temperature=temperature,
            tools=[{"type": "openrouter:web_search"}]
            if config.WEB_SEARCH_ENABLED and "openrouter.ai" in config.LLM_BASE_URL
            else None,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating reply: {e}")
        return FALLBACK_REPLY
