from typing import Dict
import json
from pathlib import Path

from google.genai import types
from google.genai import Client


class VoicePreferencesManager:

    # All 30 voices from Google's official documentation
    AVAILABLE_VOICES = {
        "zephyr":         {"name": "Zephyr",         "description": "Bright"},
        "puck":           {"name": "Puck",           "description": "Upbeat"},
        "charon":         {"name": "Charon",         "description": "Informative"},
        "kore":           {"name": "Kore",           "description": "Firm"},
        "fenrir":         {"name": "Fenrir",         "description": "Excitable"},
        "leda":           {"name": "Leda",           "description": "Youthful"},
        "orus":           {"name": "Orus",           "description": "Firm"},
        "aoede":          {"name": "Aoede",          "description": "Breezy"},
        "callirrhoe":     {"name": "Callirrhoe",     "description": "Easy-going"},
        "autonoe":        {"name": "Autonoe",        "description": "Bright"},
        "enceladus":      {"name": "Enceladus",      "description": "Breathy"},
        "iapetus":        {"name": "Iapetus",        "description": "Clear"},
        "umbriel":        {"name": "Umbriel",        "description": "Easy-going"},
        "algieba":        {"name": "Algieba",        "description": "Smooth"},
        "despina":        {"name": "Despina",        "description": "Smooth"},
        "erinome":        {"name": "Erinome",        "description": "Clear"},
        "algenib":        {"name": "Algenib",        "description": "Gravelly"},
        "rasalgethi":     {"name": "Rasalgethi",     "description": "Informative"},
        "laomedeia":      {"name": "Laomedeia",      "description": "Upbeat"},
        "achernar":       {"name": "Achernar",       "description": "Soft"},
        "alnilam":        {"name": "Alnilam",        "description": "Firm"},
        "schedar":        {"name": "Schedar",        "description": "Even"},
        "gacrux":         {"name": "Gacrux",         "description": "Mature"},
        "pulcherrima":    {"name": "Pulcherrima",    "description": "Forward"},
        "achird":         {"name": "Achird",         "description": "Friendly"},
        "zubenelgenubi":  {"name": "Zubenelgenubi",  "description": "Casual"},
        "vindemiatrix":   {"name": "Vindemiatrix",   "description": "Gentle"},
        "sadachbia":      {"name": "Sadachbia",      "description": "Lively"},
        "sadaltager":     {"name": "Sadaltager",     "description": "Knowledgeable"},
        "sulafat":        {"name": "Sulafat",        "description": "Warm"},
    }

    def __init__(self, api_key: str, prefs_file: str = "data/voice_preferences.json"):
        self.client = Client(api_key=api_key)
        self.prefs_file = Path(prefs_file)
        self.prefs_file.parent.mkdir(parents=True, exist_ok=True)
        self.preferences = self._load_preferences()
        self.available_voices = self.AVAILABLE_VOICES

    def set_voice(self, voice_key: str) -> Dict[str, str]:
        voice_key = voice_key.lower()
        if voice_key not in self.available_voices:
            return {
                "status": "error",
                "message": f"Invalid voice. Available: {', '.join(self.available_voices.keys())}",
            }
        self.preferences["selected_voice"] = voice_key
        self._save_preferences()
        voice_info = self.available_voices[voice_key]
        return {
            "status": "success",
            "voice": voice_key,
            "name": voice_info["name"],
            "description": voice_info["description"],
        }

    def get_current_voice(self) -> str:
        return self.preferences.get("selected_voice") or "aoede"

    def get_speech_config(self) -> types.SpeechConfig:
        voice_key = self.get_current_voice()
        voice_info = self.available_voices[voice_key]
        return types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_info["name"]
                )
            )
        )

    def _load_preferences(self) -> dict:
        if self.prefs_file.exists():
            with open(self.prefs_file, "r") as f:
                return json.load(f)
        # Create default preferences file
        default = {"selected_voice": "aoede"}
        with open(self.prefs_file, "w") as f:
            json.dump(default, f, indent=2)
        return default

    def _save_preferences(self) -> None:
        with open(self.prefs_file, "w") as f:
            json.dump(self.preferences, f, indent=2)