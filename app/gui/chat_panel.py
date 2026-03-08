import customtkinter as ctk
from typing import Callable


class ChatPanel(ctk.CTkFrame):
    def __init__(self, master, on_submit: Callable[[str], None], **kwargs):
        super().__init__(master, **kwargs)

        self.on_submit = on_submit

        # Layout styling
        self.grid_rowconfigure(1, weight=1)  # Chat history takes up most space
        self.grid_columnconfigure(0, weight=1)

        # 1. Header (Wake Word Status)
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="Chat & Commands",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.title_label.pack(side="left")

        self.wake_word_label = ctk.CTkLabel(
            self.header_frame,
            text="Wake Word: SLEEPING 💤",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        self.wake_word_label.pack(side="right")

        # 2. Chat History (Scrollable Box)
        self.chat_history = ctk.CTkTextbox(self, wrap="word", state="disabled")
        self.chat_history.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # 3. Input Area
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.input_entry = ctk.CTkEntry(
            self.input_frame, placeholder_text="Type a manual command here..."
        )
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.input_entry.bind("<Return>", lambda event: self._submit_button_callback())

        self.submit_button = ctk.CTkButton(
            self.input_frame,
            text="Send",
            width=60,
            command=self._submit_button_callback,
        )
        self.submit_button.grid(row=0, column=1)

    def _submit_button_callback(self):
        text = self.input_entry.get().strip()
        if text:
            self.append_message("User", text)
            self.input_entry.delete(0, "end")
            self.on_submit(text)

    def append_message(self, sender: str, message: str):
        self.chat_history.configure(state="normal")
        self.chat_history.insert("end", f"{sender}: {message}\n\n")
        self.chat_history.see("end")
        self.chat_history.configure(state="disabled")

    def set_wake_word_status(self, is_listening: bool):
        if is_listening:
            self.wake_word_label.configure(
                text="Wake Word: LISTENING 🔴", text_color="red"
            )
        else:
            self.wake_word_label.configure(
                text="Wake Word: SLEEPING 💤", text_color="gray"
            )
