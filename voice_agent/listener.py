"""Voice activity detection and audio capture for voice conversations."""

import asyncio
import io
import struct
import traceback
import wave
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Awaitable

from discord.ext import voice_recv

if TYPE_CHECKING:
    import discord


# Discord audio format: 48kHz, stereo, 16-bit PCM
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH

# Voice activity detection settings
SILENCE_THRESHOLD = 500  # RMS threshold for silence detection
SILENCE_DURATION = 1.5  # Seconds of silence before processing
MIN_SPEECH_DURATION = 0.5  # Minimum speech duration to process
STALE_BUFFER_TIMEOUT = 300  # Seconds before removing inactive user buffers (5 min)


@dataclass
class UserAudioBuffer:
    """Buffer for a single user's audio."""

    user_id: int
    user_name: str
    buffer: bytearray = field(default_factory=bytearray)
    last_audio_time: datetime = field(default_factory=datetime.now)
    is_speaking: bool = False


class VoiceActivitySink(voice_recv.AudioSink):
    """Audio sink with voice activity detection."""

    def __init__(
        self,
        on_utterance_complete: Callable[[int, str, bytes], Awaitable[None]],
        silence_duration: float = SILENCE_DURATION,
    ):
        """
        Initialize voice activity sink.

        Args:
            on_utterance_complete: Async callback when utterance is detected.
                                   Called with (user_id, user_name, wav_bytes)
            silence_duration: Seconds of silence before triggering callback
        """
        self.on_utterance_complete = on_utterance_complete
        self.silence_duration = silence_duration
        self.user_buffers: dict[int, UserAudioBuffer] = {}
        self._running = True
        self._check_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def wants_opus(self) -> bool:
        """We want decoded PCM, not raw Opus."""
        return False

    def write(self, user: "discord.User | discord.Member | None", data: voice_recv.VoiceData):
        """Called when audio data is received from a user."""
        if user is None or not self._running:
            return

        user_id = user.id
        now = datetime.now()

        # Initialize buffer for new user
        if user_id not in self.user_buffers:
            self.user_buffers[user_id] = UserAudioBuffer(
                user_id=user_id,
                user_name=user.display_name,
            )

        buf = self.user_buffers[user_id]

        # Calculate RMS to detect voice activity
        rms = self._calculate_rms(data.pcm)

        if rms > SILENCE_THRESHOLD:
            # User is speaking
            buf.is_speaking = True
            buf.buffer.extend(data.pcm)
            buf.last_audio_time = now
        elif buf.is_speaking:
            # User might have stopped, still add audio (captures trailing sounds)
            buf.buffer.extend(data.pcm)

    def _calculate_rms(self, pcm_data: bytes) -> float:
        """Calculate RMS (root mean square) of audio data."""
        if len(pcm_data) < 2:
            return 0

        # Unpack 16-bit samples
        samples = struct.unpack(f"<{len(pcm_data) // 2}h", pcm_data)
        if not samples:
            return 0

        # Calculate RMS
        sum_squares = sum(s * s for s in samples)
        rms = (sum_squares / len(samples)) ** 0.5
        return rms

    async def start_monitoring(self, loop: asyncio.AbstractEventLoop):
        """Start the silence detection monitoring task."""
        self._loop = loop
        self._check_task = loop.create_task(self._monitor_silence())

    async def _monitor_silence(self):
        """Monitor for silence and trigger callbacks."""
        while self._running:
            await asyncio.sleep(0.1)  # Check every 100ms

            now = datetime.now()
            stale_users = []

            for user_id, buf in list(self.user_buffers.items()):
                time_since_audio = (now - buf.last_audio_time).total_seconds()

                # Clean up stale buffers (users who haven't spoken in a while)
                if time_since_audio >= STALE_BUFFER_TIMEOUT and not buf.is_speaking:
                    stale_users.append(user_id)
                    continue

                if not buf.is_speaking:
                    continue

                # Check if user has been silent long enough
                if time_since_audio >= self.silence_duration:
                    # Check minimum speech duration
                    speech_duration = len(buf.buffer) / BYTES_PER_SECOND
                    if speech_duration >= MIN_SPEECH_DURATION:
                        # Convert to WAV and trigger callback
                        wav_bytes = self._buffer_to_wav(buf.buffer)
                        try:
                            await self.on_utterance_complete(
                                buf.user_id, buf.user_name, wav_bytes
                            )
                        except Exception as e:
                            print(f"Error in utterance callback: {e}")
                            traceback.print_exc()

                    # Reset buffer
                    buf.buffer.clear()
                    buf.is_speaking = False

            # Remove stale user buffers to prevent memory leak
            for user_id in stale_users:
                del self.user_buffers[user_id]

    def _buffer_to_wav(self, pcm_buffer: bytearray) -> bytes:
        """Convert PCM buffer to WAV bytes."""
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(bytes(pcm_buffer))
        return wav_io.getvalue()

    def cleanup(self):
        """Stop monitoring and clean up."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
        self.user_buffers.clear()


class VoiceListener:
    """Manages voice listening for a guild."""

    def __init__(
        self,
        voice_client: voice_recv.VoiceRecvClient,
        on_utterance: Callable[[int, str, bytes], Awaitable[None]],
    ):
        """
        Initialize voice listener.

        Args:
            voice_client: The voice client to listen on
            on_utterance: Callback when complete utterance is detected
        """
        self.voice_client = voice_client
        self.on_utterance = on_utterance
        self.sink: VoiceActivitySink | None = None
        self._active = False

    async def start(self):
        """Start listening for voice activity."""
        if self._active:
            return

        self.sink = VoiceActivitySink(on_utterance_complete=self.on_utterance)
        self.voice_client.listen(self.sink)

        # Start monitoring task
        loop = asyncio.get_running_loop()
        await self.sink.start_monitoring(loop)

        self._active = True

    def stop(self):
        """Stop listening."""
        if not self._active:
            return

        self.voice_client.stop_listening()

        if self.sink:
            self.sink.cleanup()
            self.sink = None

        self._active = False

    @property
    def is_active(self) -> bool:
        """Check if listener is active."""
        return self._active
