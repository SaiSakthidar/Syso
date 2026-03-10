import os
import sys

# Ensure the root directory is in the PYTHONPATH if run without -m
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.gui.main_window import MainWindow
from app.core.websocket_client import SystemCaretakerClient
from dotenv import load_dotenv

load_dotenv()


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

    def on_chat_msg(sender, msg, is_chunk=False):
        app.add_ui_job(lambda: app.chat_panel.append_message(sender, msg, is_chunk))

    def on_wake_word(state: bool):
        app.add_ui_job(lambda: app.chat_panel.set_wake_word_status(state))
        if state:
            app.add_ui_job(
                lambda: app.chat_panel.append_message("System", "Listening...")
            )

    client = SystemCaretakerClient("ws://localhost:8000/ws", on_log, on_chat_msg)
    app.ws_client = client

    from app.core.audio_pipeline import AudioPipeline

    pipeline = AudioPipeline(
        on_log=on_log,
        on_wake_word=on_wake_word,
        on_audio_payload=lambda p: client.enqueue_payload(p),
    )
    client.set_audio_pipeline(pipeline)

    pipeline.start()
    client.start()

    # Run the main Native OS UI threading loop
    app.mainloop()

    # Cleanup when window closed
    pipeline.stop()
    client.stop()


if __name__ == "__main__":
    main()
