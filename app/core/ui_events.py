"""
ui_events.py — Lightweight thread-safe event bus for posting UI commands from tools to the main window.

Usage:
    # From a tool (any thread):
    ui_events.post("show_dashboard")

    # In main window (main thread, polled via after()):
    event = ui_events.poll()
    if event == "show_dashboard":
        open_dashboard()
"""

import queue

_event_queue: queue.Queue = queue.Queue()


def post(event_name: str) -> None:
    """Post a UI event from any thread."""
    _event_queue.put(event_name)


def poll() -> str | None:
    """Non-blocking poll. Returns event name or None."""
    try:
        return _event_queue.get_nowait()
    except queue.Empty:
        return None
