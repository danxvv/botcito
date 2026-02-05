"""Voice agent package for voice conversations with the bot."""

from .tts import TextToSpeech, TTSProvider
from .chatterbox_tts import (
    ChatterboxTTSProvider,
    TTSConnectionError,
    TTSGenerationError,
    get_tts_config,
)
from .qwen3_tts import (
    Qwen3TTSProvider,
    QwenTTSConfigurationError,
    QwenTTSDependencyError,
    QwenTTSRuntimeError,
    get_qwen_tts_settings_path,
)
from .listener import VoiceListener
from .conversation import VoiceConversation

__all__ = [
    "TextToSpeech",
    "TTSProvider",
    "ChatterboxTTSProvider",
    "TTSConnectionError",
    "TTSGenerationError",
    "get_tts_config",
    "Qwen3TTSProvider",
    "QwenTTSConfigurationError",
    "QwenTTSDependencyError",
    "QwenTTSRuntimeError",
    "get_qwen_tts_settings_path",
    "VoiceListener",
    "VoiceConversation",
]
