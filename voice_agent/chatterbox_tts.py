"""Chatterbox TTS provider using MCP server."""

import asyncio
import os
import uuid
from pathlib import Path

from .tts import TTSProvider


class TTSConnectionError(Exception):
    """Raised when unable to connect to the TTS MCP server."""

    pass


class TTSGenerationError(Exception):
    """Raised when TTS generation fails."""

    pass


DEFAULT_TTS_MCP_URL = "http://127.0.0.1:8080/mcp"
DEFAULT_TTS_LANGUAGE = "es"


def get_tts_config() -> tuple[str, str]:
    """
    Get TTS configuration from environment variables.

    Returns:
        Tuple of (mcp_url, default_language)
    """
    mcp_url = os.getenv("TTS_MCP_URL", DEFAULT_TTS_MCP_URL)
    language = os.getenv("TTS_DEFAULT_LANGUAGE", DEFAULT_TTS_LANGUAGE)
    return mcp_url, language


class ChatterboxTTSProvider(TTSProvider):
    """TTS provider that connects to Chatterbox MCP server."""

    def __init__(
        self,
        mcp_url: str = DEFAULT_TTS_MCP_URL,
        default_language: str = DEFAULT_TTS_LANGUAGE,
        timeout: float = 60.0,
        output_dir: str | Path = "data/voice/tts",
    ):
        """
        Initialize Chatterbox TTS provider.

        Args:
            mcp_url: URL of the Chatterbox MCP server
            default_language: Default language code (e.g., "es", "en")
            timeout: Timeout for MCP calls in seconds
            output_dir: Directory to save generated audio files
        """
        self.mcp_url = mcp_url
        self.default_language = default_language
        self.timeout = timeout
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _generate_speech_async(self, text: str, language: str | None = None) -> str:
        """
        Generate speech using MCP server.

        Args:
            text: Text to convert to speech
            language: Language code (uses default if not specified)

        Returns:
            Path to the generated audio file

        Raises:
            TTSConnectionError: If unable to connect to MCP server
            TTSGenerationError: If speech generation fails
        """
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        lang = language or self.default_language

        try:
            async with streamablehttp_client(self.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    result = await asyncio.wait_for(
                        session.call_tool(
                            "generate_audio",
                            {"text": text, "language": lang},
                        ),
                        timeout=self.timeout,
                    )

                    # Extract file path from structuredContent (preferred)
                    file_path = None
                    if hasattr(result, "structuredContent") and result.structuredContent:
                        file_path = result.structuredContent.get("file_path")

                    # Fallback: try to extract from text content
                    if not file_path and result.content and len(result.content) > 0:
                        content = result.content[0]
                        if hasattr(content, "text"):
                            # The text contains a message like "Audio generated... FFmpegPCMAudio('/path')"
                            import re
                            match = re.search(r"FFmpegPCMAudio\('([^']+)'\)", content.text)
                            if match:
                                file_path = match.group(1)

                    if not file_path:
                        raise TTSGenerationError(
                            f"Could not extract file path from TTS result: {result}"
                        )

                    # Validate that the file exists
                    if not Path(file_path).exists():
                        raise TTSGenerationError(
                            f"TTS generated file not found: {file_path}"
                        )

                    return file_path

        except asyncio.TimeoutError:
            raise TTSGenerationError(f"TTS generation timed out after {self.timeout}s")
        except ConnectionRefusedError:
            raise TTSConnectionError(
                f"Cannot connect to TTS server at {self.mcp_url}. "
                "Make sure Chatterbox TTS is running."
            )
        except OSError as e:
            if "Connect call failed" in str(e) or "Connection refused" in str(e):
                raise TTSConnectionError(
                    f"Cannot connect to TTS server at {self.mcp_url}. "
                    "Make sure Chatterbox TTS is running."
                )
            raise TTSGenerationError(f"TTS generation failed: {e}")
        except Exception as e:
            error_str = str(e)
            if "Connection refused" in error_str or "connect" in error_str.lower():
                raise TTSConnectionError(
                    f"Cannot connect to TTS server at {self.mcp_url}. "
                    "Make sure Chatterbox TTS is running."
                )
            raise TTSGenerationError(f"TTS generation failed: {e}")

    async def generate_speech_async(
        self, text: str, filename: str | None = None, *, language: str | None = None
    ) -> Path:
        """
        Async version: Generate speech from text and save to file.

        Args:
            text: Text to convert to speech
            filename: Optional filename (without extension) - ignored, MCP server handles this
            language: Language code (uses default if not specified)

        Returns:
            Path to the generated audio file
        """
        result_path = await self._generate_speech_async(text, language)
        return Path(result_path)

    def generate_speech(
        self, text: str, filename: str | None = None, *, language: str | None = None
    ) -> Path:
        """
        Sync version: Generate speech from text and save to file.

        Args:
            text: Text to convert to speech
            filename: Optional filename (without extension) - ignored, MCP server handles this
            language: Language code (uses default if not specified)

        Returns:
            Path to the generated audio file
        """
        # Run async method in event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're in an async context, need to use run_coroutine_threadsafe
            # or we can create a new thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, self._generate_speech_async(text, language)
                )
                result_path = future.result()
        else:
            result_path = asyncio.run(self._generate_speech_async(text, language))

        return Path(result_path)

    def generate_speech_bytes(self, text: str, *, language: str | None = None) -> bytes:
        """
        Generate speech from text and return as bytes.

        Args:
            text: Text to convert to speech
            language: Language code (uses default if not specified)

        Returns:
            Audio data as bytes
        """
        audio_path = self.generate_speech(text, language=language)
        with open(audio_path, "rb") as f:
            return f.read()
