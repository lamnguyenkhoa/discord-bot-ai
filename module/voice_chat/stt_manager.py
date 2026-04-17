import io
import logging
import asyncio
from typing import Optional
import discord
from openai import AsyncOpenAI
import config

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=config.LLM_API_KEY)


class STTManager:
    def __init__(self):
        self.audio_buffer: list[bytes] = []
        self.is_recording: bool = False
        self.current_speaker: Optional[int] = None

    async def transcribe(self, audio_data: bytes) -> Optional[str]:
        if not audio_data:
            return None

        try:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.webm"

            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
            return response
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            return None

    def start_recording(self, user_id: int):
        self.audio_buffer.clear()
        self.is_recording = True
        self.current_speaker = user_id

    def append_audio(self, audio_chunk: bytes):
        if self.is_recording:
            self.audio_buffer.append(audio_chunk)

    def stop_recording(self) -> bytes:
        self.is_recording = False
        self.current_speaker = None
        combined = b"".join(self.audio_buffer)
        self.audio_buffer.clear()
        return combined

    def check_wake_word(self, text: str) -> tuple[bool, str]:
        text_lower = text.lower().strip()
        for wake_word in config.VOICE_WAKE_WORDS:
            wake_word_lower = wake_word.lower()
            if text_lower.startswith(wake_word_lower):
                prompt = text[len(wake_word):].strip()
                if prompt:
                    return True, prompt
                return True, ""
        return False, ""


_stt_manager: Optional[STTManager] = None


def get_stt_manager() -> STTManager:
    global _stt_manager
    if _stt_manager is None:
        _stt_manager = STTManager()
    return _stt_manager
