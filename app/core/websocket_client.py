import asyncio
import threading
import websockets
import msgpack
from typing import Optional, Callable
from pydantic import TypeAdapter

from shared.schemas import (
    WsClientPayload,
    WsServerPayload,
    ClientMetrics,
    ClientToolResult,
    ServerToolAction,
)
from app.core.telemetry import telemetry
from app.core.tools import LOCAL_TOOLS

_server_payload_adapter = TypeAdapter(WsServerPayload)


class SystemCaretakerClient:
    def __init__(
        self,
        uri: str,
        on_log: Callable[[str, str], None],
        on_chat_msg: Callable[[str, str], None],
    ):
        self.uri = uri
        self.on_log = on_log
        self.on_chat_msg = on_chat_msg

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._thread: Optional[threading.Thread] = None
        self._outbound_queue: Optional[asyncio.Queue] = None

        self.running = False

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def enqueue_payload(self, payload: WsClientPayload):
        """Thread-safe way for GUI to send to Backend"""
        if self._loop and self._outbound_queue:
            asyncio.run_coroutine_threadsafe(
                self._outbound_queue.put(payload), self._loop
            )

    def _run_async_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._outbound_queue = asyncio.Queue()

        self._loop.run_until_complete(self._main_connection_loop())

    async def _main_connection_loop(self):
        while self.running:
            try:
                self.on_log("INFO", f"Connecting to {self.uri}...")
                async with websockets.connect(self.uri) as ws:
                    self._ws = ws
                    self.on_log("INFO", "Connected to Backend WS Server.")

                    # Run listener, sender, and telemetry tasks concurrently
                    consumer = asyncio.create_task(self._listen_loop())
                    producer = asyncio.create_task(self._send_loop())
                    telemetry_worker = asyncio.create_task(self._telemetry_loop())

                    done, pending = await asyncio.wait(
                        [consumer, producer, telemetry_worker],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()
            except Exception as e:
                self.on_log("ERROR", f"Connection failed: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    async def _listen_loop(self):
        async for raw_message in self._ws:
            try:
                data = msgpack.unpackb(raw_message, raw=False)
                payload: WsServerPayload = _server_payload_adapter.validate_python(data)

                if payload.type == "agent_text":
                    self.on_chat_msg("System Caretaker", payload.text)

                elif payload.type == "error":
                    self.on_log(
                        "ERROR", f"Backend replied with error: {payload.error_msg}"
                    )

                elif payload.type == "tool_action":
                    await self._handle_tool_action(payload)

                elif payload.type == "agent_audio":
                    if hasattr(self, "audio_pipeline") and self.audio_pipeline:
                        self.audio_pipeline.queue_playback(payload.audio_bytes)
                        self.on_log(
                            "SYSTEM",
                            f"Queuing received audio chunk (~{len(payload.audio_bytes) // 1024}KB) for playback.",
                        )

            except Exception as e:
                self.on_log("ERROR", f"Invalid payload from server: {e}")

    def set_audio_pipeline(self, pipeline):
        self.audio_pipeline = pipeline

    async def _handle_tool_action(self, action: ServerToolAction):
        self.on_log(
            "SYSTEM",
            f"Agent requested Tool: {action.tool_name} with args: {action.tool_args}",
        )
        self.on_chat_msg("System", f"Executing local tool: `{action.tool_name}`...")

        if action.tool_name not in LOCAL_TOOLS:
            err = f"Unknown tool: {action.tool_name}"
            self.on_log("ERROR", err)
            result = ClientToolResult(
                call_id=action.call_id,
                tool_name=action.tool_name,
                status="error",
                message=err,
            )
            await self._outbound_queue.put(result)
            return

        # Execute
        try:
            func = LOCAL_TOOLS[action.tool_name]
            # Since these are synchronous OS tools, wrap them in to_thread so we don't block asyncio WS
            res_dict = await asyncio.to_thread(func, **action.tool_args)

            # If the tool returned an image, extract it and queue a ClientImage payload
            if "image_bytes" in res_dict:
                from shared.schemas import ClientImage

                img_bytes = res_dict.pop("image_bytes")  # Remove it from the text dict

                img_payload = ClientImage(image_bytes=img_bytes)
                await self._outbound_queue.put(img_payload)
                self.on_log(
                    "SYSTEM",
                    f"Tool returned Image payload (~{len(img_bytes) // 1024}KB) - queued separate multimodal attachment.",
                )

            status = res_dict.get("status", "success")
            msg = str(res_dict)
            self.on_log("SYSTEM", f"Tool {action.tool_name} outcome: {status}")

            result = ClientToolResult(
                call_id=action.call_id,
                tool_name=action.tool_name,
                status=status,
                message=msg,
            )
            await self._outbound_queue.put(result)

        except TypeError as e:
            await self._outbound_queue.put(
                ClientToolResult(
                    call_id=action.call_id,
                    tool_name=action.tool_name,
                    status="error",
                    message=f"Arg mismatch: {e}",
                )
            )
        except Exception as e:
            await self._outbound_queue.put(
                ClientToolResult(
                    call_id=action.call_id,
                    tool_name=action.tool_name,
                    status="error",
                    message=str(e),
                )
            )

    async def _send_loop(self):
        while True:
            payload: WsClientPayload = await self._outbound_queue.get()
            try:
                data_dict = payload.model_dump()
                raw_bytes = msgpack.packb(data_dict, use_bin_type=True)
                await self._ws.send(raw_bytes)
            except Exception as e:
                self.on_log("ERROR", f"Failed to send payload: {e}")

    async def _telemetry_loop(self):
        while True:
            # Send metrics every 15 seconds
            try:
                metrics = telemetry.get_current_metrics()
                # If memory jumps > 90%, immediately signal the UI as a spike alert?
                # Right now, just send the metrics object.
                payload = ClientMetrics(data=metrics)

                # Check for resource spike trigger - (CPU > 90% or RAM > 90%)
                if metrics.cpu_percent > 90.0 or metrics.memory_percent > 90.0:
                    self.on_log(
                        "SYSTEM",
                        f"Resource Spike detected! CPU: {metrics.cpu_percent}% RAM: {metrics.memory_percent}%",
                    )

                await self._outbound_queue.put(payload)
            except Exception as e:
                self.on_log("ERROR", f"Telemetry thread error: {e}")

            await asyncio.sleep(15)
