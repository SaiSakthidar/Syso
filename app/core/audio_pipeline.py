import pyaudio
import threading
import queue
import time
import os
import pygame
import tempfile
from typing import Callable, Optional

from shared.schemas import ClientAudio, ClientAudioStream


# PCM playback constants (Gemini Live API returns 24kHz mono 16-bit PCM)
PLAYBACK_RATE = 24000
PLAYBACK_CHANNELS = 1
PLAYBACK_FORMAT = pyaudio.paInt16


class AudioPipeline:
    def __init__(
        self,
        on_log: Callable[[str, str], None],
        on_wake_word: Callable[[bool], None],
        on_audio_payload: Callable,  # accepts ClientAudio or ClientAudioStream
    ):
        self.on_log = on_log
        self.on_wake_word = on_wake_word
        self.on_audio_payload = on_audio_payload

        self.running = False

        # PvPorcupine Setup
        try:
            import pvporcupine

            access_key = os.getenv("PICOVOICE_ACCESS_KEY")
            if not access_key:
                self.on_log("ERROR", "PICOVOICE_ACCESS_KEY not found in environment")
                self.porcupine = None
            else:
                self.porcupine = pvporcupine.create(
                    access_key=access_key,
                    keywords=["jarvis"],
                )
                self.on_log("INFO", "Loaded pvporcupine wake word: 'jarvis'")
        except Exception as e:
            self.on_log("ERROR", f"Failed to initialize pvporcupine: {e}")
            self.porcupine = None

        # PyAudio Setup
        self.pa = pyaudio.PyAudio()

        # Threads
        self.listen_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None

        # State
        self.is_streaming = False  # True while user is speaking (live streaming mode)

        # Playback queue — holds raw PCM bytes from Gemini Live API
        self.playback_queue: queue.Queue[bytes] = queue.Queue()
        self.is_playing = False
        self._playback_stream: Optional[pyaudio.Stream] = None

    def start(self):
        self.running = True
        if getattr(self, "porcupine", None):
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

        self.on_log("INFO", "Audio Pipeline started (Live streaming mode).")

    def stop(self):
        self.running = False
        if getattr(self, "porcupine", None):
            self.porcupine.delete()
        if self._playback_stream:
            try:
                self._playback_stream.stop_stream()
                self._playback_stream.close()
            except Exception:
                pass
        self.pa.terminate()

    def interrupt_playback(self):
        self.is_playing = False
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except queue.Empty:
                break
        # Don't stop the playback stream — just drain the queue.
        # Stopping it causes "Stream closed" errors on subsequent writes.
        self.on_log("SYSTEM", "Audio playback interrupted by user.")

    def queue_playback(self, audio_bytes: bytes):
        """Queue raw PCM audio bytes for playback."""
        self.playback_queue.put(audio_bytes)

    def _listen_loop(self):
        """Mic capture loop: wake word detection → real-time PCM streaming."""
        audio_stream = None
        try:
            audio_stream = self.pa.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length,
            )

            self.on_log("INFO", "Microphone listening for wake word...")

            import math
            import struct

            bg_noise_rms = 500.0
            silence_threshold_multiplier = 1.6
            silence_frames = 0

            # 3 seconds of silence ends streaming
            max_silence_duration = int(
                3.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )
            # 30 seconds max per streaming session
            max_streaming_frames = int(
                30.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )
            frames_streamed = 0

            while self.running:
                try:
                    pcm = audio_stream.read(
                        self.porcupine.frame_length, exception_on_overflow=False
                    )
                    pcm_unpacked = struct.unpack_from(
                        "h" * self.porcupine.frame_length, pcm
                    )

                    mean = sum(pcm_unpacked) / len(pcm_unpacked)
                    rms = math.sqrt(
                        sum((x - mean) ** 2 for x in pcm_unpacked) / len(pcm_unpacked)
                    )

                    if not self.is_streaming:
                        # Adapt background noise
                        bg_noise_rms = 0.9 * bg_noise_rms + 0.1 * rms

                        result = self.porcupine.process(pcm_unpacked)
                        if result >= 0:
                            self.on_log(
                                "SYSTEM",
                                f"Wake word 'jarvis' detected! Starting live stream. (Ambient RMS: {bg_noise_rms:.0f})",
                            )
                            self.on_wake_word(True)
                            self.interrupt_playback()
                            self.is_streaming = True
                            silence_frames = 0
                            frames_streamed = 0
                    else:
                        # ---- STREAMING MODE: send each PCM chunk immediately ----
                        payload = ClientAudioStream(audio_bytes=pcm)
                        self.on_audio_payload(payload)
                        frames_streamed += 1

                        # VAD silence detection
                        threshold = max(800.0, bg_noise_rms * silence_threshold_multiplier)

                        if rms < threshold:
                            silence_frames += 1
                        else:
                            silence_frames = 0

                        if (
                            silence_frames >= max_silence_duration
                            or frames_streamed >= max_streaming_frames
                        ):
                            reason = (
                                "Silence detected"
                                if silence_frames >= max_silence_duration
                                else "Max streaming length (30s) reached"
                            )
                            self.on_log("SYSTEM", f"{reason}, ending live stream.")
                            self.is_streaming = False
                            self.on_wake_word(False)
                            silence_frames = 0
                            frames_streamed = 0

                except Exception as e:
                    self.on_log("ERROR", f"Audio listen error: {e}")
                    time.sleep(1)

        except Exception as e:
            self.on_log("ERROR", f"Audio stream setup error: {e}")
        finally:
            if audio_stream:
                audio_stream.close()

    def _playback_loop(self):
        """Play raw PCM audio chunks from the Live API as they arrive."""
        # Open a persistent output stream for low-latency PCM playback
        try:
            self._playback_stream = self.pa.open(
                format=PLAYBACK_FORMAT,
                channels=PLAYBACK_CHANNELS,
                rate=PLAYBACK_RATE,
                output=True,
                frames_per_buffer=4096,
            )
        except Exception as e:
            self.on_log("ERROR", f"Failed to open playback stream: {e}")
            # Fallback: try pygame for mp3-style playback
            self._playback_stream = None

        while self.running:
            try:
                audio_bytes = self.playback_queue.get(timeout=1.0)

                if not self.is_playing:
                    self.is_playing = True

                if self._playback_stream:
                    # Direct PCM write — lowest latency
                    try:
                        if not self._playback_stream.is_active():
                            self._playback_stream.start_stream()
                        self._playback_stream.write(audio_bytes)
                    except OSError:
                        # Stream was closed — reopen it
                        try:
                            self._playback_stream = self.pa.open(
                                format=PLAYBACK_FORMAT,
                                channels=PLAYBACK_CHANNELS,
                                rate=PLAYBACK_RATE,
                                output=True,
                                frames_per_buffer=4096,
                            )
                            self._playback_stream.write(audio_bytes)
                        except Exception as e2:
                            self.on_log("ERROR", f"PCM playback reopen error: {e2}")
                    except Exception as e:
                        self.on_log("ERROR", f"PCM playback write error: {e}")
                else:
                    # Fallback: write to temp file and play with pygame
                    self._play_with_pygame(audio_bytes)

            except queue.Empty:
                if self.playback_queue.empty() and self.is_playing:
                    self.is_playing = False
            except Exception as e:
                self.on_log("ERROR", f"Playback thread error: {e}")

    def _play_with_pygame(self, audio_bytes: bytes):
        """Fallback playback via pygame for non-PCM audio (mp3 etc)."""
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_name = tmp_file.name
        try:
            pygame.mixer.music.load(tmp_name)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and self.is_playing:
                time.sleep(0.1)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception as e:
            self.on_log("ERROR", f"Pygame playback error: {e}")
        try:
            os.remove(tmp_name)
        except Exception:
            pass
