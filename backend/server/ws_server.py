from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.router.parser import parse_client_payload, serialize_server_payload
from backend.agent.gemini import GeminiOrchestrator
from shared.schemas import ServerError
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    orchestrator = GeminiOrchestrator(websocket)
    try:
        while True:
            raw_data = await websocket.receive_bytes()
            try:
                payload = parse_client_payload(raw_data)
                await orchestrator.handle_client_payload(payload)
            except Exception as e:
                logger.error(f"Error handling payload: {e}", exc_info=True)
                error_msg = ServerError(error_msg=str(e))
                await websocket.send_bytes(serialize_server_payload(error_msg))
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
