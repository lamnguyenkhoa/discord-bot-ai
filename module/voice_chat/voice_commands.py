import asyncio
import logging
import time
from typing import Optional
import discord
from discord import app_commands
from discord.ext import voice_recv
import config
from .voice_state import get_voice_state_manager
from .stt_manager import get_stt_manager
from .tts_manager import get_tts_manager
from .s2s_manager import get_s2s_manager
import llm_client

logger = logging.getLogger(__name__)


class AudioSinkWrapper(voice_recv.AudioSink):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def write(self, user, data: voice_recv.VoiceData):
        try:
            if data.pcm:
                self.callback(data.pcm, user.id if user else 0)
        except Exception as e:
            logger.warning(f"Audio callback error: {e}")

    def cleanup(self):
        pass

    def wants_opus(self) -> bool:
        return False


def load_voice_prompt() -> str:
    try:
        with open(config.VOICE_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a helpful voice assistant in a Discord voice channel. Keep responses concise and conversational."


def load_join_greeting_prompt() -> str:
    try:
        with open(config.VOICE_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a helpful voice assistant in a Discord voice channel. Greet users briefly when joining."


async def generate_join_greeting() -> str:
    try:
        response = await llm_client.generate_reply(
            user_message="Generate a brief, friendly greeting in Vietnamese for joining a voice channel.",
            memory_context="",
            channel_name="voice-greeting",
            system_prompt=load_join_greeting_prompt(),
        )
        return response if response else "Hello! I'm here and ready to chat."
    except Exception as e:
        logger.warning(f"Failed to generate greeting: {e}")
        return "Hello! I'm here and ready to chat."


async def send_greeting(state):
    if not state or not state.voice_client:
        return

    try:
        greeting_text = await generate_join_greeting()
        if not greeting_text:
            return

        tts = get_tts_manager()

        if config.VOICE_MODE == "s2s":
            s2s = get_s2s_manager()
            audio_source = await s2s.speech_to_speech(
                greeting_text, "You are saying a greeting."
            )
        else:
            audio_source = await tts.synthesize(greeting_text)

        if audio_source and state.voice_client:

            def stop_callback(e):
                if e:
                    logger.error(f"Greeting playback error: {e}")

            state.voice_client.play(audio_source, after=stop_callback)

            while state.voice_client and state.voice_client.is_playing():
                await asyncio.sleep(0.1)
    except Exception as e:
        logger.warning(f"Failed to send greeting: {e}")


async def voice_listen_loop(voice_client: discord.VoiceClient, guild_id: int):
    stt = get_stt_manager()
    tts = get_tts_manager()
    s2s = get_s2s_manager()
    state_manager = get_voice_state_manager()
    state = state_manager.get_state(guild_id)

    if not state:
        return

    audio_queue = asyncio.Queue()
    silence_start: Optional[float] = None
    is_speaking = False
    current_speaker: Optional[int] = None
    is_s2s_mode = config.VOICE_MODE == "s2s"

    def audio_callback(audio_data: bytes, user_id: int, state, is_s2s_mode: bool):
        if not audio_data:
            return

        level = (
            sum(abs(b) for b in audio_data[:100]) / len(audio_data[:100])
            if audio_data
            else 0
        )

        if level > config.VOICE_SILENCE_THRESHOLD:
            silence_start = time.time()
            if not is_speaking:
                is_speaking = True
                if is_s2s_mode:
                    s2s.start_recording(user_id)
                else:
                    stt.start_recording(user_id)
                current_speaker = user_id
            if is_s2s_mode:
                s2s.append_audio(audio_data)
            else:
                stt.append_audio(audio_data)
        elif is_speaking and silence_start:
            if time.time() - silence_start > config.VOICE_SILENCE_TIMEOUT_MS / 1000:
                if is_s2s_mode:
                    audio_queue.put_nowait(s2s.stop_recording())
                else:
                    audio_queue.put_nowait(stt.stop_recording())
                is_speaking = False
                silence_start = None

    while state.voice_client and state.voice_client.is_connected():
        try:
            audio_data = await asyncio.wait_for(audio_queue.get(), timeout=1.0)

            if is_s2s_mode:
                audio_source = await s2s.speech_to_speech(
                    audio_data, load_voice_prompt()
                )
                if audio_source and state.voice_client:

                    def stop_callback(e):
                        if e:
                            logger.error(f"Playback error: {e}")

                    state.voice_client.play(audio_source, after=stop_callback)

                    while state.voice_client and state.voice_client.is_playing():
                        await asyncio.sleep(0.1)

                        if not audio_queue.empty():
                            try:
                                audio_queue.get_nowait()
                                if state.voice_client.is_playing():
                                    state.voice_client.stop()
                            except asyncio.QueueEmpty:
                                pass
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
                            f"User: {u}\nBot: {b}"
                            for u, b in state.conversation_history
                        )
                        memory_context = f"\n\n## Recent Conversation\n{history_text}"

                    response = await llm_client.generate_reply(
                        user_message=user_text,
                        memory_context=memory_context,
                        channel_name=f"voice-{guild_id}",
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

        except asyncio.TimeoutError:
            if state.is_session_expired():
                state.end_session()
        except Exception as e:
            logger.warning(f"Voice listen loop error: {e}")
            await asyncio.sleep(1)


@app_commands.command(name="join", description="Join your voice channel")
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

    is_new_connection = False
    if existing_state and existing_state.voice_client:
        await existing_state.voice_client.move_to(voice_channel)
    else:
        vc = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
        state = state_manager.get_or_create_state(guild_id)
        state.voice_client = vc
        state.channel_id = voice_channel.id
        is_new_connection = True

        vc.listen(
            AudioSinkWrapper(
                lambda audio, user: audio_callback(
                    audio, user.id if user else 0, state, is_s2s_mode
                )
            )
        )

        asyncio.create_task(voice_listen_loop(vc, guild_id))

    mode_note = " (S2S mode)" if config.VOICE_MODE == "s2s" else " (Pipeline mode)"
    await interaction.followup.send(f"Joined {voice_channel.name}{mode_note}")

    if config.VOICE_GREETING_ENABLED and is_new_connection:
        await send_greeting(state_manager.get_state(guild_id))


@app_commands.command(name="leave", description="Leave the voice channel")
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
