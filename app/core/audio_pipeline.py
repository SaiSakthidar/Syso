import pyaudio
import threading
import queue
import time
import os
import pygame
import tempfile
from typing import Callable, Optional

from shared.schemas import ClientAudio


class AudioPipeline:
    def __init__(
        self,
        on_log: Callable[[str, str], None],
        on_wake_word: Callable[[bool], None],
        on_audio_payload: Callable[[ClientAudio], None],
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
                    keywords=["jarvis"],  # Use default 'jarvis' keyword
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
        self.is_recording = False
        self.audio_frames = []

        # Playback Jitter Buffer
        self.playback_queue = queue.Queue()
        self.is_playing = False

    def start(self):
        self.running = True
        if getattr(self, "porcupine", None):
            self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

        self.on_log("INFO", "Audio Pipeline started.")

    def stop(self):
        self.running = False
        if getattr(self, "porcupine", None):
            self.porcupine.delete()
        self.pa.terminate()

    def interrupt_playback(self):
        self.is_playing = False
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except queue.Empty:
                break
        self.on_log("SYSTEM", "Audio playback interrupted by user.")

    def queue_playback(self, audio_bytes: bytes):
        self.playback_queue.put(audio_bytes)

    def _listen_loop(self):
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

            bg_noise_rms = 500.0  # Initial guess
            silence_threshold_multiplier = 1.6  # 1.6x the ambient noise
            silence_frames = 0

            # 2 seconds of silence after speaking
            max_silence_duration = int(
                2.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )
            # 15 seconds max recording
            max_recording_frames = int(
                15.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )

            while self.running:
                try:
                    pcm = audio_stream.read(
                        self.porcupine.frame_length, exception_on_overflow=False
                    )
                    import struct

                    pcm_unpacked = struct.unpack_from(
                        "h" * self.porcupine.frame_length, pcm
                    )

                    # Calculate RMS energy with DC offset removal
                    mean = sum(pcm_unpacked) / len(pcm_unpacked)
                    rms = math.sqrt(
                        sum((x - mean) ** 2 for x in pcm_unpacked) / len(pcm_unpacked)
                    )

                    if not self.is_recording:
                        # continuously adapt background noise profile
                        bg_noise_rms = 0.9 * bg_noise_rms + 0.1 * rms

                        result = self.porcupine.process(pcm_unpacked)
                        if result >= 0:
                            self.on_log(
                                "SYSTEM",
                                f"Wake word 'jarvis' detected! (Ambient RMS Baseline: {bg_noise_rms:.0f})",
                            )
                            self.on_wake_word(True)
                            self.interrupt_playback()
                            self.is_recording = True
                            self.audio_frames = []
                            silence_frames = 0
                    else:
                        self.audio_frames.append(pcm)

                        # Check if current RMS is below the dynamic threshold
                        # Floor the threshold at 800 just in case the mic is completely muted
                        threshold = max(
                            800.0, bg_noise_rms * silence_threshold_multiplier
                        )

                        if len(self.audio_frames) % 10 == 0:
                            self.on_log(
                                "DEBUG",
                                f"Audio RMS: {rms:.0f} | Target Threshold: {threshold:.0f}",
                            )

                        if rms < threshold:
                            silence_frames += 1
                        else:
                            silence_frames = 0

                        if (
                            silence_frames >= max_silence_duration
                            or len(self.audio_frames) >= max_recording_frames
                        ):
                            reason = (
                                "Silence detected"
                                if silence_frames >= max_silence_duration
                                else "Max recording length (15s) reached"
                            )
                            self.on_log(
                                "SYSTEM",
                                f"{reason}, sending audio.",
                            )
                            self.is_recording = False
                            self.on_wake_word(False)

                            full_audio_bytes = b"".join(self.audio_frames)
                            payload = ClientAudio(audio_bytes=full_audio_bytes)
                            self.on_audio_payload(payload)

                            self.audio_frames = []
                            silence_frames = 0

                except Exception as e:
                    self.on_log("ERROR", f"Audio listen error: {e}")
                    time.sleep(1)

        except Exception as e:
            self.on_log("ERROR", f"Audio stream setup error: {e}")
        finally:
            if audio_stream:
                audio_stream.close()

    def _playback_loop(self):
        pygame.mixer.init()

        while self.running:
            try:
                audio_bytes = self.playback_queue.get(timeout=1.0)

                if not self.is_playing:
                    self.is_playing = True

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".mp3"
                ) as tmp_file:
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

            except queue.Empty:
                if self.playback_queue.empty() and self.is_playing:
                    self.is_playing = False
            except Exception as e:
                self.on_log("ERROR", f"Playback thread error: {e}")
