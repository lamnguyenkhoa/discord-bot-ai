# Voice Chat Module

Two-way voice conversation for Discord using wake word activation.

## Features

- **Wake word detection** — Bot only responds when addressed (Hey Bot, Hey Mal, Chào Bot, etc.)
- **Speech-to-text** — OpenAI Whisper for transcription
- **Text-to-speech** — ElevenLabs for natural voice responses
- **Multi-user support** — Group conversation in voice channels
- **Interrupt handling** — Bot stops speaking when someone new talks
- **Session management** — Conversation context with timeout

## Files

| File | Description |
|------|-------------|
| `voice_state.py` | Per-guild connection state and session tracking |
| `stt_manager.py` | Whisper STT integration and wake word detection |
| `tts_manager.py` | ElevenLabs TTS synthesis |
| `voice_commands.py` | /join and /leave slash commands, listen loop |

## Configuration

Set these in `.env`:

```env
VOICE_ENABLED=true
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id
```

## Wake Words

Default wake words:
- **English:** `Hey Bot`, `Hey Mal`
- **Vietnamese:** `Chào Bot`, `Chào Mal`, `Này Bot`, `Này Mal`, `Ủa Bot`, `Ủa Mal`

Customize via `VOICE_WAKE_WORDS` (pipe-separated).

## Usage

```
/join  — Bot joins your voice channel
/leave — Bot leaves the voice channel
```

After joining, address the bot with a wake word:
- "Hey Bot, what's the weather?"
- "Chào Mal, cho tôi hỏi..."

The bot will respond via voice. Within a session, follow-up messages don't need the wake word.

## How It Works

1. Bot captures audio from voice channel
2. Silence detection triggers transcription
3. Wake word check — ignores if not addressed
4. LLM generates response using voice_prompt.txt
5. ElevenLabs synthesizes speech
6. Audio plays in voice channel
