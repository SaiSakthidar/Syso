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
    # Initialize attributes to prevent AttributeErrors during late binding callbacks
    app.ws_client = None

    from app.gui.login_window import LoginWindow
    
    # 1. Define UI Sync Callbacks first
    def on_log(level, msg):
        app.add_ui_job(lambda: app.debug_panel.append_log(msg, level=level))

    def on_chat_msg(sender, msg, is_chunk=False):
        app.add_ui_job(lambda: app.chat_panel.append_message(sender, msg, is_chunk))

    def on_wake_word(state: bool):
        app.add_ui_job(lambda: app.chat_panel.set_wake_word_status(state))
        if hasattr(app, "set_tray_recording_state"):
            app.add_ui_job(lambda: app.set_tray_recording_state(state))
        if state:
            app.add_ui_job(
                lambda: app.chat_panel.append_message("System", "Listening...")
            )

    # 2. Define Service Startup Logic
    client = None
    from app.core.audio_pipeline import AudioPipeline
    pipeline = AudioPipeline(
        on_log=on_log,
        on_wake_word=on_wake_word,
        on_audio_payload=lambda p: app.ws_client.enqueue_payload(p) if app.ws_client else None,
    )
    pipeline.start()

    def start_backend_services(uid: str):
        nonlocal client
        if app.ws_client:
            app.ws_client.stop()
            
        # Update client with real identity for cloud-aware backend
        # We use ?user_id= for the simple cloud architecture
        client = SystemCaretakerClient("ws://34.14.201.124:8000/ws", on_log, on_chat_msg, user_id=uid)
        app.ws_client = client
        client.set_audio_pipeline(pipeline)
        
        # Start networking
        client.start()
        
        # Refresh greeting with user name if available
        if uid != "guest":
            # For guest, greeting is already shown. For user, show welcome back.
            pass

    # 3. Define Auth Callbacks
    is_authenticated = False
    user_id = "guest"
    
    def on_login_complete(auth_data: dict):
        nonlocal is_authenticated, user_id
        is_authenticated = True
        user_info = auth_data.get("user_info", {})
        user_id = auth_data.get("user_id", "guest")
        
        user_name = user_info.get("name", "User")
        app.chat_panel.append_message(
            "System", f"Authentication successful! Welcome back, {user_name}."
        )
        start_backend_services(user_id)
        app.deiconify()

    def on_skip():
        app.chat_panel.append_message(
            "System", "Login skipped. Some features may be personalized once you sign in."
        )
        start_backend_services("guest")
        app.deiconify()

    # 4. Trigger Login Flow
    if not is_authenticated:
        app.withdraw()
        app.after(100, lambda: LoginWindow(app, on_login_complete, on_skip))

    # Send a boot message
    app.debug_panel.append_log(
        "System Caretaker GUI initialized natively.", level="SYSTEM"
    )
    app.chat_panel.append_message("System", "Welcome to Syso. Please sign in or skip to continue.")

    # Initial start with guest if already authenticated (e.g. state management)
    if is_authenticated:
        start_backend_services(user_id)

    # Run the main Native OS UI threading loop
    app.mainloop()

    # Cleanup when window closed
    pipeline.stop()
    if app.ws_client:
        app.ws_client.stop()


if __name__ == "__main__":
    main()
