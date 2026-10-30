from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Mapping

try:
    from .keybindings import merged_hotkeys
except ImportError:  # direct-file test loading
    from karaoke_gui.keybindings import merged_hotkeys


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
    tooltip_bg: str = "#ffffcc"
    tooltip_fg: str = "#000000"

    @property
    def is_dark(self) -> bool:
        return self.mode == "night"


def _light(name: str, family: str, accent: str, accent_alt: str, *, bg="#f5f7fa", panel="#ffffff", raised="#eef2f6", input_bg=None, fg="#20242b", muted="#66707d", border="#cbd2da", canvas="#f5f7fa", canvas_alt="#edf1f5", grid="#d8dee6", selection=None, accent_fg="#ffffff") -> ThemePalette:
    return ThemePalette(
        name=name, family=family, mode="light", accent=accent, accent_alt=accent_alt,
        bg=bg, panel=panel, raised=raised, input_bg=input_bg or panel, fg=fg, muted=muted,
        border=border, canvas=canvas, canvas_alt=canvas_alt, grid=grid,
        selection=selection or accent_alt, success="#2f8a52", warning="#a56c00", danger="#b83f48",
        accent_fg=accent_fg, tooltip_bg="#ffffcc", tooltip_fg="#000000",
    )


def _night(name: str, family: str, accent: str, accent_alt: str, *, bg="#11161d", panel="#171e27", raised="#1e2732", input_bg=None, fg="#eef2f7", muted="#9aa6b4", border="#35404d", canvas="#10151b", canvas_alt="#151c24", grid="#293440", selection=None, accent_fg="#ffffff") -> ThemePalette:
    return ThemePalette(
        name=name, family=family, mode="night", accent=accent, accent_alt=accent_alt,
        bg=bg, panel=panel, raised=raised, input_bg=input_bg or panel, fg=fg, muted=muted,
        border=border, canvas=canvas, canvas_alt=canvas_alt, grid=grid,
        selection=selection or accent_alt, success="#72d19a", warning="#e6bd5b", danger="#ff747e",
        accent_fg=accent_fg, tooltip_bg="#2a2a1a", tooltip_fg="#e0e0c0",
    )


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
PREFERENCES_PATH = Path.home() / ".karaoke_sps_workbench_ui.json"


def theme_names() -> tuple[str, ...]:
    return tuple(THEMES)


def get_theme(name: str | None) -> ThemePalette:
    return THEMES.get(name or "", THEMES[DEFAULT_THEME])


def _normalize_saved_playback_speed(value: object) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        speed = 1.0
    speed = max(0.25, min(4.0, speed))
    if 0.97 - 1e-12 <= speed <= 1.03 + 1e-12:
        return 1.0
    return speed


