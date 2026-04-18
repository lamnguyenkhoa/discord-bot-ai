import io
import logging
import asyncio
from typing import Optional
import discord
from elevenlabs import ElevenLabs
import config

logger = logging.getLogger(__name__)


class TTSManager:
    def __init__(self):
        self._client = None

    @property
    def client(self) -> Optional[ElevenLabs]:
        if self._client is None and config.ELEVENLABS_API_KEY:
            self._client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        return self._client

    async def synthesize(self, text: str) -> Optional[discord.FFmpegOpusAudio]:
        if not text or not self.client:
            return None

        try:
            audio = b""
            for chunk in self.client.text_to_speech.convert(
                text=text,
                voice_id=config.ELEVENLABS_VOICE_ID,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            ):
                audio += chunk

            audio_io = io.BytesIO(audio)
            source = discord.FFmpegOpusAudio(audio_io, pipe=True)
            return source
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return None

    async def synthesize_to_file(self, text: str, filepath: str) -> bool:
        if not text or not self.client:
            return False

        try:
            audio = b""
            for chunk in self.client.text_to_speech.convert(
                text=text,
                voice_id=config.ELEVENLABS_VOICE_ID,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            ):
                audio += chunk

            with open(filepath, "wb") as f:
                f.write(audio)
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
