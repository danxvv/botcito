"""Local Qwen3-TTS provider with JSON configuration."""

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from .tts import TTSProvider

DEFAULT_QWEN_SETTINGS_PATH = "data/tts_settings.json"
DEFAULT_QWEN_OUTPUT_DIR = "data/voice/tts"
DEFAULT_CUSTOM_MODEL = "Qwen/Qwen3-TTS-0.6B"
DEFAULT_BASE_MODEL = "Qwen/Qwen3-TTS-0.6B-Base"

DEFAULT_SETTINGS: dict[str, Any] = {
    "mode": "custom_voice",
    "custom_voice": {
        "model": DEFAULT_CUSTOM_MODEL,
        "speaker": "Cherry",
        "language": "Auto",
    },
    "base_clone": {
        "model": DEFAULT_BASE_MODEL,
        "reference_audio_path": "data/voice/reference.wav",
        "reference_text": "Your reference transcript here",
        "language": "Auto",
    },
    "generation": {
        "cfg_strength": 0.5,
        "seed": 0,
    },
}

ISO_LANGUAGE_MAP = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

SUPPORTED_LANGUAGE_NAMES = {
    "Auto",
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
}


class QwenTTSConfigurationError(Exception):
    """Raised when Qwen TTS JSON configuration is invalid."""


class QwenTTSDependencyError(Exception):
    """Raised when required Qwen TTS dependencies are missing."""


class QwenTTSRuntimeError(Exception):
    """Raised when Qwen TTS inference fails."""


def _repo_root() -> Path:
    """Resolve repository root from current file location."""
    return Path(__file__).resolve().parent.parent


def get_qwen_tts_settings_path() -> Path:
    """Get Qwen TTS settings path from env or default location."""
    raw_path = os.getenv("TTS_SETTINGS_PATH", DEFAULT_QWEN_SETTINGS_PATH).strip()
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = _repo_root() / path
    return path


def _normalize_language(value: str | None) -> str:
    """Normalize ISO codes or language names to Qwen-compatible names."""
    if not value:
        return "Auto"

    text = value.strip()
    if not text:
        return "Auto"

    lowered = text.lower()
    if lowered in ISO_LANGUAGE_MAP:
        return ISO_LANGUAGE_MAP[lowered]

    for name in SUPPORTED_LANGUAGE_NAMES:
        if lowered == name.lower():
            return name

    return "Auto"


