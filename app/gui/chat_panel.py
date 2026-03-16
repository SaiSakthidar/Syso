"""
ChatPanel — Gemini-style voice assistant chat interface.

Layout (top → bottom)
─────────────────────
  [header_canvas]      ← gradient strip with title + status badge
  [messages_scroll]    ← CTkScrollableFrame with MessageBubble widgets
  [orb_section]        ← large MicIndicator centred above input
  [input_bar]          ← entry + send button

Public surface (unchanged from v1 for compatibility)
────────────────────────────────────────────────────
  append_message(sender, message, is_chunk)
  set_wake_word_status(is_listening)
"""

import tkinter as tk
import customtkinter as ctk
from typing import Callable, Optional

from app.gui import theme
from app.gui.mic_indicator import MicIndicator


class ChatPanel(ctk.CTkFrame):
    def __init__(self, master, on_submit: Callable[[str], None], **kwargs):
        super().__init__(
            master,
            corner_radius=theme.RADIUS_LG,
            fg_color=(theme.LIGHT_PANEL, theme.DARK_PANEL),
            **kwargs,
        )
        self.on_submit = on_submit

        # Streamed-message tracking
        self._current_bubble: Optional["MessageBubble"] = None
        self.last_sender: Optional[str] = None
        self.was_last_chunk = False

        # Grid layout rows:  0=header  1=messages  2=orb  3=input
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_messages()
        self._build_orb_section()
        self._build_input_bar()

    # ── Header (Canvas gradient) ──────────────────────────────────────────────

    def _build_header(self):
        self._hdr_canvas = tk.Canvas(
            self,
            height=62,
            highlightthickness=0,
            bd=0,
        )
        self._hdr_canvas.grid(row=0, column=0, sticky="ew")
        self._hdr_canvas.bind("<Configure>", self._redraw_header)
        # Delayed first draw so widget dimensions are known
        self.after(20, self._redraw_header)

    def _redraw_header(self, _event=None):
        cv = self._hdr_canvas
        w = max(cv.winfo_width(), 400)
        h = cv.winfo_height() or 62
        cv.delete("all")

        dark = theme.is_dark()
        top = theme.HEADER_TOP if dark else theme.LIGHT_HEADER_TOP
        bot = theme.HEADER_BOTTOM if dark else theme.LIGHT_HEADER_BOTTOM
        bg = theme.DARK_PANEL if dark else theme.LIGHT_PANEL

        cv.configure(bg=bg)

        # Draw gradient strip (top → bottom) — each pixel row is one line
        t_rgb = theme.hex_to_rgb(top)
        b_rgb = theme.hex_to_rgb(bot)
        for y in range(h):
            frac = y / max(h - 1, 1)
            color = "#{:02x}{:02x}{:02x}".format(
                int(t_rgb[0] + (b_rgb[0] - t_rgb[0]) * frac),
                int(t_rgb[1] + (b_rgb[1] - t_rgb[1]) * frac),
                int(t_rgb[2] + (b_rgb[2] - t_rgb[2]) * frac),
            )
            cv.create_line(0, y, w, y, fill=color)

        # App title
        title_color = theme.GREEN_PRIMARY
        title_font = ("Inter", 18, "bold")
        cv.create_text(
            theme.PAD_XL,
            h // 2,
            text="⬡  System Caretaker",
            font=title_font,
            fill=title_color,
            anchor="w",
        )

        # Status badge drawn on canvas (right side)
        badge_text = getattr(self, "_badge_text", "  💤  Sleeping  ")
        badge_color = getattr(
            self, "_badge_color", theme.DARK_MUTED if dark else theme.LIGHT_MUTED
        )
        badge_bg = getattr(
            self, "_badge_bg", theme.DARK_ELEVATED if dark else theme.LIGHT_ELEVATED
        )

        badge_x = w - theme.PAD_XL
        badge_y = h // 2
        # Draw pill background
        tx0, ty0 = badge_x - 90, badge_y - 13
        tx1, ty1 = badge_x + 4, badge_y + 13
        radius = 12
        cv.create_arc(
            tx0,
            ty0,
            tx0 + 2 * radius,
            ty1,
            start=90,
            extent=180,
            fill=badge_bg,
            outline="",
        )
        cv.create_arc(
            tx1 - 2 * radius,
            ty0,
            tx1,
            ty1,
            start=270,
            extent=180,
            fill=badge_bg,
            outline="",
        )
        cv.create_rectangle(
            tx0 + radius, ty0, tx1 - radius, ty1, fill=badge_bg, outline=""
        )
        cv.create_text(
            (tx0 + tx1) // 2,
            badge_y,
            text=badge_text,
            fill=badge_color,
            font=("Inter", 11, "bold"),
            anchor="center",
        )

        # Green bottom accent line
        cv.create_line(0, h - 2, w, h - 2, fill=theme.GREEN_PRIMARY, width=2)

    def _update_badge(self, listening: bool):
        """Update badge state variables and redraw the header canvas."""
        dark = theme.is_dark()
        if listening:
            self._badge_text = "  🎙  Listening  "
            self._badge_color = "#ffffff"
            self._badge_bg = theme.GREEN_GLOW
        else:
            self._badge_text = "  💤  Sleeping  "
            self._badge_color = theme.DARK_MUTED if dark else theme.LIGHT_MUTED
            self._badge_bg = theme.DARK_ELEVATED if dark else theme.LIGHT_ELEVATED
        self._redraw_header()

    # ── Messages area ─────────────────────────────────────────────────────────

    def _build_messages(self):
        self._msgs = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=(theme.LIGHT_ELEVATED, theme.DARK_ELEVATED),
            scrollbar_button_hover_color=theme.GREEN_PRIMARY,
        )
        self._msgs.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self._msgs.grid_columnconfigure(0, weight=1)

    # ── Orb section ───────────────────────────────────────────────────────────

    def _build_orb_section(self):
        self._orb_container = ctk.CTkFrame(
            self,
            fg_color="transparent",
            height=180,
        )
        self._orb_container.grid(row=2, column=0, sticky="ew")
        self._orb_container.grid_propagate(False)

        self._mic_orb = MicIndicator(self._orb_container, size=140)
        self._mic_orb.place(relx=0.5, rely=0.44, anchor="center")

        self._status_label = ctk.CTkLabel(
            self._orb_container,
            text="Say Hello Syso to begin…",
            font=ctk.CTkFont("Inter", 13),
            text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED),
        )
        self._status_label.place(relx=0.5, rely=0.87, anchor="center")

    # ── Input bar ─────────────────────────────────────────────────────────────

    def _build_input_bar(self):
        bar = ctk.CTkFrame(
            self,
            fg_color=(theme.LIGHT_SURFACE, theme.DARK_SURFACE),
            corner_radius=0,
        )
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=theme.PAD_XL,
            pady=theme.PAD_MD,
        )
        inner.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(
            inner,
            placeholder_text="Message System Caretaker…",
            font=ctk.CTkFont("Inter", 14),
            corner_radius=theme.RADIUS_PILL,
            border_width=2,
            border_color=(theme.LIGHT_BORDER, theme.DARK_BORDER),
            fg_color=(theme.LIGHT_ELEVATED, theme.DARK_ELEVATED),
            height=48,
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, theme.PAD_SM))
        self._entry.bind("<Return>", lambda _e: self._on_submit())
        self._entry.bind(
            "<FocusIn>",
            lambda _e: self._entry.configure(border_color=theme.GREEN_PRIMARY),
        )
        self._entry.bind(
            "<FocusOut>",
            lambda _e: self._entry.configure(
                border_color=(theme.LIGHT_BORDER, theme.DARK_BORDER)
            ),
        )

        self._send_btn = ctk.CTkButton(
            inner,
            text="➤",
            font=ctk.CTkFont("Inter", 20, weight="bold"),
            width=48,
            height=48,
            corner_radius=theme.RADIUS_PILL,
            fg_color=theme.GREEN_PRIMARY,
            hover_color=theme.GREEN_HOVER,
            text_color="white",
            command=self._on_submit,
        )
        self._send_btn.grid(row=0, column=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_wake_word_status(self, is_listening: bool):
        """Start/stop the orb animation and update the status labels."""
        self._mic_orb.set_active(is_listening)
        self._update_badge(is_listening)
        if is_listening:
            self._status_label.configure(
                text="Listening…",
                text_color=theme.GREEN_PRIMARY,
            )
        else:
            self._status_label.configure(
                text="Say Hello Syso to begin…",
                text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED),
            )

    def append_message(self, sender: str, message: str, is_chunk: bool = False):
        """Insert or extend a message bubble."""
        is_user = sender.lower() == "user"
        new_sender = sender != self.last_sender

        if is_chunk:
            if not new_sender and self._current_bubble is not None:
                self._current_bubble.append_text(message)
            else:
                self._current_bubble = self._add_bubble(sender, is_user)
                self._current_bubble.set_text(message)
        else:
            if (
                self.last_sender == sender
                and self.was_last_chunk
                and self._current_bubble is not None
            ):
                self._current_bubble.append_text(message)
            else:
                self._current_bubble = self._add_bubble(sender, is_user)
                self._current_bubble.set_text(message)

        self.last_sender = sender
        self.was_last_chunk = is_chunk
        self._scroll_bottom()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _add_bubble(self, sender: str, is_user: bool) -> "MessageBubble":
        row = ctk.CTkFrame(self._msgs, fg_color="transparent")
        row.pack(fill="x", padx=theme.PAD_LG, pady=(theme.PAD_XS, 0))

        bubble = MessageBubble(row, sender=sender, is_user=is_user)
        if is_user:
            bubble.pack(side="right", pady=theme.PAD_XS)
        else:
            bubble.pack(side="left", pady=theme.PAD_XS)
        return bubble

    def _scroll_bottom(self):
        self.after(60, lambda: self._msgs._parent_canvas.yview_moveto(1.0))

    def _on_submit(self):
        text = self._entry.get().strip()
        if not text:
            return
        self.append_message("User", text)
        self._entry.delete(0, "end")
        self.on_submit(text)


