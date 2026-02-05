"""Text-to-speech interface - ready for provider implementation."""

import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    def generate_speech(
        self, text: str, filename: str | None = None, *, language: str | None = None
    ) -> Path:
        """
        Generate speech from text and save to file.

        Args:
            text: Text to convert to speech
            filename: Optional filename (without extension)
            language: Optional language code (provider-specific)

        Returns:
            Path to the generated audio file
        """
        pass

    @abstractmethod
    def generate_speech_bytes(self, text: str, *, language: str | None = None) -> bytes:
        """
        Generate speech from text and return as bytes.

        Args:
            text: Text to convert to speech
            language: Optional language code (provider-specific)

        Returns:
            Audio data as bytes
        """
        pass


class TextToSpeech:
    """
    TTS wrapper - currently a stub ready for provider implementation.

    To implement a provider:
    1. Create a class that extends TTSProvider
    2. Pass it to TextToSpeech(provider=YourProvider())

    Example future implementation:
    ```python
    class ElevenLabsProvider(TTSProvider):
        def __init__(self, api_key: str, voice_id: str):
            self.client = ElevenLabs(api_key=api_key)
            self.voice_id = voice_id

        def generate_speech(self, text: str, filename: str | None = None) -> Path:
            # Implementation here
            pass

    tts = TextToSpeech(provider=ElevenLabsProvider(api_key="xxx", voice_id="yyy"))
    ```
    """

    def __init__(
        self,
        provider: TTSProvider | None = None,
        output_dir: str | Path = "data/voice/tts",
    ):
        """
        Initialize TTS.

        Args:
            provider: TTS provider implementation (None = stub mode)
            output_dir: Directory to save generated audio files
        """
        self.provider = provider
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_available(self) -> bool:
        """Check if TTS provider is configured."""
        return self.provider is not None

    def generate_speech(
        self, text: str, filename: str | None = None, *, language: str | None = None
    ) -> Path:
        """
        Generate speech from text and save to file.

        Args:
            text: Text to convert to speech
            filename: Optional filename (without extension)
            language: Optional language code (provider-specific)

        Returns:
            Path to the generated audio file

        Raises:
            NotImplementedError: If no provider is configured
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        if self.provider is None:
            raise NotImplementedError(
                "No TTS provider configured. "
                "Pass a TTSProvider implementation to TextToSpeech(provider=...)"
            )

        return self.provider.generate_speech(text, filename, language=language)

    def generate_speech_bytes(self, text: str, *, language: str | None = None) -> bytes:
        """
        Generate speech from text and return as bytes.

        Args:
            text: Text to convert to speech
            language: Optional language code (provider-specific)

        Returns:
            Audio data as bytes

        Raises:
            NotImplementedError: If no provider is configured
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        if self.provider is None:
            raise NotImplementedError(
                "No TTS provider configured. "
                "Pass a TTSProvider implementation to TextToSpeech(provider=...)"
            )

        return self.provider.generate_speech_bytes(text, language=language)
