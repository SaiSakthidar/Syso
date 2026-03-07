import asyncio
import base64
import json
import logging
import warnings
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

load_dotenv(Path(__file__).parent.parent / ".env")
from agent.syso_agent import system_agent as agent  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
APP_NAME = "gemini-hack"

app = FastAPI()
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=agent, session_service=session_service)


@app.get("/")
async def root():
    """Serve the index.html page."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    proactivity: bool = False,
    affective_dialog: bool = False,
) -> None:
    """WebSocket endpoint for bidirectional streaming with ADK.
    Args:
        websocket: The WebSocket connection
        user_id: User identifier
        session_id: Session identifier
        proactivity: Enable proactive audio (native audio models only)
        affective_dialog: Enable affective dialog (native audio models only)
    """
    logger.debug(
        f"WebSocket connection request: user_id={user_id}, session_id={session_id}, "
        f"proactivity={proactivity}, affective_dialog={affective_dialog}"
    )
    await websocket.accept()
    logger.debug("WebSocket connection accepted")

    model_name = agent.model
    is_native_audio = "native-audio" in model_name.lower()
    if is_native_audio:
        response_modalities = ["AUDIO"]
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=response_modalities,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(),
            proactivity=(
                types.ProactivityConfig(proactive_audio=True) if proactivity else None
            ),
            enable_affective_dialog=affective_dialog if affective_dialog else None,
        )
        logger.debug(
            f"Native audio model detected: {model_name}, "
            f"using AUDIO response modality, "
            f"proactivity={proactivity}, affective_dialog={affective_dialog}"
        )
    else:
        response_modalities = ["TEXT"]
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=response_modalities,
            input_audio_transcription=None,
            output_audio_transcription=None,
            session_resumption=types.SessionResumptionConfig(),
        )
        logger.debug(
            f"Half-cascade model detected: {model_name}, "
            "using TEXT response modality"
        )
        if proactivity or affective_dialog:
            logger.warning(
                f"Proactivity and affective dialog are only supported on native "
                f"audio models. Current model: {model_name}. "
                f"These settings will be ignored."
            )
    logger.debug(f"RunConfig created: {run_config}")
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
    live_request_queue = LiveRequestQueue()

    async def upstream_task() -> None:
        """Receives messages from WebSocket and sends to LiveRequestQueue."""
        logger.debug("upstream_task started")
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                audio_data = message["bytes"]
                logger.debug(f"Received binary audio chunk: {len(audio_data)} bytes")
                audio_blob = types.Blob(
                    mime_type="audio/pcm;rate=16000", data=audio_data
                )
                live_request_queue.send_realtime(audio_blob)
            elif "text" in message:
                text_data = message["text"]
                logger.debug(f"Received text message: {text_data[:100]}...")
                json_message = json.loads(text_data)
                if json_message.get("type") == "text":
                    logger.debug(f"Sending text content: {json_message['text']}")
                    content = types.Content(
                        parts=[types.Part(text=json_message["text"])]
                    )
                    live_request_queue.send_content(content)
                elif json_message.get("type") == "image":
                    logger.debug("Received image data")
                    image_data = base64.b64decode(json_message["data"])
                    mime_type = json_message.get("mimeType", "image/jpeg")
                    logger.debug(
                        f"Sending image: {len(image_data)} bytes, " f"type: {mime_type}"
                    )
                    image_blob = types.Blob(mime_type=mime_type, data=image_data)
                    live_request_queue.send_realtime(image_blob)

    async def downstream_task() -> None:
        """Receives Events from run_live() and sends to WebSocket."""
        logger.debug("downstream_task started, calling runner.run_live()")
        logger.debug(
            f"Starting run_live with user_id={user_id}, " f"session_id={session_id}"
        )
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=live_request_queue,
            run_config=run_config,
        ):
            event_json = event.model_dump_json(exclude_none=True, by_alias=True)
            logger.debug(f"[SERVER] Event: {event_json}")
            await websocket.send_text(event_json)
        logger.debug("run_live() generator completed")

    try:
        logger.debug("Starting asyncio.gather for upstream and downstream tasks")
        await asyncio.gather(upstream_task(), downstream_task())
        logger.debug("asyncio.gather completed normally")
    except WebSocketDisconnect:
        logger.debug("Client disconnected normally")
    except Exception as e:
        logger.error(f"Unexpected error in streaming tasks: {e}", exc_info=True)
    finally:
        logger.debug("Closing live_request_queue")
        live_request_queue.close()
