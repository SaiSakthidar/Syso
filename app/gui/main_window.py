"""
MainWindow — Application shell.

• System-aware appearance (auto light/dark) with green colour theme
• Deep navy background matching the dark palette
• Two-panel layout: chat (weight=3) | debug sidebar (weight=2)
• System tray with green recording blink dot
"""

import queue
import threading
import customtkinter as ctk

from app.gui import theme
from app.gui.chat_panel import ChatPanel
from app.gui.debug_panel import DebugPanel

# Apply theme BEFORE any widget is created
theme.apply_theme()


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("System Caretaker")
        self.geometry("1160x720")
        self.minsize(860, 560)

        # Deep navy root background
        self.configure(fg_color=(theme.LIGHT_ROOT, theme.DARK_ROOT))

        # Grid: chat(3) | debug sidebar(2)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)

        self.ui_queue = queue.Queue()

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.after(100, self._process_ui_queue)
        self._spawn_tray_icon()

    # ── Widgets ───────────────────────────────────────────────────────────────

    def _create_widgets(self):
        self.chat_panel = ChatPanel(self, on_submit=self._handle_user_input)
        self.chat_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(theme.PAD_LG, theme.PAD_SM),
            pady=theme.PAD_LG,
        )

        self.debug_panel = DebugPanel(self)
        self.debug_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(theme.PAD_SM, theme.PAD_LG),
            pady=theme.PAD_LG,
        )

    # ── User input ────────────────────────────────────────────────────────────

    def _handle_user_input(self, text: str):
        from shared.schemas import ClientText

        self.debug_panel.append_log(f"Manual command: '{text}'", level="SYSTEM")
        if hasattr(self, "ws_client") and self.ws_client:
            self.ws_client.enqueue_payload(ClientText(text=text))
        else:
            self.debug_panel.append_log("WS Client not attached yet.", level="ERROR")

    # ── UI queue ──────────────────────────────────────────────────────────────

    def add_ui_job(self, job_fn):
        """Thread-safe: enqueue a callable to run on the main thread."""
        self.ui_queue.put(job_fn)

    def _process_ui_queue(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_ui_queue)

    # ── System tray ───────────────────────────────────────────────────────────

    def _hide_to_tray(self):
        self.withdraw()

    def _spawn_tray_icon(self):
        import os
        from PIL import Image
        import pystray

        icon_path = os.path.join(
            os.path.dirname(__file__), "..", "assets", "jarvis.png"
        )
        self.base_tray_image = Image.open(icon_path)
        self._is_recording = False
        self._tray_blink_on = False

        menu = pystray.Menu(
            pystray.MenuItem(
                "Show UI", lambda _i, _it: self.after(0, self.deiconify), default=True
            ),
            pystray.MenuItem(
                "Quit Daemon", lambda icon, _it: (icon.stop(), self.after(0, self.quit))
            ),
        )
        self.tray_icon = pystray.Icon(
            "system_caretaker", self.base_tray_image, "System Caretaker", menu
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def set_tray_recording_state(self, is_recording: bool):
        if not hasattr(self, "tray_icon"):
            return
        self._is_recording = is_recording
        if is_recording:
            self._tray_blink_on = True
            self._animate_tray()
        else:
            self.tray_icon.icon = self.base_tray_image

    def _animate_tray(self):
        if not self._is_recording or not hasattr(self, "base_tray_image"):
            return
        from PIL import ImageDraw

        img = self.base_tray_image.copy()
        draw = ImageDraw.Draw(img)
        if self._tray_blink_on:
            w, h = img.size
            r = w // 5
            draw.ellipse([w - r * 2, h - r * 2, w, h], fill=theme.GREEN_PRIMARY)

        self.tray_icon.icon = img
        self._tray_blink_on = not self._tray_blink_on
        self.after(500, self._animate_tray)
