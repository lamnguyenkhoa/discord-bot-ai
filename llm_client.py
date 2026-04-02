import json
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

# TODO: Add conversation history of a few last message instead of 
# just today context / summary (for client.chat.completions.create)

async def generate_reply(user_message: str, memory_context: str, channel_name: str, facts_context: str = "") -> str:
    system_content = load_system_prompt() + "\n\n## Recent Memory\n" + memory_context
    if facts_context:
        system_content += "\n\n## Persistent Memory\n" + facts_context
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]
    try:
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
            tools=[{"type": "openrouter:web_search"}] if config.WEB_SEARCH_ENABLED else None,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating reply: {e}")
        return FALLBACK_REPLY


_EXTRACT_SYSTEM = (
    "You extract clearly stated facts from a Discord conversation exchange. "
    "Be conservative: only extract facts explicitly stated, never infer or speculate.\n\n"
    "Return ONLY valid JSON, no other text:\n"
    '{"user_facts": ["fact about this user", ...], "server_facts": ["fact about the server", ...], '
    '"corrections": [{"user": "username", "old_fact": "exact text of old fact as stored", "new_fact": "corrected version"}, ...]}\n\n'
    "user_facts: things the user explicitly shared about themselves.\n"
    "server_facts: general server events, rules, or notable things not specific to one user.\n"
    "corrections: when the user explicitly contradicts or corrects a previously known fact listed in "
    "Existing Facts. Include the exact old_fact text as it appears there. "
    "Only flag corrections when the user clearly states the old info is wrong. "
    "When a fact belongs in corrections, do NOT also include it in user_facts.\n"
    'If nothing noteworthy, return {"user_facts": [], "server_facts": [], "corrections": []}.'
)

def _empty_facts() -> dict:
    return {"user_facts": [], "server_facts": [], "corrections": []}


async def extract_facts(user_name: str, user_message: str, bot_reply: str, existing_facts: str = "") -> dict:
    exchange = f"User ({user_name}): {user_message}\nBot: {bot_reply}"
    if existing_facts:
        exchange = f"Existing Facts:\n{existing_facts}\n\n{exchange}"
    try:
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": exchange},
            ],
        )
        parsed = json.loads(response.choices[0].message.content)
        if not isinstance(parsed.get("user_facts"), list):
            parsed["user_facts"] = []
        if not isinstance(parsed.get("server_facts"), list):
            parsed["server_facts"] = []
        if not isinstance(parsed.get("corrections"), list):
            parsed["corrections"] = []
        return parsed
    except json.JSONDecodeError:
        logger.warning("extract_facts: failed to parse JSON response")
        return _empty_facts()
    except Exception as e:
        logger.error(f"Error extracting facts: {e}")
        return _empty_facts()


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
