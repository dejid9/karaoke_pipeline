from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor, log10
import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Optional, Sequence

from karaoke_core.media import WaveformData
from karaoke_core.spectrogram import SpectrogramData, SpectrogramViewSettings
from karaoke_core.sps import BurstCandidate, TimelineSyllable
from karaoke_gui.theme import DEFAULT_THEME, ThemePalette, get_theme


@dataclass(slots=True)
class Viewport:
    total_start: float = 0.0
    total_end: float = 1.0
    view_start: float = 0.0
    view_end: float = 1.0
    min_span: float = 0.05

    def set_total(self, start: float, end: float, *, reset: bool = False) -> None:
        if end <= start:
            end = start + 1.0
        old_span = self.span
        self.total_start = float(start)
        self.total_end = float(end)
        if reset or self.view_end <= self.view_start:
            self.view_start, self.view_end = self.total_start, self.total_end
        else:
            center = (self.view_start + self.view_end) / 2
            span = min(max(old_span, self.min_span), self.total_span)
            self.view_start = center - span / 2
            self.view_end = center + span / 2
            self._clamp()

    @property
    def total_span(self) -> float:
        return max(self.min_span, self.total_end - self.total_start)

    @property
    def span(self) -> float:
        return max(self.min_span, self.view_end - self.view_start)

    def reset(self) -> None:
        self.view_start, self.view_end = self.total_start, self.total_end

    def zoom(self, factor: float, anchor: float) -> None:
        if factor <= 0:
            return
        old_span = self.span
        new_span = min(self.total_span, max(self.min_span, old_span * factor))
        ratio = (anchor - self.view_start) / old_span if old_span else 0.5
        ratio = max(0.0, min(1.0, ratio))
        self.view_start = anchor - new_span * ratio
        self.view_end = self.view_start + new_span
        self._clamp()

    def pan(self, delta: float) -> None:
        self.view_start += delta
        self.view_end += delta
        self._clamp()

    def center_on(self, time_value: float) -> None:
        half = self.span / 2
        self.view_start = time_value - half
        self.view_end = time_value + half
        self._clamp()

    def _clamp(self) -> None:
        span = min(self.span, self.total_span)
        if self.view_start < self.total_start:
            self.view_start = self.total_start
            self.view_end = self.view_start + span
        if self.view_end > self.total_end:
            self.view_end = self.total_end
            self.view_start = self.view_end - span
        self.view_start = max(self.total_start, self.view_start)
        self.view_end = min(self.total_end, self.view_end)
        if self.view_end - self.view_start < self.min_span and self.total_span >= self.min_span:
            self.view_end = min(self.total_end, self.view_start + self.min_span)


def heat_colour(heat: float) -> str:
    """Cool blue -> cyan -> amber -> red, for overview-only burst speed."""
    heat = max(0.0, min(1.0, float(heat)))
    stops = (
        (0.00, (54, 96, 184)),
        (0.35, (58, 170, 190)),
        (0.68, (240, 180, 64)),
        (1.00, (216, 66, 54)),
    )
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if heat <= p1:
            t = (heat - p0) / (p1 - p0)
            rgb = tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
            return "#%02x%02x%02x" % rgb
    return "#d84236"


def _nice_tick(span: float, target_ticks: int = 8) -> float:
    rough = max(span / max(1, target_ticks), 0.001)
    power = 10 ** floor(log10(rough))
    normalized = rough / power
    if normalized <= 1:
        step = 1
    elif normalized <= 2:
        step = 2
    elif normalized <= 5:
        step = 5
    else:
        step = 10
    return step * power


def format_clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:05.2f}"
    return f"{minutes:02d}:{sec:05.2f}"


