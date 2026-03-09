import os
import sys

# Ensure the root directory is in the PYTHONPATH if run without -m
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.gui.main_window import MainWindow
from app.core.websocket_client import SystemCaretakerClient


def main():
    app = MainWindow()

    # Send a boot message
    app.debug_panel.append_log(
        "System Caretaker GUI initialized natively.", level="SYSTEM"
    )
    app.chat_panel.append_message(
        "System", "Welcome to System Caretaker! Type a manual command below."
    )

    def on_log(level, msg):
        app.add_ui_job(lambda: app.debug_panel.append_log(msg, level=level))

    def on_chat_msg(sender, msg):
        app.add_ui_job(lambda: app.chat_panel.append_message(sender, msg))

    client = SystemCaretakerClient("ws://localhost:8000/ws", on_log, on_chat_msg)
    app.ws_client = client
    client.start()

    # Run the main Native OS UI threading loop
    app.mainloop()

    # Cleanup when window closed
    client.stop()


if __name__ == "__main__":
    main()
