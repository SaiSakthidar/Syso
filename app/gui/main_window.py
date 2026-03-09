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

        # Start checking the queue for updates
        self.after(100, self._process_ui_queue)

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