class DualTimeline(ttk.Frame):
    """Navigation overview + zoomable detail lane with optional waveform.

    In SPS mode, the detail lane exposes independent perceptual start/end handles.
    The handles edit a sidecar timeline only; karaoke timing and the ASS document
    are not modified.
    """

    def __init__(
        self,
        master,
        *,
        on_selection: Optional[Callable[[set[str]], None]] = None,
        on_view_change: Optional[Callable[[Viewport], None]] = None,
        on_measurement: Optional[Callable[[str, float, float], None]] = None,
        editable_measurements: bool = False,
        on_karaoke_boundary: Optional[Callable[[str, str, float], None]] = None,
        editable_karaoke: bool = False,
        on_activate: Optional[Callable[[str], None]] = None,
        on_seek: Optional[Callable[[float], None]] = None,
    ):
        super().__init__(master)
        self.viewport = Viewport()
        self.syllables: list[TimelineSyllable] = []
        self.bursts: list[BurstCandidate] = []
        self.manual_regions: list[BurstCandidate] = []
        self.waveform: Optional[WaveformData] = None
        self.spectrogram: Optional[SpectrogramData] = None
        self.spectrogram_view = SpectrogramViewSettings()
        self.audio_mode = "waveform"
        self._spectrogram_photo: Optional[tk.PhotoImage] = None
        self._spectrogram_photo_key: Optional[tuple] = None
        self._spectrogram_photo_cache: dict[tuple, tk.PhotoImage] = {}
        self._redraw_job: Optional[str] = None
        self._resize_job: Optional[str] = None
        self._needs_redraw_on_map = False
        self.selected_ids: set[str] = set()
        self.on_selection = on_selection
        self.on_view_change = on_view_change
        self.on_measurement = on_measurement
        self.editable_measurements = editable_measurements
        self.on_karaoke_boundary = on_karaoke_boundary
        self.editable_karaoke = editable_karaoke
        self.on_activate = on_activate
        self.on_seek = on_seek
        self.playhead_time: Optional[float] = None
        self.playback_range: Optional[tuple[float, float]] = None
        self.playback_limits: tuple[Optional[float], Optional[float]] = (None, None)
        self._drag_last_x: Optional[int] = None
        self._handle_drag: Optional[tuple[str, str]] = None
        self._karaoke_drag: Optional[tuple[str, str]] = None
        self._karaoke_drag_time: Optional[float] = None
        self._syllable_resize_drag: Optional[tuple[str, str]] = None
        self._syllable_resize_time: Optional[float] = None
        self._syllable_move_drag: Optional[str] = None
        self._syllable_move_offset: float = 0.0
        self._drag_tooltip: Optional[tk.Label] = None
        self.is_karaoke: bool = editable_karaoke
        self.advanced_mode: bool = False
        self.tracks: list[int] = [0]
        self.active_track: int = 0
        self.track_scroll_y: float = 0.0
        self.on_add_track: Optional[Callable[[str, int], None]] = None
        self.on_move_track: Optional[Callable[[int, int], None]] = None
        self.on_delete_track: Optional[Callable[[int], None]] = None
        self.palette = get_theme(DEFAULT_THEME)

        self.overview = tk.Canvas(self, height=46, highlightthickness=0, background=self.palette.canvas_alt)
        self.overview.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.track_panel = tk.Canvas(self, width=135, highlightthickness=0, background=self.palette.canvas_alt)
        self.track_panel.bind("<ButtonPress-1>", self._track_panel_click)
        self.track_panel.bind("<MouseWheel>", lambda e: self._mousewheel(e, overview=False))
        self.track_panel.bind("<Shift-MouseWheel>", lambda e: self._mousewheel(e, overview=False, force_pan=True))
        self.track_panel.bind("<Configure>", lambda _e: self._draw_track_panel())

        self.detail = tk.Canvas(self, height=260, highlightthickness=0, background=self.palette.canvas)
        self.detail.grid(row=1, column=0, columnspan=2, sticky="nsew")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        for canvas in (self.overview, self.detail):
            canvas.bind("<Configure>", self._configure_redraw)
            canvas.bind("<Map>", self._mapped_redraw, add="+")
        self.overview.bind("<ButtonPress-1>", self._overview_navigate)
        self.overview.bind("<B1-Motion>", self._overview_navigate)
        self.overview.configure(cursor="hand2")
        # Navigation gestures: vertical wheel/trackpad zooms; Shift+wheel or
        # native horizontal wheel pans. Bind both canvases so the overview and
        # detailed lane feel like one editor timeline.
        for canvas, is_overview in ((self.overview, True), (self.detail, False)):
            canvas.bind("<MouseWheel>", lambda e, ov=is_overview: self._mousewheel(e, overview=ov))
            canvas.bind("<Shift-MouseWheel>", lambda e, ov=is_overview: self._mousewheel(e, overview=ov, force_pan=True))
            canvas.bind("<Button-4>", lambda e, ov=is_overview: self._linux_wheel(e, -1, overview=ov))
            canvas.bind("<Button-5>", lambda e, ov=is_overview: self._linux_wheel(e, 1, overview=ov))
            # Windows precision touchpads normally surface horizontal motion as
            # Shift+MouseWheel in Tk. Some X11 builds expose buttons 6/7, but
            # standard Tk rejects those button numbers, so Shift+wheel remains
            # the portable horizontal gesture.
        self.detail.bind("<ButtonPress-1>", self._detail_press)
        self.detail.bind("<B1-Motion>", self._detail_drag)
        self.detail.bind("<ButtonRelease-1>", self._detail_release)
        self.detail.bind("<Shift-Button-1>", self._detail_shift_click)
        self.detail.bind("<Double-Button-1>", self._detail_double_click)
        self.detail.bind("<ButtonPress-2>", self._pan_start)
        self.detail.bind("<B2-Motion>", self._pan_drag)
        self.detail.bind("<ButtonPress-3>", self._detail_right_click)

    def _wave_bounds(self, h: int) -> tuple[int, int]:
        wave_top = 26
        if self.is_karaoke and self.advanced_mode:
            # Multi-track mode: waveform / spectrogram height increased by 1.5x
            base_h = max(30, int(h * 0.35) - wave_top)
            wave_bottom = wave_top + int(base_h * 1.5)
        else:
            wave_bottom = max(wave_top + 30, int(h * 0.66))
        return wave_top, wave_bottom

    def _draw_track_panel(self) -> None:
        if not hasattr(self, "track_panel") or not self.track_panel.winfo_ismapped():
            return
        c = self.track_panel
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill=self.palette.canvas_alt, outline="")
        wave_top, wave_bottom = self._wave_bounds(h)
        lane_top = wave_bottom + 5
        lane_bottom = h - 10
        TRACK_LANE_HEIGHT = 75

        c.create_text(w / 2, 12, text="Дорожки", fill=self.palette.muted, font=("TkDefaultFont", 8, "bold"))
        c.create_line(0, lane_top - 1, w, lane_top - 1, fill=self.palette.border)

        for i, track_id in enumerate(self.tracks):
            y0 = lane_top + i * TRACK_LANE_HEIGHT - self.track_scroll_y
            y1 = y0 + TRACK_LANE_HEIGHT
            if y1 < lane_top or y0 > lane_bottom:
                continue
            is_active = (track_id == self.active_track)
            bg = self.palette.raised if is_active else self.palette.panel
            outline = self.palette.accent if is_active else self.palette.border
            c.create_rectangle(2, y0 + 1, w - 2, y1 - 1, fill=bg, outline=outline, width=1.5 if is_active else 1, tags=("track_bg", f"track:{track_id}"))

            title = f"Дорожка {track_id}" + (" (основная)" if track_id == 0 else "")
            c.create_text(6, y0 + 13, text=title, anchor="w", fill=self.palette.fg, font=("TkDefaultFont", 8, "bold"), tags=("track_title", f"track:{track_id}"))

            if track_id != 0:
                c.create_rectangle(w - 22, y0 + 4, w - 5, y0 + 20, fill=self.palette.canvas, outline=self.palette.danger, tags=("btn_del", f"track:{track_id}"))
                c.create_text(w - 13, y0 + 12, text="✕", fill=self.palette.danger, font=("TkDefaultFont", 7, "bold"), tags=("btn_del", f"track:{track_id}"))

            by0 = y0 + 32
            by1 = y0 + 64
            if track_id == 0 and len(self.tracks) == 1:
                c.create_rectangle(6, by0, w - 6, by1, fill=self.palette.canvas, outline=self.palette.border, tags=("btn_add_above", f"track:{track_id}"))
                c.create_text(w / 2, (by0 + by1) / 2, text="+ Выше", fill=self.palette.fg, font=("TkDefaultFont", 8), tags=("btn_add_above", f"track:{track_id}"))
            else:
                c.create_rectangle(4, by0, 44, by1, fill=self.palette.canvas, outline=self.palette.border, tags=("btn_add_above", f"track:{track_id}"))
                c.create_text(24, (by0 + by1) / 2, text="+Выше", fill=self.palette.fg, font=("TkDefaultFont", 7), tags=("btn_add_above", f"track:{track_id}"))

                c.create_rectangle(47, by0, 87, by1, fill=self.palette.canvas, outline=self.palette.border, tags=("btn_add_below", f"track:{track_id}"))
                c.create_text(67, (by0 + by1) / 2, text="+Ниже", fill=self.palette.fg, font=("TkDefaultFont", 7), tags=("btn_add_below", f"track:{track_id}"))

                c.create_rectangle(90, by0, 108, by1, fill=self.palette.canvas, outline=self.palette.border, tags=("btn_move_up", f"track:{track_id}"))
                c.create_text(99, (by0 + by1) / 2, text="▲", fill=self.palette.fg, font=("TkDefaultFont", 8), tags=("btn_move_up", f"track:{track_id}"))

                c.create_rectangle(111, by0, 129, by1, fill=self.palette.canvas, outline=self.palette.border, tags=("btn_move_down", f"track:{track_id}"))
                c.create_text(120, (by0 + by1) / 2, text="▼", fill=self.palette.fg, font=("TkDefaultFont", 8), tags=("btn_move_down", f"track:{track_id}"))

    def _track_panel_click(self, event) -> str:
        current = self.track_panel.find_withtag("current")
        if not current:
            return "break"
        tags = self.track_panel.gettags(current[0])
        track_tag = next((t for t in tags if t.startswith("track:")), None)
        if not track_tag:
            return "break"
        track_id = int(track_tag.split("track:", 1)[1])
        if "btn_add_above" in tags:
            if self.on_add_track:
                self.on_add_track("above", track_id)
        elif "btn_add_below" in tags:
            if self.on_add_track:
                self.on_add_track("below", track_id)
        elif "btn_move_up" in tags:
            if self.on_move_track:
                self.on_move_track(track_id, -1)
        elif "btn_move_down" in tags:
            if self.on_move_track:
                self.on_move_track(track_id, 1)
        elif "btn_del" in tags:
            if self.on_delete_track:
                self.on_delete_track(track_id)
        else:
            self.active_track = track_id
            self.redraw()
            self._draw_track_panel()
        return "break"

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette = palette
        self.overview.configure(background=palette.canvas_alt)
        self.detail.configure(background=palette.canvas)
        if hasattr(self, "track_panel"):
            self.track_panel.configure(background=palette.canvas_alt)
        # Theme switches should not block the combobox callback while a heavy
        # SPS/spectrogram view is open.  The spectrogram PhotoImage is reusable
        # across themes; only lightweight overlays need repainting.
        self.request_redraw(delay_ms=1)

    def set_advanced_mode(self, advanced: bool) -> None:
        self.advanced_mode = bool(advanced)
        if self.is_karaoke and self.advanced_mode:
            self.track_panel.grid(row=1, column=0, sticky="ns")
            self.detail.grid(row=1, column=1, sticky="nsew")
            self.columnconfigure(0, weight=0)
            self.columnconfigure(1, weight=1)
        else:
            self.track_panel.grid_remove()
            self.detail.grid(row=1, column=0, columnspan=2, sticky="nsew")
            self.columnconfigure(0, weight=1)
            self.columnconfigure(1, weight=0)
        self.request_redraw(delay_ms=1, force=True)

    def set_data(
        self,
        syllables: Sequence[TimelineSyllable] | Iterable[TimelineSyllable],
        *,
        bursts: Optional[Sequence[BurstCandidate]] = None,
        manual_regions: Optional[Sequence[BurstCandidate]] = None,
        reset_view: bool = True,
    ) -> None:
        self.syllables = list(syllables)
        self.bursts = list(bursts or [])
        self.manual_regions = list(manual_regions or [])
        present_tracks = sorted({getattr(s, "track", 0) for s in self.syllables})
        if not present_tracks:
            present_tracks = [0]
        if 0 not in present_tracks:
            present_tracks = [0] + present_tracks
        if reset_view:
            self.tracks = list(present_tracks)
        else:
            self.tracks = [t for t in self.tracks if t in present_tracks]
            for t in present_tracks:
                if t not in self.tracks:
                    self.tracks.append(t)
        if 0 not in self.tracks:
            self.tracks.insert(0, 0)
        if self.active_track not in self.tracks:
            self.active_track = self.tracks[0] if self.tracks else 0
        self.selected_ids.intersection_update({s.id for s in self.syllables})
        self._update_total(reset_view=reset_view)
        self._sync_scrollbar()
        self.redraw()

    def set_waveform(self, waveform: Optional[WaveformData], *, reset_view: bool = False) -> None:
        self.waveform = waveform
        self._update_total(reset_view=reset_view)
        self.redraw()

    def set_spectrogram(
        self,
        spectrogram: Optional[SpectrogramData],
        *,
        view: Optional[SpectrogramViewSettings] = None,
        reset_view: bool = False,
    ) -> None:
        self.spectrogram = spectrogram
        self._invalidate_spectrogram_images()
        if view is not None:
            self.spectrogram_view = view
        self._update_total(reset_view=reset_view)
        self.redraw()

    def set_spectrogram_view(self, view: SpectrogramViewSettings) -> None:
        self.spectrogram_view = view
        self._invalidate_spectrogram_images()
        self.redraw()

    def set_audio_mode(self, mode: str) -> None:
        mode = mode.lower().strip()
        if mode not in {"waveform", "spectrogram", "both"}:
            raise ValueError(f"Unsupported audio view mode: {mode}")
        self.audio_mode = mode
        self.redraw()

    def _update_total(self, *, reset_view: bool) -> None:
        starts = [s.start for s in self.syllables]
        ends = [s.end for s in self.syllables]
        if self.waveform is not None and self.waveform.duration > 0:
            starts.append(0.0)
            ends.append(self.waveform.duration)
        if self.spectrogram is not None and self.spectrogram.duration > 0:
            starts.append(0.0)
            ends.append(self.spectrogram.duration)
        if starts and ends:
            start, end = min(starts), max(ends)
        else:
            start, end = 0.0, 1.0
        self.viewport.set_total(start, end, reset=reset_view)

    def set_bursts(self, bursts: Sequence[BurstCandidate]) -> None:
        self.bursts = list(bursts)
        self.redraw()

    def clear_selection(self) -> None:
        self.selected_ids.clear()
        self.redraw()
        self._emit_selection()

    def select_ids(self, ids: Iterable[str]) -> None:
        valid = {s.id for s in self.syllables}
        self.selected_ids = set(ids).intersection(valid)
        if self.is_karaoke and self.advanced_mode and len(self.selected_ids) == 1:
            sid = next(iter(self.selected_ids))
            s = next((item for item in self.syllables if item.id == sid), None)
            if s is not None:
                track = getattr(s, "track", 0)
                if track != self.active_track:
                    self.active_track = track
                    self._draw_track_panel()
        self.redraw()
        self._emit_selection()

    def selected_syllables(self) -> list[TimelineSyllable]:
        return [s for s in self.syllables if s.id in self.selected_ids]

    def focus_time(self, time_value: float) -> None:
        self.viewport.center_on(time_value)
        self._view_changed()

    def _invalidate_spectrogram_images(self) -> None:
        self._spectrogram_photo = None
        self._spectrogram_photo_key = None
        self._spectrogram_photo_cache.clear()

    def _is_drawable(self) -> bool:
        try:
            return bool(self.winfo_ismapped() and self.overview.winfo_ismapped() and self.detail.winfo_ismapped())
        except tk.TclError:
            return False

    def request_redraw(self, delay_ms: int = 16, *, force: bool = False) -> None:
        """Throttle expensive canvas work to one pending frame.

        Notebook pages and minimized windows are not redrawn while hidden.
        Instead a single frame is remembered and flushed on <Map>.
        """
        if not force and not self._is_drawable():
            self._needs_redraw_on_map = True
            return
        if self._redraw_job is not None:
            return
        self._redraw_job = self.after(max(0, int(delay_ms)), self._scheduled_redraw)

    def _scheduled_redraw(self) -> None:
        self._redraw_job = None
        if not self._is_drawable():
            self._needs_redraw_on_map = True
            return
        self._needs_redraw_on_map = False
        self.redraw()

    def _mapped_redraw(self, _event=None) -> None:
        if self._needs_redraw_on_map:
            self._needs_redraw_on_map = False
        self.request_redraw(delay_ms=1, force=True)

    def _configure_redraw(self, _event=None) -> None:
        # Ignore resize storms for hidden notebook pages/minimized windows.
        if not self._is_drawable():
            self._needs_redraw_on_map = True
            return
        # Rebuilding a spectrogram image for every intermediate Windows resize
        # event makes even dragging the window border feel sticky. Wait until
        # geometry settles briefly, while wheel/touchpad navigation stays on a
        # much shorter throttle.
        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        self._resize_job = self.after(90, self._finish_configure_redraw)

    def _finish_configure_redraw(self) -> None:
        self._resize_job = None
        if not self._is_drawable():
            self._needs_redraw_on_map = True
            return
        self.redraw()

    def redraw(self) -> None:
        if not self._is_drawable():
            self._needs_redraw_on_map = True
            return
        self._needs_redraw_on_map = False
        self._draw_overview()
        self._draw_detail()
        if self.is_karaoke and self.advanced_mode:
            self._draw_track_panel()
        self._sync_scrollbar()

    def _time_to_x(self, t: float, *, overview: bool) -> float:
        canvas = self.overview if overview else self.detail
        width = max(1, canvas.winfo_width())
        start = self.viewport.total_start if overview else self.viewport.view_start
        end = self.viewport.total_end if overview else self.viewport.view_end
        return (t - start) / max(1e-9, end - start) * width

    def _x_to_time(self, x: float, *, overview: bool) -> float:
        canvas = self.overview if overview else self.detail
        width = max(1, canvas.winfo_width())
        start = self.viewport.total_start if overview else self.viewport.view_start
        end = self.viewport.total_end if overview else self.viewport.view_end
        return start + max(0.0, min(1.0, x / width)) * (end - start)

    def _draw_overview(self) -> None:
        c = self.overview
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill=self.palette.canvas_alt, outline="")
        for region in self.manual_regions:
            x0 = self._time_to_x(region.start, overview=True)
            x1 = self._time_to_x(region.end, overview=True)
            c.create_rectangle(x0, 6, max(x0 + 1, x1), h - 7, fill=self.palette.danger, outline="")
        # Automatic speed encoding appears ONLY on the navigation overview.
        for burst in self.bursts:
            x0 = self._time_to_x(burst.start, overview=True)
            x1 = self._time_to_x(burst.end, overview=True)
            c.create_rectangle(x0, 6, max(x0 + 1, x1), h - 7, fill=heat_colour(burst.heat), outline="")
        vx0 = self._time_to_x(self.viewport.view_start, overview=True)
        vx1 = self._time_to_x(self.viewport.view_end, overview=True)
        c.create_rectangle(vx0, 2, vx1, h - 3, outline=self.palette.fg, width=2)
        zoom = self.viewport.total_span / max(self.viewport.span, 1e-9)
        c.create_text(w - 5, h - 4, text=f"×{zoom:.1f}", anchor="se", fill=self.palette.muted, font=("TkDefaultFont", 7))
        if self.playback_range is not None:
            start, end = self.playback_range
            in_x = self._time_to_x(start, overview=True)
            out_x = self._time_to_x(end, overview=True)
            left, right = sorted((in_x, out_x))
            c.create_rectangle(left, 4, max(left + 1, right), h - 5, outline=self.palette.warning, width=2, dash=(4, 3), tags=("playback-range",))
            c.create_text(in_x + (3 if in_x <= out_x else -3), 4, text="I", anchor=("nw" if in_x <= out_x else "ne"), fill=self.palette.warning, font=("TkDefaultFont", 7, "bold"), tags=("playback-range",))
            c.create_text(out_x + (3 if out_x <= in_x else -3), 4, text="O", anchor=("nw" if out_x <= in_x else "ne"), fill=self.palette.warning, font=("TkDefaultFont", 7, "bold"), tags=("playback-range",))
        play_start, play_stop = self.playback_limits
        if play_start is not None and self.viewport.total_start <= play_start <= self.viewport.total_end:
            x = self._time_to_x(play_start, overview=True)
            c.create_line(x, 1, x, h - 1, fill=self.palette.success, width=2, dash=(2, 2), tags=("playback-limits",))
            c.create_text(x + 3, h - 4, text="|←", anchor="sw", fill=self.palette.success, font=("TkDefaultFont", 8, "bold"), tags=("playback-limits",))
        if play_stop is not None and self.viewport.total_start <= play_stop <= self.viewport.total_end:
            x = self._time_to_x(play_stop, overview=True)
            c.create_line(x, 1, x, h - 1, fill=self.palette.danger, width=2, dash=(2, 2), tags=("playback-limits",))
            c.create_text(x - 3, h - 4, text="→|", anchor="se", fill=self.palette.danger, font=("TkDefaultFont", 7, "bold"), tags=("playback-limits",))
        if self.playhead_time is not None and self.viewport.total_start <= self.playhead_time <= self.viewport.total_end:
            px = self._time_to_x(self.playhead_time, overview=True)
            c.create_line(px, 1, px, h - 1, fill=self.palette.accent, width=2, tags=("playhead",))

    def _draw_spectrogram(self, c: tk.Canvas, w: int, top: int, bottom: int) -> bool:
        if self.spectrogram is None or self.spectrogram.duration <= 0 or bottom <= top:
            self._spectrogram_photo = None
            self._spectrogram_photo_key = None
            return False
        height = max(1, bottom - top)
        # Cache the actual Tk image, not just RGB bytes. Selection/text changes
        # can cause many redraws with the same viewport; those redraws should not
        # rerasterize the spectrogram nor recreate PhotoImage each time.
        key = (
            id(self.spectrogram),
            round(self.viewport.view_start, 6),
            round(self.viewport.view_end, 6),
            int(w), int(height), self.spectrogram_view,
        )
        photo = self._spectrogram_photo_cache.get(key)
        if photo is None:
            try:
                ppm = self.spectrogram.render_ppm(
                    self.viewport.view_start, self.viewport.view_end, w, height, self.spectrogram_view
                )
                photo = tk.PhotoImage(master=c, data=ppm, format="PPM")
            except Exception:
                self._spectrogram_photo = None
                self._spectrogram_photo_key = None
                return False
            self._spectrogram_photo_cache[key] = photo
            # Four viewport images are enough for small back/forth gestures and
            # keep memory bounded even on wide monitors.
            while len(self._spectrogram_photo_cache) > 4:
                oldest = next(iter(self._spectrogram_photo_cache))
                if oldest == key and len(self._spectrogram_photo_cache) > 1:
                    oldest = next(k for k in self._spectrogram_photo_cache if k != key)
                self._spectrogram_photo_cache.pop(oldest, None)
        self._spectrogram_photo = photo
        self._spectrogram_photo_key = key
        c.create_image(0, top, image=photo, anchor="nw")
        hi = min(self.spectrogram.nyquist, self.spectrogram_view.max_frequency)
        lo = max(0.0, self.spectrogram_view.min_frequency)
        c.create_text(4, top + 5, text=f"{hi/1000:.1f} kHz", anchor="nw", fill=self.palette.fg, font=("TkDefaultFont", 7))
        c.create_text(4, bottom - 5, text=f"{lo:.0f} Hz", anchor="sw", fill=self.palette.fg, font=("TkDefaultFont", 7))
        return True

    def _draw_waveform(self, c: tk.Canvas, w: int, top: int, bottom: int, *, show_missing: bool = True) -> bool:
        if self.waveform is None or self.waveform.duration <= 0 or bottom <= top:
            if show_missing:
                c.create_text(w / 2, (top + bottom) / 2, text="Waveform: медиа не загружено", fill=self.palette.muted)
            return False
        columns = self.waveform.columns(self.viewport.view_start, self.viewport.view_end, w)
        center = (top + bottom) / 2
        half = max(1.0, (bottom - top) / 2 - 2)
        scale = half / 32768.0
        upper_pairs: list[tuple[float, float]] = []
        lower_pairs: list[tuple[float, float]] = []
        for x, (lo, hi) in enumerate(columns):
            upper_pairs.append((x, center - hi * scale))
            lower_pairs.append((x, center - lo * scale))
        upper = [coord for point in upper_pairs for coord in point]
        lower = [coord for point in lower_pairs for coord in point]

        # The previous implementation created one Canvas line per screen pixel
        # (often 1200+ Tcl objects per frame). Two polylines, or one filled
        # envelope in waveform-only mode, are dramatically cheaper to redraw.
        if self.audio_mode == "both":
            if len(upper) >= 4:
                c.create_line(*upper, fill=self.palette.accent_alt, width=1)
                c.create_line(*lower, fill=self.palette.accent_alt, width=1)
        else:
            # Reverse the *points*, not the flattened x/y scalar list.  The old
            # scalar reversal turned (... x, y ...) into (... y, x ...) and
            # produced the large diagonal wedges visible in filled waveform
            # mode.
            polygon_pairs = upper_pairs + list(reversed(lower_pairs))
            polygon = [coord for point in polygon_pairs for coord in point]
            if len(polygon) >= 8:
                c.create_polygon(*polygon, fill=self.palette.raised, outline="")
                c.create_line(*upper, fill=self.palette.accent_alt, width=1)
                c.create_line(*lower, fill=self.palette.accent_alt, width=1)
        c.create_line(0, center, w, center, fill=self.palette.grid)
        return True

    def _draw_detail(self) -> None:
        c = self.detail
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill=self.palette.canvas, outline="")
        is_multi_track = bool(self.is_karaoke and self.advanced_mode)
        time_bottom = 24
        wave_top, wave_bottom = self._wave_bounds(h)
        lane_top = wave_bottom + 5
        lane_bottom = h - 10
        TRACK_LANE_HEIGHT = 75

        step = _nice_tick(self.viewport.span)
        first = floor(self.viewport.view_start / step) * step
        t = first
        while t <= self.viewport.view_end + step:
            if t >= self.viewport.view_start - 1e-9:
                x = self._time_to_x(t, overview=False)
                c.create_line(x, 0, x, h, fill=self.palette.grid)
                c.create_text(x + 3, 11, text=format_clock(t), anchor="w", fill=self.palette.muted, font=("TkDefaultFont", 8))
            t += step

        if self.audio_mode == "spectrogram":
            if not self._draw_spectrogram(c, w, wave_top, wave_bottom):
                c.create_text(w / 2, (wave_top + wave_bottom) / 2, text="Спектрограмма: ещё не построена", fill=self.palette.muted)
        elif self.audio_mode == "both":
            rendered = self._draw_spectrogram(c, w, wave_top, wave_bottom)
            self._draw_waveform(c, w, wave_top, wave_bottom, show_missing=not rendered)
        else:
            self._spectrogram_photo = None
            self._draw_waveform(c, w, wave_top, wave_bottom)

        visible = [
            s for s in self.syllables
            if s.end >= self.viewport.view_start and s.start <= self.viewport.view_end
        ]

        if is_multi_track:
            total_tracks_h = len(self.tracks) * TRACK_LANE_HEIGHT
            avail_h = max(TRACK_LANE_HEIGHT, lane_bottom - lane_top)
            max_scroll = max(0.0, float(total_tracks_h - avail_h))
            self.track_scroll_y = max(0.0, min(max_scroll, self.track_scroll_y))

            track0_syllables = [s for s in self.syllables if getattr(s, "track", 0) == 0]
            track0_id_map = {s.id: idx + 1 for idx, s in enumerate(track0_syllables)}
            track0_by_seq_id = {idx + 1: s for idx, s in enumerate(track0_syllables)}

            for i, t_id in enumerate(self.tracks):
                lane_y0 = lane_top + i * TRACK_LANE_HEIGHT - self.track_scroll_y
                lane_y1 = lane_y0 + TRACK_LANE_HEIGHT
                if lane_y1 < lane_top or lane_y0 > lane_bottom:
                    continue
                lane_bg = self.palette.raised if t_id == self.active_track else self.palette.canvas
                c.create_rectangle(0, lane_y0, w, lane_y1, fill=lane_bg, outline="", tags=("track_lane", f"track:{t_id}"))
                c.create_line(0, lane_y1, w, lane_y1, fill=self.palette.border, tags=("track_div", f"track:{t_id}"))

            for i, t_id in enumerate(self.tracks):
                lane_y0 = lane_top + i * TRACK_LANE_HEIGHT - self.track_scroll_y
                lane_y1 = lane_y0 + TRACK_LANE_HEIGHT
                if lane_y1 < lane_top or lane_y0 > lane_bottom:
                    continue
                syllables_for_track = [
                    s for s in visible
                    if getattr(s, "track", 0) == t_id or (t_id == 0 and getattr(s, "track", 0) not in self.tracks)
                ]
                syl_top = lane_y0 + 2
                syl_bottom = lane_y1 - 2

                for s in syllables_for_track:
                    x0 = self._time_to_x(s.start, overview=False)
                    x1 = self._time_to_x(s.end, overview=False)
                    selected = s.id in self.selected_ids
                    changed = s.measurement_changed
                    raw_src = s.source.raw_text if s.source else ""
                    is_remap = bool(re.search(r"\\remap\b", s.text or "") or re.search(r"\\remap\b", raw_src))

                    if selected:
                        fill = self.palette.selection
                    elif is_remap and t_id == 0:
                        fill = self.palette.canvas
                    elif s.burst_marked:
                        fill = self.palette.danger
                    elif changed:
                        fill = self.palette.raised
                    else:
                        fill = self.palette.panel

                    if selected:
                        outline = self.palette.fg
                    elif is_remap and t_id == 0:
                        outline = self.palette.muted
                    elif changed:
                        outline = self.palette.accent_alt
                    elif s.burst_marked:
                        outline = self.palette.danger
                    else:
                        outline = self.palette.border

                    c.create_rectangle(
                        x0, syl_top, max(x0 + 2, x1), syl_bottom,
                        fill=fill, outline=outline, width=2 if selected or changed else 1,
                        dash=(3, 2) if (is_remap and t_id == 0 and not selected) else (),
                        tags=("syllable", s.id),
                    )
                    # Resize handles for independent syllable edge editing
                    if selected and self.editable_karaoke:
                        handle_w = 6
                        handle_h = 10
                        mid_y = (syl_top + syl_bottom) / 2
                        # Left handle
                        c.create_polygon(
                            x0, mid_y - handle_h/2,
                            x0 + handle_w, mid_y,
                            x0, mid_y + handle_h/2,
                            fill=self.palette.warning, outline="",
                            tags=("syllable-resize-left", s.id),
                        )
                        # Right handle
                        c.create_polygon(
                            max(x0 + 2, x1), mid_y - handle_h/2,
                            max(x0 + 2, x1) - handle_w, mid_y,
                            max(x0 + 2, x1), mid_y + handle_h/2,
                            fill=self.palette.warning, outline="",
                            tags=("syllable-resize-right", s.id),
                        )

                    width_px = x1 - x0
                    if width_px >= 14:
                        if t_id == 0:
                            label = s.text.strip().replace("\n", " ")
                            if is_remap:
                                label = "[remap] " + label if label else "[remap]"
                            if len(label) > 16:
                                label = label[:15] + "…"
                            text_colour = self.palette.accent_fg if s.burst_marked and not selected else self.palette.fg
                            c.create_text((x0 + x1) / 2, lane_y0 + 26, text=label, fill=text_colour, font=("TkDefaultFont", 9), width=max(1, int(width_px - 4)), tags=("syllable", s.id))
                            seq_id = track0_id_map.get(s.id)
                            if seq_id is not None:
                                c.create_text((x0 + x1) / 2, lane_y0 + 52, text=f"id: {seq_id}", fill=self.palette.muted, font=("TkDefaultFont", 8), tags=("syllable", s.id))
                        else:
                            id_match = re.search(r"\\id0:(\d+)", s.text or raw_src)
                            ref_syl = track0_by_seq_id.get(int(id_match.group(1))) if id_match else None
                            label = s.text.strip().replace("\n", " ")
                            if not label and ref_syl is not None:
                                label = ref_syl.text.strip().replace("\n", " ")
                            if len(label) > 16:
                                label = label[:15] + "…"
                            text_colour = self.palette.accent_fg if s.burst_marked and not selected else self.palette.fg
                            if id_match:
                                c.create_text((x0 + x1) / 2, lane_y0 + 26, text=label, fill=text_colour, font=("TkDefaultFont", 9), width=max(1, int(width_px - 4)), tags=("syllable", s.id))
                                c.create_text((x0 + x1) / 2, lane_y0 + 52, text=f"id0: {id_match.group(1)}", fill=self.palette.muted, font=("TkDefaultFont", 8), tags=("syllable", s.id))
                            else:
                                c.create_text((x0 + x1) / 2, (lane_y0 + lane_y1) / 2, text=label, fill=text_colour, font=("TkDefaultFont", 9), width=max(1, int(width_px - 4)), tags=("syllable", s.id))
        else:
            dense_lod = len(visible) > max(260, w // 3)
            if dense_lod and visible:
                c.create_rectangle(0, lane_top, w, lane_bottom, fill=self.palette.panel, outline=self.palette.border, width=1)
                important = [s for s in visible if s.id in self.selected_ids or s.measurement_changed or s.burst_marked]
            else:
                important = visible

            for s in important:
                x0 = self._time_to_x(s.start, overview=False)
                x1 = self._time_to_x(s.end, overview=False)
                selected = s.id in self.selected_ids
                changed = s.measurement_changed
                if selected:
                    fill = self.palette.selection
                elif s.burst_marked:
                    fill = self.palette.danger
                elif changed:
                    fill = self.palette.raised
                else:
                    fill = self.palette.panel
                if selected:
                    outline = self.palette.fg
                elif changed:
                    outline = self.palette.accent_alt
                elif s.burst_marked:
                    outline = self.palette.danger
                else:
                    outline = self.palette.border
                c.create_rectangle(
                    x0, lane_top, max(x0 + 2, x1), lane_bottom,
                    fill=fill, outline=outline, width=2 if selected or changed else 1,
                    tags=("syllable", s.id),
                )
                # Resize handles for independent syllable edge editing
                if selected and self.editable_karaoke:
                    handle_w = 6
                    handle_h = 10
                    mid_y = (lane_top + lane_bottom) / 2
                    # Left handle
                    c.create_polygon(
                        x0, mid_y - handle_h/2,
                        x0 + handle_w, mid_y,
                        x0, mid_y + handle_h/2,
                        fill=self.palette.warning, outline="",
                        tags=("syllable-resize-left", s.id),
                    )
                    # Right handle
                    c.create_polygon(
                        max(x0 + 2, x1), mid_y - handle_h/2,
                        max(x0 + 2, x1) - handle_w, mid_y,
                        max(x0 + 2, x1), mid_y + handle_h/2,
                        fill=self.palette.warning, outline="",
                        tags=("syllable-resize-right", s.id),
                    )
                if s.burst_marked and x1 - x0 >= 11:
                    c.create_text(
                        x0 + 3, lane_top + 2, text="B", anchor="nw",
                        fill=self.palette.accent_fg, font=("TkDefaultFont", 7, "bold"),
                        tags=("syllable", s.id),
                    )
                if changed:
                    mx0 = self._time_to_x(s.effective_start, overview=False)
                    mx1 = self._time_to_x(s.effective_end, overview=False)
                    measured_left = min(mx0, mx1)
                    measured_right = max(mx0, mx1)
                    c.create_rectangle(
                        measured_left, lane_top + 3, max(measured_left + 2, measured_right), lane_bottom - 3,
                        outline=self.palette.accent_alt, width=2,
                        dash=(4, 2) if s.effective_end < s.effective_start else (),
                        tags=("syllable", s.id),
                    )
                width_px = x1 - x0
                if not dense_lod and width_px >= 18 and s.text.strip():
                    label = s.text.strip().replace("\n", " ")
                    if len(label) > 18:
                        label = label[:17] + "…"
                    text_colour = self.palette.accent_fg if s.burst_marked and not selected else self.palette.fg
                    c.create_text((x0 + x1) / 2, (lane_top + lane_bottom) / 2, text=label, fill=text_colour, width=max(1, int(width_px - 4)), tags=("syllable", s.id))

        if self.editable_measurements and len(self.selected_ids) == 1:
            sid = next(iter(self.selected_ids))
            s = next((item for item in self.syllables if item.id == sid), None)
            if s is not None:
                self._draw_measurement_handles(c, s, wave_top, lane_bottom)

        if self.editable_karaoke and len(self.selected_ids) == 1:
            sid = next(iter(self.selected_ids))
            index = next((i for i, item in enumerate(self.syllables) if item.id == sid), None)
            if index is not None:
                self._draw_karaoke_handles(c, index, wave_top, lane_bottom)

        if not self.syllables:
            c.create_text(w / 2, lane_top + 15, text="Откройте ASS с karaoke-тегами", fill=self.palette.muted)
        if self.playback_range is not None:
            start, end = self.playback_range
            for value, label in ((start, "I"), (end, "O")):
                if self.viewport.view_start <= value <= self.viewport.view_end:
                    rx = self._time_to_x(value, overview=False)
                    c.create_line(rx, 0, rx, h, fill=self.palette.warning, width=2, dash=(5, 4), tags=("playback-range",))
                    c.create_text(rx + (3 if label == "I" else -3), 4, text=label, anchor=("nw" if label == "I" else "ne"), fill=self.palette.warning, font=("TkDefaultFont", 8, "bold"), tags=("playback-range",))
        play_start, play_stop = self.playback_limits
        if play_start is not None and self.viewport.view_start <= play_start <= self.viewport.view_end:
            x = self._time_to_x(play_start, overview=False)
            c.create_line(x, 0, x, h, fill=self.palette.success, width=2, dash=(3, 3), tags=("playback-limits",))
            c.create_text(x + 3, 18, text="|←", anchor="nw", fill=self.palette.success, font=("TkDefaultFont", 8, "bold"), tags=("playback-limits",))
        if play_stop is not None and self.viewport.view_start <= play_stop <= self.viewport.view_end:
            x = self._time_to_x(play_stop, overview=False)
            c.create_line(x, 0, x, h, fill=self.palette.danger, width=2, dash=(3, 3), tags=("playback-limits",))
            c.create_text(x - 3, 18, text="→|", anchor="ne", fill=self.palette.danger, font=("TkDefaultFont", 8, "bold"), tags=("playback-limits",))
        if self.playhead_time is not None and self.viewport.view_start <= self.playhead_time <= self.viewport.view_end:
            px = self._time_to_x(self.playhead_time, overview=False)
            c.create_line(px, 0, px, h, fill=self.palette.accent, width=2, tags=("playhead",))
        c.create_line(0, time_bottom, w, time_bottom, fill=self.palette.border)

    def set_playback_range(self, start: Optional[float], end: Optional[float]) -> None:
        """Show an In/Out transport range without changing selection or timing."""
        if start is None or end is None:
            self.playback_range = None
        else:
            self.playback_range = (float(start), float(end))
        self.request_redraw(delay_ms=1)

    def set_playback_limits(self, start: Optional[float], stop: Optional[float]) -> None:
        """Show independent ordinary-Play start/stop markers.

        Unlike In/Out, either marker may exist on its own.
        """
        self.playback_limits = (
            None if start is None else float(start),
            None if stop is None else float(stop),
        )
        self.request_redraw(delay_ms=1)

    def set_playhead(self, value: Optional[float], *, ensure_visible: bool = False) -> None:
        self.playhead_time = None if value is None else float(value)
        if ensure_visible and self.playhead_time is not None:
            if self.playhead_time < self.viewport.view_start or self.playhead_time > self.viewport.view_end:
                self.viewport.center_on(self.playhead_time)
                self._view_changed()
                return
        self._update_playhead_items()

    def _update_playhead_items(self) -> None:
        if not self._is_drawable():
            # The current time is already stored in self.playhead_time.  A full
            # redraw on <Map> will place the line correctly without doing Tk
            # canvas work at 25–30 FPS on a hidden tab.
            self._needs_redraw_on_map = True
            return
        value = self.playhead_time
        for canvas, overview in ((self.overview, True), (self.detail, False)):
            items = canvas.find_withtag("playhead")
            visible = value is not None and (
                self.viewport.total_start <= value <= self.viewport.total_end if overview
                else self.viewport.view_start <= value <= self.viewport.view_end
            )
            if not visible:
                for item in items:
                    canvas.delete(item)
                continue
            assert value is not None
            x = self._time_to_x(float(value), overview=overview)
            h = max(1, canvas.winfo_height())
            if items:
                canvas.coords(items[0], x, 1 if overview else 0, x, h - 1 if overview else h)
                canvas.itemconfigure(items[0], fill=self.palette.accent, width=2)
                for extra in items[1:]:
                    canvas.delete(extra)
            else:
                canvas.create_line(
                    x, 1 if overview else 0, x, h - 1 if overview else h,
                    fill=self.palette.accent, width=2, tags=("playhead",),
                )

    def _draw_measurement_handles(self, c: tk.Canvas, s: TimelineSyllable, top: int, bottom: int) -> None:
        for side, value in (("start", s.effective_start), ("end", s.effective_end)):
            x = self._time_to_x(value, overview=False)
            tags = ("measure-handle", f"handle-{side}", s.id)
            c.create_line(x, top, x, bottom, fill=self.palette.accent_alt, width=2, tags=tags)
            if side == "start":
                pts = (x, top, x + 7, top + 6, x, top + 12)
            else:
                pts = (x, top, x - 7, top + 6, x, top + 12)
            c.create_polygon(*pts, fill=self.palette.accent_alt, outline="", tags=tags)

    def _same_karaoke_event(self, left: TimelineSyllable, right: TimelineSyllable) -> bool:
        return (
            left.source is not None
            and right.source is not None
            and left.source.event_line_index == right.source.event_line_index
            and right.source.syllable_ordinal == left.source.syllable_ordinal + 1
        )

    def _draw_karaoke_handles(self, c: tk.Canvas, index: int, top: int, bottom: int) -> None:
        current = self.syllables[index]
        pairs: list[tuple[TimelineSyllable, TimelineSyllable, float]] = []
        if index > 0:
            left = self.syllables[index - 1]
            if self._same_karaoke_event(left, current):
                pairs.append((left, current, current.start))
        if index + 1 < len(self.syllables):
            right = self.syllables[index + 1]
            if self._same_karaoke_event(current, right):
                pairs.append((current, right, current.end))
        for left, right, value in pairs:
            x = self._time_to_x(value, overview=False)
            tags = (
                "karaoke-boundary",
                f"left={left.id}",
                f"right={right.id}",
                current.id,
            )
            c.create_line(x, top, x, bottom, fill=self.palette.warning, width=2, tags=tags)
            c.create_polygon(
                x - 6, top + 2, x + 6, top + 2, x, top + 10,
                fill=self.palette.warning, outline="", tags=tags,
            )

    @staticmethod
    def _boundary_ids_from_tags(tags: Iterable[str]) -> tuple[Optional[str], Optional[str]]:
        left = next((tag[5:] for tag in tags if tag.startswith("left=")), None)
        right = next((tag[6:] for tag in tags if tag.startswith("right=")), None)
        return left, right

    def _current_tags(self) -> tuple[str, ...]:
        current = self.detail.find_withtag("current")
        return self.detail.gettags(current[0]) if current else ()

    def _syllable_id_from_tags(self, tags: Iterable[str]) -> Optional[str]:
        return next((tag for tag in tags if tag.startswith("L") and ":S" in tag), None)

    def _syllable_at_time(self, value: float) -> Optional[str]:
        # Used both as a fallback in normal mode and as the primary hit-test in
        # dense LOD mode where we intentionally do not create one Canvas object
        # per syllable. Gaps return the nearest neighbour within a few pixels.
        if not self.syllables:
            return None
        pool = self.syllables
        if self.is_karaoke and self.advanced_mode:
            track_pool = [s for s in self.syllables if getattr(s, "track", 0) == self.active_track]
            if track_pool:
                pool = track_pool
            elif self.active_track != 0:
                return None
        inside = [s for s in pool if s.start <= value <= s.end]
        if inside:
            return min(inside, key=lambda s: s.end - s.start).id
        nearest = min(self.syllables, key=lambda s: min(abs(value - s.start), abs(value - s.end)))
        tolerance = self.viewport.span * 8.0 / max(1, self.detail.winfo_width())
        distance = min(abs(value - nearest.start), abs(value - nearest.end))
        return nearest.id if distance <= tolerance else None

    def _sid_from_event(self, event) -> Optional[str]:
        sid = self._syllable_id_from_tags(self._current_tags())
        if sid:
            s = next((item for item in self.syllables if item.id == sid), None)
            if s is not None and self.is_karaoke and self.advanced_mode:
                new_track = getattr(s, "track", 0)
                if new_track != self.active_track:
                    self.active_track = new_track
                    self._draw_track_panel()
            return sid
        if self.is_karaoke and self.advanced_mode:
            h = max(1, self.detail.winfo_height())
            wave_top, wave_bottom = self._wave_bounds(h)
            lane_top = wave_bottom + 5
            TRACK_LANE_HEIGHT = 75
            if event.y >= lane_top:
                idx = int((event.y - lane_top + self.track_scroll_y) // TRACK_LANE_HEIGHT)
                if 0 <= idx < len(self.tracks):
                    new_track = self.tracks[idx]
                    if new_track != self.active_track:
                        self.active_track = new_track
                        self._draw_track_panel()
                    track_syllables = [s for s in self.syllables if getattr(s, "track", 0) == self.active_track]
                    t_val = self._x_to_time(event.x, overview=False)
                    inside = [s for s in track_syllables if s.start <= t_val <= s.end]
                    if inside:
                        return min(inside, key=lambda s: s.end - s.start).id
                    return None
        return self._syllable_at_time(self._x_to_time(event.x, overview=False))

    def _detail_press(self, event) -> None:
        try: self.detail.focus_set()
        except tk.TclError: pass
        tags = self._current_tags()
        sid = self._syllable_id_from_tags(tags)
        if self.is_karaoke and self.advanced_mode:
            new_active = None
            if sid:
                s = next((item for item in self.syllables if item.id == sid), None)
                if s is not None:
                    new_active = getattr(s, "track", 0)
            elif "karaoke-boundary" in tags:
                left, right = self._boundary_ids_from_tags(tags)
                s = next((item for item in self.syllables if item.id in (left, right)), None)
                if s is not None:
                    new_active = getattr(s, "track", 0)
            else:
                track_tag = next((t for t in tags if t.startswith("track:")), None)
                if track_tag:
                    try:
                        new_active = int(track_tag.split("track:", 1)[1])
                    except ValueError:
                        pass
                if new_active is None:
                    h = max(1, self.detail.winfo_height())
                    wave_top, wave_bottom = self._wave_bounds(h)
                    lane_top = wave_bottom + 5
                    TRACK_LANE_HEIGHT = 75
                    if event.y >= lane_top:
                        idx = int((event.y - lane_top + self.track_scroll_y) // TRACK_LANE_HEIGHT)
                        if 0 <= idx < len(self.tracks):
                            new_active = self.tracks[idx]
            if new_active is not None and new_active != self.active_track:
                self.active_track = new_active
                self._draw_track_panel()
        if not sid:
            sid = self._sid_from_event(event)
        if self.editable_karaoke and "karaoke-boundary" in tags:
            left, right = self._boundary_ids_from_tags(tags)
            if left and right:
                self._handle_drag = None
                self._karaoke_drag = (left, right)
                left_item = next((s for s in self.syllables if s.id == left), None)
                right_item = next((s for s in self.syllables if s.id == right), None)
                self._karaoke_drag_time = right_item.start if right_item is not None else None
                # Keep the already selected syllable when possible; selecting the
                # right side otherwise makes the edited boundary obvious.
                if not self.selected_ids.intersection({left, right}):
                    self.selected_ids = {right}
                self.redraw()
                self._emit_selection()
                return
        if self.editable_karaoke and "syllable-resize-left" in tags and sid:
            self._syllable_resize_drag = (sid, "start")
            self._syllable_resize_time = None
            self._handle_drag = None
            self._karaoke_drag = None
            self._syllable_move_drag = None
            self.selected_ids = {sid}
            self.redraw()
            self._emit_selection()
            return
        if self.editable_karaoke and "syllable-resize-right" in tags and sid:
            self._syllable_resize_drag = (sid, "end")
            self._syllable_resize_time = None
            self._handle_drag = None
            self._karaoke_drag = None
            self._syllable_move_drag = None
            self.selected_ids = {sid}
            self.redraw()
            self._emit_selection()
            return
        # Shift+click on syllable body initiates move mode
        shift_pressed = bool(getattr(event, "state", 0) & 0x0001)
        if self.editable_karaoke and sid and shift_pressed and "syllable" in tags:
            s = next((item for item in self.syllables if item.id == sid), None)
            if s is not None:
                self._syllable_move_drag = sid
                self._syllable_move_offset = self._x_to_time(event.x, overview=False) - s.start
                self._handle_drag = None
                self._karaoke_drag = None
                self._syllable_resize_drag = None
                self.selected_ids = {sid}
                self.redraw()
                self._emit_selection()
                return
        if self.editable_measurements and "measure-handle" in tags and sid:
            side = "start" if "handle-start" in tags else "end"
            self.selected_ids = {sid}
            self._handle_drag = (sid, side)
            self._karaoke_drag = None
            self.redraw()
            self._emit_selection()
            return
        if self.on_seek is not None:
            try:
                self.on_seek(self._x_to_time(event.x, overview=False))
            except Exception:
                pass
        self._handle_drag = None
        self._karaoke_drag = None
        self.selected_ids = {sid} if sid else set()
        self.redraw()
        self._emit_selection()

    def _detail_drag(self, event) -> None:
        if self._karaoke_drag is not None:
            left_id, right_id = self._karaoke_drag
            li = next((i for i, item in enumerate(self.syllables) if item.id == left_id), None)
            ri = next((i for i, item in enumerate(self.syllables) if item.id == right_id), None)
            if li is None or ri is None:
                return
            left = self.syllables[li]
            right = self.syllables[ri]
            t = round(self._x_to_time(event.x, overview=False) * 100.0) / 100.0
            t = max(left.start, min(right.end, t))
            self.syllables[li] = replace(left, end=t)
            self.syllables[ri] = replace(right, start=t)
            self._karaoke_drag_time = t
            self._show_drag_tooltip(event.x, event.y, f"{format_clock(t)}")
            self.request_redraw()
            return
        if self._syllable_resize_drag is not None:
            sid, side = self._syllable_resize_drag
            index = next((i for i, item in enumerate(self.syllables) if item.id == sid), None)
            if index is None:
                return
            s = self.syllables[index]
            t = round(self._x_to_time(event.x, overview=False) * 100.0) / 100.0
            if side == "start":
                t = min(t, s.end - 0.01)
                self.syllables[index] = replace(s, start=t)
            else:
                t = max(t, s.start + 0.01)
                self.syllables[index] = replace(s, end=t)
            self._syllable_resize_time = t
            new_s = self.syllables[index]
            self._show_drag_tooltip(event.x, event.y, f"{side.upper()}: {format_clock(t)}  |  Dur: {new_s.end - new_s.start:.3f}s")
            self.request_redraw()
            return
        if self._syllable_move_drag is not None:
            sid = self._syllable_move_drag
            index = next((i for i, item in enumerate(self.syllables) if item.id == sid), None)
            if index is None:
                return
            s = self.syllables[index]
            t = self._x_to_time(event.x, overview=False) - self._syllable_move_offset
            duration = s.end - s.start
            t = max(0.0, t)
            self.syllables[index] = replace(s, start=t, end=t + duration)
            self._show_drag_tooltip(event.x, event.y, f"Start: {format_clock(t)}  |  Dur: {duration:.3f}s")
            self.request_redraw()
            return
        if self._handle_drag is None:
            return
        sid, side = self._handle_drag
        index = next((i for i, item in enumerate(self.syllables) if item.id == sid), None)
        if index is None:
            return
        s = self.syllables[index]
        t = self._x_to_time(event.x, overview=False)
        if side == "start":
            new_start = max(s.start, min(t, s.end))
            updated = s.with_measurement(new_start, s.effective_end)
        else:
            new_end = max(s.start, min(t, s.end))
            updated = s.with_measurement(s.effective_start, new_end)
        self.syllables[index] = updated
        self.request_redraw()

    def _detail_release(self, _event) -> None:
        self._hide_drag_tooltip()
        if self._karaoke_drag is not None:
            left, right = self._karaoke_drag
            boundary = self._karaoke_drag_time
            self._karaoke_drag = None
            self._karaoke_drag_time = None
            if boundary is not None and self.on_karaoke_boundary:
                self.on_karaoke_boundary(left, right, boundary)
            return
        if self._syllable_resize_drag is not None:
            sid, side = self._syllable_resize_drag
            self._syllable_resize_drag = None
            item = next((s for s in self.syllables if s.id == sid), None)
            if item is not None and self.on_syllable_resize:
                self.on_syllable_resize(sid, item.start, item.end)
            return
        if self._syllable_move_drag is not None:
            sid = self._syllable_move_drag
            self._syllable_move_drag = None
            item = next((s for s in self.syllables if s.id == sid), None)
            if item is not None and self.on_syllable_move:
                self.on_syllable_move(sid, item.start)
            return
        if self._handle_drag is None:
            return
        sid, _side = self._handle_drag
        self._handle_drag = None
        item = next((s for s in self.syllables if s.id == sid), None)
        if item is not None and self.on_measurement:
            self.on_measurement(sid, item.effective_start, item.effective_end)

    def _detail_double_click(self, event) -> str:
        tags = self._current_tags()
        if "karaoke-boundary" in tags or "measure-handle" in tags:
            return "break"
        sid = self._syllable_id_from_tags(tags) or self._sid_from_event(event)
        if sid:
            self.selected_ids = {sid}
            self.redraw()
            self._emit_selection()
            if self.on_activate:
                self.on_activate(sid)
        return "break"

    def _detail_shift_click(self, event) -> str:
        tags = self._current_tags()
        sid = self._syllable_id_from_tags(tags) or self._sid_from_event(event)
        if not sid:
            return "break"
        if not self.selected_ids:
            self.selected_ids = {sid}
        else:
            ids = [s.id for s in self.syllables]
            selected_indices = [ids.index(i) for i in self.selected_ids if i in ids]
            anchor = min(selected_indices) if selected_indices else ids.index(sid)
            b = ids.index(sid)
            lo, hi = sorted((anchor, b))
            self.selected_ids = set(ids[lo:hi + 1])
        self.redraw()
        self._emit_selection()
        return "break"

    def _detail_right_click(self, event) -> str:
        """Show context menu for syllable operations on the timeline."""
        tags = self._current_tags()
        sid = self._syllable_id_from_tags(tags) or self._sid_from_event(event)
        if not sid:
            return "break"
        self.selected_ids = {sid}
        self.redraw()
        self._emit_selection()
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Разделить", command=lambda: self._context_action("__split__", sid))
        menu.add_command(label="Удалить", command=lambda: self._context_action("__delete__", sid))
        menu.add_command(label="Вставить после", command=lambda: self._context_action("__insert__", sid))
        menu.add_separator()
        menu.add_command(label="Совместить с предыдущим", command=lambda: self._context_action("__merge_prev__", sid))
        menu.add_command(label="Совместить со следующим", command=lambda: self._context_action("__merge_next__", sid))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _context_action(self, action: str, sid: str) -> None:
        if self.on_activate:
            self.on_activate(f"{action}:{sid}")

    def _show_drag_tooltip(self, x: int, y: int, text: str) -> None:
        if self._drag_tooltip is None:
            self._drag_tooltip = tk.Label(
                self.detail,
                text=text,
                bg=self.palette.tooltip_bg,
                fg=self.palette.tooltip_fg,
                font=("TkDefaultFont", 9),
                relief="solid",
                borderwidth=1,
                padx=4,
                pady=2,
            )
        else:
            self._drag_tooltip.configure(text=text)
        # Position above the cursor
        tx = max(0, min(x + 10, self.detail.winfo_width() - 100))
        ty = max(0, y - 30)
        self._drag_tooltip.place(x=tx, y=ty)

    def _hide_drag_tooltip(self) -> None:
        if self._drag_tooltip is not None:
            self._drag_tooltip.place_forget()

    def _overview_navigate(self, event) -> str:
        """Scrub/pan the detailed viewport directly from the mini timeline."""
        try: self.overview.focus_set()
        except tk.TclError: pass
        self.viewport.center_on(self._x_to_time(event.x, overview=True))
        self._view_changed()
        return "break"

    @staticmethod
    def _wheel_steps(delta: int | float) -> float:
        # Windows traditionally reports +/-120 per notch, while precision
        # touchpads may emit smaller values. macOS/Tk can report +/-1. Keep the
        # gesture proportional instead of collapsing everything to one notch.
        value = float(delta or 0.0)
        if value == 0:
            return 0.0
        if abs(value) < 10:
            return value
        return value / 120.0

    def _pan_wheel_steps(self, steps: float) -> str:
        if not steps:
            return "break"
        # Positive Shift+wheel (wheel up / swipe left on common Windows
        # touchpads) moves the viewport left; negative moves it right.
        self.viewport.pan(-steps * self.viewport.span * 0.08)
        self._view_changed()
        return "break"

    def _mousewheel(self, event, *, overview: bool = False, force_pan: bool = False) -> str:
        steps = self._wheel_steps(getattr(event, "delta", 0))
        shift = bool(getattr(event, "state", 0) & 0x0001)
        ctrl = bool(getattr(event, "state", 0) & 0x0004)
        if self.is_karaoke and self.advanced_mode and not overview:
            if ctrl:
                if not steps:
                    return "break"
                factor = 0.8 ** steps
                anchor = self._x_to_time(event.x, overview=False)
                self.viewport.zoom(factor, anchor)
                self._view_changed()
                return "break"
            elif force_pan or shift:
                return self._pan_wheel_steps(steps)
            else:
                if not steps:
                    return "break"
                TRACK_LANE_HEIGHT = 75
                total_tracks_h = len(self.tracks) * TRACK_LANE_HEIGHT
                h = max(1, self.detail.winfo_height())
                wave_top, wave_bottom = self._wave_bounds(h)
                lane_top = wave_bottom + 5
                lane_bottom = h - 10
                avail_h = max(TRACK_LANE_HEIGHT, lane_bottom - lane_top)
                max_scroll = max(0.0, float(total_tracks_h - avail_h))
                self.track_scroll_y = max(0.0, min(max_scroll, self.track_scroll_y - steps * 25.0))
                self.redraw()
                self._draw_track_panel()
                return "break"
        if force_pan or shift:
            return self._pan_wheel_steps(steps)
        if not steps:
            return "break"
        factor = 0.8 ** steps
        anchor = self._x_to_time(event.x, overview=overview)
        self.viewport.zoom(factor, anchor)
        self._view_changed()
        return "break"

    def _linux_wheel(self, event, direction: int, *, overview: bool = False) -> str:
        shift = bool(getattr(event, "state", 0) & 0x0001)
        ctrl = bool(getattr(event, "state", 0) & 0x0004)
        if self.is_karaoke and self.advanced_mode and not overview:
            if ctrl:
                factor = 0.8 if direction < 0 else 1.25
                anchor = self._x_to_time(event.x, overview=False)
                self.viewport.zoom(factor, anchor)
                self._view_changed()
                return "break"
            elif shift:
                return self._pan_wheel_steps(-float(direction))
            else:
                TRACK_LANE_HEIGHT = 75
                total_tracks_h = len(self.tracks) * TRACK_LANE_HEIGHT
                h = max(1, self.detail.winfo_height())
                wave_top, wave_bottom = self._wave_bounds(h)
                lane_top = wave_bottom + 5
                lane_bottom = h - 10
                avail_h = max(TRACK_LANE_HEIGHT, lane_bottom - lane_top)
                max_scroll = max(0.0, float(total_tracks_h - avail_h))
                self.track_scroll_y = max(0.0, min(max_scroll, self.track_scroll_y + float(direction) * 25.0))
                self.redraw()
                self._draw_track_panel()
                return "break"
        if shift:
            return self._pan_wheel_steps(-float(direction))
        factor = 0.8 if direction < 0 else 1.25
        anchor = self._x_to_time(event.x, overview=overview)
        self.viewport.zoom(factor, anchor)
        self._view_changed()
        return "break"

    def _horizontal_wheel(self, direction: float) -> str:
        # Native horizontal gestures have their own direction and do not need
        # Shift. One event corresponds to roughly one traditional wheel step.
        self.viewport.pan(float(direction) * self.viewport.span * 0.08)
        self._view_changed()
        return "break"

    def _pan_start(self, event) -> None:
        self._drag_last_x = event.x

    def _pan_drag(self, event) -> None:
        if self._drag_last_x is None:
            self._drag_last_x = event.x
            return
        width = max(1, self.detail.winfo_width())
        dx = event.x - self._drag_last_x
        self._drag_last_x = event.x
        self.viewport.pan(-dx / width * self.viewport.span)
        self._view_changed()

    def _scroll_command(self, *args) -> None:
        if not args:
            return
        if args[0] == "moveto":
            fraction = float(args[1])
            span = self.viewport.span
            available = max(0.0, self.viewport.total_span - span)
            self.viewport.view_start = self.viewport.total_start + fraction * available
            self.viewport.view_end = self.viewport.view_start + span
        elif args[0] == "scroll":
            units = int(args[1])
            kind = args[2]
            scale = 0.8 if kind == "pages" else 0.08
            self.viewport.pan(units * self.viewport.span * scale)
        self._view_changed()

    def _sync_scrollbar(self) -> None:
        # Kept as a compatibility no-op because the SPS graph calls this helper.
        # Navigation/viewport feedback now lives entirely in the overview canvas.
        return

    def _view_changed(self) -> None:
        self.request_redraw()
        if self.on_view_change:
            self.on_view_change(self.viewport)

    def _emit_selection(self) -> None:
        if self.on_selection:
            self.on_selection(set(self.selected_ids))
