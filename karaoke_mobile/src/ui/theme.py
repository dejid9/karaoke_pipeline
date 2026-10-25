"""Theme and color tokens for Karaoke Mobile UI."""

import flet as ft

# Dark modern theme palette (Catppuccin inspired)
BG_DARK = "#181825"
SURFACE_DARK = "#1e1e2e"
SURFACE_CARD = "#2a2a3d"
SURFACE_ELEVATED = "#313244"

COLOR_PRIMARY = "#89b4fa"       # Blue accent
COLOR_SECONDARY = "#cba6f7"     # Lavender
COLOR_BURST_BASE = "#f38ba8"    # Red (default burst)
COLOR_BURST_ALT = "#fab387"     # Orange (default alt/pulse)
COLOR_SUCCESS = "#a6e3a1"       # Green
COLOR_WARNING = "#f9e2af"       # Yellow
COLOR_ERROR = "#eba0ac"         # Soft red

TEXT_PRIMARY = "#cdd6f4"
TEXT_SECONDARY = "#a6adc8"
TEXT_MUTED = "#6c7086"


def apply_mobile_theme(page: ft.Page) -> None:
    """Apply responsive dark mobile theme to Flet page."""
    page.title = "Karaoke Mobile"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_DARK
    page.padding = 0

    # Mobile viewport defaults (when testing on desktop)
    try:
        if hasattr(page, "window") and page.window:
            page.window.width = 412
            page.window.height = 860
            page.window.min_width = 360
            page.window.min_height = 640
    except Exception:
        pass

    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=COLOR_PRIMARY,
            secondary=COLOR_SECONDARY,
            surface=SURFACE_DARK,
        )
    )
