"""
Configuration loader and persistent JSON storage for LiveSpeech Translator.
Reads and writes settings directly to config.json.

Supports bidirectional mode with per-channel settings (outgoing / incoming)
while maintaining full backwards compatibility with the original flat schema.
"""

import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent

CONFIG_PATH = ROOT_DIR / "config.json"

# Supported target languages — full list from Gemini Live Translate docs
# https://ai.google.dev/gemini-api/docs/live-api/live-translate#supported-languages
SUPPORTED_LANGUAGES = [
    {"code": "af", "name": "Afrikaans", "flag": "🇿🇦"},
    {"code": "ak", "name": "Akan", "flag": "🇬🇭"},
    {"code": "sq", "name": "Albanian", "flag": "🇦🇱"},
    {"code": "am", "name": "Amharic", "flag": "🇪🇹"},
    {"code": "ar", "name": "Arabic", "flag": "🇸🇦"},
    {"code": "hy", "name": "Armenian", "flag": "🇦🇲"},
    {"code": "az", "name": "Azerbaijani", "flag": "🇦🇿"},
    {"code": "eu", "name": "Basque", "flag": "🏴"},
    {"code": "be", "name": "Belarusian", "flag": "🇧🇾"},
    {"code": "bn", "name": "Bengali", "flag": "🇧🇩"},
    {"code": "bg", "name": "Bulgarian", "flag": "🇧🇬"},
    {"code": "my", "name": "Burmese (Myanmar)", "flag": "🇲🇲"},
    {"code": "ca", "name": "Catalan", "flag": "🏴"},
    {"code": "zh-Hans", "name": "Chinese (Simplified)", "flag": "🇨🇳"},
    {"code": "zh-Hant", "name": "Chinese (Traditional)", "flag": "🇹🇼"},
    {"code": "hr", "name": "Croatian", "flag": "🇭🇷"},
    {"code": "cs", "name": "Czech", "flag": "🇨🇿"},
    {"code": "da", "name": "Danish", "flag": "🇩🇰"},
    {"code": "nl", "name": "Dutch", "flag": "🇳🇱"},
    {"code": "en", "name": "English", "flag": "🇺🇸"},
    {"code": "et", "name": "Estonian", "flag": "🇪🇪"},
    {"code": "fil", "name": "Filipino", "flag": "🇵🇭"},
    {"code": "fi", "name": "Finnish", "flag": "🇫🇮"},
    {"code": "fr", "name": "French", "flag": "🇫🇷"},
    {"code": "gl", "name": "Galician", "flag": "🏴"},
    {"code": "ka", "name": "Georgian", "flag": "🇬🇪"},
    {"code": "de", "name": "German", "flag": "🇩🇪"},
    {"code": "el", "name": "Greek", "flag": "🇬🇷"},
    {"code": "gu", "name": "Gujarati", "flag": "🇮🇳"},
    {"code": "ha", "name": "Hausa", "flag": "🇳🇬"},
    {"code": "he", "name": "Hebrew", "flag": "🇮🇱"},
    {"code": "hi", "name": "Hindi", "flag": "🇮🇳"},
    {"code": "hu", "name": "Hungarian", "flag": "🇭🇺"},
    {"code": "is", "name": "Icelandic", "flag": "🇮🇸"},
    {"code": "id", "name": "Indonesian", "flag": "🇮🇩"},
    {"code": "it", "name": "Italian", "flag": "🇮🇹"},
    {"code": "ja", "name": "Japanese", "flag": "🇯🇵"},
    {"code": "jv", "name": "Javanese", "flag": "🇮🇩"},
    {"code": "kn", "name": "Kannada", "flag": "🇮🇳"},
    {"code": "kk", "name": "Kazakh", "flag": "🇰🇿"},
    {"code": "km", "name": "Khmer", "flag": "🇰🇭"},
    {"code": "rw", "name": "Kinyarwanda", "flag": "🇷🇼"},
    {"code": "ko", "name": "Korean", "flag": "🇰🇷"},
    {"code": "lo", "name": "Lao", "flag": "🇱🇦"},
    {"code": "lv", "name": "Latvian", "flag": "🇱🇻"},
    {"code": "lt", "name": "Lithuanian", "flag": "🇱🇹"},
    {"code": "mk", "name": "Macedonian", "flag": "🇲🇰"},
    {"code": "ms", "name": "Malay", "flag": "🇲🇾"},
    {"code": "ml", "name": "Malayalam", "flag": "🇮🇳"},
    {"code": "mr", "name": "Marathi", "flag": "🇮🇳"},
    {"code": "mn", "name": "Mongolian", "flag": "🇲🇳"},
    {"code": "ne", "name": "Nepali", "flag": "🇳🇵"},
    {"code": "no", "name": "Norwegian", "flag": "🇳🇴"},
    {"code": "fa", "name": "Persian", "flag": "🇮🇷"},
    {"code": "pl", "name": "Polish", "flag": "🇵🇱"},
    {"code": "pt-BR", "name": "Portuguese (Brazil)", "flag": "🇧🇷"},
    {"code": "pt-PT", "name": "Portuguese (Portugal)", "flag": "🇵🇹"},
    {"code": "pa", "name": "Punjabi", "flag": "🇮🇳"},
    {"code": "ro", "name": "Romanian", "flag": "🇷🇴"},
    {"code": "ru", "name": "Russian", "flag": "🇷🇺"},
    {"code": "sr", "name": "Serbian", "flag": "🇷🇸"},
    {"code": "sd", "name": "Sindhi", "flag": "🇵🇰"},
    {"code": "si", "name": "Sinhala", "flag": "🇱🇰"},
    {"code": "sk", "name": "Slovak", "flag": "🇸🇰"},
    {"code": "sl", "name": "Slovenian", "flag": "🇸🇮"},
    {"code": "es", "name": "Spanish", "flag": "🇪🇸"},
    {"code": "su", "name": "Sundanese", "flag": "🇮🇩"},
    {"code": "sw", "name": "Swahili", "flag": "🇰🇪"},
    {"code": "sv", "name": "Swedish", "flag": "🇸🇪"},
    {"code": "ta", "name": "Tamil", "flag": "🇮🇳"},
    {"code": "te", "name": "Telugu", "flag": "🇮🇳"},
    {"code": "th", "name": "Thai", "flag": "🇹🇭"},
    {"code": "tr", "name": "Turkish", "flag": "🇹🇷"},
    {"code": "uk", "name": "Ukrainian", "flag": "🇺🇦"},
    {"code": "ur", "name": "Urdu", "flag": "🇵🇰"},
    {"code": "uz", "name": "Uzbek", "flag": "🇺🇿"},
    {"code": "vi", "name": "Vietnamese", "flag": "🇻🇳"},
    {"code": "zu", "name": "Zulu", "flag": "🇿🇦"},
]

