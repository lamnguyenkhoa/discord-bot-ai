import random
import time
import logging
from typing import Optional
import config
import mem0_manager
import llm_client
import discord
from . import personalities

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


class ScheduledPoster:
    def __init__(self):
        self.channel_index = 0
        self.channel_last_message_time: dict[str, float] = {}
        self.scheduled_channels: list[str] = []
        self.last_successful_post: dict[str, float] = {}

    def get_next_channel(self) -> Optional[str]:
        if not self.scheduled_channels:
            return None
        
        attempts = 0
        while attempts < len(self.scheduled_channels):
            channel = self.scheduled_channels[self.channel_index]
            self.channel_index = (self.channel_index + 1) % len(self.scheduled_channels)
            attempts += 1
            if channel:
                return channel
        return None

    def is_channel_quiet(self, channel_key: str, quiet_minutes: int) -> bool:
        last_msg = self.channel_last_message_time.get(channel_key, 0)
        return time.time() - last_msg >= quiet_minutes * 60

    def record_message(self, channel_key: str):
        self.channel_last_message_time[channel_key] = time.time()

    async def post_scheduled(self, client, guild_id: Optional[str] = None):
        channel_key = self.get_next_channel()
        if not channel_key:
            return False

        if not self.is_channel_quiet(channel_key, config.AUTO_POST_SCHEDULED_ACTIVE_SKIP_MINUTES):
            logger.debug(f"Skipping scheduled post for #{channel_key} - too active")
            return False

        guild = None
        target_channel = None
        for g in client.guilds:
            if str(g.id) == guild_id:
                guild = g
                break
        
        if guild:
            target_channel = discord.utils.get(guild.text_channels, name=channel_key)
        
        if not target_channel:
            logger.warning(f"Could not find channel #{channel_key} for scheduled post")
            return False

        last_post = self.last_successful_post.get(channel_key, 0)
        if time.time() - last_post < config.AUTO_POST_COOLDOWN_SECONDS:
            return False

        context = mem0_manager.get_channel_context(channel_key, guild_id, config.AUTO_POST_CONTEXT_HOURS)
        channel_focus = personalities.get_channel_focus(channel_key)
        
        prompt = f"""In 1-2 sentences, write a standalone statement related to recent conversation in #{channel_key}.
It can comment on something discussed or share an interesting memory.
Keep it short (under {config.AUTO_POST_MAX_LENGTH} chars), conversational, no questions.

Recent context:
{context}"""

        if channel_focus:
            prompt += f"\n\nChannel purpose: {channel_focus}"

        try:
            async with target_channel.typing():
                post = await llm_client.generate_reply(prompt, "", channel_key)

            if post and len(post) <= config.AUTO_POST_MAX_LENGTH:
                await target_channel.send(post)
                logger.info(f"Scheduled auto-post in #{channel_key}")
                self.last_successful_post[channel_key] = time.time()
                return True
            elif post and len(post) > config.AUTO_POST_MAX_LENGTH:
                truncated = post[:config.AUTO_POST_MAX_LENGTH - 3] + "..."
                await target_channel.send(truncated)
                logger.info(f"Scheduled auto-post (truncated) in #{channel_key}")
                self.last_successful_post[channel_key] = time.time()
                return True
        except Exception as e:
            logger.warning(f"Scheduled auto-post failed: {e}")
        
        return False

    def set_channels(self, channels: list[str]):
        self.scheduled_channels = channels
        self.channel_index = 0


_scheduled_poster = None


def get_scheduled_poster() -> ScheduledPoster:
    global _scheduled_poster
    if _scheduled_poster is None:
        _scheduled_poster = ScheduledPoster()
    return _scheduled_poster