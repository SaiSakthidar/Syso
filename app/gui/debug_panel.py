import customtkinter as ctk
import datetime


class DebugPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="Debug / Live Feed",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.title_label.pack(side="left")

        # 2. Log History
        self.log_textbox = ctk.CTkTextbox(
            self,
            wrap="none",
            state="disabled",
            font=ctk.CTkFont(family="Courier", size=12),
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    def append_log(self, text: str, level: str = "INFO"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        log_line = f"[{timestamp}] [{level}] {text}\n"

        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", log_line)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
