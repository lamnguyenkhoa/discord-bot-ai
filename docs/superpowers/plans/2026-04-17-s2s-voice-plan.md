# GPT-4o Audio Speech-to-Speech Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline.

**Goal:** Add GPT-4o audio speech-to-speech as an alternative to the current Whisper + ElevenLabs pipeline, controlled via `VOICE_MODE` env var.

**Architecture:** Create `s2s_manager.py` for GPT-4o audio S2S. Update voice_commands.py to select between pipeline (STT + LLM + TTS) and S2S modes based on config.

**Tech Stack:** OpenAI SDK (gpt-audio-mini or gpt-realtime-mini), existing llm_client.py

---

## Task 1: Add S2S Config

**Files:**
- Modify: `config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add VOICE_MODE config to config.py**

Add after line 87:
```python
# Voice mode: "pipeline" (Whisper + LLM + ElevenLabs) or "s2s" (GPT-4o audio)
VOICE_MODE = os.getenv("VOICE_MODE", "pipeline").lower()
VOICE_S2S_MODEL = os.getenv("VOICE_S2S_MODEL", "gpt-audio-mini-2025-12-15")
```

- [ ] **Step 2: Update .env.example**

Add to Voice Chat section:
```
VOICE_MODE=pipeline  # pipeline or s2s
VOICE_S2S_MODEL=gpt-audio-mini-2025-12-15
```

- [ ] **Step 3: Commit**
```bash
git add config.py .env.example
git commit -m "feat(voice): add VOICE_MODE config for S2S switch"
```

---

## Task 2: Create S2S Manager

**Files:**
- Create: `module/voice_chat/s2s_manager.py`

- [ ] **Step 1: Create s2s_manager.py**

```python
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
```

- [ ] **Step 2: Update __init__.py to export S2S manager**

Add to `module/voice_chat/__init__.py`:
```python
from .s2s_manager import S2SManager, get_s2s_manager

__all__ = ["VoiceStateManager", "get_voice_state_manager", "S2SManager", "get_s2s_manager"]
```

- [ ] **Step 3: Commit**
```bash
git add module/voice_chat/s2s_manager.py module/voice_chat/__init__.py
git commit -m "feat(voice): add GPT-4o audio S2S manager"
```

---

## Task 3: Update Voice Commands for Mode Selection

**Files:**
- Modify: `module/voice_chat/voice_commands.py`

- [ ] **Step 1: Update imports**

Add after existing imports:
```python
from .s2s_manager import get_s2s_manager
```

- [ ] **Step 2: Update voice_listen_loop to support both modes**

Replace the main processing section with:
```python
            if config.VOICE_MODE == "s2s":
                s2s = get_s2s_manager()
                audio_source = await s2s.speech_to_speech(audio_data, load_voice_prompt())
                if audio_source and state.voice_client:
                    state.voice_client.play(audio_source, after=lambda e: logger.error(f"Playback error: {e}") if e else None)
                    while state.voice_client and state.voice_client.is_playing():
                        await asyncio.sleep(0.1)
            else:
                transcription = await stt.transcribe(audio_data)
                if not transcription:
                    continue

                has_wake, prompt = stt.check_wake_word(transcription)
                
                if has_wake or state.session_active:
                    if has_wake:
                        state.start_session()
                        if prompt:
                            user_text = prompt
                        else:
                            continue
                    else:
                        user_text = transcription

                    memory_context = ""
                    if state.conversation_history:
                        history_text = "\n".join(
                            f"User: {u}\nBot: {b}" for u, b in state.conversation_history
                        )
                        memory_context = f"\n\n## Recent Conversation\n{history_text}"

                    response = await llm_client.generate_reply(
                        user_message=user_text,
                        memory_context=memory_context,
                        channel_name=f"voice-{guild_id}"
                    )

                    state.add_turn(user_text, response)

                    audio_source = await tts.synthesize(response)
                    if audio_source and state.voice_client:
                        def stop_callback(e):
                            if e:
                                logger.error(f"Playback error: {e}")
                        
                        state.voice_client.play(audio_source, after=stop_callback)
                        
                        while state.voice_client and state.voice_client.is_playing():
                            await asyncio.sleep(0.1)
                            
                            if not audio_queue.empty():
                                try:
                                    queue_item = audio_queue.get_nowait()
                                    if state.voice_client.is_playing():
                                        state.voice_client.stop()
                                except asyncio.QueueEmpty:
                                    pass
```

- [ ] **Step 3: Commit**
```bash
git add module/voice_chat/voice_commands.py
git commit -m "feat(voice): add VOICE_MODE switch between pipeline and S2S"
```

---

## Task 4: Update Documentation

**Files:**
- Modify: `module/voice_chat/README.md`
- Modify: `README.md`

- [ ] **Step 1: Update module README**

Add section about VOICE_MODE:
```markdown
## Voice Modes

Two modes available via `VOICE_MODE` env var:

### Pipeline Mode (default)
- STT: OpenAI Whisper → LLM → TTS: ElevenLabs
- More controllable, separate components
- Set `VOICE_MODE=pipeline`

### S2S Mode (GPT-4o Audio)
- Direct speech-to-speech using GPT-4o audio models
- Faster, more natural prosody
- Single API call
- Set `VOICE_MODE=s2s`

## Configuration

Set in `.env`:
```env
VOICE_MODE=pipeline  # or s2s
VOICE_S2S_MODEL=gpt-audio-mini-2025-12-15
```
```

- [ ] **Step 2: Commit**
```bash
git add module/voice_chat/README.md README.md
git commit -m "docs(voice): document VOICE_MODE configuration"
```

---

## Spec Coverage Check

- [x] VOICE_MODE config switch - Task 1
- [x] S2S manager with GPT-4o audio - Task 2
- [x] Pipeline mode (existing) preserved - Task 3
- [x] S2S mode integration - Task 3
- [x] Documentation updated - Task 4
