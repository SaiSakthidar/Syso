import os
import sys

# Ensure the root directory is in the PYTHONPATH if run without -m
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.gui.main_window import MainWindow


def main():
    app = MainWindow()

    # Send a boot message
    app.debug_panel.append_log(
        "System Caretaker GUI initialized natively.", level="SYSTEM"
    )
    app.chat_panel.append_message(
        "System", "Welcome to System Caretaker! Type a manual command below."
    )

    # Run the main Native OS UI threading loop
    app.mainloop()


if __name__ == "__main__":
    main()