def load_ui_preferences(path: Path | None = None) -> dict[str, object]:
    target = path or PREFERENCES_PATH
    defaults: dict[str, object] = {
        "theme": DEFAULT_THEME,
        "advanced": False,
        "ffmpeg_mode": "portable",
        "ffmpeg_path": "",
        "playback_warmup_ms": 700,
        "playback_tail_ms": 250,
        "playback_speed": 1.0,
        "playback_cursor_offset_ms": 0,
        # Legacy compatibility only; no longer drives the playhead.
        "playback_cursor_delay_ms": 0,
        "playback_preserve_pitch": True,
        "playback_return_to_start": True,
        "playback_follow_default_device": True,
        "spectrogram_mode": "Waveform",
        "spectrogram_analysis": {},
        "spectrogram_view": {},
        "spectrogram_voice_preset": "Средний голос",
        "spectrogram_speed_preset": "Средне (6–12 SPS)",
        "spectrogram_expected_sps": "10",
        "sps_graph_source": "Оба",
        "sps_graph_smoothing": 1,
        "hotkeys": merged_hotkeys(None),
        "autosave_mode": "disabled",
    }
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            theme = str(raw.get("theme", DEFAULT_THEME))
            defaults["theme"] = theme if theme in THEMES else DEFAULT_THEME
            defaults["advanced"] = bool(raw.get("advanced", False))
            defaults["autosave_mode"] = str(raw.get("autosave_mode", "disabled"))
            if defaults["autosave_mode"] not in {"disabled", "after_edit", "1", "5", "10"}:
                defaults["autosave_mode"] = "disabled"
            mode = str(raw.get("ffmpeg_mode", "portable")).strip().lower()
            defaults["ffmpeg_mode"] = mode if mode in {"portable", "custom"} else "portable"
            defaults["ffmpeg_path"] = str(raw.get("ffmpeg_path", "") or "")
            try:
                defaults["playback_warmup_ms"] = max(0, min(2000, int(raw.get("playback_warmup_ms", 700))))
            except (TypeError, ValueError):
                defaults["playback_warmup_ms"] = 700
            try:
                defaults["playback_tail_ms"] = max(0, min(2000, int(raw.get("playback_tail_ms", 250))))
            except (TypeError, ValueError):
                defaults["playback_tail_ms"] = 250
            try:
                defaults["playback_speed"] = _normalize_saved_playback_speed(raw.get("playback_speed", 1.0))
            except (TypeError, ValueError):
                defaults["playback_speed"] = 1.0
            try:
                # Do not migrate the old positive cursor delay (typically 80 ms):
                # it is exactly what caused the visible late playhead with PortAudio.
                defaults["playback_cursor_offset_ms"] = max(-250, min(250, int(raw.get("playback_cursor_offset_ms", 0))))
            except (TypeError, ValueError):
                defaults["playback_cursor_offset_ms"] = 0
            try:
                # Keep the retired field readable for older helper/tests only.
                defaults["playback_cursor_delay_ms"] = max(0, min(2000, int(raw.get("playback_cursor_delay_ms", 0))))
            except (TypeError, ValueError):
                defaults["playback_cursor_delay_ms"] = 0
            defaults["playback_preserve_pitch"] = bool(raw.get("playback_preserve_pitch", True))
            defaults["playback_return_to_start"] = bool(raw.get("playback_return_to_start", True))
            defaults["playback_follow_default_device"] = bool(raw.get("playback_follow_default_device", True))
            spectrogram_mode = str(raw.get("spectrogram_mode", "Waveform"))
            defaults["spectrogram_mode"] = (
                spectrogram_mode if spectrogram_mode in {"Waveform", "Spectrogram", "Both"}
                else "Waveform"
            )
            analysis = raw.get("spectrogram_analysis", {})
            defaults["spectrogram_analysis"] = dict(analysis) if isinstance(analysis, dict) else {}
            view = raw.get("spectrogram_view", {})
            defaults["spectrogram_view"] = dict(view) if isinstance(view, dict) else {}
            defaults["spectrogram_voice_preset"] = str(
                raw.get("spectrogram_voice_preset", "Средний голос")
            )
            defaults["spectrogram_speed_preset"] = str(
                raw.get("spectrogram_speed_preset", "Средне (6–12 SPS)")
            )
            defaults["spectrogram_expected_sps"] = str(
                raw.get("spectrogram_expected_sps", "10")
            )
            source = str(raw.get("sps_graph_source", "Оба"))
            defaults["sps_graph_source"] = source if source in {"ASS timing", "Точное measurement", "Оба"} else "Оба"
            try:
                defaults["sps_graph_smoothing"] = max(1, min(31, int(raw.get("sps_graph_smoothing", 1))))
            except (TypeError, ValueError):
                defaults["sps_graph_smoothing"] = 1
            defaults["hotkeys"] = merged_hotkeys(raw.get("hotkeys"))
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def save_ui_preferences(
    theme: str,
    advanced: bool,
    path: Path | None = None,
    *,
    ffmpeg_mode: str = "portable",
    ffmpeg_path: str = "",
    playback_warmup_ms: int = 700,
    playback_tail_ms: int = 250,
    playback_speed: float = 1.0,
    playback_cursor_delay_ms: int | None = None,  # legacy, ignored
    playback_cursor_offset_ms: int = 0,
    playback_preserve_pitch: bool = True,
    playback_return_to_start: bool = True,
    playback_follow_default_device: bool = True,
    spectrogram_mode: str = "Waveform",
    spectrogram_analysis: Mapping[str, object] | None = None,
    spectrogram_view: Mapping[str, object] | None = None,
    spectrogram_voice_preset: str = "Средний голос",
    spectrogram_speed_preset: str = "Средне (6–12 SPS)",
    spectrogram_expected_sps: str = "10",
    sps_graph_source: str = "Оба",
    sps_graph_smoothing: int = 1,
    hotkeys: Mapping[str, str] | None = None,
    autosave_mode: str = "disabled",
) -> None:
    target = path or PREFERENCES_PATH
    mode = (ffmpeg_mode or "portable").strip().lower()
    if mode not in {"portable", "custom"}:
        mode = "portable"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "theme": theme if theme in THEMES else DEFAULT_THEME,
                    "advanced": bool(advanced),
                    "autosave_mode": autosave_mode if autosave_mode in {"disabled", "after_edit", "1", "5", "10"} else "disabled",
                    "ffmpeg_mode": mode,
                    "ffmpeg_path": str(ffmpeg_path or ""),
                    "playback_warmup_ms": max(0, min(2000, int(playback_warmup_ms))),
                    "playback_tail_ms": max(0, min(2000, int(playback_tail_ms))),
                    "playback_speed": _normalize_saved_playback_speed(playback_speed),
                    "playback_cursor_offset_ms": max(-250, min(250, int(playback_cursor_offset_ms))),
                    "playback_cursor_delay_ms": max(0, min(2000, int(playback_cursor_delay_ms or 0))),
                    "playback_preserve_pitch": bool(playback_preserve_pitch),
                    "playback_return_to_start": bool(playback_return_to_start),
                    "playback_follow_default_device": bool(playback_follow_default_device),
                    "spectrogram_mode": spectrogram_mode if spectrogram_mode in {"Waveform", "Spectrogram", "Both"} else "Waveform",
                    "spectrogram_analysis": dict(spectrogram_analysis or {}),
                    "spectrogram_view": dict(spectrogram_view or {}),
                    "spectrogram_voice_preset": str(spectrogram_voice_preset),
                    "spectrogram_speed_preset": str(spectrogram_speed_preset),
                    "spectrogram_expected_sps": str(spectrogram_expected_sps),
                    "sps_graph_source": sps_graph_source if sps_graph_source in {"ASS timing", "Точное measurement", "Оба"} else "Оба",
                    "sps_graph_smoothing": max(1, min(31, int(sps_graph_smoothing))),
                    "hotkeys": merged_hotkeys(dict(hotkeys or {})),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        # UI preferences must never prevent the workbench from starting or closing.
        return


