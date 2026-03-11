import os
import wave
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Import the manager from the same directory
from backend.agent.voice_config import VoicePreferencesManager

# Setup paths
BASE_DIR = Path(__file__).parent.parent.parent
PREFS_FILE = BASE_DIR / "backend" / "agent" / "data" / "voice_preferences.json"

# Load environment variables from project root .env
load_dotenv(BASE_DIR / ".env")
api_key = os.getenv("GEMINI_API_KEY")


def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    """Saves PCM data to a wave file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def speak_current_preference():
    print("--- Reading Voice from Preferences ---")

    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    # 1. Initialize the Manager (loads from voice_preferences.json automatically)
    manager = VoicePreferencesManager(api_key=api_key, prefs_file=str(PREFS_FILE))

    # 2. Get the current voice key from JSON
    current_voice_key = manager.get_current_voice()
    voice_info = manager.available_voices.get(current_voice_key)

    if not voice_info:
        print(f"Warning: Voice '{current_voice_key}' not found. Falling back to Aoede.")
        current_voice_key = "aoede"
        voice_info = manager.available_voices[current_voice_key]

    voice_name = voice_info["name"]
    description = voice_info["description"]

    print(f"Current Preference in JSON: {current_voice_key}")
    print(f"Using Voice: {voice_name} ({description})")
    print(f"Preferences file: {PREFS_FILE}")

    # 3. Initialize GenAI Client
    client = genai.Client(api_key=api_key)

    prompt = (
        f"Hello! I am currently speaking with the {voice_name} voice, "
        f"which is described as {description}. How do I sound?"
    )

    print("Generating sample audio...")

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents="How did i do?",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                ),
            ),
        )

        # 4. Save the audio
        if response.candidates and response.candidates[0].content.parts:
            audio_part = next(
                (p for p in response.candidates[0].content.parts if p.inline_data), None
            )
            if audio_part:
                data = audio_part.inline_data.data
                file_name = "out.wav"
                wave_file(file_name, data)
                print(f"--- SUCCESS ---")
                print(f"Saved to: {os.path.abspath(file_name)}")
                print(f"To test a different voice, edit 'selected_voice' in:")
                print(f"  {PREFS_FILE}")
                print(f"Available voices: {', '.join(manager.available_voices.keys())}")
            else:
                print("Error: No audio data in response.")
        else:
            print("Error: Model returned no content.")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    speak_current_preference()