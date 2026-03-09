import uuid
import logging
from typing import Dict
import os

import google.generativeai as genai
from google.ai.generativelanguage import Part, FunctionResponse

from backend.agent.tools_schema import system_tools
from shared.schemas import (
    WsClientPayload,
    WsServerPayload,
    ServerText,
    ServerToolAction,
    ServerError,
)
from backend.router.parser import serialize_server_payload

logger = logging.getLogger(__name__)


class GeminiOrchestrator:
    def __init__(self, websocket):
        self.websocket = websocket

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

        system_instruction = (
            "You are 'System Caretaker', an automatic system operator and caretaker. "
            "You help monitor system vitals, handle user queries (text/audio), and use tools to manage their OS. "
            "You have access to current system metrics provided by the user. "
            "Be helpful, proactive, and concise. Don't be too verbose unless explicitly asked to."
        )
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",  # Use flash for speed
            tools=system_tools,
        )

        # We start the chat with the system prompt injected into the history since 0.4.1 doesn't support system_instruction
        self.chat = self.model.start_chat(
            history=[
                {"role": "user", "parts": [system_instruction]},
                {"role": "model", "parts": ["Understood. I am your System Caretaker."]},
            ],
            enable_automatic_function_calling=False,
        )
        self.pending_tool_calls: Dict[str, str] = {}
        self.latest_metrics = None

    async def send_to_client(self, payload: WsServerPayload):
        raw_bytes = serialize_server_payload(payload)
        await self.websocket.send_bytes(raw_bytes)

    async def handle_client_payload(self, payload: WsClientPayload):
        try:
            if payload.type == "metrics":
                self.latest_metrics = payload.data
                # We do not forward metrics unconditionally, we just keep them handy.

            elif payload.type == "text":
                content = [payload.text]
                if self.latest_metrics:
                    content.append(
                        f"[Current System State]: {self.latest_metrics.model_dump_json()}"
                    )
                await self._send_to_gemini(content)

            elif payload.type == "image":
                part = {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": payload.image_bytes,
                    }
                }
                content = [part]
                if self.latest_metrics:
                    content.append(
                        f"[Current System Metrics]: {self.latest_metrics.model_dump_json()}"
                    )
                await self._send_to_gemini(content)

            elif payload.type == "audio":
                import io
                import wave

                # The user spoke to us! We provide the audio and expect AUDIO back.
                wav_io = io.BytesIO()
                with wave.open(wav_io, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)  # pvporcupine rate is specifically 16kHz
                    wf.writeframes(payload.audio_bytes)

                # The old 0.4.1 SDK requires dict dictionaries for inline data to be specifically
                # structured and often base_64 encoded depending on the abstraction layer.
                # Actually, according to google.ai.generativelanguage Part:
                part = {
                    "inline_data": {"mime_type": "audio/wav", "data": wav_io.getvalue()}
                }
                content = [part]
                if self.latest_metrics:
                    content.append(
                        f"[Current System Metrics]: {self.latest_metrics.model_dump_json()}"
                    )
                await self._send_to_gemini(content)

            elif payload.type == "tool_result":
                if payload.call_id not in self.pending_tool_calls:
                    logger.warning(
                        f"Received unknown tool result call_id: {payload.call_id}"
                    )
                    return

                tool_name = self.pending_tool_calls.pop(payload.call_id)
                response_part = Part(
                    function_response=FunctionResponse(
                        name=tool_name,
                        response={"status": payload.status, "message": payload.message},
                    )
                )
                await self._send_to_gemini(response_part)
        except Exception as e:
            logger.error(f"Error handling payload: {e}", exc_info=True)
            await self.send_to_client(ServerError(error_msg=f"Agent Error: {str(e)}"))

    async def _send_to_gemini(self, content):
        try:
            response = await self.chat.send_message_async(content)
            await self._process_gemini_response(response)
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            await self.send_to_client(
                ServerError(error_msg=f"Gemini API Error: {str(e)}")
            )

    async def _process_gemini_response(self, response):
        if not response.parts:
            return

        for part in response.parts:
            # Check for tool call first
            if fn := part.function_call:
                call_id = str(uuid.uuid4())
                self.pending_tool_calls[call_id] = fn.name

                # Extract args safely to a standard dict
                args_dict = type(fn).to_dict(fn).get("args", {})

                tool_action = ServerToolAction(
                    call_id=call_id, tool_name=fn.name, tool_args=args_dict
                )
                await self.send_to_client(tool_action)

            # Then check for text
            elif text := part.text:
                await self.send_to_client(ServerText(text=text))

                # Generate edge-tts audio and send ServerAudio
                try:
                    import edge_tts
                    import io

                    communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
                    audio_io = io.BytesIO()
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            audio_io.write(chunk["data"])

                    audio_bytes = audio_io.getvalue()
                    if len(audio_bytes) > 0:
                        from shared.schemas import ServerAudio

                        await self.send_to_client(ServerAudio(audio_bytes=audio_bytes))
                except Exception as e:
                    logger.error(f"TTS generation error: {e}")
