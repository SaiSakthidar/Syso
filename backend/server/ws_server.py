from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.router.parser import parse_client_payload, serialize_server_payload
from backend.agent.gemini import GeminiOrchestrator
from backend.agent.monitoring_engine import MonitoringEngine
from backend.agent.memory_tier3 import MemoryTier3
from shared.schemas import ServerError
import asyncio
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Extract user identity for cloud-native isolation
    user_id = websocket.query_params.get("user_id", "guest")
    base_dir = os.getenv("DATA_PATH", "data")
    
    logger.info(f"New WebSocket connection for user: {user_id}")
    orchestrator = GeminiOrchestrator(websocket, user_id=user_id)

    # Start the Gemini session first so push_alert can queue into an open session
    await orchestrator.start()

    # Launch the proactive monitoring engine as a background task for this session
    # Uses the same cloud-native Tier 3 as the orchestrator
    monitor = MonitoringEngine(orchestrator, tier3=orchestrator.tier3)
    monitor_task = asyncio.create_task(monitor.run())
    logger.info(f"MonitoringEngine task started for user: {user_id}")

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
    finally:
        monitor_task.cancel()
        logger.info("MonitoringEngine task cancelled.")

