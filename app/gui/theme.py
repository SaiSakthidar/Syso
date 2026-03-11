"""
Design system — single source of truth for colors, fonts, spacing.
Supports both light and dark mode via (light, dark) tuples understood by CTk.
"""

import customtkinter as ctk

# ── Primary palette ───────────────────────────────────────────────────────────
GREEN_PRIMARY = "#22c55e"
GREEN_HOVER = "#16a34a"
GREEN_GLOW = "#15803d"
GREEN_DARK_BADGE = "#052e16"

# ── Semantic colors ───────────────────────────────────────────────────────────
COLOR_ERROR = "#f87171"
COLOR_WARNING = "#fbbf24"
COLOR_INFO = "#60a5fa"
COLOR_SYSTEM = "#c084fc"
COLOR_SUCCESS = GREEN_PRIMARY

# ── Animated orb color cycle (Gemini-style) ───────────────────────────────────
ORB_COLORS = ["#22c55e", "#06b6d4", "#818cf8", "#c084fc", "#f472b6", "#34d399"]

# ── Dark palette ──────────────────────────────────────────────────────────────
DARK_ROOT = "#07111f"  # window / outermost bg
DARK_PANEL = "#0e1a2d"  # panel frame bg
DARK_SURFACE = "#111f33"  # above panel
DARK_ELEVATED = "#172743"  # cards, inputs
DARK_BORDER = "#223354"  # subtle dividers
DARK_MUTED = "#5a7399"  # placeholder / secondary text
DARK_TEXT = "#dde6f5"  # primary text

# Header gradient end-points (drawn via Canvas, top → bottom)
HEADER_TOP = "#0a1828"
HEADER_BOTTOM = "#07111f"

# ── Light palette ─────────────────────────────────────────────────────────────
LIGHT_ROOT = "#f0f4f8"
LIGHT_PANEL = "#ffffff"
LIGHT_SURFACE = "#f1f5f9"
LIGHT_ELEVATED = "#e8f0e8"
LIGHT_BORDER = "#c8d9c8"
LIGHT_MUTED = "#64748b"
LIGHT_TEXT = "#0f172a"

LIGHT_HEADER_TOP = "#e8f5e9"
LIGHT_HEADER_BOTTOM = "#f0fdf4"

# ── Chat bubbles ──────────────────────────────────────────────────────────────
BUBBLE_USER_DARK = "#0c2a40"
BUBBLE_ASST_DARK = "#101e32"
BUBBLE_USER_LIGHT = "#dcfce7"
BUBBLE_ASST_LIGHT = "#f8fafc"

# ── Corner radii ──────────────────────────────────────────────────────────────
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 22
RADIUS_PILL = 999

# ── Spacing ───────────────────────────────────────────────────────────────────
PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 24
PAD_XXL = 32

# ── Typography ────────────────────────────────────────────────────────────────
FONT_APP_TITLE = ("Inter", 19, "bold")
FONT_SECTION = ("Inter", 16, "bold")
FONT_BODY = ("Inter", 14)
FONT_BODY_BOLD = ("Inter", 14, "bold")
FONT_SMALL = ("Inter", 12)
FONT_CAPTION = ("Inter", 11)
FONT_MONO = ("JetBrains Mono", 13)

# ── Log level → display color ─────────────────────────────────────────────────
LOG_LEVEL_COLORS = {
    "INFO": COLOR_INFO,
    "SYSTEM": COLOR_SYSTEM,
    "WARNING": COLOR_WARNING,
    "ERROR": COLOR_ERROR,
    "SUCCESS": COLOR_SUCCESS,
}


# ── Theme helpers ─────────────────────────────────────────────────────────────


def apply_theme():
    """Call once at startup before any widgets are created."""
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("green")


def current_mode() -> str:
    """Return 'Dark' or 'Light'."""
    return ctk.get_appearance_mode()


def is_dark() -> bool:
    return current_mode() == "Dark"


def resolve(dark_val, light_val):
    """Pick dark or light value based on current appearance mode."""
    return dark_val if is_dark() else light_val


def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def blend_hex(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two hex colors. t=0 → c1, t=1 → c2."""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def alpha_blend(fg: str, bg: str, alpha: float) -> str:
    """Blend fg over bg with given alpha (0.0 fully transparent → 1.0 opaque)."""
    return blend_hex(bg, fg, alpha)
