import uuid
import logging
from typing import Dict
import os
import asyncio
import json

from google import genai
from google.genai import types

from backend.agent.tools_schema import system_tools
from shared.schemas import (
    WsClientPayload,
    WsServerPayload,
    ServerText,
    ServerToolAction,
    ServerError,
    ServerAudio,
)
from backend.router.parser import serialize_server_payload
from backend.agent.memory_tier2 import MemoryTier2
from backend.agent.memory_tier3 import MemoryTier3

logger = logging.getLogger(__name__)


class GeminiOrchestrator:
    def __init__(self, websocket, user_id: str = "guest"):
        self.websocket = websocket
        self.user_id = user_id

        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        # Initialize cloud-aware memory tiers
        base_dir = os.getenv("DATA_PATH", "data")
        self.tier2 = MemoryTier2(user_id=user_id, base_dir=base_dir)
        self.tier3 = MemoryTier3(user_id=user_id, base_dir=base_dir)
        
        profile = self.tier3.get_profile()
        profile_summary = profile.get("summary", "New user, no learned preferences yet.")
        verbosity = profile["preferences"].get("verbosity", "moderate")

        verbosity_instructions = {
            "chatty": "Be extremely conversational, friendly, and expressive. Provide detailed explanations, proactive insights, and engage in natural small talk.",
            "moderate": "Be helpful, proactive, and balanced. Provide clear but concise answers. Strike a balance between personality and efficiency.",
            "silent": "Be extremely brief and efficient. Reply with the absolute minimum number of words necessary. Avoid all small talk or pleasantries.",
        }
        v_constraint = verbosity_instructions.get(verbosity, verbosity_instructions["moderate"])

        self.system_instruction = (
            "You are 'System Caretaker', an automatic system operator and caretaker running on the user's machine. "
            "You help monitor system vitals, handle user queries (text/audio), and use tools to manage their OS. "
            "You have access to current system metrics provided by the user. "
            f"PERSONALITY: {v_constraint}\n\n"
            "IMPORTANT: You have powerful tools available. USE THEM whenever relevant:\n"
            "- get_desktop_picture: Takes a screenshot of the user's screen so you can SEE what they see.\n"
            "- get_system_health: Gets current CPU, RAM, disk metrics.\n"
            "- get_all_process_and_resource_usage: Lists the top resource-heavy processes.\n"
            "- terminate_process: Kills a process by PID.\n"
            "- set_focus_environment: Enables dark mode, DND, or closes distractions.\n"
            "- get_system_logs: Reads recent OS logs.\n"
            "- disk_usage_scan: Scans for large files.\n"
            "- cleanup_disk: Cleans temp files.\n"
            "- manage_browser_tabs: Suspends or kills browser tabs.\n"
            "- manage_background_services: Stops or restarts services.\n\n"
            "CONFIRMATION REQUIRED — CRITICAL RULE:\n"
            "The following tools are DESTRUCTIVE and will modify or delete data on the user's machine. "
            "You MUST verbally tell the user what you are about to do and explicitly ask for their confirmation "
            "before calling any of these tools. NEVER call them autonomously without a clear 'yes' or equivalent from the user:\n"
            "- cleanup_disk (deletes files)\n"
            "- terminate_process (kills a running process)\n"
            "- manage_browser_tabs with action=kill (closes tabs)\n"
            "- manage_background_services with action=stop (stops services)\n"
            "- set_focus_environment (changes system settings)\n\n"
            "For diagnostic/read-only tools (get_desktop_picture, get_system_health, disk_usage_scan, etc.) you may call freely without asking.\n\n"
            "When a user asks about their screen, processes, or system — ALWAYS call the relevant tool first. "
            "Do NOT say you cannot see the screen — you CAN via get_desktop_picture.\n\n"
            f"[User Profile & Learned Preferences]:\n{profile_summary}"
        )

        self.pending_tool_calls: Dict[str, Dict[str, str]] = {}
        self.latest_metrics = None
        self.latest_query = "initial load"

        # Queues for decoupling the FastAPI handler from the Gemini session loop
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._session_task: asyncio.Task | None = None
        self._session_ready = asyncio.Event()

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    async def start(self):
        """Launches the persistent session loop as a background task."""
        if self._session_task and not self._session_task.done():
            return
        self._session_ready.clear()
        self._session_task = asyncio.create_task(self._session_loop())
        await self._session_ready.wait()

    async def handle_client_payload(self, payload: WsClientPayload):
        try:
            if not self._session_task or self._session_task.done():
                await self.start()

            if payload.type == "metrics":
                self.latest_metrics = payload.data
                return

            elif payload.type == "text":
                self.latest_query = payload.text
                text = payload.text
                if self.latest_metrics:
                    past_events = self.tier2.retrieve_similar_events(
                        "user_query", payload.text
                    )
                    text += f"\n[Past Relevant Memory]: {json.dumps(past_events)}\n"
                    text += f"[Current System State]: {self.latest_metrics.model_dump_json()}"
                await self._send_queue.put(("text", text))

            elif payload.type == "image":
                self.latest_query = "image upload"
                parts = [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": payload.image_bytes,
                        }
                    }
                ]
                if self.latest_metrics:
                    parts.append(
                        {
                            "text": f"[System Metrics]: {self.latest_metrics.model_dump_json()}"
                        }
                    )
                await self._send_queue.put(("content", parts))

            elif payload.type == "audio_stream":
                # Used for raw PCM chunks in streaming mode
                await self._send_queue.put(("audio", payload.audio_bytes))

            elif payload.type == "audio":
                # Legacy full-audio buffer message
                self.latest_query = "voice command"
                await self._send_queue.put(("audio", payload.audio_bytes))

            elif payload.type == "interrupt":
                # The user interrupted via voice or UI
                logger.info("Received interrupt payload from client.")
                
                # 1. Clear any pending messages in our own send queue
                while not self._send_queue.empty():
                    try:
                        self._send_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                # 2. Add an explicit interrupt command to send to Gemini
                await self._send_queue.put(("interrupt", None))

            elif payload.type == "settings_update":
                logger.info(f"Settings update: {payload.setting} = {payload.value}")
                
                if payload.setting == "verbosity":
                    self.tier3.add_preference("verbosity", payload.value)
                    # Note: Gemini instructions only update on next session/re-connect 
                    # unless we update live config. For now, it updates on next boot.
                    logger.info(f"Verbosity preference updated in Tier 3: {payload.value}")

            elif payload.type == "tool_result":
                if payload.call_id not in self.pending_tool_calls:
                    logger.warning(f"Unknown tool result call_id: {payload.call_id}")
                    return
                call_info = self.pending_tool_calls.pop(payload.call_id)
                tool_name = call_info.get("tool_name", "unknown")
                event_id = call_info.get("event_id")

                if event_id:
                    self.tier2.record_operation_outcome(
                        event_id=event_id,
                        status=payload.status,
                        result_metrics={"message": payload.message},
                    )
                    self.tier2.record_user_response(
                        event_id=event_id,
                        accepted=True if payload.status == "success" else False,
                    )

                # Format tool result for sending
                await self._send_queue.put(
                    (
                        "tool_result",
                        (payload.call_id, tool_name, payload.status, payload.message),
                    )
                )

        except Exception as e:
            logger.error(f"Error handling payload: {e}", exc_info=True)
            await self.send_to_client(
                ServerError(error_msg=f"Agent Request Error: {str(e)}")
            )

    async def push_alert(self, alert_message: str):
        """
        Inject a proactive system alert into the Gemini session send queue.
        Called by MonitoringEngine when a threshold is breached.
        The alert is sent as а user-side text so Gemini will respond aloud.
        """
        logger.info(f"Pushing proactive alert to Gemini: {alert_message[:80]}...")
        await self._send_queue.put(("alert", alert_message))

    async def send_to_client(self, payload: WsServerPayload):
        raw_bytes = serialize_server_payload(payload)
        await self.websocket.send_bytes(raw_bytes)

    async def close(self):
        if self._session_task:
            self._session_task.cancel()

    # -------------------------------------------------------------------------
    # Session management
    # -------------------------------------------------------------------------

    async def _session_loop(self):
        """
        Keeps the Gemini Live API connection alive for the duration of this WebSocket.
        The `async with` block MUST stay open — the session closes when we exit it.
        """
        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=self.system_instruction)]
            ),
            tools=system_tools,
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        try:
            async with self.client.aio.live.connect(
                model="gemini-2.5-flash-native-audio-latest", config=config
            ) as session:
                logger.info("Connected to Gemini Multimodal Live API.")
                self._session_ready.set()

                send_task = asyncio.create_task(self._send_loop(session))
                recv_task = asyncio.create_task(self._receive_loop(session))

                done, pending = await asyncio.wait(
                    [send_task, recv_task], return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()

        except asyncio.CancelledError:
            logger.info("Session loop cancelled.")
        except Exception as e:
            logger.error(f"Session loop error: {e}", exc_info=True)
            self._session_ready.set()  # Unblock start() so handle_client_payload doesn't hang
            await self.send_to_client(ServerError(error_msg=f"Session Error: {str(e)}"))

    async def _send_loop(self, session):
        """Drains the send queue and forwards messages to Gemini using the modern API."""
        while True:
            kind, data = await self._send_queue.get()
            try:
                if kind == "text":
                    await session.send_client_content(
                        turns=[{"role": "user", "parts": [{"text": data}]}],
                        turn_complete=True,
                    )
                elif kind == "content":
                    await session.send_client_content(
                        turns=[{"role": "user", "parts": data}],
                        turn_complete=True,
                    )
                elif kind == "audio":
                    await session.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
                elif kind == "alert":
                    # Proactive system alert — inject as a new user turn.
                    # Gemini speaks its response aloud; only the transcription shows in chat.
                    logger.info("Forwarding proactive alert turn to Gemini Live API.")
                    await session.send_client_content(
                        turns=[{"role": "user", "parts": [{"text": data}]}],
                        turn_complete=True,
                    )
                elif kind == "interrupt":
                    # Send an empty user content piece with turn_complete=False to halt 
                    # whatever the model is currently generating immediately.
                    logger.info("Sending interrupt signal to Gemini Live API.")
                    await session.send_client_content(
                        turns=[{"role": "user", "parts": []}],
                        turn_complete=False,
                    )
                elif kind == "tool_result":
                    call_id, tool_name, status, message = data
                    await session.send_tool_response(
                        function_responses=[
                            types.FunctionResponse(
                                name=tool_name,
                                id=call_id,
                                response={"status": status, "message": message},
                            )
                        ]
                    )
            except Exception as e:
                logger.error(f"Send error (kind={kind}): {e}", exc_info=True)

    async def _receive_loop(self, session):
        """Receives streaming audio/transcription/tool-calls from Gemini and proxies to client."""
        try:
            async for response in session.receive():
                sc = response.server_content
                if sc is not None:
                    # Audio chunks — primary output modality
                    if sc.model_turn is not None:
                        for part in sc.model_turn.parts:
                            if part.inline_data is not None:
                                if part.inline_data.mime_type.startswith("audio/pcm"):
                                    await self.send_to_client(
                                        ServerAudio(audio_bytes=part.inline_data.data)
                                    )
                            # Tool calls
                            if part.function_call is not None:
                                await self._dispatch_tool_call(part.function_call)

                    # Transcription of the model's spoken audio
                    if sc.output_transcription is not None:
                        text = sc.output_transcription.text
                        if text:
                            await self.send_to_client(
                                ServerText(text=text, is_chunk=True)
                            )

                if response.tool_call is not None:
                    for fn in response.tool_call.function_calls:
                        await self._dispatch_tool_call(fn)

        except asyncio.CancelledError:
            logger.info("Receive loop cancelled.")
        except Exception as e:
            logger.error(f"Receive loop error: {e}", exc_info=True)
            await self.send_to_client(ServerError(error_msg=f"Receive Error: {str(e)}"))

    async def _dispatch_tool_call(self, fn):
        call_id = fn.id or str(uuid.uuid4())
        tool_name = fn.name

        args_dict = fn.args if fn.args else {}
        if not isinstance(args_dict, dict):
            args_dict = dict(args_dict) if hasattr(args_dict, "__iter__") else {}

        # Record event in episodic memory
        system_state = self.latest_metrics.model_dump() if self.latest_metrics else {}
        event_id = None
        if hasattr(self, "tier2") and self.tier2:
            event_id = self.tier2.create_event(
                event_type="user_interaction",
                system_state=system_state,
                suggestion=f"Tool called: {fn.name} with {args_dict}",
                suggestion_context=self.latest_query,
            )
        self.pending_tool_calls[call_id] = {
            "tool_name": tool_name,
            "event_id": event_id,
        }

        await self.send_to_client(
            ServerToolAction(call_id=call_id, tool_name=tool_name, tool_args=args_dict)
        )
