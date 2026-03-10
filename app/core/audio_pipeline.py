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
            import struct

            bg_noise_rms = 500.0
            silence_threshold_multiplier = 1.6
            silence_frames = 0
            has_speech = False  # True once user actually says something post wake-word
            stream_buffer = []  # Accumulate ~160ms chunks before sending

            # Only start counting silence AFTER user has spoken —
            # 4s of silence after speech ends the recording.
            max_silence_after_speech = int(
                4.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )
            # Hard max: 4s of total silence with NO speech at all after wake word
            max_silence_before_speech = int(
                4.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )
            # 15 seconds max recording
            max_recording_frames = int(
                15.0 * (self.porcupine.sample_rate / self.porcupine.frame_length)
            )
            # Stream every N frames (~160ms at 16kHz / 512 frame_length)
            stream_chunk_frames = 5

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

                    if not self.is_recording:
                        bg_noise_rms = 0.9 * bg_noise_rms + 0.1 * rms
                        result = self.porcupine.process(pcm_unpacked)
                        if result >= 0:
                            self.on_log(
                                "SYSTEM",
                                f"Wake word 'jarvis' detected! (Ambient RMS: {bg_noise_rms:.0f})",
                            )
                            self.on_wake_word(True)
                            self.interrupt_playback()
                            self.is_recording = True
                            stream_buffer = []
                            silence_frames = 0
                            has_speech = False
                    else:
                        stream_buffer.append(pcm)

                        threshold = max(
                            800.0, bg_noise_rms * silence_threshold_multiplier
                        )

                        if len(stream_buffer) % 10 == 0:
                            self.on_log(
                                "DEBUG",
                                f"Audio RMS: {rms:.0f} | Threshold: {threshold:.0f} | Has speech: {has_speech}",
                            )

                        if rms >= threshold:
                            # User is speaking
                            has_speech = True
                            silence_frames = 0
                        else:
                            # Silence — only count against the limit if user has spoken
                            if has_speech:
                                silence_frames += 1

                        # Stream buffered frames to backend every N frames (real-time)
                        if len(stream_buffer) >= stream_chunk_frames:
                            chunk_bytes = b"".join(stream_buffer)
                            stream_buffer = []
                            payload = ClientAudio(audio_bytes=chunk_bytes)
                            self.on_audio_payload(payload)

                        # Determine silence limit based on whether user has spoken yet
                        silence_limit = (
                            max_silence_after_speech
                            if has_speech
                            else max_silence_before_speech
                        )

                        total_frames = (
                            len(stream_buffer)
                            +
                            # approximate count already streamed
                            0
                        )

                        if (
                            silence_frames >= silence_limit
                            or len(stream_buffer) >= max_recording_frames
                        ):
                            reason = (
                                "Silence detected after speech"
                                if (has_speech and silence_frames >= silence_limit)
                                else "No speech within 4s of wake word"
                                if (not has_speech)
                                else "Max recording length (15s) reached"
                            )
                            self.on_log("SYSTEM", f"{reason}, stopping recording.")
                            self.is_recording = False
                            self.on_wake_word(False)

                            # Flush any remaining buffered frames
                            if stream_buffer:
                                payload = ClientAudio(
                                    audio_bytes=b"".join(stream_buffer)
                                )
                                self.on_audio_payload(payload)

                            stream_buffer = []
                            silence_frames = 0
                            has_speech = False

                except Exception as e:
                    self.on_log("ERROR", f"Audio listen error: {e}")
                    time.sleep(1)

        except Exception as e:
            self.on_log("ERROR", f"Audio stream setup error: {e}")
        finally:
            if audio_stream:
                audio_stream.close()

    def _playback_loop(self):
        """
        Playback loop with two paths:
        - Raw PCM bytes (Gemini Live API) → written directly to a persistent
          PyAudio output stream for gapless, low-latency playback.
        - WAV / MP3 (legacy encoded audio) → pygame music player.
        """
        # Persistent PyAudio output stream for 24kHz 16-bit mono PCM
        pcm_stream = None
        try:
            pcm_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=24000,  # Gemini Live API native output rate
                output=True,
                frames_per_buffer=1024,
            )
        except Exception as e:
            self.on_log("ERROR", f"Failed to open PCM playback stream: {e}")

        pygame.mixer.init()

        while self.running:
            try:
                audio_bytes = self.playback_queue.get(timeout=1.0)
                self.is_playing = True

                is_wav = audio_bytes[:4] == b"RIFF"
                is_mp3 = audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb"

                if is_wav or is_mp3:
                    # Legacy encoded audio: use pygame
                    suffix = ".wav" if is_wav else ".mp3"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                        f.write(audio_bytes)
                        tmp_name = f.name
                    try:
                        pygame.mixer.music.load(tmp_name)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy() and self.is_playing:
                            time.sleep(0.05)
                        pygame.mixer.music.stop()
                        pygame.mixer.music.unload()
                    except Exception as e:
                        self.on_log("ERROR", f"Pygame playback error: {e}")
                    try:
                        os.remove(tmp_name)
                    except Exception:
                        pass
                else:
                    # Raw PCM → write directly into the open PyAudio stream (no gaps)
                    if pcm_stream and pcm_stream.is_active():
                        try:
                            pcm_stream.write(audio_bytes)
                        except Exception as e:
                            self.on_log("ERROR", f"PCM stream write error: {e}")

            except queue.Empty:
                if self.playback_queue.empty() and self.is_playing:
                    self.is_playing = False
            except Exception as e:
                self.on_log("ERROR", f"Playback thread error: {e}")

        # Cleanup
        if pcm_stream:
            try:
                pcm_stream.stop_stream()
                pcm_stream.close()
            except Exception:
                pass
