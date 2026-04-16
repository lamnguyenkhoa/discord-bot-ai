import random
import time
import logging
from typing import Optional
import config
import llm_client

logger = logging.getLogger(__name__)


class FollowUpManager:
    def __init__(self):
        self.last_follow_up_time: dict[str, float] = {}

    def should_trigger(self, channel_key: str) -> bool:
        if not config.FOLLOW_UP_CHANCE or config.FOLLOW_UP_CHANCE <= 0:
            return False

        last_time = self.last_follow_up_time.get(channel_key, 0)
        if time.time() - last_time < config.FOLLOW_UP_COOLDOWN_SECONDS:
            return False

        trigger_roll = random.randint(1, 100)
        return trigger_roll <= config.FOLLOW_UP_CHANCE

    async def generate_follow_up(self, user_message: str, bot_reply: str, channel_key: str) -> Optional[str]:
        prompt = f"""Given this conversation:
User: {user_message}
Bot: {bot_reply}

Write a brief follow-up message (1-2 sentences) to continue the conversation naturally. 
It could be a clarifying question, an additional thought, or relevant comment.
Keep it under 100 characters. If nothing meaningful to add, return empty string."""

        try:
            follow_up = await llm_client.generate_reply(prompt, "", channel_key)
            if follow_up and len(follow_up.strip()) > 0 and len(follow_up) <= 200:
                return follow_up.strip()
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")

        return None

    def record_follow_up(self, channel_key: str):
        self.last_follow_up_time[channel_key] = time.time()


_follow_up_manager = None


def get_follow_up_manager() -> FollowUpManager:
    global _follow_up_manager
    if _follow_up_manager is None:
        _follow_up_manager = FollowUpManager()
    return _follow_up_manager