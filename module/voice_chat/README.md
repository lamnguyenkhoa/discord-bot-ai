# Voice Chat Module

Two-way voice conversation for Discord using wake word activation.

## Features

- **Wake word detection** — Bot only responds when addressed (Hey Bot, Hey Mal, Chào Bot, etc.)
- **Two voice modes** — Pipeline (Whisper + LLM + ElevenLabs) or S2S (GPT-4o audio)
- **Speech-to-text** — OpenAI Whisper for transcription (pipeline mode)
- **Text-to-speech** — ElevenLabs for natural voice responses (pipeline mode)
- **Multi-user support** — Group conversation in voice channels
- **Interrupt handling** — Bot stops speaking when someone new talks
- **Session management** — Conversation context with timeout

## Voice Modes

Switch between modes via `VOICE_MODE` env var:

| Mode | Setting | Description |
|------|---------|-------------|
| **Pipeline** | `VOICE_MODE=pipeline` | Whisper STT → LLM → ElevenLabs TTS |
| **S2S** | `VOICE_MODE=s2s` | Direct speech-to-speech with GPT-4o audio |

### Pipeline Mode (default)
- Separate, well-tested components
- More controllable (swap TTS provider, add logging)
- Requires: ElevenLabs API key

### S2S Mode (GPT-4o Audio)
- Single API call, faster response
- More natural prosody preservation
- Uses GPT-4o audio model
- Requires: OpenAI API key with audio access

## Files

| File | Description |
|------|-------------|
| `voice_state.py` | Per-guild connection state and session tracking |
| `stt_manager.py` | Whisper STT integration and wake word detection |
| `tts_manager.py` | ElevenLabs TTS synthesis |
| `s2s_manager.py` | GPT-4o audio speech-to-speech |
| `voice_commands.py` | /join and /leave slash commands, listen loop |

## Configuration

Set in `.env`:

```env
VOICE_ENABLED=true
VOICE_MODE=pipeline  # or s2s

# Pipeline mode (default)
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id

# S2S mode
VOICE_S2S_MODEL=gpt-audio-mini-2025-12-15
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

**Pipeline mode:**
1. Bot captures audio from voice channel
2. Silence detection triggers transcription (Whisper)
3. Wake word check — ignores if not addressed
4. LLM generates response using voice_prompt.txt
5. ElevenLabs synthesizes speech
6. Audio plays in voice channel

**S2S mode:**
1. Bot captures audio from voice channel
2. Silence detection triggers processing
3. GPT-4o audio processes speech directly → speech output
4. Audio plays in voice channel