# ── MessageBubble ─────────────────────────────────────────────────────────────


class MessageBubble(ctk.CTkFrame):
    """
    A single rounded chat bubble.
    User bubbles: right-aligned, green-tinted dark background.
    Assistant bubbles: left-aligned, slightly lighter dark background.
    """

    _WRAP = 460  # max wraplength in pixels

    def __init__(self, master, sender: str, is_user: bool = False, **kwargs):
        bubble_bg = (
            (theme.BUBBLE_USER_LIGHT, theme.BUBBLE_USER_DARK)
            if is_user
            else (theme.BUBBLE_ASST_LIGHT, theme.BUBBLE_ASST_DARK)
        )
        super().__init__(
            master,
            fg_color=bubble_bg,
            corner_radius=theme.RADIUS_XL,
            **kwargs,
        )
        self._text = ""
        self._is_user = is_user

        # Sender label (hidden for user to keep it clean)
        if not is_user:
            ctk.CTkLabel(
                self,
                text=sender,
                font=ctk.CTkFont("Inter", 11),
                text_color=theme.COLOR_INFO,
                anchor="w",
            ).pack(anchor="w", padx=theme.PAD_MD, pady=(theme.PAD_SM, 0))

        self._label = ctk.CTkLabel(
            self,
            text="",
            wraplength=self._WRAP,
            justify="left",
            font=ctk.CTkFont("Inter", 14),
            text_color=(theme.LIGHT_TEXT, theme.DARK_TEXT),
            anchor="w",
        )
        top_pad = theme.PAD_XS if not is_user else theme.PAD_MD
        self._label.pack(
            anchor="w",
            padx=theme.PAD_MD,
            pady=(top_pad, theme.PAD_MD),
        )

    def set_text(self, text: str):
        self._text = text
        self._label.configure(text=text)

    def append_text(self, chunk: str):
        self._text += chunk
        self._label.configure(text=self._text)
