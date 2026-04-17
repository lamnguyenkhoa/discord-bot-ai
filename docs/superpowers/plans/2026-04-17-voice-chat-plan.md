# Two-Way Voice Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable two-way voice chat in Discord via wake word activation, speech-to-text transcription, LLM response generation, and text-to-speech playback.

**Architecture:** Module-based approach following existing patterns. `module/voice_chat/` contains voice state management, STT (Whisper), TTS (ElevenLabs), and slash commands. Wake word detection after Whisper transcription. Session-based conversation with interrupt handling.

**Tech Stack:** discord.py[voice], openai (Whisper), elevenlabs, aiohttp, existing llm_client.py

---

## File Structure

```
module/voice_chat/
├── __init__.py           # Singleton getter pattern
├── voice_state.py        # Per-guild connection state, session tracking
├── stt_manager.py        # Audio capture, Whisper API
├── tts_manager.py       # ElevenLabs API
└── voice_commands.py     # /join, /leave commands

bot.py                    # Modify: add intents, import voice module
config.py                 # Modify: add VOICE_* config values
requirements.txt          # Modify: add voice dependencies
.env.example              # Modify: add VOICE_* env vars
voice_prompt.txt          # Create: voice-specific system prompt
```

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add voice dependencies to requirements.txt**

Add to end of file:
```
discord.py[voice]>=2.3
elevenlabs>=1.0
```

- [ ] **Step 2: Add VOICE_* env vars to .env.example**

Add to end of file:
```
# Voice Chat
VOICE_ENABLED=true
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=premade/chat-abcd
VOICE_WAKE_WORDS=Hey Bot|Hey Mal|Chào Bot|Chào Mal|Này Bot|Này Mal|Ủa Bot|Ủa Mal
VOICE_SILENCE_THRESHOLD=0.1
VOICE_SILENCE_TIMEOUT_MS=500
VOICE_SESSION_TIMEOUT_SECONDS=30
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt .env.example
git commit -m "feat(voice): add voice chat dependencies and env vars"
```

---

## Task 2: Add Voice Config

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add VOICE_* config values to config.py**

Add to end of file (before any trailing newlines):
```python
# Voice Chat
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() in ("1", "true", "yes")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "premade/chat-abcd")
VOICE_WAKE_WORDS = os.getenv("VOICE_WAKE_WORDS", "Hey Bot|Hey Mal").split("|")
VOICE_SILENCE_THRESHOLD = float(os.getenv("VOICE_SILENCE_THRESHOLD", "0.1"))
VOICE_SILENCE_TIMEOUT_MS = int(os.getenv("VOICE_SILENCE_TIMEOUT_MS", "500"))
VOICE_SESSION_TIMEOUT_SECONDS = int(os.getenv("VOICE_SESSION_TIMEOUT_SECONDS", "30"))
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat(voice): add voice chat config values"
```

---

## Task 3: Create Voice State Manager

**Files:**
- Create: `module/voice_chat/__init__.py`
- Create: `module/voice_chat/voice_state.py`

- [ ] **Step 1: Create module/voice_chat/__init__.py**

```python
from .voice_state import VoiceStateManager, get_voice_state_manager

__all__ = ["VoiceStateManager", "get_voice_state_manager"]
```

- [ ] **Step 2: Create module/voice_chat/voice_state.py**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add module/voice_chat/__init__.py module/voice_chat/voice_state.py
git commit -m "feat(voice): add voice state manager"
```

---

## Task 4: Create STT Manager

**Files:**
- Create: `module/voice_chat/stt_manager.py`

- [ ] **Step 1: Create module/voice_chat/stt_manager.py**

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
```

- [ ] **Step 2: Commit**

```bash
git add module/voice_chat/stt_manager.py
git commit -m "feat(voice): add STT manager with Whisper integration"
```

---

## Task 5: Create TTS Manager

**Files:**
- Create: `module/voice_chat/tts_manager.py`

- [ ] **Step 1: Create module/voice_chat/tts_manager.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add module/voice_chat/tts_manager.py
git commit -m "feat(voice): add TTS manager with ElevenLabs integration"
```

---

## Task 6: Create Voice Commands

**Files:**
- Create: `module/voice_chat/voice_commands.py`

- [ ] **Step 1: Create module/voice_chat/voice_commands.py**

```python
import asyncio
import logging
import time
from typing import Optional
import discord
from discord import app_commands
import config
from .voice_state import get_voice_state_manager
from .stt_manager import get_stt_manager
from .tts_manager import get_tts_manager
import llm_client

logger = logging.getLogger(__name__)


