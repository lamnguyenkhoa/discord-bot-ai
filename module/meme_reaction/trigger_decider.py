import re
import llm_client
import config
import logging

logger = logging.getLogger(__name__)

KEYWORDS = [
    "lol", "haha", "lmao", "omg", "wow", "bro", "that's funny",
    "kekw", "lul", "pog", "lulw", "hah", "hahaha", "hahaa", "yay",
    "🤣", "😂", "😭", "😆", "🤪"
]


class TriggerDecider:
    def __init__(self):
        self._keyword_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(k) for k in KEYWORDS) + r')\b',
            re.IGNORECASE
        )

    async def should_trigger_meme(self, message_text: str) -> bool:
        """Check if meme should be triggered."""
        if self.check_keywords(message_text):
            return True
        
        return await self.check_sentiment(message_text)

    def check_keywords(self, text: str) -> bool:
        """Check if text contains trigger keywords."""
        return bool(self._keyword_pattern.search(text.lower()))

    async def check_sentiment(self, text: str) -> bool:
        """Use LLM to check sentiment intensity (1-5)."""
        if not config.LLM_API_KEY:
            return False
        
        prompt = f"""Analyze this message and rate emotion intensity from 1-5.
Only respond with a number 1-5. No other text.

Message: {text[:200]}
Intensity (1=neutral, 5=very emotional):"""
        
        try:
            result = await llm_client.generate_reply(
                user_message=prompt,
                memory_context="",
                channel_name="sentiment-check"
            )
            result = result.strip()
            if result.isdigit():
                intensity = int(result)
                return intensity >= 4
        except Exception as e:
            logger.warning(f"Sentiment check failed: {e}")
        return False


_trigger_decider = None


def get_trigger_decider() -> TriggerDecider:
    global _trigger_decider
    if _trigger_decider is None:
        _trigger_decider = TriggerDecider()
    return _trigger_decider