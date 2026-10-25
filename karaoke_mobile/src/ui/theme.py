"""Theme and color tokens for Karaoke Mobile UI matching desktop PC themes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
import flet as ft


@dataclass(frozen=True, slots=True)
class ThemePalette:
    name: str
    family: str
    mode: str
    accent: str
    accent_alt: str
    bg: str
    panel: str
    raised: str
    input_bg: str
    fg: str
    muted: str
    border: str
    canvas: str
    canvas_alt: str
    grid: str
    selection: str
    success: str
    warning: str
    danger: str
    accent_fg: str = "#ffffff"

    @property
    def is_dark(self) -> bool:
        return self.mode == "night"


def _light(
    name: str,
    family: str,
    accent: str,
    accent_alt: str,
    *,
    bg="#f5f7fa",
    panel="#ffffff",
    raised="#eef2f6",
    input_bg=None,
    fg="#20242b",
    muted="#66707d",
    border="#cbd2da",
    canvas="#f5f7fa",
    canvas_alt="#edf1f5",
    grid="#d8dee6",
    selection=None,
    accent_fg="#ffffff",
) -> ThemePalette:
    return ThemePalette(
        name=name,
        family=family,
        mode="light",
        accent=accent,
        accent_alt=accent_alt,
        bg=bg,
        panel=panel,
        raised=raised,
        input_bg=input_bg or panel,
        fg=fg,
        muted=muted,
        border=border,
        canvas=canvas,
        canvas_alt=canvas_alt,
        grid=grid,
        selection=selection or accent_alt,
        success="#2f8a52",
        warning="#a56c00",
        danger="#b83f48",
        accent_fg=accent_fg,
    )


def _night(
    name: str,
    family: str,
    accent: str,
    accent_alt: str,
    *,
    bg="#11161d",
    panel="#171e27",
    raised="#1e2732",
    input_bg=None,
    fg="#eef2f7",
    muted="#9aa6b4",
    border="#35404d",
    canvas="#10151b",
    canvas_alt="#151c24",
    grid="#293440",
    selection=None,
    accent_fg="#ffffff",
) -> ThemePalette:
    return ThemePalette(
        name=name,
        family=family,
        mode="night",
        accent=accent,
        accent_alt=accent_alt,
        bg=bg,
        panel=panel,
        raised=raised,
        input_bg=input_bg or panel,
        fg=fg,
        muted=muted,
        border=border,
        canvas=canvas,
        canvas_alt=canvas_alt,
        grid=grid,
        selection=selection or accent_alt,
        success="#72d19a",
        warning="#e6bd5b",
        danger="#ff747e",
        accent_fg=accent_fg,
    )


# 14 Full PC-matched palettes
THEMES: dict[str, ThemePalette] = {
    "Тёмно-синяя · светлая": _light("Тёмно-синяя · светлая", "navy", "#315fbd", "#77a5ff", bg="#f3f6fb", raised="#e9eef7"),
    "Тёмно-синяя · ночная": _night("Тёмно-синяя · ночная", "navy", "#5d8fe8", "#8fb8ff", bg="#10151d", panel="#161d27", raised="#1d2734"),
    "Фиолетовая · светлая": _light("Фиолетовая · светлая", "purple", "#7a4eb0", "#bd8af0", bg="#f7f4fa", raised="#eee8f4"),
    "Фиолетовая · ночная": _night("Фиолетовая · ночная", "purple", "#a777dc", "#d5a8ff", bg="#16121c", panel="#201827", raised="#2a2033"),
    "Красная · светлая": _light("Красная · светлая", "red", "#b6434b", "#ec8388", bg="#faf5f5", raised="#f3e9ea"),
    "Красная · ночная": _night("Красная · ночная", "red", "#dc626a", "#ff969d", bg="#1a1113", panel="#24171a", raised="#301d21"),
    "Зелёная · светлая": _light("Зелёная · светлая", "green", "#347a4e", "#75bd8c", bg="#f3f8f4", raised="#e7f1e9"),
    "Зелёная · ночная": _night("Зелёная · ночная", "green", "#54ae72", "#86d89f", bg="#101813", panel="#17221a", raised="#1e2c22"),
    "Жёлтая · светлая": _light("Жёлтая · светлая", "yellow", "#9b7000", "#d3a82e", bg="#faf8f0", raised="#f2eddb", selection="#e8c85f", accent_fg="#ffffff"),
    "Жёлтая · ночная": _night("Жёлтая · ночная", "yellow", "#d5aa37", "#f1cd67", bg="#19170f", panel="#242116", raised="#302b1a", accent_fg="#17130a"),
    "Вэйпорвэйв · светлая": _light("Вэйпорвэйв · светлая", "vaporwave", "#b04ec9", "#4ecbd4", bg="#fff6ff", panel="#fffaff", raised="#f5eaff", fg="#30243b", muted="#75657e", border="#dbcbe5", canvas="#fff6ff", canvas_alt="#f6e9fb", grid="#e6d4ed", selection="#72dce4"),
    "Вэйпорвэйв · ночная": _night("Вэйпорвэйв · ночная", "vaporwave", "#ff71ce", "#70e7ef", bg="#120d1c", panel="#1c1329", raised="#28183a", fg="#f9ecff", muted="#bba5c8", border="#4b3561", canvas="#100a19", canvas_alt="#191024", grid="#352348", selection="#70e7ef", accent_fg="#251026"),
    "Каппучино · светлая": _light("Каппучино · светлая", "cappuccino", "#8a5c40", "#c49572", bg="#f6efe7", panel="#fffaf4", raised="#eee3d8", fg="#3e3028", muted="#76665b", border="#d7c7b8", canvas="#f8f0e8", canvas_alt="#efe3d8", grid="#ddcfc3", selection="#c9a181"),
    "Каппучино · ночная": _night("Каппучино · ночная", "cappuccino", "#c58f6e", "#e0b18f", bg="#181411", panel="#231c18", raised="#2f251f", fg="#f1e5dc", muted="#b5a398", border="#4d3e35", canvas="#15110f", canvas_alt="#1e1814", grid="#392e28", selection="#d2a07f", accent_fg="#21150f"),
}

DEFAULT_THEME = "Тёмно-синяя · ночная"
_current_theme_name: str = DEFAULT_THEME


def theme_names() -> tuple[str, ...]:
    """Return all available theme names."""
    return tuple(THEMES.keys())


def get_theme(name: Optional[str]) -> ThemePalette:
    """Get palette by name or default."""
    return THEMES.get(name or "", THEMES[DEFAULT_THEME])


def get_current_palette() -> ThemePalette:
    """Return active palette."""
    return THEMES.get(_current_theme_name, THEMES[DEFAULT_THEME])


def set_current_theme(name: str) -> ThemePalette:
    """Update active theme by name."""
    global _current_theme_name
    if name in THEMES:
        _current_theme_name = name
    return get_current_palette()


def apply_mobile_theme(page: ft.Page, theme_name: Optional[str] = None) -> ThemePalette:
    """Apply the selected theme palette to the Flet page."""
    if theme_name:
        set_current_theme(theme_name)
    pal = get_current_palette()

    page.title = "Karaoke Mobile"
    page.theme_mode = ft.ThemeMode.DARK if pal.is_dark else ft.ThemeMode.LIGHT
    page.bgcolor = pal.bg
    page.padding = 0

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
            primary=pal.accent,
            secondary=pal.accent_alt,
            surface=pal.panel,
            on_primary=pal.accent_fg,
            on_surface=pal.fg,
        )
    )
    return pal


# Initial fallback color tokens
BG_DARK = "#10151d"
SURFACE_DARK = "#161d27"
SURFACE_CARD = "#161d27"
SURFACE_ELEVATED = "#1d2734"
COLOR_PRIMARY = "#5d8fe8"
COLOR_SECONDARY = "#8fb8ff"
COLOR_BURST_BASE = "#dc626a"
COLOR_BURST_ALT = "#d5aa37"
COLOR_SUCCESS = "#54ae72"
COLOR_WARNING = "#d5aa37"
COLOR_ERROR = "#dc626a"
TEXT_PRIMARY = "#eef2f7"
TEXT_SECONDARY = "#9aa6b4"
TEXT_MUTED = "#9aa6b4"


def __getattr__(name: str):
    """Dynamically return active palette colors for module-level variables."""
    pal = get_current_palette()
    if name in ("BG_DARK", "BG"):
        return pal.bg
    if name in ("SURFACE_DARK", "SURFACE_CARD", "PANEL"):
        return pal.panel
    if name in ("SURFACE_ELEVATED", "RAISED"):
        return pal.raised
    if name in ("COLOR_PRIMARY", "ACCENT"):
        return pal.accent
    if name in ("COLOR_SECONDARY", "ACCENT_ALT"):
        return pal.accent_alt
    if name in ("COLOR_BURST_BASE", "DANGER", "COLOR_ERROR"):
        return pal.danger
    if name in ("COLOR_BURST_ALT", "WARNING", "COLOR_WARNING"):
        return pal.warning
    if name in ("COLOR_SUCCESS", "SUCCESS"):
        return pal.success
    if name in ("TEXT_PRIMARY", "FG"):
        return pal.fg
    if name in ("TEXT_SECONDARY", "TEXT_MUTED", "MUTED"):
        return pal.muted
    raise AttributeError(f"module {__name__} has no attribute {name}")
