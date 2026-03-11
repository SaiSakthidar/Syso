"""
MicIndicator — Gemini-style animated orb widget.

Idle  : small static coloured dot  (zero CPU)
Active: multi-layer soft-glow pulsing blob, colour-cycling at 30 fps

The glow is simulated by drawing concentric circles blended toward the
background colour at decreasing alpha — no real transparency needed.
"""

import math
import tkinter as tk
import customtkinter as ctk

from app.gui import theme


_FPS = 30
_FRAME_MS = 1000 // _FPS
_PULSE_SPEED = 0.055  # radians / frame
_COLOR_SPEED = 0.012  # color blend progress / frame


class MicIndicator(ctk.CTkFrame):
    """
    Parameters
    ----------
    size : int
        Width == height of the widget in pixels.
    """

    def __init__(self, master, size: int = 130, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._size = size
        self._active = False
        self._phase = 0.0  # pulse phase
        self._color_t = 0.0  # blend progress between consecutive orb colors
        self._color_idx = 0  # current base color index

        # The single canvas that does all drawing
        self._cv = tk.Canvas(
            self,
            width=size,
            height=size,
            highlightthickness=0,
            bd=0,
        )
        self._cv.pack()
        self._cv.bind("<Configure>", lambda _e: self._redraw())

        # Draw after the widget is mapped so _resolve_bg works
        self.after(10, self._redraw)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_active(self, active: bool):
        if active == self._active:
            return
        self._active = active
        if active:
            self._phase = 0.0
            self._color_t = 0.0
            self._color_idx = 0
            self._animate()
        else:
            self._redraw()  # draw idle state immediately

    # ── Animation loop ────────────────────────────────────────────────────────

    def _animate(self):
        if not self._active:
            return
        self._phase += _PULSE_SPEED
        self._color_t += _COLOR_SPEED
        if self._color_t >= 1.0:
            self._color_t -= 1.0
            self._color_idx = (self._color_idx + 1) % len(theme.ORB_COLORS)
        self._draw_active()
        self.after(_FRAME_MS, self._animate)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _redraw(self):
        if self._active:
            self._draw_active()
        else:
            self._draw_idle()

    def _draw_idle(self):
        cv = self._cv
        bg = self._resolve_bg()
        cx = cy = self._size / 2

        cv.delete("all")
        cv.configure(bg=bg)

        # Dim outer ring
        r_ring = self._size * 0.32
        cv.create_oval(
            cx - r_ring,
            cy - r_ring,
            cx + r_ring,
            cy + r_ring,
            outline=theme.DARK_BORDER,
            width=1,
            fill="",
        )

        # Small coloured dot (GREEN_PRIMARY blended towards bg at 70%)
        r_dot = self._size * 0.10
        dot_color = theme.alpha_blend(theme.GREEN_PRIMARY, bg, 0.70)
        cv.create_oval(
            cx - r_dot,
            cy - r_dot,
            cx + r_dot,
            cy + r_dot,
            fill=dot_color,
            outline="",
        )

    def _draw_active(self):
        cv = self._cv
        bg = self._resolve_bg()
        bg_rgb = theme.hex_to_rgb(bg)
        cx = cy = self._size / 2

        cv.delete("all")
        cv.configure(bg=bg)

        # Current and next colour for smooth blending
        c1 = theme.ORB_COLORS[self._color_idx % len(theme.ORB_COLORS)]
        c2 = theme.ORB_COLORS[(self._color_idx + 1) % len(theme.ORB_COLORS)]
        color = theme.blend_hex(c1, c2, self._color_t)

        # Pulse: oscillate between ~0.65 and ~1.0 using a sine
        pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(self._phase))

        # Glow layers: (radius_fraction, alpha, optional_secondary_color_blend)
        layers = [
            (0.90, 0.06),
            (0.72, 0.12),
            (0.56, 0.22),
            (0.42, 0.38),
            (0.30, 0.60),
            (0.18, 0.88),
            (0.10, 1.00),  # solid core
        ]

        r_rgb = theme.hex_to_rgb(color)
        for frac, alpha in layers:
            r = (self._size / 2) * frac * pulse
            # Alpha-blend the orb colour over the canvas background
            blended = "#{:02x}{:02x}{:02x}".format(
                int(r_rgb[0] * alpha + bg_rgb[0] * (1 - alpha)),
                int(r_rgb[1] * alpha + bg_rgb[1] * (1 - alpha)),
                int(r_rgb[2] * alpha + bg_rgb[2] * (1 - alpha)),
            )
            cv.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                fill=blended,
                outline="",
            )

        # Bright white highlight on core
        r_hi = (self._size / 2) * 0.06 * pulse
        cv.create_oval(
            cx - r_hi,
            cy - r_hi,
            cx + r_hi,
            cy + r_hi,
            fill="#ffffff",
            outline="",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_bg(self) -> str:
        """Return the effective background color of the parent widget."""
        try:
            parent = self.master
            while parent is not None:
                if hasattr(parent, "cget"):
                    try:
                        fc = parent.cget("fg_color")
                        if isinstance(fc, (list, tuple)):
                            mode_idx = 1 if theme.is_dark() else 0
                            color = fc[mode_idx]
                        else:
                            color = fc
                        if color and color.lower() not in ("transparent", ""):
                            return color
                    except Exception:
                        pass
                parent = getattr(parent, "master", None)
        except Exception:
            pass
        return theme.DARK_PANEL if theme.is_dark() else theme.LIGHT_PANEL