class Qwen3TTSProvider(TTSProvider):
    """TTS provider that runs local Qwen3-TTS models."""

    def __init__(
        self,
        settings_path: str | Path | None = None,
        output_dir: str | Path = DEFAULT_QWEN_OUTPUT_DIR,
    ):
        self.settings_path = Path(settings_path) if settings_path else get_qwen_tts_settings_path()
        if not self.settings_path.is_absolute():
            self.settings_path = _repo_root() / self.settings_path

        self.output_dir = Path(output_dir)
        if not self.output_dir.is_absolute():
            self.output_dir = _repo_root() / self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._model = None
        self._model_name: str | None = None
        self._model_lock = threading.Lock()

    def _import_runtime(self):
        """Import optional dependencies at runtime."""
        try:
            import torch
        except ImportError as e:
            raise QwenTTSDependencyError(
                "Missing dependency 'torch'. Run `uv sync` to install dependencies."
            ) from e

        try:
            import soundfile as sf
        except ImportError as e:
            raise QwenTTSDependencyError(
                "Missing dependency 'soundfile'. Run `uv sync` to install dependencies."
            ) from e

        try:
            from qwen_tts import Qwen3TTSModel
        except ImportError as e:
            raise QwenTTSDependencyError(
                "Missing dependency 'qwen-tts'. Run `uv sync` to install dependencies."
            ) from e

        return torch, sf, Qwen3TTSModel

    def _ensure_settings_file(self) -> None:
        """Create default settings file if it does not exist."""
        if self.settings_path.exists():
            return

        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
            f.write("\n")

    def _load_settings(self) -> dict[str, Any]:
        """Load and validate JSON settings."""
        self._ensure_settings_file()

        try:
            with self.settings_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise QwenTTSConfigurationError(
                f"Invalid JSON in settings file: {self.settings_path}"
            ) from e
        except OSError as e:
            raise QwenTTSConfigurationError(
                f"Unable to read settings file: {self.settings_path}"
            ) from e

        if not isinstance(data, dict):
            raise QwenTTSConfigurationError("Qwen TTS settings must be a JSON object.")

        mode = data.get("mode", "custom_voice")
        if mode not in {"custom_voice", "base_clone"}:
            raise QwenTTSConfigurationError(
                "Invalid `mode` in Qwen TTS settings. Use `custom_voice` or `base_clone`."
            )

        generation = data.get("generation", {})
        if generation and not isinstance(generation, dict):
            raise QwenTTSConfigurationError("`generation` must be an object if provided.")

        if "cfg_strength" in generation and not isinstance(generation["cfg_strength"], (int, float)):
            raise QwenTTSConfigurationError("`generation.cfg_strength` must be a number.")
        if "seed" in generation and not isinstance(generation["seed"], int):
            raise QwenTTSConfigurationError("`generation.seed` must be an integer.")

        mode_config = data.get(mode, {})
        if not isinstance(mode_config, dict):
            raise QwenTTSConfigurationError(f"`{mode}` settings must be an object.")

        if mode == "custom_voice":
            speaker = mode_config.get("speaker")
            if not isinstance(speaker, str) or not speaker.strip():
                raise QwenTTSConfigurationError("`custom_voice.speaker` is required and must be text.")

        if mode == "base_clone":
            reference_text = mode_config.get("reference_text")
            if not isinstance(reference_text, str) or not reference_text.strip():
                raise QwenTTSConfigurationError(
                    "`base_clone.reference_text` is required and must be non-empty text."
                )

            reference_audio = mode_config.get("reference_audio_path")
            if not isinstance(reference_audio, str) or not reference_audio.strip():
                raise QwenTTSConfigurationError(
                    "`base_clone.reference_audio_path` is required and must be a file path."
                )

            resolved_audio = self._resolve_audio_path(reference_audio)
            if not resolved_audio.exists():
                raise QwenTTSConfigurationError(
                    f"Reference audio file not found: {resolved_audio}"
                )

        return data

    def _resolve_audio_path(self, value: str) -> Path:
        """Resolve reference audio paths relative to repository root."""
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return _repo_root() / path

    def _generation_kwargs(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Extract generation kwargs from config."""
        generation = settings.get("generation", {})
        kwargs: dict[str, Any] = {}

        if "cfg_strength" in generation:
            kwargs["cfg_strength"] = float(generation["cfg_strength"])
        if "seed" in generation:
            kwargs["seed"] = int(generation["seed"])
        return kwargs

    def _ensure_model(self, model_name: str):
        """Load Qwen model lazily and switch if model config changes."""
        with self._model_lock:
            if self._model is not None and self._model_name == model_name:
                return self._model

            torch, _, Qwen3TTSModel = self._import_runtime()
            if not torch.cuda.is_available():
                raise QwenTTSRuntimeError(
                    "CUDA is required for Qwen TTS, but no CUDA device is available."
                )

            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

            try:
                model = Qwen3TTSModel.from_pretrained(
                    model_name,
                    device_map="cuda:0",
                    dtype=dtype,
                    attn_implementation="flash_attention_2",
                )
            except Exception:
                try:
                    model = Qwen3TTSModel.from_pretrained(
                        model_name,
                        device_map="cuda:0",
                        dtype=dtype,
                    )
                except Exception as e:
                    raise QwenTTSRuntimeError(
                        f"Failed to load Qwen TTS model `{model_name}`: {e}"
                    ) from e

            self._model = model
            self._model_name = model_name
            return model

    def _build_output_path(self, filename: str | None) -> Path:
        """Build a safe output filename in provider output dir."""
        if filename:
            safe_name = Path(filename).name
            if not safe_name.lower().endswith(".wav"):
                safe_name = f"{safe_name}.wav"
        else:
            safe_name = f"{uuid.uuid4().hex}.wav"
        return self.output_dir / safe_name

    def generate_speech(
        self, text: str, filename: str | None = None, *, language: str | None = None
    ) -> Path:
        """Generate speech from text using local Qwen models."""
        if not text.strip():
            raise ValueError("Text cannot be empty")

        settings = self._load_settings()
        mode = settings.get("mode", "custom_voice")
        mode_config = settings.get(mode, {})
        generation_kwargs = self._generation_kwargs(settings)

        model_name = mode_config.get(
            "model",
            DEFAULT_CUSTOM_MODEL if mode == "custom_voice" else DEFAULT_BASE_MODEL,
        )
        if not isinstance(model_name, str) or not model_name.strip():
            raise QwenTTSConfigurationError(f"Invalid model value for `{mode}`.")

        normalized_language = _normalize_language(language or mode_config.get("language"))
        model = self._ensure_model(model_name)

        try:
            if mode == "custom_voice":
                speaker = mode_config["speaker"].strip()
                wavs, sample_rate = model.generate_custom_voice(
                    text=text,
                    language=normalized_language,
                    speaker=speaker,
                    **generation_kwargs,
                )
            elif mode == "base_clone":
                reference_audio = self._resolve_audio_path(mode_config["reference_audio_path"])
                reference_text = mode_config["reference_text"].strip()
                wavs, sample_rate = model.generate_voice_clone(
                    text=text,
                    language=normalized_language,
                    ref_audio=str(reference_audio),
                    ref_text=reference_text,
                    **generation_kwargs,
                )
            else:
                raise QwenTTSConfigurationError(
                    "Invalid `mode` in Qwen TTS settings. Use `custom_voice` or `base_clone`."
                )
        except QwenTTSConfigurationError:
            raise
        except Exception as e:
            raise QwenTTSRuntimeError(f"Qwen TTS generation failed: {e}") from e

        if not wavs:
            raise QwenTTSRuntimeError("Qwen TTS did not return any audio samples.")

        output_path = self._build_output_path(filename)
        _, sf, _ = self._import_runtime()
        try:
            sf.write(str(output_path), wavs[0], sample_rate)
        except Exception as e:
            raise QwenTTSRuntimeError(f"Failed to write generated audio file: {e}") from e

        return output_path

    def generate_speech_bytes(self, text: str, *, language: str | None = None) -> bytes:
        """Generate speech and return audio bytes."""
        audio_path = self.generate_speech(text, language=language)
        try:
            with audio_path.open("rb") as f:
                return f.read()
        except OSError as e:
            raise QwenTTSRuntimeError(f"Failed to read generated audio file: {e}") from e
