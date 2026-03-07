#!/usr/bin/env python3
import os
import sys
import asyncio
import struct
import pyaudio
import pvporcupine
from dotenv import load_dotenv
from google import genai
from google.genai import types

from agent.registry import get_all_tools
import core.system_ops as ops

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY")

MAX_RAM_PERCENT = 90.0
MAX_CPU_PERCENT = 60.0
POLL_INTERVAL_SECONDS = 5

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL_ID = "gemini-2.5-flash-native-audio-latest"

def check_keys():
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_api_key_here":
        print("[ERROR] GEMINI_API_KEY is missing in .env")
        sys.exit(1)
    if not PORCUPINE_ACCESS_KEY or PORCUPINE_ACCESS_KEY == "your_porcupine_key_here":
        print("[ERROR] PORCUPINE_ACCESS_KEY is missing in .env")
        sys.exit(1)

class SysoVoiceAgent:
    def __init__(self):
        self.pya = pyaudio.PyAudio()
        self.client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
        self.system_tools = get_all_tools()
        
        self.is_connected = False
        self.alert_to_send = None
        
        self.audio_queue_output = asyncio.Queue()
        self.audio_queue_mic = asyncio.Queue(maxsize=10)
        
    async def play_audio(self):
        stream = await asyncio.to_thread(
            self.pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        try:
            while True:
                bytestream = await self.audio_queue_output.get()
                await asyncio.to_thread(stream.write, bytestream)
                self.audio_queue_output.task_done()
        except asyncio.CancelledError:
            stream.stop_stream()
            stream.close()

    async def listen_mic(self, porcupine):
        mic_info = self.pya.get_default_input_device_info()
        stream = await asyncio.to_thread(
            self.pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=porcupine.frame_length,
        )
        
        print("\n[Syso] Listening locally for 'Porcupine'...")
        
        try:
            while True:
                data = await asyncio.to_thread(stream.read, porcupine.frame_length, exception_on_overflow=False)
                
                if not self.is_connected:
                    pcm = struct.unpack_from("h" * porcupine.frame_length, data)
                    keyword_index = porcupine.process(pcm)
                    if keyword_index >= 0:
                        print("\n[WAKE WORD DETECTED]")
                        self.is_connected = True
                else:
                    await self.audio_queue_mic.put({"data": data, "mime_type": "audio/pcm"})
        except asyncio.CancelledError:
            stream.stop_stream()
            stream.close()

    async def send_to_gemini(self, session):
        if self.alert_to_send:
            await session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": self.alert_to_send}]}],
                turn_complete=True
            )
            self.alert_to_send = None

        while True:
            msg = await self.audio_queue_mic.get()
            await session.send_realtime_input(audio=msg)
            self.audio_queue_mic.task_done()

    async def receive_from_gemini(self, session):
        try:
            while True:
                async for response in session.receive():
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                await self.audio_queue_output.put(part.inline_data.data)
                            if part.text:
                                if len(part.text) < 15:
                                    print(part.text, end="", flush=True)

                    if response.server_content and response.server_content.turn_complete:
                        print()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"\n[Gemini Error] {e}")
            self.is_connected = False

    async def monitor_system(self):
        in_alert = False
        while True:
            try:
                ram = ops.get_memory_usage()['percent_used']
                cpu = ops.get_cpu_usage(interval=1)
                
                if (ram > MAX_RAM_PERCENT or cpu > MAX_CPU_PERCENT) and not in_alert:
                    in_alert = True
                    reason = f"RAM {ram}%" if ram > MAX_RAM_PERCENT else f"CPU {cpu}%"
                    self.alert_to_send = (
                        f"[SYSTEM ALERT]: {reason}. Wake up and warn the user. "
                        "Check heavy processes and ask to kill the target."
                    )
                    print(f"\n[!!!] ALERT: {reason}")
                    self.is_connected = True
                
                if ram < (MAX_RAM_PERCENT - 5) and cpu < (MAX_CPU_PERCENT - 5):
                    in_alert = False
                    
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def run(self):
        check_keys()
        
        porcupine = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keywords=["porcupine"])
        
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.play_audio())
            tg.create_task(self.listen_mic(porcupine))
            tg.create_task(self.monitor_system())
            
            while True:
                if self.is_connected:
                    print("[Syso] Connecting to Gemini Live...")
                    config = {
                        "tools": self.system_tools,
                        "system_instruction": "You are Syso, a friendly voice system agent. respond with AUDIO ONLY. concise.",
                        "response_modalities": ["AUDIO"],
                        "temperature": 0.3,
                    }
                    
                    try:
                        async with self.client.aio.live.connect(model=MODEL_ID, config=config) as session:
                            print("[Syso] Gemini Connected.")
                            tx_task = tg.create_task(self.send_to_gemini(session))
                            rx_task = tg.create_task(self.receive_from_gemini(session))
                            
                            while self.is_connected:
                                await asyncio.sleep(0.5)
                            
                            tx_task.cancel()
                            rx_task.cancel()
                            while not self.audio_queue_mic.empty():
                                self.audio_queue_mic.get_nowait()
                                
                    except Exception as e:
                        print(f"[Syso] Connection Failed: {e}")
                        self.is_connected = False
                
                await asyncio.sleep(0.5)

if __name__ == "__main__":
    agent = SysoVoiceAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\nShutting down Syso.")
