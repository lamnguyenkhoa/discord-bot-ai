import asyncio
import logging
import time
from typing import Optional
import discord
import config

logger = logging.getLogger(__name__)


class VoiceState:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.voice_client: Optional[discord.VoiceClient] = None
        self.channel_id: Optional[int] = None
        self.session_active: bool = False
        self.last_speech_time: float = 0
        self.conversation_history: list[tuple[str, str]] = []
        self._silence_task: Optional[asyncio.Task] = None

    def start_session(self):
        self.session_active = True
        self.last_speech_time = time.time()

    def end_session(self):
        self.session_active = False
        self.conversation_history.clear()

    def add_turn(self, user_speech: str, bot_response: str):
        self.conversation_history.append((user_speech, bot_response))
        if len(self.conversation_history) > 10:
            self.conversation_history.pop(0)
        self.last_speech_time = time.time()

    def is_session_expired(self) -> bool:
        if not self.session_active:
            return True
        elapsed = time.time() - self.last_speech_time
        return elapsed > config.VOICE_SESSION_TIMEOUT_SECONDS


class VoiceStateManager:
    def __init__(self):
        self._states: dict[int, VoiceState] = {}

    def get_state(self, guild_id: int) -> Optional[VoiceState]:
        return self._states.get(guild_id)

    def create_state(self, guild_id: int) -> VoiceState:
        state = VoiceState(guild_id)
        self._states[guild_id] = state
        return state

    def remove_state(self, guild_id: int):
        if guild_id in self._states:
            del self._states[guild_id]

    def get_or_create_state(self, guild_id: int) -> VoiceState:
        if guild_id not in self._states:
            return self.create_state(guild_id)
        return self._states[guild_id]


_voice_state_manager: Optional[VoiceStateManager] = None


def get_voice_state_manager() -> VoiceStateManager:
    global _voice_state_manager
    if _voice_state_manager is None:
        _voice_state_manager = VoiceStateManager()
    return _voice_state_manager