def load_voice_prompt() -> str:
    try:
        with open(config.VOICE_PPROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a helpful voice assistant in a Discord voice channel. Keep responses concise and conversational."


async def voice_listen_loop(voice_client: discord.VoiceClient, guild_id: int):
    stt = get_stt_manager()
    tts = get_tts_manager()
    state_manager = get_voice_state_manager()
    state = state_manager.get_state(guild_id)
    
    if not state:
        return

    audio_queue = asyncio.Queue()
    silence_start: Optional[float] = None
    is_speaking = False
    current_speaker: Optional[int] = None

    def audio_callback(audio: bytes, user_id: int):
        if not audio:
            return
        
        level = sum(abs(b) for b in audio[:100]) / len(audio[:100]) if audio else 0
        
        if level > config.VOICE_SILENCE_THRESHOLD:
            silence_start = time.time()
            if not is_speaking:
                is_speaking = True
                stt.start_recording(user_id)
                current_speaker = user_id
            stt.append_audio(audio)
        elif is_speaking and silence_start:
            if time.time() - silence_start > config.VOICE_SILENCE_TIMEOUT_MS / 1000:
                audio_queue.put_nowait(stt.stop_recording())
                is_speaking = False
                silence_start = None

    while state.voice_client and state.voice_client.is_connected():
        try:
            audio_data = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
            
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

                voice_prompt = load_voice_prompt()
                
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
                    state.voice_client.play(audio_source, after=lambda e: logger.error(f"Playback error: {e}") if e else None)
                    
                    while state.voice_client and state.voice_client.is_playing():
                        await asyncio.sleep(0.1)

        except asyncio.TimeoutError:
            if state.is_session_expired():
                state.end_session()
        except Exception as e:
            logger.warning(f"Voice listen loop error: {e}")
            await asyncio.sleep(1)


@tree.command(name="join", description="Join your voice channel")
async def join_command(interaction: discord.Interaction):
    if not config.VOICE_ENABLED:
        await interaction.response.send_message("Voice chat is not enabled.")
        return

    if not interaction.user.voice:
        await interaction.response.send_message("Join a voice channel first.")
        return

    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel
    guild_id = interaction.guild.id
    
    state_manager = get_voice_state_manager()
    existing_state = state_manager.get_state(guild_id)
    
    if existing_state and existing_state.voice_client:
        await existing_state.voice_client.move_to(voice_channel)
    else:
        vc = await voice_channel.connect()
        state = state_manager.get_or_create_state(guild_id)
        state.voice_client = vc
        state.channel_id = voice_channel.id
        
        asyncio.create_task(voice_listen_loop(vc, guild_id))

    await interaction.followup.send(f"Joined {voice_channel.name}")


@tree.command(name="leave", description="Leave the voice channel")
async def leave_command(interaction: discord.Interaction):
    if not config.VOICE_ENABLED:
        await interaction.response.send_message("Voice chat is not enabled.")
        return

    guild_id = interaction.guild.id
    state_manager = get_voice_state_manager()
    state = state_manager.get_state(guild_id)

    if not state or not state.voice_client:
        await interaction.response.send_message("Not in a voice channel.")
        return

    await state.voice_client.disconnect()
    state_manager.remove_state(guild_id)
    await interaction.response.send_message("Left the voice channel.")
```

- [ ] **Step 2: Commit**

```bash
git add module/voice_chat/voice_commands.py
git commit -m "feat(voice): add voice commands with listen loop"
```

---

## Task 7: Integrate Voice Module in Bot

**Files:**
- Modify: `bot.py`
- Create: `voice_prompt.txt`

- [ ] **Step 1: Add voice intents and imports to bot.py**

Add to intents section (after line 30):
```python
intents.voice_states = True
```

Add import after other module imports:
```python
from module.voice_chat.voice_commands import join_command, leave_command
```

Add command registration after `tree = app_commands.CommandTree(client)`:
```python
tree.add_command(join_command)
tree.add_command(leave_command)
```

- [ ] **Step 2: Create voice_prompt.txt**

```txt
You are a friendly, conversational voice assistant. You are speaking with users in a Discord voice channel.

Guidelines:
- Keep responses SHORT and conversational (1-3 sentences max)
- Speak naturally as if in a phone call
- Be helpful, friendly, and concise
- Adapt to the language the user is speaking (English or Vietnamese)
- If you don't know something, say so briefly
- Ask clarifying questions if needed, but keep it brief
```

- [ ] **Step 3: Commit**

```bash
git add bot.py voice_prompt.txt
git commit -m "feat(voice): integrate voice module into bot"
```

---

## Task 8: Add Interrupt Handling

**Files:**
- Modify: `module/voice_chat/voice_commands.py`
- Modify: `module/voice_chat/voice_state.py`

- [ ] **Step 1: Update voice_listen_loop to handle interrupts**

Replace the `while state.voice_client.is_playing()` section with:

```python
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

- [ ] **Step 2: Update VoiceState to include audio_queue**

Add to `VoiceState.__init__`:
```python
from asyncio import Queue
self.audio_queue: Queue = Queue()
```

- [ ] **Step 3: Commit**

```bash
git add module/voice_chat/voice_commands.py module/voice_chat/voice_state.py
git commit -m "feat(voice): add interrupt handling during playback"
```

---

## Task 9: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add voice chat documentation to README**

Add after the Follow-Up Chat section:

```markdown
### Voice Chat

Two-way voice conversation in Discord voice channels.

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_ENABLED` | false | Enable voice chat |
| `ELEVENLABS_API_KEY` | | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | premade/chat-abcd | Voice preset ID |
| `VOICE_WAKE_WORDS` | Hey Bot\\|Hey Mal | Wake words (pipe-separated) |
| `VOICE_SILENCE_TIMEOUT_MS` | 500 | Silence timeout before processing |
| `VOICE_SESSION_TIMEOUT_SECONDS` | 30 | Session timeout |

## Commands

- `/join` - Join your voice channel
- `/leave` - Leave the voice channel
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add voice chat documentation"
```

---

## Spec Coverage Check

- [x] Wake word detection (English + Vietnamese) - Task 4
- [x] Multi-user handling / group conversation - Task 4, 6
- [x] Session management with timeout - Task 3
- [x] Interrupt handling - Task 8
- [x] STT via Whisper - Task 4
- [x] TTS via ElevenLabs - Task 5
- [x] LLM integration via existing llm_client - Task 6
- [x] Voice commands /join, /leave - Task 6
- [x] Config values - Task 2
- [x] Dependencies - Task 1
- [x] Documentation - Task 9

## Placeholder Scan

All steps contain complete code. No TODOs or TBDs.
