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

    def _hide_to_tray(self):
        self.withdraw()  # Hide UI
        self._spawn_tray_icon()

    def _spawn_tray_icon(self):
        from PIL import Image, ImageDraw
        import pystray
        import threading

        # Generate a cool default icon on the fly
        image = Image.new("RGB", (64, 64), color=(30, 30, 30))
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 48, 48), fill=(0, 150, 255))
        draw.ellipse((24, 24, 40, 40), fill=(255, 255, 255))

        def show_window(icon, item):
            icon.stop()
            self.after(0, self.deiconify)  # Safely bring back UI on main thread

        def quit_app(icon, item):
            icon.stop()
            self.after(0, self.quit)  # Stop mainloop, cleanly terminating everything

        menu = pystray.Menu(
            pystray.MenuItem("Show UI", show_window, default=True),
            pystray.MenuItem("Quit Daemon", quit_app),
        )

        self.tray_icon = pystray.Icon(
            "system_caretaker", image, "System Caretaker", menu
        )

        # Run pystray blocking loop in a bg thread
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

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
