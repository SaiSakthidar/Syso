import asyncio
import base64
import json
import uuid
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from backend.router.parser import parse_client_payload, serialize_server_payload
from shared.schemas import (
    ServerText,
    ServerAudio,
    ServerToolAction,
    ServerError,
)

router = APIRouter()
logger = logging.getLogger(__name__)

APP_NAME = "gemini-hack"

# ---------- shared singletons (created once at import) ----------
from agent.syso_agent import system_agent  # noqa: E402

session_service = InMemorySessionService()
runner = Runner(
    app_name=APP_NAME,
    agent=system_agent,
    session_service=session_service,
)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id = "desktop_user"
    session_id = str(uuid.uuid4())

    # Create session
    await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    model_name = system_agent.model
    is_native_audio = "live" in model_name.lower() or "native-audio" in model_name.lower()

    if is_native_audio:
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(),
        )
    else:
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["TEXT"],
            session_resumption=types.SessionResumptionConfig(),
        )

    logger.info("Live session starting — model=%s, native_audio=%s", model_name, is_native_audio)

    live_request_queue = LiveRequestQueue()
    latest_metrics = None
    pending_tool_calls: dict[str, str] = {}  # call_id -> tool_name
    ws_closed = False

    # ---- upstream: desktop client → Live API ----
    async def upstream_task():
        nonlocal latest_metrics, ws_closed
        try:
            while True:
                raw_data = await websocket.receive_bytes()
                try:
                    payload = parse_client_payload(raw_data)
                except Exception as e:
                    logger.error("Bad payload from client: %s", e)
                    continue

                if payload.type == "metrics":
                    latest_metrics = payload.data

                elif payload.type == "audio_stream":
                    # Real-time PCM chunk from mic
                    audio_blob = types.Blob(
                        mime_type="audio/pcm;rate=16000",
                        data=payload.audio_bytes,
                    )
                    live_request_queue.send_realtime(audio_blob)

                elif payload.type == "audio":
                    # Legacy full-utterance fallback — wrap as PCM
                    audio_blob = types.Blob(
                        mime_type="audio/pcm;rate=16000",
                        data=payload.audio_bytes,
                    )
                    live_request_queue.send_realtime(audio_blob)

                elif payload.type == "text":
                    content = types.Content(
                        parts=[types.Part(text=payload.text)]
                    )
                    live_request_queue.send_content(content)

                elif payload.type == "image":
                    image_blob = types.Blob(
                        mime_type="image/jpeg",
                        data=payload.image_bytes,
                    )
                    live_request_queue.send_realtime(image_blob)

                elif payload.type == "tool_result":
                    tool_name = pending_tool_calls.pop(payload.call_id, payload.tool_name)
                    response_parts = [
                        types.Part.from_function_response(
                            name=tool_name,
                            response={
                                "status": payload.status,
                                "message": payload.message,
                            },
                        )
                    ]
                    if payload.image_bytes:
                        response_parts.append(
                            types.Part.from_bytes(
                                data=payload.image_bytes,
                                mime_type="image/jpeg",
                            )
                        )
                    content = types.Content(parts=response_parts)
                    live_request_queue.send_content(content)

        except WebSocketDisconnect:
            logger.info("Client disconnected (upstream)")
            ws_closed = True
        except Exception as e:
            logger.error("Upstream error: %s", e, exc_info=True)
            ws_closed = True

    # ---- downstream: Live API → desktop client ----
    async def downstream_task():
        try:
            async for event in runner.run_live(
                user_id=user_id,
                session_id=session_id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                # ADK events have .content with parts, or actions
                try:
                    if not event.content or not event.content.parts:
                        continue

                    for part in event.content.parts:
                        if ws_closed:
                            return

                        # ---- Audio response (raw PCM bytes) ----
                        if part.inline_data and part.inline_data.mime_type and "audio" in part.inline_data.mime_type:
                            audio_payload = ServerAudio(audio_bytes=part.inline_data.data)
                            await websocket.send_bytes(serialize_server_payload(audio_payload))

                        # ---- Text response ----
                        elif part.text:
                            text_payload = ServerText(text=part.text)
                            await websocket.send_bytes(serialize_server_payload(text_payload))

                        # ---- Tool / function call ----
                        elif part.function_call:
                            fn = part.function_call
                            call_id = str(uuid.uuid4())
                            args_dict = dict(fn.args) if fn.args else {}
                            pending_tool_calls[call_id] = fn.name

                            tool_payload = ServerToolAction(
                                call_id=call_id,
                                tool_name=fn.name,
                                tool_args=args_dict,
                            )
                            await websocket.send_bytes(serialize_server_payload(tool_payload))

                except Exception as inner_e:
                    logger.error("Error processing event: %s", inner_e, exc_info=True)

        except Exception as e:
            logger.error("Downstream error: %s", e, exc_info=True)

    try:
        await asyncio.gather(upstream_task(), downstream_task())
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error("WebSocket session error: %s", e, exc_info=True)
    finally:
        live_request_queue.close()
