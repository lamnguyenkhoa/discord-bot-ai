import io
import logging
import asyncio
from typing import Optional
import discord
from openai import AsyncOpenAI
import config

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=config.LLM_API_KEY)


class S2SManager:
    def __init__(self):
        self.audio_buffer: list[bytes] = []
        self.is_recording: bool = False
        self.current_speaker: Optional[int] = None

    async def speech_to_speech(self, audio_data: bytes, system_prompt: str) -> Optional[discord.FFmpegOpusAudio]:
        if not audio_data:
            return None

        try:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.webm"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": audio_file}
            ]

            response = await client.chat.completions.create(
                model=config.VOICE_S2S_MODEL,
                messages=messages,
                modalities=["text", "audio"],
                audio={"voice": "alloy", "format": "wav"},
            )

            audio_content = response.choices[0].message.audio
            if audio_content and audio_content.data:
                audio_bytes = bytes.fromhex(audio_content.data)
                audio_io = io.BytesIO(audio_bytes)
                source = discord.FFmpegOpusAudio(audio_io, pipe=True)
                return source

            return None
        except Exception as e:
            logger.error(f"S2S failed: {e}")
            return None

    async def transcribe_only(self, audio_data: bytes) -> Optional[str]:
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
            logger.error(f"Transcription failed: {e}")
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


_s2s_manager: Optional[S2SManager] = None


def get_s2s_manager() -> S2SManager:
    global _s2s_manager
    if _s2s_manager is None:
        _s2s_manager = S2SManager()
    return _s2s_manager
