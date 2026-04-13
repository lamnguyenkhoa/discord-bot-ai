import random
import time
import logging
import config
import mem0_manager
import llm_client
import discord

logger = logging.getLogger(__name__)


class AutoPostManager:
    def __init__(self):
        self.message_count: dict[str, int] = {}
        self.last_post_time: dict[str, float] = {}

    def should_post(self, channel_key: str) -> bool:
        if not config.AUTO_POST_ENABLED:
            return False

        if channel_key not in self.message_count:
            return False

        trigger_threshold = random.randint(config.AUTO_POST_TRIGGER_MIN, config.AUTO_POST_TRIGGER_MAX)
        return self.message_count[channel_key] >= trigger_threshold

    async def post(self, message: discord.Message, guild, channel_key: str):
        last_post = self.last_post_time.get(channel_key, 0)
        if time.time() - last_post < config.AUTO_POST_COOLDOWN_SECONDS:
            self.message_count[channel_key] = 0
            return

        guild_id = str(guild.id) if guild else None
        channel_context = mem0_manager.format_context_for_prompt(guild_id, None, "")

        prompt = f"""In 1-2 sentences, write a standalone statement related to recent conversation in #{channel_key}.
It can comment on something discussed or share an interesting memory.
Keep it short (under {config.AUTO_POST_MAX_LENGTH} chars), conversational, no questions.

Recent context:
{channel_context}"""

        try:
            async with message.channel.typing():
                post = await llm_client.generate_reply(prompt, "", channel_key)

            if post and len(post) <= config.AUTO_POST_MAX_LENGTH:
                await message.channel.send(post)
                logger.info(f"Auto-posted in #{channel_key}")
                self.last_post_time[channel_key] = time.time()
            elif post and len(post) > config.AUTO_POST_MAX_LENGTH:
                truncated = post[:497] + "..."
                await message.channel.send(truncated)
                logger.info(f"Auto-posted (truncated) in #{channel_key}")
                self.last_post_time[channel_key] = time.time()
        except Exception as e:
            logger.warning(f"Auto-post failed: {e}")

        self.message_count[channel_key] = 0


_auto_post_manager = None


def get_auto_post_manager() -> AutoPostManager:
    global _auto_post_manager
    if _auto_post_manager is None:
        _auto_post_manager = AutoPostManager()
    return _auto_post_manager