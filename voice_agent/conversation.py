"""Voice conversation orchestrator - connects listening, AI, and speaking."""

import asyncio
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from discord.ext import voice_recv

from game_agent import GameAgent
from .listener import VoiceListener
from .tts import TextToSpeech, TTSProvider

if TYPE_CHECKING:
    from music_player import MusicPlayerManager


# Volume level when ducking for TTS playback
DUCK_VOLUME = 0.2
NORMAL_VOLUME = 1.0

# Wake phrases for triggering bot response (case-insensitive)
WAKE_PHRASES = ["hey bot", "hola bot", "saludos bot"]


@dataclass
class VoiceConversationState:
    """State for an active voice conversation."""

    guild_id: int
    listener: VoiceListener
    tts: TextToSpeech
    is_processing: bool = False
    is_speaking: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class VoiceConversation:
    """
    Orchestrates voice conversations.

    Handles the flow: Listen → Understand → Respond
    """

    def __init__(
        self,
        game_agent: GameAgent,
        player_manager: "MusicPlayerManager",
        tts_provider: TTSProvider | None = None,
    ):
        """
        Initialize voice conversation manager.

        Args:
            game_agent: The game agent for processing queries
            player_manager: Music player manager for audio playback
            tts_provider: Optional TTS provider for speech output
        """
        self.game_agent = game_agent
        self.player_manager = player_manager
        self.tts_provider = tts_provider
        self.active_conversations: dict[int, VoiceConversationState] = {}

    @property
    def tts_available(self) -> bool:
        """Check if TTS is available."""
        return self.tts_provider is not None

    async def start(self, guild_id: int, voice_client: voice_recv.VoiceRecvClient) -> bool:
        """
        Start voice conversation for a guild.

        Args:
            guild_id: Discord guild ID
            voice_client: Voice client to use

        Returns:
            True if started successfully
        """
        if guild_id in self.active_conversations:
            return False  # Already active

        # Create TTS instance (may not have a provider)
        tts = TextToSpeech(provider=self.tts_provider)

        # Create callback for when utterance is detected
        async def on_utterance(user_id: int, user_name: str, wav_bytes: bytes):
            await self._handle_utterance(guild_id, user_id, user_name, wav_bytes)

        # Create and start listener
        listener = VoiceListener(voice_client, on_utterance)
        await listener.start()

        # Store state
        self.active_conversations[guild_id] = VoiceConversationState(
            guild_id=guild_id,
            listener=listener,
            tts=tts,
        )

        return True

    def stop(self, guild_id: int) -> bool:
        """
        Stop voice conversation for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            True if stopped successfully
        """
        state = self.active_conversations.pop(guild_id, None)
        if not state:
            return False

        state.listener.stop()
        return True

    def is_active(self, guild_id: int) -> bool:
        """Check if voice conversation is active for guild."""
        return guild_id in self.active_conversations

    def _check_wake_phrase(self, text: str) -> tuple[bool, str]:
        """
        Check if text starts with a wake phrase.

        Args:
            text: The transcribed text to check

        Returns:
            Tuple of (wake_phrase_detected, text_with_phrase_stripped)
        """
        text_lower = text.lower().strip()
        for phrase in WAKE_PHRASES:
            if text_lower.startswith(phrase):
                # Strip the wake phrase and any following punctuation/space
                remaining = text[len(phrase):].lstrip(" ,.:!?")
                return True, remaining
        return False, text

    async def _handle_utterance(
        self, guild_id: int, user_id: int, user_name: str, wav_bytes: bytes
    ):
        """Handle a detected utterance from a user."""
        state = self.active_conversations.get(guild_id)
        if not state:
            return

        # Use lock to prevent race conditions
        async with state._lock:
            # Skip if already processing (double-check inside lock)
            if state.is_processing:
                return

            state.is_processing = True
            try:
                print(f"[Voice] Processing utterance from {user_name} ({len(wav_bytes)} bytes)")

                # First, transcribe the audio to check for wake phrase
                transcription = await self.game_agent.transcribe_audio(
                    audio_data=wav_bytes,
                    audio_format="wav",
                )

                if not transcription.strip():
                    print("[Voice] Empty transcription")
                    return

                print(f"[Voice] Transcription: {transcription}")

                # Check for wake phrase
                wake_detected, question = self._check_wake_phrase(transcription)
                if not wake_detected:
                    print("[Voice] No wake phrase detected, ignoring")
                    return

                print(f"[Voice] Wake phrase detected! Question: {question}")

                if not question.strip():
                    print("[Voice] No question after wake phrase")
                    return

                # Get response from game agent using the stripped question
                response_text = await self.game_agent.ask_simple(
                    guild_id=guild_id,
                    user_id=user_id,
                    question=question,
                )

                if not response_text.strip():
                    print("[Voice] Empty response from agent")
                    return

                print(f"[Voice] Agent response: {response_text[:100]}...")

                # Generate and play speech if TTS is available
                if state.tts.is_available:
                    # Clean text for speech (remove markdown formatting)
                    clean_text = await self.game_agent.clean_text_for_speech(response_text)
                    print(f"[Voice] Cleaned text: {clean_text[:100]}...")

                    # Run blocking TTS in executor to avoid blocking event loop
                    loop = asyncio.get_running_loop()
                    audio_path = await loop.run_in_executor(
                        None,
                        lambda: state.tts.generate_speech(clean_text)
                    )
                    print(f"[Voice] Generated speech: {audio_path}")
                    await self._play_response(guild_id, audio_path, state)
                else:
                    print(f"[Voice] TTS not available. Response: {response_text}")

            except Exception as e:
                print(f"[Voice] Error handling utterance: {e}")
                traceback.print_exc()
            finally:
                state.is_processing = False

    async def _play_response(self, guild_id: int, audio_path: Path, state: VoiceConversationState | None = None):
        """Play TTS response with music ducking."""
        if state:
            state.is_speaking = True

        # Store previous volume to restore later
        previous_volume = self.player_manager.get_volume(guild_id)
        was_playing = self.player_manager.is_playing(guild_id)

        try:
            # Duck music volume if playing
            if was_playing:
                self.player_manager.set_volume(guild_id, DUCK_VOLUME)

            # Play TTS audio and wait for completion
            await self.player_manager.play_audio_file(guild_id, str(audio_path))

        finally:
            # Restore previous volume
            if was_playing:
                self.player_manager.set_volume(guild_id, previous_volume)
            if state:
                state.is_speaking = False

            # Clean up audio file
            try:
                audio_path.unlink()
            except OSError:
                pass

    async def speak_text(self, guild_id: int, text: str, language: str | None = None) -> bool:
        """
        Speak text directly (for /speak command).

        Args:
            guild_id: Discord guild ID
            text: Text to speak
            language: Optional language code for TTS

        Returns:
            True if speech started successfully

        Raises:
            NotImplementedError: If TTS provider not configured
        """
        if not self.tts_available:
            raise NotImplementedError("TTS provider not configured")

        # Check if bot is in voice channel
        player = self.player_manager.get_player(guild_id)
        if not player.voice_client or not player.voice_client.is_connected():
            return False

        # Clean text for speech (remove markdown formatting)
        clean_text = await self.game_agent.clean_text_for_speech(text)

        # Run blocking TTS in executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        audio_path = await loop.run_in_executor(
            None,
            lambda: self.tts_provider.generate_speech(clean_text, language=language)
        )

        # Get state if available (for tracking speaking status and locking)
        state = self.active_conversations.get(guild_id)

        # Play the response (use lock if state exists to prevent volume race conditions)
        if state:
            async with state._lock:
                await self._play_response(guild_id, audio_path, state)
        else:
            await self._play_response(guild_id, audio_path, state)
        return True
