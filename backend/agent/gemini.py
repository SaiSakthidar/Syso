import uuid
import logging
from typing import Dict, Any

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

        system_instruction = (
            "You are 'System Caretaker', an automatic system operator and caretaker. "
            "You help monitor system vitals, handle user queries (text/audio), and use tools to manage their OS. "
            "You have access to current system metrics provided by the user. "
            "Be helpful, proactive, and concise. Don't be too verbose unless explicitly asked to."
        )
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",  # Use flash for speed
            tools=system_tools,
            system_instruction=system_instruction,
        )
        self.chat = self.model.start_chat(enable_automatic_function_calling=False)
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
                part = {"mime_type": "image/jpeg", "data": payload.image_bytes}
                content = [part]
                if self.latest_metrics:
                    content.append(
                        f"[Current System Metrics]: {self.latest_metrics.model_dump_json()}"
                    )
                await self._send_to_gemini(content)

            elif payload.type == "audio":
                # Assuming PCM or WAV audio bytes depending on the client PyAudio
                part = {"mime_type": "audio/wav", "data": payload.audio_bytes}
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