# Per-channel settings defaults
CHANNEL_DEFAULTS = {
    "enabled": True,
    "input_device_index": None,
    "output_device_index": None,
    "target_language": "en",
}

DEFAULTS = {
    "api_key": "",
    "model_id": "gemini-3.5-live-translate-preview",
    "mode": "bidirectional",  # "bidirectional" | "outgoing" | "incoming"
    "rate_in": 16000,
    "rate_out": 24000,
    "chunk_size": 1600,
    "echo_target_language": True,
    "outgoing": {
        **CHANNEL_DEFAULTS,
        "target_language": "en",
    },
    "incoming": {
        **CHANNEL_DEFAULTS,
        "target_language": "ru",
    },
}

# Keys from old flat schema that map into per-channel settings
_LEGACY_FLAT_KEYS = {"target_language", "input_device_index", "output_device_index"}


def load_config() -> dict:
    """
    Load configuration from config.json, falling back to defaults.

    Handles legacy flat-key configs by migrating them into the new
    nested outgoing/incoming structure on read.
    """
    config = _deep_copy_defaults()

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except (json.JSONDecodeError, OSError):
            stored = {}

        # Apply top-level scalar keys
        for k in ("api_key", "model_id", "mode", "rate_in", "rate_out",
                   "chunk_size", "echo_target_language"):
            if k in stored:
                config[k] = stored[k]

        # Apply nested channel configs if present
        for ch in ("outgoing", "incoming"):
            if ch in stored and isinstance(stored[ch], dict):
                for ck in CHANNEL_DEFAULTS:
                    if ck in stored[ch]:
                        config[ch][ck] = stored[ch][ck]

        # Legacy migration: if flat keys exist but no nested channels,
        # populate outgoing channel from flat keys
        if not stored.get("outgoing") and not stored.get("incoming"):
            if "target_language" in stored:
                config["outgoing"]["target_language"] = stored["target_language"]
            if "input_device_index" in stored:
                config["outgoing"]["input_device_index"] = stored["input_device_index"]
            if "output_device_index" in stored:
                config["outgoing"]["output_device_index"] = stored["output_device_index"]
            # Default to outgoing-only mode for legacy configs
            if "mode" not in stored:
                config["mode"] = "outgoing"

    # Sanity checks
    if not config.get("model_id"):
        config["model_id"] = "gemini-3.5-live-translate-preview"
    if config.get("mode") not in ("bidirectional", "outgoing", "incoming"):
        config["mode"] = "bidirectional"
    for ch in ("outgoing", "incoming"):
        if not config[ch].get("target_language"):
            config[ch]["target_language"] = "en" if ch == "outgoing" else "ru"
        if not isinstance(config[ch].get("input_device_index"), int):
            config[ch]["input_device_index"] = None
        if not isinstance(config[ch].get("output_device_index"), int):
            config[ch]["output_device_index"] = None

    return config


def save_config(config: dict) -> None:
    """Persist configuration to config.json (new nested format)."""
    to_save = {}

    # Save top-level keys
    for k in ("api_key", "model_id", "mode", "rate_in", "rate_out",
              "chunk_size", "echo_target_language"):
        if k in config:
            to_save[k] = config[k]

    # Save per-channel settings
    for ch in ("outgoing", "incoming"):
        if ch in config and isinstance(config[ch], dict):
            to_save[ch] = {ck: config[ch].get(ck, v) for ck, v in CHANNEL_DEFAULTS.items()}

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)


def get_api_key(config: dict) -> str:
    """Resolve API key directly from config."""
    return config.get("api_key", "")


def _deep_copy_defaults() -> dict:
    """Create a fresh deep copy of DEFAULTS."""
    return {
        **{k: v for k, v in DEFAULTS.items() if k not in ("outgoing", "incoming")},
        "outgoing": dict(DEFAULTS["outgoing"]),
        "incoming": dict(DEFAULTS["incoming"]),
    }
