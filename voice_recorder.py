"""Voice recording with per-user WAV file output."""

import os
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from discord.ext import voice_recv

if TYPE_CHECKING:
    import discord


# Discord audio format: 48kHz, stereo, 16-bit PCM
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


@dataclass
class RecordingSession:
    """Metadata for a recording session."""

    session_id: str
    guild_id: int
    started_by: int  # User ID who started recording
    started_at: datetime = field(default_factory=datetime.now)
    output_dir: Path = field(default=None)

    def __post_init__(self):
        if self.output_dir is None:
            self.output_dir = Path("data/recordings") / str(self.guild_id) / self.session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)


class WavAudioSink(voice_recv.AudioSink):
    """Audio sink that buffers PCM audio per user."""

    def __init__(self, session: RecordingSession):
        self.session = session
        self.user_buffers: dict[int, bytearray] = {}  # user_id -> PCM data
        self.user_names: dict[int, str] = {}  # user_id -> display name

    def wants_opus(self) -> bool:
        """We want decoded PCM, not raw Opus."""
        return False

    def write(self, user: "discord.User | discord.Member | None", data: voice_recv.VoiceData):
        """Called when audio data is received from a user."""
        if user is None:
            return

        user_id = user.id
        if user_id not in self.user_buffers:
            self.user_buffers[user_id] = bytearray()
            self.user_names[user_id] = user.display_name

        self.user_buffers[user_id].extend(data.pcm)

    def cleanup(self):
        """Called when recording stops."""
        pass


def save_recordings(sink: WavAudioSink) -> dict[int, Path]:
    """Save all user buffers to WAV files. Returns dict of user_id -> file path."""
    saved_files: dict[int, Path] = {}

    for user_id, pcm_data in sink.user_buffers.items():
        if not pcm_data:
            continue

        # Sanitize username for filename
        username = sink.user_names.get(user_id, str(user_id))
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in username)
        filename = f"{safe_name}_{user_id}.wav"
        filepath = sink.session.output_dir / filename

        # Write WAV file
        with wave.open(str(filepath), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(bytes(pcm_data))

        saved_files[user_id] = filepath

    return saved_files


def get_recording_stats(sink: WavAudioSink) -> dict:
    """Get statistics about the recording."""
    total_bytes = sum(len(buf) for buf in sink.user_buffers.values())
    bytes_per_second = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
    total_seconds = total_bytes / bytes_per_second if bytes_per_second else 0

    return {
        "user_count": len(sink.user_buffers),
        "total_seconds": total_seconds,
        "total_bytes": total_bytes,
        "users": {
            user_id: {
                "name": sink.user_names.get(user_id, str(user_id)),
                "bytes": len(buf),
                "seconds": len(buf) / bytes_per_second if bytes_per_second else 0,
            }
            for user_id, buf in sink.user_buffers.items()
        },
    }
