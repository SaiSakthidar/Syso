from pydantic import BaseModel, Field
from typing import Literal, Union, List, Any, Dict

class SystemMetricsData(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    active_window: str = ""
    top_processes: List[Dict[str, Any]] = Field(default_factory=list)

# --- CLIENT TO BACKEND (Native App sends) ---
class ClientMetrics(BaseModel):
    type: Literal["metrics"] = "metrics"
    data: SystemMetricsData

class ClientText(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ClientAudio(BaseModel):
    type: Literal["audio"] = "audio"
    audio_bytes: bytes

class ClientAudioStream(BaseModel):
    """Real-time PCM audio chunk for Live API streaming."""
    type: Literal["audio_stream"] = "audio_stream"
    audio_bytes: bytes

class ClientImage(BaseModel):
    type: Literal["image"] = "image"
    image_bytes: bytes

class ClientToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    tool_name: str
    status: Literal["success", "error"]
    message: str
    image_bytes: bytes = b""  # Optional: populated when tool returns an image (e.g. screenshot)

WsClientPayload = Union[ClientMetrics, ClientText, ClientAudio, ClientAudioStream, ClientImage, ClientToolResult]

# --- BACKEND TO CLIENT (Server sends) ---
class ServerText(BaseModel):
    type: Literal["agent_text"] = "agent_text"
    text: str

class ServerAudio(BaseModel):
    type: Literal["agent_audio"] = "agent_audio"
    audio_bytes: bytes

class ServerToolAction(BaseModel):
    type: Literal["tool_action"] = "tool_action"
    call_id: str
    tool_name: str
    tool_args: Dict[str, Any]

class ServerError(BaseModel):
    type: Literal["error"] = "error"
    error_msg: str

WsServerPayload = Union[ServerText, ServerAudio, ServerToolAction, ServerError]
