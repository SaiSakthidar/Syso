import customtkinter as ctk
import queue
from app.gui.chat_panel import ChatPanel
from app.gui.debug_panel import DebugPanel

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("System Caretaker - Copilot")
        self.geometry("900x600")

        # Grid config: 1 row, 2 columns (chat on left, debug on right)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)  # Chat takes 1x space
        self.grid_columnconfigure(1, weight=1)  # Debug takes 1x space

        # UI Queue for thread-safe cross-thread UI updates
        self.ui_queue = queue.Queue()

        self._create_widgets()

        # Intercept window close to hide to tray
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        # Start checking the queue for updates
        self.after(100, self._process_ui_queue)

        # Always run tray icon
        self._spawn_tray_icon()

    def _hide_to_tray(self):
        self.withdraw()  # Hide UI

    def _spawn_tray_icon(self):
        from PIL import Image
        import pystray
        import threading
        import os

        # Load the custom jarvis icon
        icon_path = os.path.join(
            os.path.dirname(__file__), "..", "assets", "jarvis.png"
        )
        self.base_tray_image = Image.open(icon_path)
        self._is_recording = False
        self._tray_blink_state = False

        def show_window(icon, item):
            self.after(0, self.deiconify)  # Safely bring back UI on main thread

        def quit_app(icon, item):
            icon.stop()
            self.after(0, self.quit)  # Stop mainloop, cleanly terminating everything

        menu = pystray.Menu(
            pystray.MenuItem("Show UI", show_window, default=True),
            pystray.MenuItem("Quit Daemon", quit_app),
        )

        self.tray_icon = pystray.Icon(
            "system_caretaker", self.base_tray_image, "System Caretaker", menu
        )

        # Run pystray blocking loop in a bg thread
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def set_tray_recording_state(self, is_recording: bool):
        if not hasattr(self, "tray_icon"):
            return
        self._is_recording = is_recording
        if is_recording:
            self._tray_blink_state = True
            self._animate_tray()
        else:
            self.tray_icon.icon = self.base_tray_image

    def _animate_tray(self):
        if not self._is_recording or not hasattr(self, "base_tray_image"):
            return
        from PIL import ImageDraw

        animated_image = self.base_tray_image.copy()
        if self._tray_blink_state:
            draw = ImageDraw.Draw(animated_image)
            w, h = animated_image.size
            r = w // 5
            draw.ellipse([w - r * 2, h - r * 2, w, h], fill="red")

        self.tray_icon.icon = animated_image
        self._tray_blink_state = not self._tray_blink_state
        self.after(500, self._animate_tray)

    def _create_widgets(self):
        self.chat_panel = ChatPanel(self, on_submit=self._handle_user_input)
        self.chat_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.debug_panel = DebugPanel(self)
        self.debug_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

    def _handle_user_input(self, text: str):
        # Fallback manual text input handling
        from shared.schemas import ClientText

        self.debug_panel.append_log(
            f"Handling manual text command: '{text}'", level="SYSTEM"
        )
        if hasattr(self, "ws_client") and self.ws_client:
            self.ws_client.enqueue_payload(ClientText(text=text))
        else:
            self.debug_panel.append_log("WS Client not attached yet.", level="ERROR")

    def add_ui_job(self, job_fn):
        """Thread-safe way to update UI from daemon threads."""
        self.ui_queue.put(job_fn)

    def _process_ui_queue(self):
        try:
            while True:
                job_fn = self.ui_queue.get_nowait()
                job_fn()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_ui_queue)
