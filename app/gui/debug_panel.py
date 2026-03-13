"""
DebugPanel — Sleek sidebar log viewer.

Features
────────
• Colour-coded severity: INFO blue, WARNING amber, ERROR red, SYSTEM purple
• Monospaced log body with muted timestamp column
• Clear button in header
• Matches the dark/light theme automatically via CTk tuples
"""

import datetime
import customtkinter as ctk

from app.gui import theme


class DebugPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=theme.RADIUS_LG,
            fg_color=(theme.LIGHT_PANEL, theme.DARK_PANEL),
            **kwargs,
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_log_view()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=theme.PAD_LG,
            pady=(theme.PAD_LG, theme.PAD_SM),
        )
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr,
            text="📋  Debug / Live Feed",
            font=ctk.CTkFont("Inter", 16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            hdr,
            text="Clear",
            font=ctk.CTkFont("Inter", 12),
            width=62,
            height=28,
            corner_radius=theme.RADIUS_PILL,
            fg_color="transparent",
            border_width=1,
            border_color=(theme.LIGHT_BORDER, theme.DARK_BORDER),
            hover_color=(theme.LIGHT_ELEVATED, theme.DARK_ELEVATED),
            command=self._clear,
        ).grid(row=0, column=1, sticky="e")

        # Thin accent divider
        ctk.CTkFrame(
            self,
            height=2,
            fg_color=(theme.LIGHT_BORDER, theme.DARK_BORDER),
            corner_radius=1,
        ).grid(row=0, column=0, sticky="sew", padx=theme.PAD_LG)

    # ── Log textbox ───────────────────────────────────────────────────────────

    def _build_log_view(self):
        self._log = ctk.CTkTextbox(
            self,
            wrap="none",
            state="disabled",
            font=ctk.CTkFont("JetBrains Mono", 13),
            corner_radius=theme.RADIUS_MD,
            border_width=1,
            border_color=(theme.LIGHT_BORDER, theme.DARK_BORDER),
        )
        self._log.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=theme.PAD_LG,
            pady=(theme.PAD_SM, theme.PAD_LG),
        )
        self._configure_tags()

    def _configure_tags(self):
        tb = self._log._textbox
        for level, color in theme.LOG_LEVEL_COLORS.items():
            tb.tag_config(f"lvl_{level}", foreground=color)
        tb.tag_config("ts", foreground=theme.DARK_MUTED)
        tb.tag_config("body", foreground="")  # inherits CTkTextbox fg

    # ── Public API ────────────────────────────────────────────────────────────

    def append_log(self, text: str, level: str = "INFO"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        ltag = (
            f"lvl_{level.upper()}"
            if level.upper() in theme.LOG_LEVEL_COLORS
            else "lvl_INFO"
        )

        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] ", "ts")
        self._log.insert("end", f"[{level.upper():7s}] ", ltag)
        self._log.insert("end", f"{text}\n", "body")
        self._log.see("end")
        self._log.configure(state="disabled")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
