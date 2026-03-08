# System Caretaker - Implementation Plan

## Goal Description
Build "System Caretaker," an automatic system operator and resilient Copilot-style Native Desktop App (Python GUI). It monitors system vitals, handles voice/text input, and interacts with a **remote cloud backend** via WebSockets. The backend orchestrates a multimodal Gemini AI agent to diagnose issues and proxy execution of system-level tools back to the user's desktop.

## User Review Required
> [!IMPORTANT]
> The development is split into 5 distinct phases. Development will pause at the end of each phase for your review and approval before proceeding further.

## Proposed Folder Structure
```text
system-caretaker/
├── app/                      # Native Desktop App (Runs locally on user's machine)
│   ├── main.py               # Entry point
│   ├── gui/                  # CustomTkinter components
│   │   ├── chat_panel.py
│   │   ├── debug_panel.py
│   │   └── main_window.py
│   ├── core/                 # Background workers and clients
│   │   ├── websocket_client.py
│   │   ├── audio_pipeline.py # PyAudio & pvporcupine
│   │   ├── telemetry.py      # psutil vitals & screenshots
│   │   └── tools.py          # ACTUAL EXECUTION wrappers (e.g., psutil script here)
├── backend/                  # Remote Cloud Server (Layered Architecture)
│   ├── main.py               # FastAPI server entry point
│   ├── server/               # WebSocket Server Layer
│   │   └── ws_server.py
│   ├── router/               # Message Routing Layer
│   │   └── parser.py         # Handles incoming MsgPack and passes to internal layers
│   ├── agent/                # AI Agent & Definitions Layer
│   │   ├── gemini.py         # AI Integration & conversation state
│   │   └── tools_schema.py   # TOOL DEFINITIONS (What to tell Gemini)
│   └── database/             # Data Layer (For future DBs, auth, RAG)
│       └── models.py
├── shared/                   # Shared Resources
│   ├── schemas.py            # Pydantic schemas for Msgpack routing
├── requirements.txt
└── PROJECT.md                # Requirements
```

## Architecture and Flow Explanation
### 1. Tool Declaration (App vs Backend)
The backend is hosted remotely in the cloud, meaning it cannot access or manage the user's OS processes, screenshots, or local logs. Therefore:
- The **Backend (`backend/agent/tools_schema.py`)** only stores the _JSON Schema_ of the tools to let Gemini know these functions exist.
- The **App (`app/core/tools.py`)** actually implements the logic using `psutil`, `subprocess`, etc. 
Whenever Gemini decides to invoke `get_desktop_picture()`, the backend wraps that request into a `ServerToolAction` and passes it back to the local app via WebSocket. The App runs the actual function and responds with a `ClientToolResult`.

### 2. Multimodal Input/Output Proxy Flow
1. **Trigger:** The local app detects a wake word, user typing a message, or sees a severe spike in RAM.
2. **App -> Backend:** The app captures audio, text, or a screenshot (Image Bytes) combined with `SystemMetricsData` and sends it to the remote backend as a MessagePack payload.
3. **Backend -> Gemini:** The `ws_server` hands the payload to the `router`, which passes it to the `agent` layer. The agent layer formats the bytes and metrics precisely as a Multimodal prompt for Gemini.
4. **Gemini -> Backend -> App:** 
    - If Gemini responds with a tool call (e.g. "Take a screenshot" or "Kill Chrome"), the backend receives this and sends a `ServerToolAction` containing a unique `call_id` to the App over the WebSocket. The App physically executes this logic on the user's OS, returns a `ClientToolResult` with the identical `call_id` to the Backend, which forwards it immediately to Gemini.
    - If Gemini formulates a final textual or audio response, the backend constructs a `ServerAudio` or `ServerText` object and proxies it to the Desktop GUI, where the TTS is played or text is displayed.

## Phases of Development
Development will strictly follow these phases:

### Phase 1: Foundation & Data Contracts
- Setup project folder structure for App and Layered Backend.
- Define `requirements.txt`.
- Implement `shared/schemas.py` corresponding to the Pydantic data schemas provided.

### Phase 2: Remote Backend & AI Orchestration
- Create FastAPI WebSocket server.
- Connect the Gemini multimodal API as a client within the Agent layer.
- Setup tool schemas for the Gemini agent.
- Implement the router to parse MsgPack payloads and bridge Server vs Agent logic.

### Phase 3: Native Interface & Event Loop
- Build `CustomTkinter` UI shell on the main thread.
- Add text chat interface, fallback manual command input.
- Add "Debug / Live Feed" panel and Wake Word status label.

### Phase 4: Telemetry, Workers & Proxy Execution
- Wire up daemon threads/`asyncio` for hardware monitoring (RAM, CPU, memory, Disk) & screenshots.
- Implement local system tool wrappers for executing AI actions in `app/core/tools.py`.
- Establish proxy action mappings (execute tool calls sent remotely from backend and return exact `call_id`).

### Phase 5: Audio Pipeline & Wake Word Integration
- Implement `PyAudio` producer/consumer queues for mic input.
- Setup Jitter Buffer queue for incoming audio playback.
- Integrate offline wake word detection (`pvporcupine`).

## Verification Plan
After each phase, we will manually test the implemented modules or components to ensure they meet the [PROJECT.md](file:///home/skndash96/code/system-caretaker/PROJECT.md) requirements.
- Phase 1: Schemas valid and successfully imported.
- Phase 2: Mock websocket client successfully communicates with backend.
- Phase 3: GUI displays correctly without freezing.
- Phase 4: Telemetry works; test tool proxies.
- Phase 5: Voice chat integration tested fully end-to-end.