def _pick_font(root: tk.Misc) -> str:
    try:
        families = {name.lower(): name for name in tkfont.families(root)}
    except tk.TclError:
        return "TkDefaultFont"
    for wanted in ("Segoe UI", "Cantarell", "Noto Sans", "DejaVu Sans"):
        if wanted.lower() in families:
            return families[wanted.lower()]
    return "TkDefaultFont"


def apply_ttk_theme(root: tk.Misc, palette: ThemePalette) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    family = _pick_font(root)
    root.configure(background=palette.bg)

    style.configure(".", font=(family, 9), background=palette.bg, foreground=palette.fg)
    style.configure("TFrame", background=palette.bg)
    style.configure("Panel.TFrame", background=palette.panel)
    style.configure("Toolbar.TFrame", background=palette.panel, padding=(10, 7))
    style.configure("Header.TFrame", background=palette.panel, padding=(12, 8))
    style.configure("Subheader.TFrame", background=palette.panel, padding=(8, 6))
    style.configure("Card.TFrame", background=palette.panel, relief="flat", borderwidth=0, padding=(10, 8))
    style.configure("BorderCard.TFrame", background=palette.panel, relief="flat", borderwidth=0, padding=(10, 8))
    style.configure("TLabel", background=palette.bg, foreground=palette.fg)
    style.configure("Panel.TLabel", background=palette.panel, foreground=palette.fg)
    style.configure("Header.TLabel", background=palette.bg, foreground=palette.fg, font=(family, 11, "bold"))
    style.configure("Title.TLabel", background=palette.panel, foreground=palette.fg, font=(family, 12, "bold"))
    style.configure("CardHeader.TLabel", background=palette.panel, foreground=palette.fg, font=(family, 10, "bold"))
    style.configure("CardTitle.TLabel", background=palette.panel, foreground=palette.accent, font=(family, 9, "bold"))
    style.configure("CardMuted.TLabel", background=palette.panel, foreground=palette.muted, font=(family, 8))
    style.configure("Metric.TLabel", background=palette.panel, foreground=palette.accent, font=(family, 12, "bold"))
    style.configure("Badge.TLabel", background=palette.raised, foreground=palette.accent, font=(family, 8, "bold"), padding=(6, 2))
    style.configure("Chip.TLabel", background=palette.raised, foreground=palette.fg, font=(family, 8), padding=(8, 3))
    style.configure("Muted.TLabel", foreground=palette.muted, background=palette.bg)
    style.configure("PanelMuted.TLabel", foreground=palette.muted, background=palette.panel)
    style.configure("Status.TLabel", padding=(10, 5), foreground=palette.muted, background=palette.panel)

    style.configure("TButton", padding=(10, 6), background=palette.raised, foreground=palette.fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.raised)
    style.map("TButton", background=[("pressed", palette.selection), ("active", palette.selection), ("disabled", palette.raised)], foreground=[("disabled", palette.muted)], bordercolor=[("active", palette.accent), ("pressed", palette.accent)])
    style.configure("Accent.TButton", padding=(11, 6), background=palette.accent, foreground=palette.accent_fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.accent, font=(family, 9, "bold"))
    style.map("Accent.TButton", background=[("pressed", palette.accent_alt), ("active", palette.accent_alt)], foreground=[("disabled", palette.muted)], bordercolor=[("active", palette.accent_fg), ("pressed", palette.accent_fg)])
    style.configure("Primary.TButton", padding=(12, 6), background=palette.accent, foreground=palette.accent_fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.accent, font=(family, 9, "bold"))
    style.map("Primary.TButton", background=[("pressed", palette.accent_alt), ("active", palette.accent_alt)], foreground=[("disabled", palette.muted)], bordercolor=[("active", palette.accent_fg), ("pressed", palette.accent_fg)])
    style.configure("Secondary.TButton", padding=(10, 6), background=palette.raised, foreground=palette.fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.raised)
    style.map("Secondary.TButton", background=[("pressed", palette.selection), ("active", palette.selection)], bordercolor=[("active", palette.accent), ("pressed", palette.accent)])
    style.configure("Danger.TButton", padding=(10, 6), background=palette.danger, foreground="#ffffff", borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.danger)
    style.map("Danger.TButton", background=[("pressed", "#991b1b"), ("active", "#dc2626")], bordercolor=[("active", "#ff9999"), ("pressed", "#ff9999")])
    style.configure("Success.TButton", padding=(10, 6), background=palette.success, foreground="#ffffff", borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.success)
    style.map("Success.TButton", background=[("pressed", "#166534"), ("active", "#15803d")], bordercolor=[("active", "#86efac"), ("pressed", "#86efac")])
    style.configure("Pill.TButton", padding=(7, 4), background=palette.raised, foreground=palette.fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.raised)
    style.map("Pill.TButton", background=[("active", palette.selection), ("pressed", palette.selection)], bordercolor=[("active", palette.accent), ("pressed", palette.accent)])
    style.configure("Transport.TButton", padding=(11, 6), background=palette.raised, foreground=palette.fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.raised, font=(family, 10, "bold"))
    style.map("Transport.TButton", background=[("active", palette.selection), ("pressed", palette.selection)], bordercolor=[("active", palette.accent), ("pressed", palette.accent)])
    style.configure("Flat.TButton", padding=(9, 5), background=palette.panel, foreground=palette.fg, borderwidth=1, relief="solid", focusthickness=0, focuscolor=palette.panel)
    style.map("Flat.TButton", background=[("active", palette.raised), ("pressed", palette.selection)], bordercolor=[("active", palette.accent), ("pressed", palette.accent)])

    for cls in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(cls, fieldbackground=palette.input_bg, background=palette.input_bg, foreground=palette.fg, bordercolor=palette.border, lightcolor=palette.border, darkcolor=palette.border, insertcolor=palette.fg, arrowcolor=palette.fg)
        style.map(cls, fieldbackground=[("readonly", palette.input_bg), ("disabled", palette.raised)], foreground=[("readonly", palette.fg), ("disabled", palette.muted)], bordercolor=[("focus", palette.accent), ("active", palette.accent)])

    style.configure("TCheckbutton", background=palette.bg, foreground=palette.fg, indicatorbackground=palette.input_bg, indicatorforeground=palette.accent, bordercolor=palette.border, focuscolor=palette.bg)
    style.map("TCheckbutton", background=[("active", palette.bg)], indicatorbackground=[("selected", palette.accent), ("active", palette.selection)])
    style.configure("Switch.TCheckbutton", background=palette.panel, foreground=palette.fg, padding=(6, 3), focuscolor=palette.panel)
    style.map("Switch.TCheckbutton", background=[("active", palette.raised)], foreground=[("selected", palette.accent)])
    style.configure("TRadiobutton", background=palette.bg, foreground=palette.fg, focuscolor=palette.bg)

    style.configure("TLabelframe", background=palette.bg, bordercolor=palette.bg, lightcolor=palette.bg, darkcolor=palette.bg, relief="flat", borderwidth=0, padding=(8, 6))
    style.configure("TLabelframe.Label", background=palette.bg, foreground=palette.fg, font=(family, 9, "bold"))

    style.configure("TNotebook", background=palette.bg, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", padding=(18, 9), background=palette.panel, foreground=palette.muted, borderwidth=0, relief="flat", focusthickness=0, focuscolor=palette.panel, font=(family, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", palette.raised), ("active", palette.raised)], foreground=[("selected", palette.accent), ("active", palette.fg)])

    style.configure("Treeview", background=palette.input_bg, fieldbackground=palette.input_bg, foreground=palette.fg, bordercolor=palette.bg, borderwidth=0, relief="flat", rowheight=25)
    style.map("Treeview", background=[("selected", palette.accent)], foreground=[("selected", palette.accent_fg)])
    style.configure("Treeview.Heading", background=palette.raised, foreground=palette.fg, relief="flat", bordercolor=palette.raised, borderwidth=0, padding=(8, 5))
    style.map("Treeview.Heading", background=[("active", palette.selection)])

    style.configure("TPanedwindow", background=palette.bg, sashwidth=3)
    style.configure("TSeparator", background=palette.border)
    style.configure("Horizontal.TSeparator", background=palette.border)
    style.configure("Vertical.TSeparator", background=palette.border)
    style.configure("TMenubutton", background=palette.raised, foreground=palette.fg, borderwidth=0, relief="flat", arrowcolor=palette.fg, padding=(9, 5), focuscolor=palette.raised)
    style.map("TMenubutton", background=[("active", palette.selection), ("pressed", palette.selection)])
    style.configure("TScale", background=palette.bg, troughcolor=palette.raised, sliderrelief="flat", borderwidth=0, focuscolor=palette.bg)
    style.configure("Horizontal.TScrollbar", background=palette.raised, troughcolor=palette.bg, bordercolor=palette.bg, arrowcolor=palette.fg, relief="flat")
    style.configure("Vertical.TScrollbar", background=palette.raised, troughcolor=palette.bg, bordercolor=palette.bg, arrowcolor=palette.fg, relief="flat")
    style.map("Horizontal.TScrollbar", background=[("active", palette.selection)])
    style.map("Vertical.TScrollbar", background=[("active", palette.selection)])
    style.configure("Horizontal.TProgressbar", background=palette.accent, troughcolor=palette.raised, bordercolor=palette.raised, lightcolor=palette.accent, darkcolor=palette.accent, borderwidth=0, thickness=8)
    style.configure("Vertical.TProgressbar", background=palette.accent, troughcolor=palette.raised, bordercolor=palette.raised, lightcolor=palette.accent, darkcolor=palette.accent, borderwidth=0, thickness=8)

    # Tk's combobox pop-down is a native Listbox, not a ttk widget. Without
    # these option-db entries it keeps the Windows/system colours while the
    # entry itself changes theme.
    try:
        root.option_add("*TCombobox*Listbox.background", palette.input_bg)
        root.option_add("*TCombobox*Listbox.foreground", palette.fg)
        root.option_add("*TCombobox*Listbox.selectBackground", palette.accent)
        root.option_add("*TCombobox*Listbox.selectForeground", palette.accent_fg)
        root.option_add("*TCombobox*Listbox.borderWidth", 0)
    except tk.TclError:
        pass


def apply_text_theme(widget: tk.Text, palette: ThemePalette, *, panel: bool = False) -> None:
    widget.configure(
        background=palette.input_bg if not panel else palette.panel,
        foreground=palette.fg,
        insertbackground=palette.accent,
        selectbackground=palette.accent,
        selectforeground=palette.accent_fg,
        highlightbackground=palette.input_bg,
        highlightcolor=palette.accent,
        highlightthickness=0,
        relief="flat",
    )


def apply_menu_theme(menu: tk.Menu, palette: ThemePalette) -> None:
    try:
        menu.configure(
            background=palette.panel,
            foreground=palette.fg,
            activebackground=palette.accent,
            activeforeground=palette.accent_fg,
            selectcolor=palette.accent,
            borderwidth=0,
            relief="flat",
        )
    except tk.TclError:
        return
    for child in menu.winfo_children():
        if isinstance(child, tk.Menu):
            apply_menu_theme(child, palette)
