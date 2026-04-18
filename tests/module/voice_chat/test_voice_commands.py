import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


class TestCreateAudioCallback:
    @pytest.fixture
    def mock_config(self):
        with patch("module.voice_chat.voice_commands.config") as cfg:
            cfg.VOICE_SILENCE_THRESHOLD = 50
            cfg.VOICE_SILENCE_TIMEOUT_MS = 500
            yield cfg

    @pytest.fixture
    def mock_managers(self):
        with patch("module.voice_chat.voice_commands.get_stt_manager") as stt_mock, \
             patch("module.voice_chat.voice_commands.get_s2s_manager") as s2s_mock:
            stt = MagicMock()
            s2s = MagicMock()
            stt_mock.return_value = stt
            s2s_mock.return_value = s2s
            yield stt, s2s

    def test_returns_callable(self, mock_config, mock_managers):
        from module.voice_chat import voice_commands
        stt, s2s = mock_managers

        audio_queue = asyncio.Queue()
        state = MagicMock()
        callback = voice_commands.create_audio_callback(audio_queue, state, False)

        assert callable(callback)

    def test_empty_audio_ignored(self, mock_config, mock_managers):
        from module.voice_chat import voice_commands
        stt, s2s = mock_managers

        audio_queue = asyncio.Queue()
        state = MagicMock()
        callback = voice_commands.create_audio_callback(audio_queue, state, False)

        callback(b"", 123)

        assert audio_queue.empty()

    def test_low_volume_ignored(self, mock_config, mock_managers):
        from module.voice_chat import voice_commands
        stt, s2s = mock_managers

        audio_queue = asyncio.Queue()
        state = MagicMock()
        callback = voice_commands.create_audio_callback(audio_queue, state, False)

        quiet_audio = bytes([10] * 100)
        callback(quiet_audio, 123)

        stt.start_recording.assert_not_called()
        assert audio_queue.empty()

    def test_high_volume_triggers_recording_pipeline_mode(self, mock_config, mock_managers):
        from module.voice_chat import voice_commands
        stt, s2s = mock_managers

        audio_queue = asyncio.Queue()
        state = MagicMock()
        callback = voice_commands.create_audio_callback(audio_queue, state, False)

        loud_audio = bytes([100] * 100)
        callback(loud_audio, 456)

        stt.start_recording.assert_called_once_with(456)
        stt.append_audio.assert_called_once_with(loud_audio)

    def test_high_volume_triggers_recording_s2s_mode(self, mock_config, mock_managers):
        from module.voice_chat import voice_commands
        stt, s2s = mock_managers

        audio_queue = asyncio.Queue()
        state = MagicMock()
        callback = voice_commands.create_audio_callback(audio_queue, state, True)

        loud_audio = bytes([100] * 100)
        callback(loud_audio, 789)

        s2s.start_recording.assert_called_once_with(789)
        s2s.append_audio.assert_called_once_with(loud_audio)

    def test_silence_after_speech_queues_audio(self, mock_config, mock_managers):
        from module.voice_chat import voice_commands
        stt, s2s = mock_managers
        stt.stop_recording.return_value = b"transcribed_audio"

        import module.voice_chat.voice_commands as vc
        with patch.object(vc, "time") as mock_time:
            mock_time.time.side_effect = [1000.0, 2000.5]

            audio_queue = asyncio.Queue()
            state = MagicMock()
            callback = voice_commands.create_audio_callback(audio_queue, state, False)

            loud_audio = bytes([100] * 100)
            callback(loud_audio, 123)

            quiet_audio = bytes([10] * 100)
            callback(quiet_audio, 123)

        stt.stop_recording.assert_called_once()
        assert not audio_queue.empty()
        assert audio_queue.get_nowait() == b"transcribed_audio"


class TestAudioSinkWrapper:
    @pytest.fixture
    def mock_voice_recv(self):
        with patch("module.voice_chat.voice_commands.voice_recv") as vr:
            yield vr

    def test_write_calls_callback_with_pcm(self, mock_voice_recv):
        from module.voice_chat import voice_commands

        mock_callback = MagicMock()
        wrapper = voice_commands.AudioSinkWrapper(mock_callback)

        mock_user = MagicMock()
        mock_user.id = 123
        mock_data = MagicMock()
        mock_data.pcm = b"audio_data_here"

        wrapper.write(mock_user, mock_data)

        mock_callback.assert_called_once_with(b"audio_data_here", 123)

    def test_write_ignores_opus_data(self, mock_voice_recv):
        from module.voice_chat import voice_commands

        mock_callback = MagicMock()
        wrapper = voice_commands.AudioSinkWrapper(mock_callback)

        mock_user = MagicMock()
        mock_data = MagicMock()
        mock_data.pcm = None

        wrapper.write(mock_user, mock_data)

        mock_callback.assert_not_called()

    def test_write_handles_none_user(self, mock_voice_recv):
        from module.voice_chat import voice_commands

        mock_callback = MagicMock()
        wrapper = voice_commands.AudioSinkWrapper(mock_callback)

        mock_data = MagicMock()
        mock_data.pcm = b"audio"

        wrapper.write(None, mock_data)

        mock_callback.assert_called_once_with(b"audio", 0)

    def test_write_handles_exception(self, mock_voice_recv):
        from module.voice_chat import voice_commands

        mock_callback = MagicMock(side_effect=Exception("test error"))
        wrapper = voice_commands.AudioSinkWrapper(mock_callback)

        mock_user = MagicMock()
        mock_data = MagicMock()
        mock_data.pcm = b"audio"

        wrapper.write(mock_user, mock_data)

    def test_wants_opus_returns_false(self, mock_voice_recv):
        from module.voice_chat import voice_commands

        wrapper = voice_commands.AudioSinkWrapper(MagicMock())

        assert wrapper.wants_opus() is False