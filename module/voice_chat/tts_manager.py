import io
import logging
import asyncio
from typing import Optional
import discord
import elevenlabs
import config

logger = logging.getLogger(__name__)


class TTSManager:
    def __init__(self):
        if config.ELEVENLABS_API_KEY:
            elevenlabs.api_key = config.ELEVENLABS_API_KEY

    async def synthesize(self, text: str) -> Optional[discord.FFmpegOpusAudio]:
        if not text:
            return None

        try:
            audio = await asyncio.to_thread(
                elevenlabs.text_to_speech.convert,
                text=text,
                voice=config.ELEVENLABS_VOICE_ID,
                model="eleven_multilingual_v2"
            )

            audio_io = io.BytesIO(audio)
            source = discord.FFmpegOpusAudio(audio_io, pipe=True)
            return source
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return None

    async def synthesize_to_file(self, text: str, filepath: str) -> bool:
        if not text:
            return False

        try:
            await asyncio.to_thread(
                elevenlabs.text_to_speech.save,
                text=text,
                voice=config.ELEVENLABS_VOICE_ID,
                filename=filepath
            )
            return True
        except Exception as e:
            logger.error(f"TTS file save failed: {e}")
            return False


_tts_manager: Optional[TTSManager] = None


def get_tts_manager() -> TTSManager:
    global _tts_manager
    if _tts_manager is None:
        _tts_manager = TTSManager()
    return _tts_manager
