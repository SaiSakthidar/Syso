"""
SettingsPanel — System configuration dashboard.

Layout (top → bottom)
─────────────────────
  [header_canvas]      ← gradient strip with "Settings" title
  [settings_scroll]    ← CTkScrollableFrame with settings controls
    • Voice Profile selector with description
    • Volume control slider
"""

import tkinter as tk
import customtkinter as ctk
from typing import Callable, Optional, Dict, Any
import json
from pathlib import Path

from app.gui import theme


class SettingsPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_back: Callable[[], None],
        on_settings_change: Callable[[str, Any], None],
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=theme.RADIUS_LG,
            fg_color=(theme.LIGHT_PANEL, theme.DARK_PANEL),
            **kwargs,
        )
        self.on_back = on_back
        self.on_settings_change = on_settings_change

        # Available voices from backend config
        self.available_voices = {
            "zephyr": {"name": "Zephyr", "description": "Bright"},
            "puck": {"name": "Puck", "description": "Upbeat"},
            "charon": {"name": "Charon", "description": "Informative"},
            "kore": {"name": "Kore", "description": "Firm"},
            "fenrir": {"name": "Fenrir", "description": "Excitable"},
            "leda": {"name": "Leda", "description": "Youthful"},
            "orus": {"name": "Orus", "description": "Firm"},
            "aoede": {"name": "Aoede", "description": "Breezy"},
            "callirrhoe": {"name": "Callirrhoe", "description": "Easy-going"},
            "autonoe": {"name": "Autonoe", "description": "Bright"},
            "enceladus": {"name": "Enceladus", "description": "Breathy"},
            "iapetus": {"name": "Iapetus", "description": "Clear"},
            "umbriel": {"name": "Umbriel", "description": "Easy-going"},
            "algieba": {"name": "Algieba", "description": "Smooth"},
            "despina": {"name": "Despina", "description": "Smooth"},
            "erinome": {"name": "Erinome", "description": "Clear"},
            "algenib": {"name": "Algenib", "description": "Gravelly"},
            "rasalgethi": {"name": "Rasalgethi", "description": "Informative"},
            "laomedeia": {"name": "Laomedeia", "description": "Upbeat"},
            "achernar": {"name": "Achernar", "description": "Soft"},
            "alnilam": {"name": "Alnilam", "description": "Firm"},
            "schedar": {"name": "Schedar", "description": "Even"},
            "gacrux": {"name": "Gacrux", "description": "Mature"},
            "pulcherrima": {"name": "Pulcherrima", "description": "Forward"},
            "achird": {"name": "Achird", "description": "Friendly"},
            "zubenelgenubi": {"name": "Zubenelgenubi", "description": "Casual"},
            "vindemiatrix": {"name": "Vindemiatrix", "description": "Gentle"},
            "sadachbia": {"name": "Sadachbia", "description": "Lively"},
            "sadaltager": {"name": "Sadaltager", "description": "Knowledgeable"},
            "sulafat": {"name": "Sulafat", "description": "Warm"},
        }

        # Load current settings
        self.settings = self._load_settings()

        # Grid layout rows:  0=header  1=content_scroll
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_content()

    # ── Header (Canvas gradient + Back button) ────────────────────────────────

    def _build_header(self):
        header_frame = ctk.CTkFrame(
            self,
            height=62,
            fg_color=(theme.LIGHT_PANEL, theme.DARK_PANEL),
            corner_radius=0,
        )
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_propagate(False)

        # Canvas gradient background
        self._hdr_canvas = tk.Canvas(
            header_frame,
            height=62,
            highlightthickness=0,
            bd=0,
        )
        self._hdr_canvas.pack(fill="both", expand=True)
        self._hdr_canvas.bind("<Configure>", self._redraw_header)
        self.after(20, self._redraw_header)

        # Back button + Title
        controls_frame = ctk.CTkFrame(
            header_frame,
            fg_color="transparent",
            width=500,
            height=38,
        )
        controls_frame.place(x=20, y=12)

        back_btn = ctk.CTkButton(
            controls_frame,
            text="← Back",
            width=70,
            height=32,
            fg_color=theme.GREEN_PRIMARY,
            hover_color=theme.GREEN_HOVER,
            command=self.on_back,
            font=("Inter", 11, "bold"),
        )
        back_btn.pack(side="left", padx=(0, 12))

        title_label = ctk.CTkLabel(
            controls_frame,
            text="Settings",
            font=("Inter", 18, "bold"),
            text_color=(theme.LIGHT_TEXT, theme.DARK_TEXT),
        )
        title_label.pack(side="left")

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

        t_rgb = theme.hex_to_rgb(top)
        b_rgb = theme.hex_to_rgb(bot)
        for y in range(h):
            frac = y / max(h - 1, 1)
            r = int(t_rgb[0] + (b_rgb[0] - t_rgb[0]) * frac)
            g = int(t_rgb[1] + (b_rgb[1] - t_rgb[1]) * frac)
            b_val = int(t_rgb[2] + (b_rgb[2] - t_rgb[2]) * frac)
            color = f"#{r:02x}{g:02x}{b_val:02x}"
            cv.create_line(0, y, w, y, fill=color, width=1)

    # ── Content Area (Scrollable) ──────────────────────────────────────────────

    def _build_content(self):
        """Build scrollable settings content"""
        scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            label_text="",
        )
        scroll_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=theme.PAD_LG,
            pady=theme.PAD_LG,
        )
        scroll_frame.grid_columnconfigure(0, weight=1)

        # Section 1: Voice Profile
        self._build_voice_section(scroll_frame)

        # Section 2: Volume Control
        self._build_volume_section(scroll_frame)

    def _build_voice_section(self, parent):
        """Voice profile selector with dropdown and description"""
        section_frame = ctk.CTkFrame(
            parent,
            fg_color=(theme.LIGHT_SURFACE, theme.DARK_SURFACE),
            corner_radius=theme.RADIUS_MD,
        )
        section_frame.grid(row=0, column=0, sticky="ew", pady=theme.PAD_MD)
        section_frame.grid_columnconfigure(0, weight=1)

        # Title
        title_label = ctk.CTkLabel(
            section_frame,
            text="Voice Profile",
            font=("Inter", 14, "bold"),
            text_color=(theme.LIGHT_TEXT, theme.DARK_TEXT),
        )
        title_label.grid(row=0, column=0, sticky="w", padx=theme.PAD_MD, pady=(theme.PAD_MD, theme.PAD_SM))

        # Voice dropdown - display format: "Name - Description"
        # Create mapping of display names to voice keys for reverse lookup
        self.voice_display_to_key = {}
        voice_options = []
        for key in self.available_voices.keys():
            voice_info = self.available_voices[key]
            display_name = f"{voice_info['name']} - {voice_info['description']}"
            voice_options.append(display_name)
            self.voice_display_to_key[display_name] = key

        current_voice = self.settings.get("voice", "aoede")
        current_voice_info = self.available_voices[current_voice]
        current_display = f"{current_voice_info['name']} - {current_voice_info['description']}"

        self.voice_dropdown = ctk.CTkComboBox(
            section_frame,
            values=voice_options,
            command=self._on_voice_changed,
            fg_color=(theme.LIGHT_ELEVATED, theme.DARK_ELEVATED),
            button_color=(theme.GREEN_PRIMARY, theme.GREEN_HOVER),
            button_hover_color=theme.GREEN_HOVER,
            state="readonly",
        )
        self.voice_dropdown.set(current_display)
        self.voice_dropdown.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=theme.PAD_MD,
            pady=theme.PAD_SM,
        )

        # Voice description (will be updated on selection)
        self.voice_desc_label = ctk.CTkLabel(
            section_frame,
            text=f"Description: {self.available_voices[current_voice]['description']}",
            font=("Inter", 10),
            text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED),
            wraplength=300,
            justify="left",
        )
        self.voice_desc_label.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=theme.PAD_MD,
            pady=(theme.PAD_SM, theme.PAD_MD),
        )

    def _build_volume_section(self, parent):
        """Volume control slider"""
        section_frame = ctk.CTkFrame(
            parent,
            fg_color=(theme.LIGHT_SURFACE, theme.DARK_SURFACE),
            corner_radius=theme.RADIUS_MD,
        )
        section_frame.grid(row=1, column=0, sticky="ew", pady=theme.PAD_MD)
        section_frame.grid_columnconfigure(0, weight=1)

        # Title with current value display
        title_frame = ctk.CTkFrame(section_frame, fg_color="transparent")
        title_frame.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=theme.PAD_MD,
            pady=(theme.PAD_MD, theme.PAD_SM),
        )
        title_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            title_frame,
            text="Voice Volume",
            font=("Inter", 14, "bold"),
            text_color=(theme.LIGHT_TEXT, theme.DARK_TEXT),
        )
        title_label.pack(side="left")

        self.volume_value_label = ctk.CTkLabel(
            title_frame,
            text=f"{int(self.settings.get('volume', 100))}%",
            font=("Inter", 12, "bold"),
            text_color=theme.GREEN_PRIMARY,
        )
        self.volume_value_label.pack(side="right")

        # Volume slider
        self.volume_slider = ctk.CTkSlider(
            section_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            command=self._on_volume_changed,
            fg_color=(theme.LIGHT_BORDER, theme.DARK_BORDER),
            progress_color=theme.GREEN_PRIMARY,
            button_color=theme.GREEN_PRIMARY,
            button_hover_color=theme.GREEN_HOVER,
        )
        self.volume_slider.set(self.settings.get("volume", 100))
        self.volume_slider.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=theme.PAD_MD,
            pady=(theme.PAD_SM, theme.PAD_MD),
        )

        # Info text
        info_label = ctk.CTkLabel(
            section_frame,
            text="Adjust the volume for voice output",
            font=("Inter", 10),
            text_color=(theme.LIGHT_MUTED, theme.DARK_MUTED),
        )
        info_label.grid(
            row=2,
            column=0,
            sticky="w",
            padx=theme.PAD_MD,
            pady=(0, theme.PAD_MD),
        )

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_voice_changed(self, choice: str):
        """Handle voice profile selection"""
        # Use the mapping to get voice key from display name
        voice_key = self.voice_display_to_key.get(choice)
        if voice_key and voice_key in self.available_voices:
            voice_info = self.available_voices[voice_key]
            self.voice_desc_label.configure(
                text=f"Description: {voice_info['description']}"
            )
            self.settings["voice"] = voice_key
            self._save_settings()
            self.on_settings_change("voice", voice_key)

    def _on_volume_changed(self, value: str):
        """Handle volume slider change"""
        volume = int(float(value))
        self.volume_value_label.configure(text=f"{volume}%")
        self.settings["volume"] = volume
        self._save_settings()
        self.on_settings_change("volume", volume)

    # ── Preferences Management ─────────────────────────────────────────────────

    def _load_settings(self) -> dict:
        """Load settings from file"""
        settings_file = Path("data/app_settings.json")
        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        # Default settings
        return {
            "voice": "aoede",
            "volume": 100,
        }

    def _save_settings(self) -> None:
        """Save settings to file"""
        settings_file = Path("data/app_settings.json")
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_file, "w") as f:
            json.dump(self.settings, f, indent=2)
