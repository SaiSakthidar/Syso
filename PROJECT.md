# Role and Objective
You are an expert Principal Python Engineer specializing in system programming, desktop GUIs, real-time websockets, multimodal AI pipelines, and Google Cloud platform architectures. 

Please feel free to change the existing codebase as much as you want or ignore it if it is irrelevant.

Your task is to build a hackathon project called **"System Caretaker"**, an automatic system operator and caretaker. The project requires a highly resilient, Copilot-style Native Desktop App (Python GUI) that monitors system vitals, handles voice/text input, and interacts with a local backend via websockets. The backend orchestrates a multimodal Gemini AI agent to diagnose issues and execute system-level tools.

Our goal is to perfectly execute 4 specific DEMO use cases. Prioritize implementation of these features over generic boilerplate.

---

# Tech Stack

## 1. The Native Desktop App (The GUI & The Watcher)
* **UI Layout**: 
    * Use `CustomTkinter` or similar choice.
    * A text chat interface (input box and submit button) for fallback manual commands. Include a UI label showing the current Wake Word status.
    * A "Debug / Live Feed" panel that visually logs system stats, screenshots taken, and the Agent's internal decisions.
* **Background Monitoring**: Continuously collects: RAM, CPU, Memory, and Disk space for processes and store in memory. Periodically collect Desktop screenshots as well for sending as input to the backend.
* **Audio & Wake Word**: Uses `PyAudio` and an offline wake-word detector (e.g., `pvporcupine`). 
* **Communication**: Maintains a persistent WebSocket client connection to the backend. Uses `msgpack` over Binary WebSocket frames for maximum efficiency.
* **Thread Safety**: The main thread MUST ONLY handle the CustomTkinter GUI. All network calls, hardware monitoring, and audio processing must run on separate daemon threads or via `asyncio` to prevent the UI from freezing. *(CRITICAL: Do not mix blocking PyAudio calls with the `asyncio` websocket loop. You must use thread-safe producer/consumer queues for mic input and a Jitter Buffer queue for incoming audio playback).*

## 2. Backend (On cloud servers)
* **Server**: `FastAPI` + `websockets` routing.
* **AI Integration**: Acts as a client to the Gemini multimodal API. 
* **Routing**: Receives `msgpack` payloads, routes them, formats data for Gemini, exposes tools to Gemini, and proxies the multimodal responses back using `msgpack`.
* In future we might add databases, authentication, RAG etc. please seperate the code into layers (like server layer, agent layer etc. as you prefer).

---

# User Process Flow

In the user's system, there are three possible triggers:
* Wake word
* Text input in GUI
* Resource usage spike

On trigger:
* Sending the audio (case 1), text (case 2) or the resource usages (all cases) along with desktop screenshots to the backend via WS.
* The backend might return any one or a combination of the below:
    * text response (show in the GUI)
    * audio response (play it out)
    * tool action (run the tool command and return the output. **CRITICAL: The backend must send a unique `call_id` with the tool request, and the native app MUST return that exact `call_id` with the tool result so the AI doesn't mix up responses.**)
* Please handle all the cases.

# Backend Process Flow
* The backend receives text/audio/image input (MULTIMODAL), it should proxy it to the gemini, receive toolcall if any proxy it to the user system, proxy the tool output back to the gemini and then send the final response (which shall be GEMINI MULTIMODAL response) to the user.

---

# Data Schemas (MessagePack Routing)
*Note: This schema is flexible! You can change, expand, or modify it as you see fit for the architecture. Just ensure you maintain the core concepts (like using raw `bytes` for media and a `call_id` for tool tracking).*

```python
from pydantic import BaseModel, Field
from typing import Literal, Union, List, Any, Dict

class SystemMetricsData(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
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

class ClientImage(BaseModel):
    type: Literal["image"] = "image"
    image_bytes: bytes

class ClientToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    tool_name: str
    status: Literal["success", "error"]
    message: str

WsClientPayload = Union[ClientMetrics, ClientText, ClientAudio, ClientImage, ClientToolResult]

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
```

---

# Required Tools (Function Calling)
Do NOT allow the LLM to execute arbitrary shell commands via `subprocess` without strict validation. Build specific Python wrapper functions:
1.  `get_system_health()`: CPU/RAM/Network state.
2.  `get_desktop_picture()`: Latest screenshot.
3.  `get_all_process_and_resource_usage()`: Top resource-heavy processes.
4.  `terminate_process(pid)`: Safely kills process via `psutil`.
5.  `set_focus_environment(params)`: Dark mode, DND, closes distracting apps.
6.  `restart_graphics_server()`: Securely restarts graphics service.
7.  `get_system_logs(lines)`: Parses OS logs for errors.
8.  `disk_usage_scan()`: Returns large file targets.
9.  `cleanup_disk()`: Temp file cleanup.
10. `manage_browser_tabs(browser, action)`: Suspend/kill browser processes.
11. `manage_background_services(service_name, action)`: Stop/restart services.

---

# The 4 Hackathon Demo Use Cases
All actions must be logged visually in the GUI's Debug Panel.

1. **Context-Aware Slowdown**: User: "Why is my PC lagging?" -> Agent reads stats (98% RAM) + screenshot -> Suggests suspending Chrome tabs hoarding 12GB -> Executes `manage_browser_tabs`.
2. **Video Call Rescue (PROACTIVE)**: Polling detects active Zoom call + network spike -> Agent initiates interaction -> "Internet struggling, Windows Update detected" -> Offers to pause update -> Executes `manage_background_services`.
3. **Silent Saboteur (Logs)**: User: "My video player closed!" -> Agent fetches logs + screen -> Diagnoses graphics crash -> Executes `restart_graphics_server`.
4. **Interrupted Study Session**: User: "Get ready for study" -> Agent starts `set_focus_environment` -> User INTERRUPTS (voice/text): "Wait, don't close Spotify!" -> Agent halts original tool call -> Executes modified environment.

---

# Phases
Please implement this project in strict phases. Stop and wait for my approval after completing each phase. Do NOT write the entire codebase at once.

* **Phase 1: Foundation & Data Contracts.** Set up the project directory structure and `requirements.txt` (fastapi, websockets, psutil, pyaudio, pillow, google-generativeai, customtkinter, pvporcupine, msgpack). Implement the flexible Pydantic schemas and shared data models.
* **Phase 2: Backend Orchestration & AI Integration.** Build the FastAPI WebSocket server. Integrate the Gemini SDK, configure the tool definitions for the LLM, and set up the `msgpack` payload routing logic.
* **Phase 3: Native Interface & Event Loop.** Create the `CustomTkinter` UI shell, including the chat box, debug panel, and wake word status. Ensure the GUI runs smoothly on the main thread without backend connections.
* **Phase 4: Telemetry, Workers & Proxy Execution.** Implement background daemon threads for `psutil` system metrics, desktop screenshots, and the WebSocket client. Implement the local tool wrapper functions and map them to safely handle incoming `ServerToolAction` requests. Pipe logs to the UI.
* **Phase 5: Audio Pipeline & Wake Word Integration.** Implement the thread-safe producer/consumer queues for `PyAudio` mic input and Jitter Buffer playback. Integrate `pvporcupine` for wake word detection and handle WebSocket audio interruption logic.