# Two-Way Voice Chat Feature Design

## Overview

The bot will join Discord voice channels via slash command, listen for speech (transcribed via OpenAI Whisper), detect wake words, generate responses using the existing LLM client with a voice-specific prompt, and speak back via ElevenLabs TTS. Multiple users can be in the voice channel; the bot treats it as a group conversation.

## Wake Words

The bot responds only when a wake word is detected at the start of a speech segment.

**English:**
- `Hey Bot`
- `Hey Mal`

**Vietnamese:**
- `Chào Bot` / `Chào Mal`
- `Này Bot` / `Này Mal`
- `Ủa Bot` / `Ủa Mal`

Wake word detection is case-insensitive. Detection happens after Whisper transcription.

## Session Flow

```
User: "Hey Bot, what's for lunch?"
  → Wake word detected → Bot processes → ElevenLabs responds
User: "What about pizza?" (continuing conversation)
  → No wake word needed (within session) → Bot processes → Responds
User: (someone talking about unrelated stuff)
  → No wake word → Bot ignores
User: (30 seconds of silence)
  → Session resets → Needs wake word again
User: "Chào Mal, cho tôi hỏi về..."
  → Vietnamese wake word → Bot processes → Responds (Vietnamese TTS)
```

## Multi-User Handling

- Bot treats the voice channel as a **group conversation**
- **Speaker identification**: Discord provides `user_id` via voice packets — tracked for logging
- **Turn management**: Uses audio level threshold + silence timeout (500ms) to detect when speech segment ends

## Interrupt Handling

- Bot monitors audio input while speaking
- If new speech detected (different user):
  1. Stop current TTS playback (`voice_client.stop_playing()`)
  2. Process the new speech
  3. Generate and play new response

## Architecture

```
module/voice_chat/
├── __init__.py
├── voice_state.py      # Per-guild connection state, session tracking
├── stt_manager.py      # Audio capture, Whisper API integration
├── tts_manager.py      # ElevenLabs API integration
└── voice_commands.py   # /join, /leave slash commands
```

## Data Flow

1. User runs `/join` → bot connects to user's voice channel
2. Bot continuously captures audio from voice channel
3. Silence detected → chunk audio for processing
4. Audio sent to Whisper API → transcription returned
5. Check transcription for wake word
   - If no wake word → ignore, continue listening
   - If wake word → process remaining text as prompt
6. If processing: LLM generates response (with voice_prompt.txt context)
7. Response sent to ElevenLabs → audio returned
8. Audio played in voice channel via `voice_client.play()`
9. Return to passive listening

## Configuration

```env
# Voice (new)
VOICE_ENABLED=true
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=          # e.g., "premade/chat-abcd"
VOICE_PPROMPT_FILE=voice_prompt.txt
VOICE_WAKE_WORDS=en:Hey Bot|Hey Mal,vi:Chào Bot|Chào Mal|Này Bot|Này Mal|Ủa Bot|Ủa Mal
VOICE_SILENCE_THRESHOLD=0.1   # Audio level to trigger capture
VOICE_SILENCE_TIMEOUT_MS=500  # Wait time after speech ends
VOICE_SESSION_TIMEOUT_SECONDS=30
```

## New Dependencies

```
discord.py[voice]>=2.3
openai>=1.0
elevenlabs>=1.0
aiohttp>=3.9
```

## Component Details

### voice_state.py
- `VoiceState` class per guild
- Tracks: `voice_client`, `current_channel`, `session_active`, `last_speech_time`
- Manages session timeout and reset

### stt_manager.py
- `STTManager` class
- Methods: `transcribe(audio_data: bytes) -> str`
- Uses OpenAI Whisper API
- Handles audio chunking and formatting

### tts_manager.py
- `TTSManager` class
- Methods: `synthesize(text: str) -> AudioSource`
- Uses ElevenLabs API
- Returns `discord.FFmpegOpusAudio` for playback

### voice_commands.py
- `/join` — Connects bot to user's current voice channel
- `/leave` — Disconnects bot from voice channel
- Both admin-only or configurable per-user

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Not in voice channel for `/join` | Reply: "Join a voice channel first" |
| Mic/audio unavailable | Notify user, stay in channel |
| STT fails | Retry once, then ignore speech |
| TTS fails | Fall back to text reply in channel |
| Bot disconnects unexpectedly | Clean up state, reset session |
| LLM fails | Reply with error message via TTS |

## File Cleanup

- Temp audio files deleted immediately after Whisper processing
- FFmpeg temp files cleaned up after playback

## Threading

No separate threads needed. All operations are async:
- Whisper API: async via `aiohttp`
- ElevenLabs API: async
- LLM calls: async (existing `llm_client.py`)
- Audio processing: `loop.run_in_executor()` for CPU-bound work
- Interrupt detection: main async loop

## Integration with Existing Code

1. Add `intents.voice_states = True` to bot intents in `bot.py`
2. Import voice commands module in `bot.py`
3. Voice commands registered via `tree`
4. Reuse existing `llm_client.py` with `voice_prompt.txt` system prompt
5. Config values added to `config.py`

## Testing Considerations

- Mock Whisper/TTS for unit tests
- Test wake word detection with various phrasings
- Test interrupt handling with multiple speakers
- Test session timeout behavior
- Test Vietnamese transcription/response cycle
