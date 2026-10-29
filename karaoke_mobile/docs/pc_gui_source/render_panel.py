from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import math
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable, Optional

from karaoke_core.render import (
    AssTextStyle,
    BurstCounterSettings,
    CropRect,
    RenderLayoutSettings,
    RenderMeasurement,
    RenderOutputSettings,
    RenderRangeError,
    RenderRangeSettings,
    ResolvedRenderRange,
    VerticalFollowSettings,
    ass_playres,
    build_burst_style_preview_document,
    burst_counter_regions,
    composite_rgba_to_ppm,
    export_render_ass,
    make_even_crop,
    max_dialogue_end,
    measure_render_layout,
    render_karaoke_video,
    render_burst_counter_video,
    render_rgba_frame,
    resolve_render_range,
    scaled_crop_rect,
    karaoke_text_style,
    vertical_viewport_crop,
    shift_hue,
    calculate_hue_offset_degrees,
    normalize_ass_colour,
    ass_to_rgb,
    rgb_to_ass,
)
from karaoke_core.media import probe_audio_bounds, probe_media_duration
from karaoke_core.measurements import read_measurements
from karaoke_gui.theme import DEFAULT_THEME, ThemePalette, get_theme


BURST_COLOR_MODES = {
    "single": "Один цвет",
    "alternate": "Чередование",
    "gradient": "Градиент по слогам",
    "dynamic": "Динамический перелив",
}
BURST_COLOR_MODES_INV = {v: k for k, v in BURST_COLOR_MODES.items()}


PROFILE_LABELS = {
    "Прозрачный MOV (qtrle, alpha)": "transparent_mov",
    "MP4 H.264 (чёрный фон)": "black_mp4",
}

TEXT_CASE_CHOICES = {
    "as_is": "Как в ASS (без изменений)",
    "upper": "Все заглавные",
    "lower": "Все строчные",
    "sentence": "Как в предложении (после переноса)",
}
TEXT_CASE_LABELS = {v: k for k, v in TEXT_CASE_CHOICES.items()}


class CropPreviewDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        measurement: RenderMeasurement,
        *,
        initial_crop: CropRect,
        auto_crop: CropRect,
        on_apply: Callable[[CropRect], None],
        output_scale: float = 2.0,
        follow_enabled: bool = False,
    ) -> None:
        super().__init__(master)
        self.title("Preview и ручная обрезка")
        self.transient(master)
        self.geometry("980x690")
        self.minsize(720, 520)
        self.measurement = measurement
        self.follow_enabled = bool(follow_enabled)
        self.rect = initial_crop.clamp(measurement.playres_x, measurement.playres_y)
        self.auto_crop = auto_crop.clamp(measurement.playres_x, measurement.playres_y)
        self.on_apply = on_apply
        self.output_scale = max(1.0, float(output_scale))
        self.palette: ThemePalette = getattr(master, "palette", get_theme(DEFAULT_THEME))
        self.configure(background=self.palette.bg)

        toolbar = ttk.Frame(self, padding=(8, 8, 8, 5))
        toolbar.pack(side="top", fill="x")
        self._vars = {
            "x": tk.StringVar(), "y": tk.StringVar(),
            "w": tk.StringVar(), "h": tk.StringVar(),
        }
        for column, (label, key) in enumerate((("X:", "x"), ("Y:", "y"), ("W:", "w"), ("H:", "h"))):
            ttk.Label(toolbar, text=label).grid(row=0, column=column * 2, sticky="w")
            ttk.Entry(toolbar, textvariable=self._vars[key], width=8).grid(
                row=0, column=column * 2 + 1, sticky="w", padx=(3, 9)
            )
        ttk.Button(toolbar, text="Применить поля", command=self._apply_fields).grid(row=0, column=8, padx=(3, 6), sticky="w")

        btn_row = ttk.Frame(toolbar)
        btn_row.grid(row=1, column=0, columnspan=10, sticky="w", pady=(5, 0))
        ttk.Button(btn_row, text="Авто", command=self._use_auto).pack(side="left")
        ttk.Button(btn_row, text="Центр по содержимому", command=self._center_on_content).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Чётный размер", command=self._make_even).pack(side="left", padx=4)
        ttk.Button(btn_row, text="+50px сверху/снизу", command=self._add_50px_vertical).pack(side="left", padx=4)

        footer = ttk.Frame(self, padding=(8, 4, 8, 8))
        footer.pack(side="bottom", fill="x")
        self.info = ttk.Label(footer, text="", style="Muted.TLabel")
        self.info.pack(side="left")
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Использовать crop", command=self._accept).pack(side="right", padx=(0, 6))

        holder = ttk.Frame(self, padding=(8, 0, 8, 6))
        holder.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(holder, background=self.palette.canvas, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<ButtonPress-1>", self._drag_start_event)
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        # The expanded measurement canvas may be several thousand pixels tall.
        # Build only a screen-sized preview instead of compositing millions of
        # pixels on Tk's UI thread.
        self._preview_subsample = max(
            1,
            math.ceil(max(measurement.playres_x / 920, measurement.playres_y / 560)),
        )
        self._ppm = composite_rgba_to_ppm(
            measurement.rgba, measurement.playres_x, measurement.playres_y,
            subsample=self._preview_subsample,
        )
        self._photo_source = tk.PhotoImage(data=self._ppm, format="PPM")
        self._photo = self._photo_source
        self._scale = 1.0
        self._image_origin = (0.0, 0.0)
        self._drag: Optional[tuple[str, float, float, CropRect]] = None
        self._sync_fields()
        self._update_info()
        self.after_idle(self._redraw)
        self.grab_set()

    def _sync_fields(self) -> None:
        self._vars["x"].set(str(self.rect.x))
        self._vars["y"].set(str(self.rect.y))
        self._vars["w"].set(str(self.rect.width))
        self._vars["h"].set(str(self.rect.height))

    def _set_rect(self, rect: CropRect) -> None:
        self.rect = rect.clamp(self.measurement.playres_x, self.measurement.playres_y)
        self._sync_fields()
        self._update_info()
        self._redraw()

    def _apply_fields(self) -> None:
        try:
            rect = CropRect(
                int(self._vars["x"].get()), int(self._vars["y"].get()),
                int(self._vars["w"].get()), int(self._vars["h"].get()),
            )
        except ValueError:
            messagebox.showerror("Некорректный crop", "X, Y, W и H должны быть целыми числами.", parent=self)
            return
        self._set_rect(rect)

    def _use_auto(self) -> None:
        self._set_rect(self.auto_crop)

    def _center_on_content(self) -> None:
        bbox = self.measurement.content_bbox
        x = int(round((bbox.x + bbox.right - self.rect.width) / 2))
        y = int(round((bbox.y + bbox.bottom - self.rect.height) / 2))
        self._set_rect(CropRect(x, y, self.rect.width, self.rect.height))

    def _make_even(self) -> None:
        self._set_rect(make_even_crop(
            self.rect, self.measurement.playres_x, self.measurement.playres_y
        ))

    def _add_50px_vertical(self) -> None:
        new_y = self.rect.y - 50
        new_h = self.rect.height + 100
        self._set_rect(CropRect(self.rect.x, new_y, self.rect.width, new_h))

    def _accept(self) -> None:
        self.on_apply(self.rect)
        self.destroy()

    def _update_info(self) -> None:
        output = scaled_crop_rect(
            self.rect, self.measurement.playres_x, self.measurement.playres_y,
            self.output_scale,
        )
        follow_hint = " (следование активно)" if self.follow_enabled else ""
        self.info.configure(text=(
            f"Технический кадр: {self.measurement.playres_x}×{self.measurement.playres_y}; "
            f"crop: {self.rect.width}×{self.rect.height}{follow_hint}; "
            f"итог {self.output_scale:g}×: {output.width}×{output.height}. "
            "Рамку можно двигать и растягивать за углы."
        ))

    def _preview_geometry(self) -> tuple[float, float, float]:
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        w = self._photo_source.width()
        h = self._photo_source.height()
        factor = max(1, math.ceil(max(w / max(1, cw - 20), h / max(1, ch - 20))))
        if factor != getattr(self, "_subsample_factor", None):
            self._subsample_factor = factor
            self._photo = self._photo_source.subsample(factor, factor) if factor > 1 else self._photo_source
        display_w = self._photo.width()
        display_h = self._photo.height()
        ox = (cw - display_w) / 2
        oy = (ch - display_h) / 2
        return 1.0 / (self._preview_subsample * factor), ox, oy

    def _redraw(self) -> None:
        self.canvas.delete("all")
        scale, ox, oy = self._preview_geometry()
        self._scale = scale
        self._image_origin = (ox, oy)
        self.canvas.create_image(ox, oy, image=self._photo, anchor="nw")
        bbox = self.measurement.content_bbox
        bx0 = ox + bbox.x * scale
        by0 = oy + bbox.y * scale
        bx1 = ox + bbox.right * scale
        by1 = oy + bbox.bottom * scale
        self.canvas.create_rectangle(bx0, by0, bx1, by1, outline=self.palette.accent_alt, width=1, dash=(4, 3))
        self.canvas.create_text(
            bx0 + 4, by0 + 4, text="Полный bbox текста", anchor="nw",
            fill=self.palette.accent_alt, font=("TkDefaultFont", 8),
        )
        x0, y0, x1, y1 = self._canvas_rect(self.rect)
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=self.palette.warning, width=2, tags="crop")
        size = 4
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            self.canvas.create_rectangle(
                x - size, y - size, x + size, y + size,
                fill=self.palette.warning, outline=self.palette.warning,
            )

    def _canvas_rect(self, rect: CropRect) -> tuple[float, float, float, float]:
        ox, oy = self._image_origin
        s = self._scale
        return (ox + rect.x * s, oy + rect.y * s, ox + rect.right * s, oy + rect.bottom * s)

    def _source_point(self, canvas_x: float, canvas_y: float) -> tuple[float, float]:
        ox, oy = self._image_origin
        scale = max(1e-9, self._scale)
        return (canvas_x - ox) / scale, (canvas_y - oy) / scale

    def _drag_start_event(self, event) -> None:
        sx, sy = self._source_point(event.x, event.y)
        rect = self.rect
        tolerance = 10 / max(1e-9, self._scale)
        near_left = abs(sx - rect.x) <= tolerance
        near_right = abs(sx - rect.right) <= tolerance
        near_top = abs(sy - rect.y) <= tolerance
        near_bottom = abs(sy - rect.bottom) <= tolerance
        if near_left and near_top:
            mode = "nw"
        elif near_right and near_top:
            mode = "ne"
        elif near_left and near_bottom:
            mode = "sw"
        elif near_right and near_bottom:
            mode = "se"
        elif rect.x <= sx <= rect.right and rect.y <= sy <= rect.bottom:
            mode = "move"
        else:
            return
        self._drag = (mode, sx, sy, rect)

    def _drag_motion(self, event) -> None:
        if self._drag is None:
            return
        mode, start_x, start_y, original = self._drag
        sx, sy = self._source_point(event.x, event.y)
        dx, dy = int(round(sx - start_x)), int(round(sy - start_y))
        canvas_w, canvas_h = self.measurement.playres_x, self.measurement.playres_y
        if mode == "move":
            x = max(0, min(canvas_w - original.width, original.x + dx))
            y = max(0, min(canvas_h - original.height, original.y + dy))
            rect = CropRect(x, y, original.width, original.height)
        else:
            left, top, right, bottom = original.x, original.y, original.right, original.bottom
            if "w" in mode:
                left = max(0, min(right - 1, left + dx))
            if "e" in mode:
                right = min(canvas_w, max(left + 1, right + dx))
            if "n" in mode:
                top = max(0, min(bottom - 1, top + dy))
            if "s" in mode:
                bottom = min(canvas_h, max(top + 1, bottom + dy))
            rect = CropRect(left, top, right - left, bottom - top)
        self.rect = rect
        self._sync_fields()
        self._update_info()
        self._redraw()

    def _drag_end(self, _event) -> None:
        self._drag = None


class BurstStyleEditorDialog(tk.Toplevel):
    """Edit the shared karaoke/counter ASS style with a real libass preview."""

    PREVIEW_WIDTH = 900
    PREVIEW_HEIGHT = 220

    def __init__(
        self,
        master,
        *,
        source_style: AssTextStyle,
        initial_style: AssTextStyle,
        ffmpeg: str | Path | None,
        on_apply: Callable[[AssTextStyle], bool],
        burst_color_mode: str = "single",
        burst_base_color: str = "&H0000FF&",
        burst_alt_color: str = "&H0080FF&",
        burst_hue_offset: float = 30.0,
        burst_pulse_hz: float = 2.0,
        font_offset_y: int = 0,
        on_apply_burst_colors: Optional[Callable[..., None]] = None,
    ) -> None:
        super().__init__(master)
        self.owner = master.winfo_toplevel()
        self.title("Стиль karaoke и Burst SPS")
        self.transient(self.owner)
        self.resizable(False, False)
        self.source_style = source_style
        self.base_style = initial_style
        self.ffmpeg = ffmpeg
        self.on_apply = on_apply
        self.on_apply_burst_colors = on_apply_burst_colors
        self.burst_updating = False
        display_mode = BURST_COLOR_MODES.get(burst_color_mode, "Один цвет")
        self.burst_mode_var = tk.StringVar(value=display_mode)
        self.burst_base_color_var = tk.StringVar(value=normalize_ass_colour(burst_base_color))
        self.burst_alt_color_var = tk.StringVar(value=normalize_ass_colour(burst_alt_color))
        self.burst_hue_offset_var = tk.StringVar(value=f"{burst_hue_offset:g}")
        self.burst_hue_slider_var = tk.DoubleVar(value=burst_hue_offset)
        self.burst_pulse_hz = max(0.05, float(burst_pulse_hz))
        self.burst_pulse_hz_var = tk.StringVar(value=f"{self.burst_pulse_hz:g}")
        self.burst_pulse_bpm_var = tk.StringVar(value=f"{self.burst_pulse_hz * 60.0:g}")
        self.burst_font_offset_y_var = tk.StringVar(value=str(font_offset_y))
        self._syncing_tempo = False
        self._preview_job: Optional[str] = None
        self._preview_generation = 0
        self._preview_photo: Optional[tk.PhotoImage] = None
        self.palette: ThemePalette = getattr(master, "palette", get_theme(DEFAULT_THEME))
        self.configure(background=self.palette.bg)

        self.vars: dict[str, tk.Variable] = {
            "font_name": tk.StringVar(), "font_size": tk.StringVar(),
            "primary_colour": tk.StringVar(), "secondary_colour": tk.StringVar(),
            "outline_colour": tk.StringVar(), "back_colour": tk.StringVar(),
            "bold": tk.BooleanVar(), "italic": tk.BooleanVar(),
            "underline": tk.BooleanVar(), "strike_out": tk.BooleanVar(),
            "scale_x": tk.StringVar(), "scale_y": tk.StringVar(),
            "spacing": tk.StringVar(), "angle": tk.StringVar(),
            "border_style": tk.StringVar(), "outline": tk.StringVar(),
            "shadow": tk.StringVar(), "alignment": tk.StringVar(),
        }

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=f"Исходный karaoke-стиль: {source_style.name}",
            style="Header.TLabel",
        ).grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(
            body,
            text="Предпросмотр обновляется через тот же libass/FFmpeg, который используется при рендере.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(3, 10))

        ttk.Label(body, text="Шрифт:").grid(row=2, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.vars["font_name"], width=28).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(5, 12)
        )
        ttk.Label(body, text="Размер:").grid(row=2, column=3, sticky="e")
        ttk.Entry(body, textvariable=self.vars["font_size"], width=8).grid(
            row=2, column=4, sticky="w", padx=(5, 0)
        )

        toggles = ttk.Frame(body)
        toggles.grid(row=3, column=0, columnspan=6, sticky="w", pady=(8, 4))
        for key, label in (
            ("bold", "Bold"), ("italic", "Italic"),
            ("underline", "Underline"), ("strike_out", "Strikeout"),
        ):
            ttk.Checkbutton(toggles, text=label, variable=self.vars[key]).pack(side="left", padx=(0, 12))

        colour_rows = (
            ("primary_colour", "Основной цвет:"),
            ("secondary_colour", "Вторичный цвет:"),
            ("outline_colour", "Цвет обводки:"),
            ("back_colour", "Цвет тени:"),
        )
        for offset, (key, label) in enumerate(colour_rows):
            row = 4 + offset // 2
            col = (offset % 2) * 3
            ttk.Label(body, text=label).grid(row=row, column=col, sticky="w", pady=3)
            ttk.Entry(body, textvariable=self.vars[key], width=14).grid(
                row=row, column=col + 1, sticky="w", padx=(5, 3), pady=3
            )
            ttk.Button(
                body, text="…", width=3,
                command=lambda name=key: self._choose_colour(name),
            ).grid(row=row, column=col + 2, sticky="w", padx=(0, 12), pady=3)

        numeric = (
            ("scale_x", "Scale X:"), ("scale_y", "Scale Y:"),
            ("spacing", "Spacing:"), ("angle", "Angle:"),
            ("outline", "Outline:"), ("shadow", "Shadow:"),
        )
        for offset, (key, label) in enumerate(numeric):
            row = 6 + offset // 3
            col = (offset % 3) * 2
            ttk.Label(body, text=label).grid(row=row, column=col, sticky="w", pady=(7, 0))
            ttk.Entry(body, textvariable=self.vars[key], width=9).grid(
                row=row, column=col + 1, sticky="w", padx=(5, 12), pady=(7, 0)
            )
        ttk.Label(body, text="BorderStyle:").grid(row=8, column=0, sticky="w", pady=(7, 0))
        ttk.Combobox(
            body, state="readonly", width=7,
            textvariable=self.vars["border_style"], values=("1", "3"),
        ).grid(row=8, column=1, sticky="w", padx=(5, 12), pady=(7, 0))
        ttk.Label(body, text="Alignment:").grid(row=8, column=2, sticky="w", pady=(7, 0))
        ttk.Combobox(
            body, state="readonly", width=7,
            textvariable=self.vars["alignment"], values=("5", "2", "8", "4", "6", "1", "3", "7", "9"),
        ).grid(row=8, column=3, sticky="w", padx=(5, 12), pady=(7, 0))

        # Row 9: Burst Coloring Section
        burst_frame = ttk.LabelFrame(body, text="Окраска бёрста при рендере", padding=8)
        burst_frame.grid(row=9, column=0, columnspan=6, sticky="ew", pady=(10, 0))

        ttk.Label(burst_frame, text="Режим окраски:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(
            burst_frame, state="readonly", width=22,
            textvariable=self.burst_mode_var, values=list(BURST_COLOR_MODES.values()),
        ).grid(row=0, column=1, columnspan=2, sticky="w", padx=(5, 12), pady=2)

        ttk.Label(burst_frame, text="Базовый цвет:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(burst_frame, textvariable=self.burst_base_color_var, width=14).grid(
            row=1, column=1, sticky="w", padx=(5, 3), pady=3
        )
        ttk.Button(
            burst_frame, text="…", width=3,
            command=self._choose_burst_base_colour,
        ).grid(row=1, column=2, sticky="w", padx=(0, 12), pady=3)

        ttk.Label(burst_frame, text="Цвет чередования / финиша:").grid(row=1, column=3, sticky="w", pady=3)
        ttk.Entry(burst_frame, textvariable=self.burst_alt_color_var, width=14).grid(
            row=1, column=4, sticky="w", padx=(5, 3), pady=3
        )
        ttk.Button(
            burst_frame, text="…", width=3,
            command=self._choose_burst_alt_colour,
        ).grid(row=1, column=5, sticky="w", padx=(0, 12), pady=3)

        ttk.Label(burst_frame, text="Смещение оттенка (Hue):").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(burst_frame, textvariable=self.burst_hue_offset_var, width=7).grid(
            row=2, column=1, sticky="w", padx=(5, 3), pady=3
        )
        ttk.Scale(
            burst_frame, from_=-180.0, to=180.0,
            variable=self.burst_hue_slider_var, command=self._on_hue_slider_moved,
        ).grid(row=2, column=2, columnspan=3, sticky="ew", padx=(3, 12), pady=3)
        ttk.Label(burst_frame, text="±180°", style="Muted.TLabel").grid(row=2, column=5, sticky="w")

        ttk.Label(burst_frame, text="Пульсация (динамика):").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(burst_frame, textvariable=self.burst_pulse_hz_var, width=7).grid(
            row=3, column=1, sticky="w", padx=(5, 3), pady=3
        )
        ttk.Label(burst_frame, text="Гц").grid(row=3, column=2, sticky="w")
        ttk.Label(burst_frame, text="BPM:").grid(row=3, column=3, sticky="e", pady=3)
        ttk.Entry(burst_frame, textvariable=self.burst_pulse_bpm_var, width=7).grid(
            row=3, column=4, sticky="w", padx=(5, 3), pady=3
        )
        ttk.Label(burst_frame, text="уд/мин", style="Muted.TLabel").grid(row=3, column=5, sticky="w")

        ttk.Label(burst_frame, text="Смещение шрифта счетчика Y:").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Spinbox(
            burst_frame, from_=-500, to=500, textvariable=self.burst_font_offset_y_var, width=7,
        ).grid(row=4, column=1, sticky="w", padx=(5, 3), pady=3)
        ttk.Label(burst_frame, text="px (смещает текст отдельно от фона плашки)", style="Muted.TLabel").grid(
            row=4, column=2, columnspan=4, sticky="w"
        )
        burst_frame.columnconfigure(2, weight=1)

        preview_frame = ttk.LabelFrame(body, text="Live preview", padding=6)
        preview_frame.grid(row=10, column=0, columnspan=6, sticky="ew", pady=(12, 0))
        self.preview = ttk.Label(preview_frame, anchor="center")
        self.preview.pack()
        self.preview_status = tk.StringVar(value="")
        ttk.Label(preview_frame, textvariable=self.preview_status, style="Muted.TLabel").pack(
            anchor="w", pady=(4, 0)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=11, column=0, columnspan=6, sticky="ew", pady=(12, 0))
        ttk.Button(
            buttons, text="Исходный karaoke-стиль",
            command=self._reset_fields,
        ).pack(side="left")
        ttk.Button(buttons, text="Отмена", command=self._close).pack(side="right")
        ttk.Button(buttons, text="Применить", command=self._apply).pack(side="right", padx=(0, 6))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self._set_fields(initial_style)
        for variable in self.vars.values():
            variable.trace_add("write", self._schedule_preview)
        for burst_var in (self.burst_mode_var, self.burst_base_color_var, self.burst_alt_color_var, self.burst_hue_offset_var):
            burst_var.trace_add("write", self._schedule_preview)
        self.burst_pulse_hz_var.trace_add("write", self._on_hz_written)
        self.burst_pulse_bpm_var.trace_add("write", self._on_bpm_written)
        self.burst_pulse_hz_var.trace_add("write", self._schedule_preview)
        self.burst_font_offset_y_var.trace_add("write", self._schedule_preview)
        self.burst_base_color_var.trace_add("write", lambda *_a: self._recalculate_alt_from_hue())
        self.burst_hue_offset_var.trace_add("write", lambda *_a: self._recalculate_alt_from_hue())
        self._schedule_preview()

        self.update_idletasks()
        try:
            x = self.owner.winfo_rootx() + max(12, (self.owner.winfo_width() - self.winfo_reqwidth()) // 2)
            y = self.owner.winfo_rooty() + max(12, (self.owner.winfo_height() - self.winfo_reqheight()) // 3)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        self.lift(self.owner)
        self.focus_force()
        self.grab_set()

    @staticmethod
    def _ass_to_rgb(value: str) -> tuple[str, int]:
        raw = value.strip().rstrip("&")
        if raw[:2].casefold() == "&h":
            raw = raw[2:]
        number = int(raw, 16)
        alpha = (number >> 24) & 0xFF
        red, green, blue = number & 0xFF, (number >> 8) & 0xFF, (number >> 16) & 0xFF
        return f"#{red:02X}{green:02X}{blue:02X}", alpha

    @staticmethod
    def _rgb_to_ass(rgb: str, alpha: int) -> str:
        value = rgb.lstrip("#")
        red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
        return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"

    def _choose_colour(self, key: str) -> None:
        try:
            initial, alpha = self._ass_to_rgb(str(self.vars[key].get()))
        except (TypeError, ValueError):
            initial, alpha = "#FFFFFF", 0
        _rgb, chosen = colorchooser.askcolor(initialcolor=initial, parent=self, title="Выберите цвет")
        if chosen:
            self.vars[key].set(self._rgb_to_ass(chosen, alpha))

    def _choose_burst_base_colour(self) -> None:
        try:
            initial, _ = self._ass_to_rgb(str(self.burst_base_color_var.get()))
        except Exception:
            initial = "#FF0000"
        _rgb, chosen = colorchooser.askcolor(initialcolor=initial, parent=self, title="Базовый цвет бёрста")
        if chosen:
            self.burst_base_color_var.set(normalize_ass_colour(chosen))
            self._recalculate_alt_from_hue()

    def _choose_burst_alt_colour(self) -> None:
        try:
            initial, _ = self._ass_to_rgb(str(self.burst_alt_color_var.get()))
        except Exception:
            initial = "#FF8000"
        _rgb, chosen = colorchooser.askcolor(initialcolor=initial, parent=self, title="Цвет чередования / финиша")
        if chosen:
            self.burst_alt_color_var.set(normalize_ass_colour(chosen))
            self._recalculate_hue_from_alt()

    def _on_hue_slider_moved(self, val: str) -> None:
        if self.burst_updating:
            return
        self.burst_updating = True
        try:
            deg = round(float(val), 1)
            self.burst_hue_offset_var.set(f"{deg:g}")
            new_alt = shift_hue(self.burst_base_color_var.get(), deg)
            self.burst_alt_color_var.set(new_alt)
        finally:
            self.burst_updating = False
        self._schedule_preview()

    def _on_hz_written(self, *_args) -> None:
        if self._syncing_tempo:
            return
        self._syncing_tempo = True
        try:
            val = float(self.burst_pulse_hz_var.get().replace(",", "."))
            bpm = round(val * 60.0, 1)
            self.burst_pulse_bpm_var.set(f"{bpm:g}")
        except Exception:
            pass
        finally:
            self._syncing_tempo = False

    def _on_bpm_written(self, *_args) -> None:
        if self._syncing_tempo:
            return
        self._syncing_tempo = True
        try:
            val = float(self.burst_pulse_bpm_var.get().replace(",", "."))
            hz = round(val / 60.0, 3)
            self.burst_pulse_hz_var.set(f"{hz:g}")
        except Exception:
            pass
        finally:
            self._syncing_tempo = False

    def _recalculate_alt_from_hue(self) -> None:
        if self.burst_updating:
            return
        self.burst_updating = True
        try:
            deg = float(self.burst_hue_offset_var.get().replace(",", "."))
            new_alt = shift_hue(self.burst_base_color_var.get(), deg)
            self.burst_alt_color_var.set(new_alt)
            self.burst_hue_slider_var.set(deg)
        except Exception:
            pass
        finally:
            self.burst_updating = False
        self._schedule_preview()

    def _recalculate_hue_from_alt(self) -> None:
        if self.burst_updating:
            return
        self.burst_updating = True
        try:
            deg = calculate_hue_offset_degrees(self.burst_base_color_var.get(), self.burst_alt_color_var.get())
            self.burst_hue_offset_var.set(f"{deg:g}")
            self.burst_hue_slider_var.set(deg)
        except Exception:
            pass
        finally:
            self.burst_updating = False
        self._schedule_preview()

    @staticmethod
    def _number(value: object) -> float:
        return float(str(value).replace(",", "."))

    def _current_style(self) -> AssTextStyle:
        return replace(
            self.base_style,
            font_name=str(self.vars["font_name"].get()).strip(),
            font_size=self._number(self.vars["font_size"].get()),
            primary_colour=str(self.vars["primary_colour"].get()).strip(),
            secondary_colour=str(self.vars["secondary_colour"].get()).strip(),
            outline_colour=str(self.vars["outline_colour"].get()).strip(),
            back_colour=str(self.vars["back_colour"].get()).strip(),
            bold=bool(self.vars["bold"].get()), italic=bool(self.vars["italic"].get()),
            underline=bool(self.vars["underline"].get()), strike_out=bool(self.vars["strike_out"].get()),
            scale_x=self._number(self.vars["scale_x"].get()),
            scale_y=self._number(self.vars["scale_y"].get()),
            spacing=self._number(self.vars["spacing"].get()),
            angle=self._number(self.vars["angle"].get()),
            border_style=int(str(self.vars["border_style"].get())),
            outline=self._number(self.vars["outline"].get()),
            shadow=self._number(self.vars["shadow"].get()),
            alignment=int(str(self.vars["alignment"].get())),
        ).validate()

    def _set_fields(self, style: AssTextStyle) -> None:
        values = asdict(style)
        for key, variable in self.vars.items():
            value = values[key]
            if isinstance(value, float):
                value = f"{value:g}"
            variable.set(value)
        self.base_style = style

    def _reset_fields(self) -> None:
        self._set_fields(self.source_style)

    def _schedule_preview(self, *_args) -> None:
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
        self._preview_job = self.after(220, self._launch_preview)

    def _launch_preview(self) -> None:
        self._preview_job = None
        if self.ffmpeg is None:
            self.preview_status.set(
                "Live preview недоступен: настройте FFmpeg; редактирование и применение стиля работают."
            )
            return
        try:
            style = self._current_style()
        except (TypeError, ValueError) as exc:
            self.preview_status.set(f"Некорректный стиль: {exc}")
            return
        self._preview_generation += 1
        generation = self._preview_generation
        self.preview_status.set("libass: обновление…")

        def work() -> None:
            try:
                mode_key = BURST_COLOR_MODES_INV.get(self.burst_mode_var.get(), "single")
                try:
                    hue_off = float(self.burst_hue_offset_var.get().replace(",", "."))
                except ValueError:
                    hue_off = 30.0
                try:
                    pulse_hz = max(0.05, min(50.0, float(self.burst_pulse_hz_var.get().replace(",", "."))))
                except ValueError:
                    pulse_hz = 2.0
                try:
                    font_off_y = int(self.burst_font_offset_y_var.get())
                except ValueError:
                    font_off_y = 0
                document = build_burst_style_preview_document(
                    style,
                    width=self.PREVIEW_WIDTH,
                    height=self.PREVIEW_HEIGHT,
                    burst_color_mode=mode_key,
                    burst_base_color=self.burst_base_color_var.get(),
                    burst_alt_color=self.burst_alt_color_var.get(),
                    burst_hue_offset=hue_off,
                    burst_pulse_hz=pulse_hz,
                    font_offset_y=font_off_y,
                )
                rgba, width, height = render_rgba_frame(
                    document,
                    ffmpeg=self.ffmpeg,
                    width=self.PREVIEW_WIDTH,
                    height=self.PREVIEW_HEIGHT,
                    timestamp=0.5,
                )
                ppm = composite_rgba_to_ppm(rgba, width, height)
            except Exception as exc:
                try:
                    self.after(0, lambda exc=exc: self._preview_failed(generation, exc))
                except tk.TclError:
                    pass
                return
            try:
                self.after(0, lambda: self._preview_ready(generation, ppm))
            except tk.TclError:
                pass

        threading.Thread(target=work, name="burst-style-preview", daemon=True).start()

    def _preview_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._preview_generation or not self.winfo_exists():
            return
        self.preview_status.set(f"Preview: {exc}")

    def _preview_ready(self, generation: int, ppm: bytes) -> None:
        if generation != self._preview_generation or not self.winfo_exists():
            return
        self._preview_photo = tk.PhotoImage(master=self, data=ppm, format="PPM")
        self.preview.configure(image=self._preview_photo)
        self.preview_status.set("Текущий стиль — отрисовано libass")

    def _apply(self) -> None:
        try:
            style = self._current_style()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Некорректный стиль", str(exc), parent=self)
            return
        if not self.on_apply(style):
            return
        if self.on_apply_burst_colors is not None:
            mode_key = BURST_COLOR_MODES_INV.get(self.burst_mode_var.get(), "single")
            try:
                hue_off = float(self.burst_hue_offset_var.get().replace(",", "."))
            except ValueError:
                hue_off = 30.0
            try:
                pulse_hz = max(0.05, min(50.0, float(self.burst_pulse_hz_var.get().replace(",", "."))))
            except ValueError:
                pulse_hz = 2.0
            try:
                font_off_y = int(self.burst_font_offset_y_var.get())
            except ValueError:
                font_off_y = 0
            self.on_apply_burst_colors(
                mode_key,
                self.burst_base_color_var.get(),
                self.burst_alt_color_var.get(),
                hue_off,
                pulse_hz,
                font_off_y,
            )
        self._close()


    def _close(self) -> None:
        self._preview_generation += 1
        if self._preview_job is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
        self.destroy()

class RenderPanel(ttk.Frame):
    _PROJECT_STATE_VARS = (
        "max_words_var", "max_chars_var", "remove_original_breaks_var",
        "spacing_var", "origin_var", "padding_var", "even_var",
        "enable_romanization_var",
        "romanization_size_percent_var", "romanization_offset_y_var",
        "text_case_var", "romanization_case_var",
        "burst_color_mode_var", "burst_base_color_var", "burst_alt_color_var", "burst_hue_offset_var",
        "burst_pulse_hz_var", "burst_font_offset_y_var",
        "fps_var", "resolution_scale_var", "profile_var", "output_var",
        "include_audio_var", "follow_enabled_var", "follow_lines_var",
        "follow_easing_var", "follow_smooth_var", "follow_motion_var", "show_burst_sps_var", "burst_counter_interval_var",
        "burst_round_summary_var", "burst_custom_summary_var",
        "range_enabled_var", "range_pre_var", "range_post_var",
    )

    def __init__(
        self,
        master,
        *,
        session,
        prepare_source: Callable[[], bool],
        set_status: Callable[[str], None],
        task_center: TaskCenter | None = None,
        selected_syllables: Optional[Callable[[], set[str]]] = None,
        document_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master, padding=8)
        self.session = session
        self.prepare_source = prepare_source
        self.set_status = set_status
        self.task_center = task_center
        self.selected_syllables = selected_syllables or (lambda: set())
        self.document_changed = document_changed or (lambda: None)
        self.measurement: Optional[RenderMeasurement] = None
        self.crop: Optional[CropRect] = None
        self._generation = 0
        self._render_generation = 0
        self._render_cancel_event: Optional[threading.Event] = None
        self.palette: ThemePalette = get_theme(DEFAULT_THEME)
        self.advanced_mode = True

        self.max_words_var = tk.StringVar(value="0")
        self.max_chars_var = tk.StringVar(value="0")
        self.remove_original_breaks_var = tk.BooleanVar(value=False)
        self.spacing_var = tk.StringVar(value="20")
        self.origin_var = tk.StringVar(value="-2000000")
        self.padding_var = tk.StringVar(value="24")
        self.even_var = tk.BooleanVar(value=True)
        self.enable_romanization_var = tk.BooleanVar(value=True)
        self.romanization_size_percent_var = tk.StringVar(value="55")
        self.romanization_offset_y_var = tk.StringVar(value="0")
        self.text_case_var = tk.StringVar(value="as_is")
        self.romanization_case_var = tk.StringVar(value="as_is")
        self.text_case_display_var = tk.StringVar(value=TEXT_CASE_CHOICES["as_is"])
        self.romanization_case_display_var = tk.StringVar(value=TEXT_CASE_CHOICES["as_is"])

        def _sync_text_case(*_args):
            code = TEXT_CASE_LABELS.get(self.text_case_display_var.get(), self.text_case_display_var.get())
            if code in TEXT_CASE_CHOICES and self.text_case_var.get() != code:
                self.text_case_var.set(code)
            self._layout_geometry_changed()

        def _sync_romaji_case(*_args):
            code = TEXT_CASE_LABELS.get(self.romanization_case_display_var.get(), self.romanization_case_display_var.get())
            if code in TEXT_CASE_CHOICES and self.romanization_case_var.get() != code:
                self.romanization_case_var.set(code)
            self._layout_geometry_changed()

        def _sync_text_case_var(*_args):
            val = self.text_case_var.get()
            disp = TEXT_CASE_CHOICES.get(val, TEXT_CASE_CHOICES["as_is"])
            if self.text_case_display_var.get() != disp:
                self.text_case_display_var.set(disp)

        def _sync_romaji_case_var(*_args):
            val = self.romanization_case_var.get()
            disp = TEXT_CASE_CHOICES.get(val, TEXT_CASE_CHOICES["as_is"])
            if self.romanization_case_display_var.get() != disp:
                self.romanization_case_display_var.set(disp)

        self.text_case_display_var.trace_add("write", _sync_text_case)
        self.romanization_case_display_var.trace_add("write", _sync_romaji_case)
        self.text_case_var.trace_add("write", _sync_text_case_var)
        self.romanization_case_var.trace_add("write", _sync_romaji_case_var)
        self.playres_var = tk.StringVar(value="PlayRes: —")
        self.measure_var = tk.StringVar(value="Размещение текста ещё не проверено")
        self.crop_var = tk.StringVar(value="Итоговый кадр: —")
        self.fps_var = tk.StringVar(value="60")
        self.resolution_scale_var = tk.StringVar(value="2")
        self.profile_var = tk.StringVar(value=next(iter(PROFILE_LABELS)))
        self.output_var = tk.StringVar(value="")
        self.overlay_audio_var = tk.StringVar(value="Аудио: медиа не выбрано")
        self.include_audio_var = tk.BooleanVar(value=True)
        self.follow_enabled_var = tk.BooleanVar(value=False)
        self.follow_lines_var = tk.StringVar(value="4")
        self.follow_easing_var = tk.StringVar(value="0.35")
        self.follow_smooth_var = tk.StringVar(value="50")
        self.follow_motion_var = tk.StringVar(value="Переход к активной строке")
        self.show_burst_sps_var = tk.BooleanVar(value=False)
        self.burst_counter_interval_var = tk.StringVar(value="Весь трек")
        self.burst_round_summary_var = tk.BooleanVar(value=False)
        self.burst_custom_summary_var = tk.StringVar(value="")
        self.burst_color_mode_var = tk.StringVar(value="single")
        self.burst_color_mode_display_var = tk.StringVar(value=BURST_COLOR_MODES["single"])
        self.burst_base_color_var = tk.StringVar(value="&H0000FF&")
        self.burst_alt_color_var = tk.StringVar(value="&H0080FF&")
        self.burst_hue_offset_var = tk.StringVar(value="30")
        self.burst_pulse_hz_var = tk.StringVar(value="2.0")
        self.burst_font_offset_y_var = tk.StringVar(value="0")
        self.burst_color_summary_var = tk.StringVar(value="")
        self.burst_style_override: Optional[AssTextStyle] = None
        self.burst_style_label_var = tk.StringVar(value="Общий стиль karaoke и счётчика: —")
        self.range_enabled_var = tk.BooleanVar(value=False)
        self.range_start_var = tk.StringVar(value="")
        self.range_end_var = tk.StringVar(value="")
        self.range_pre_var = tk.StringVar(value="0")
        self.range_post_var = tk.StringVar(value="0")
        self.range_summary_var = tk.StringVar(value="Диапазон: весь ASS")
        self._range_label_to_id: dict[str, str] = {}
        self._range_id_to_label: dict[str, str] = {}
        self._update_burst_color_summary()
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="Karaoke render / layout", style="Header.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.playres_var, style="Muted.TLabel").pack(side="left", padx=12)

        settings = ttk.LabelFrame(self, text="Разметка перед рендером", padding=8)
        self.layout_settings_frame = settings
        settings.pack(fill="x", pady=(8, 6))
        ttk.Label(settings, text="Макс. слов в строке (0 = не менять):").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.max_words_var, width=8).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(settings, text="Межстрочный интервал, px:").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.spacing_var, width=8).grid(row=0, column=3, sticky="w", padx=(6, 18))
        ttk.Label(settings, text="Далёкий X для \\org:").grid(row=0, column=4, sticky="w")
        ttk.Entry(settings, textvariable=self.origin_var, width=12).grid(row=0, column=5, sticky="w", padx=(6, 0))

        ttk.Label(settings, text="Padding вокруг текста, px:").grid(row=1, column=0, sticky="w", pady=(7, 0))
        ttk.Entry(settings, textvariable=self.padding_var, width=8).grid(row=1, column=1, sticky="w", padx=(6, 18), pady=(7, 0))
        ttk.Label(settings, text="Перенести слово после символа (0 = выкл.):").grid(row=1, column=2, sticky="w", pady=(7, 0))
        ttk.Entry(settings, textvariable=self.max_chars_var, width=8).grid(row=1, column=3, sticky="w", padx=(6, 18), pady=(7, 0))
        ttk.Checkbutton(
            settings, text="Убрать оригинальные переносы",
            variable=self.remove_original_breaks_var,
            command=self._layout_geometry_changed,
        ).grid(row=1, column=4, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            settings, text="Чётные W/H", variable=self.even_var,
            command=self._layout_geometry_changed,
        ).grid(row=2, column=0, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            settings, text="Рендерить ромадзи", variable=self.enable_romanization_var,
            command=self._on_enable_romanization_toggled,
        ).grid(row=2, column=1, sticky="w", padx=(0, 18), pady=(7, 0))
        ttk.Label(settings, text="Размер ромадзи, %:").grid(row=2, column=2, sticky="w", pady=(7, 0))
        self.romanization_size_entry = ttk.Entry(settings, textvariable=self.romanization_size_percent_var, width=8)
        self.romanization_size_entry.grid(
            row=2, column=3, sticky="w", padx=(6, 18), pady=(7, 0)
        )
        ttk.Label(settings, text="Смещение ромадзи Y, px:").grid(row=2, column=4, sticky="w", pady=(7, 0))
        self.romanization_offset_entry = ttk.Entry(settings, textvariable=self.romanization_offset_y_var, width=12)
        self.romanization_offset_entry.grid(
            row=2, column=5, sticky="w", padx=(6, 0), pady=(7, 0)
        )
        self._update_romanization_entry_states()

        ttk.Label(settings, text="Регистр текста:").grid(row=3, column=0, sticky="w", pady=(7, 0))
        ttk.Combobox(
            settings, state="readonly", width=34,
            textvariable=self.text_case_display_var,
            values=tuple(TEXT_CASE_CHOICES.values()),
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(6, 18), pady=(7, 0))
        ttk.Label(settings, text="Регистр ромадзи:").grid(row=3, column=3, sticky="w", pady=(7, 0))
        ttk.Combobox(
            settings, state="readonly", width=34,
            textvariable=self.romanization_case_display_var,
            values=tuple(TEXT_CASE_CHOICES.values()),
        ).grid(row=3, column=4, columnspan=2, sticky="w", padx=(6, 0), pady=(7, 0))

        ttk.Label(
            settings,
            text=(
                "Переносы меняются только в render-копии и никогда не переписывают исходный ASS. "
                "Интервал: \\org(-2000000,0) + точно вычисленный микроповорот \\frz."
            ),
            style="Muted.TLabel",
        ).grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
        for variable in (
            self.max_words_var, self.max_chars_var, self.spacing_var,
            self.origin_var, self.padding_var,
            self.romanization_size_percent_var, self.romanization_offset_y_var,
        ):
            variable.trace_add("write", lambda *_args: self._layout_geometry_changed())
        self.enable_romanization_var.trace_add("write", lambda *_args: self._on_enable_romanization_toggled())

        measure = ttk.LabelFrame(self, text="Точный crop по расширенному libass-пререндеру", padding=8)
        measure.pack(fill="x", pady=(0, 6))
        measure_actions = ttk.Frame(measure)
        measure_actions.pack(fill="x")
        ttk.Button(measure_actions, text="Рассчитать crop", command=self.measure_async).pack(side="left")
        ttk.Button(measure_actions, text="Preview / ручная обрезка…", command=self.open_crop_preview).pack(side="left", padx=(6, 0))
        ttk.Button(measure_actions, text="Экспорт render ASS…", command=self.export_ass).pack(side="left", padx=(6, 0))
        ttk.Label(measure, textvariable=self.measure_var, style="Muted.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Label(measure, textvariable=self.crop_var).pack(anchor="w", pady=(2, 0))

        range_frame = ttk.LabelFrame(self, text="Фрагмент рендера", padding=8)
        self.range_frame = range_frame
        range_frame.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(
            range_frame, text="Рендерить только выбранный диапазон слогов",
            variable=self.range_enabled_var, command=self._range_geometry_changed,
        ).grid(row=0, column=0, columnspan=5, sticky="w")
        ttk.Label(range_frame, text="Начало:").grid(row=1, column=0, sticky="w", pady=(7, 0))
        self.range_start_combo = ttk.Combobox(range_frame, state="readonly", textvariable=self.range_start_var, width=40)
        self.range_start_combo.grid(row=1, column=1, sticky="ew", padx=(5, 12), pady=(7, 0))
        self.range_start_combo.bind("<<ComboboxSelected>>", lambda _e: self._range_geometry_changed())
        ttk.Label(range_frame, text="Конец:").grid(row=1, column=2, sticky="w", pady=(7, 0))
        self.range_end_combo = ttk.Combobox(range_frame, state="readonly", textvariable=self.range_end_var, width=40)
        self.range_end_combo.grid(row=1, column=3, sticky="ew", padx=(5, 12), pady=(7, 0))
        self.range_end_combo.bind("<<ComboboxSelected>>", lambda _e: self._range_geometry_changed())
        ttk.Button(range_frame, text="Из выделения Karaoke", command=self._range_from_selection).grid(row=1, column=4, sticky="e", pady=(7, 0))
        ttk.Label(range_frame, text="До начала, с:").grid(row=2, column=0, sticky="w", pady=(7, 0))
        ttk.Entry(range_frame, textvariable=self.range_pre_var, width=9).grid(row=2, column=1, sticky="w", padx=(5, 12), pady=(7, 0))
        ttk.Label(range_frame, text="После конца, с:").grid(row=2, column=2, sticky="w", pady=(7, 0))
        ttk.Entry(range_frame, textvariable=self.range_post_var, width=9).grid(row=2, column=3, sticky="w", padx=(5, 12), pady=(7, 0))
        ttk.Label(
            range_frame, text="Pre/post-roll обрезает видео по таймингам слогов; добавленное аудио получает fade in/out той же длительности.",
            style="Muted.TLabel", wraplength=1050, justify="left",
        ).grid(row=3, column=0, columnspan=5, sticky="w", pady=(7, 0))
        ttk.Label(range_frame, textvariable=self.range_summary_var, style="Muted.TLabel").grid(
            row=4, column=0, columnspan=5, sticky="w", pady=(5, 0)
        )
        range_frame.columnconfigure(1, weight=1)
        range_frame.columnconfigure(3, weight=1)

        output = ttk.LabelFrame(self, text="Вывод", padding=8)
        self.overlay_output_frame = output
        output.pack(fill="x")
        ttk.Label(output, text="FPS:").grid(row=0, column=0, sticky="w")
        ttk.Entry(output, textvariable=self.fps_var, width=7).grid(row=0, column=1, sticky="w", padx=(5, 14))
        ttk.Label(output, text="Формат:").grid(row=0, column=2, sticky="w")
        profile = ttk.Combobox(output, state="readonly", width=30, textvariable=self.profile_var, values=tuple(PROFILE_LABELS))
        profile.grid(row=0, column=3, sticky="w", padx=(5, 14))
        profile.bind("<<ComboboxSelected>>", lambda _e: self._profile_changed())
        ttk.Label(output, text="Разрешение:").grid(row=0, column=4, sticky="w")
        self.overlay_scale_combo = ttk.Combobox(
            output, state="readonly", width=6, textvariable=self.resolution_scale_var,
            values=("1", "1.5", "2", "3", "4"),
        )
        self.overlay_scale_combo.grid(row=0, column=5, sticky="w", padx=(5, 14))
        self.overlay_scale_combo.bind("<<ComboboxSelected>>", lambda _e: self._resolution_scale_changed())
        ttk.Label(output, text="×").grid(row=0, column=6, sticky="w", padx=(0, 8))
        ttk.Label(output, text="Файл:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(output, textvariable=self.output_var).grid(row=1, column=1, columnspan=6, sticky="ew", padx=(5, 6), pady=(8, 0))
        ttk.Button(output, text="…", width=3, command=self.choose_output).grid(row=1, column=7, sticky="w", pady=(8, 0))
        btn_frame = ttk.Frame(output)
        btn_frame.grid(row=0, column=7, sticky="e")
        self.render_btn = ttk.Button(btn_frame, text="Рендер", command=self.render_async)
        self.render_btn.pack(side="left", padx=(0, 4))
        self.stop_render_btn = ttk.Button(btn_frame, text="Остановить", command=self.stop_render, state="disabled")
        self.stop_render_btn.pack(side="left")
        ttk.Checkbutton(
            output,
            text="Добавить исходное аудио из выбранного медиа",
            variable=self.include_audio_var,
            command=self._update_overlay_audio_label,
        ).grid(row=2, column=0, columnspan=8, sticky="w", pady=(7, 0))
        ttk.Label(output, textvariable=self.overlay_audio_var, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=8, sticky="w", pady=(3, 0)
        )
        output.columnconfigure(6, weight=1)
        self._overlay_advanced_widgets = []
        for col in range(4):
            self._overlay_advanced_widgets.extend(output.grid_slaves(row=0, column=col))

        follow = ttk.LabelFrame(self, text="Динамическое следование по строкам", padding=8)
        self.follow_frame = follow
        follow.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(
            follow,
            text="Обрезать высоту и плавно следовать за активной строкой",
            variable=self.follow_enabled_var,
            command=self._follow_changed,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(follow, text="Строк в кадре:").grid(row=0, column=2, sticky="e", padx=(18, 0))
        self.follow_lines_entry = ttk.Entry(follow, textvariable=self.follow_lines_var, width=7)
        self.follow_lines_entry.grid(row=0, column=3, sticky="w", padx=(5, 16))
        self.follow_easing_label = ttk.Label(follow, text="Easing, с:")
        self.follow_easing_label.grid(row=0, column=4, sticky="e")
        self.follow_easing_entry = ttk.Entry(follow, textvariable=self.follow_easing_var, width=7)
        self.follow_easing_entry.grid(row=0, column=5, sticky="w", padx=(5, 0))
        ttk.Label(follow, text="Движение камеры:").grid(row=1, column=0, sticky="w", pady=(7, 0))
        self.follow_motion_combo = ttk.Combobox(
            follow, state="readonly", width=28,
            textvariable=self.follow_motion_var,
            values=("Переход к активной строке", "Непрерывное скольжение"),
        )
        self.follow_motion_combo.grid(row=1, column=1, columnspan=2, sticky="w", pady=(7, 0))
        self.follow_motion_combo.bind("<<ComboboxSelected>>", lambda _e: self._follow_changed())
        self.follow_lines_entry.bind("<KeyRelease>", lambda _e: self._follow_changed())
        self.follow_easing_entry.bind("<KeyRelease>", lambda _e: self._follow_changed())
        ttk.Label(
            follow,
            text=(
                "Кадр сохраняет полную ширину текста, но показывает заданное число строк. "
                "Обычный режим делает cubic-easing переход при новой строке. Непрерывный режим "
                "скользит между строками; параметр сглаживания регулирует скорость: "
                "0% — изначальная ломаная, 50% — сглаженная кривая без остановок, 100% — линейная функция."
            ),
            style="Muted.TLabel", wraplength=1040, justify="left",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            follow,
            text="Show burst SPS",
            variable=self.show_burst_sps_var,
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(follow, text="Отдельный счётчик:").grid(
            row=3, column=1, sticky="e", padx=(18, 5), pady=(8, 0)
        )
        ttk.Combobox(
            follow,
            state="readonly",
            width=18,
            textvariable=self.burst_counter_interval_var,
            values=("Весь трек", "Только таблица"),
        ).grid(row=3, column=2, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(
            follow,
            text="Рендер счётчика отдельно…",
            command=self.render_burst_counter_async,
        ).grid(row=3, column=4, sticky="e", padx=(8, 4), pady=(8, 0))
        ttk.Button(
            follow,
            text="Стиль karaoke и счётчика…",
            command=self.open_burst_style_editor,
        ).grid(row=3, column=5, sticky="e", pady=(8, 0))
        ttk.Checkbutton(
            follow,
            text="Округлить итог бёрста до целой секунды",
            variable=self.burst_round_summary_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Label(follow, text="Своя итоговая строка:").grid(
            row=4, column=2, sticky="e", padx=(12, 5), pady=(7, 0)
        )
        ttk.Entry(
            follow, textvariable=self.burst_custom_summary_var,
        ).grid(row=4, column=3, columnspan=3, sticky="ew", pady=(7, 0))
        ttk.Label(
            follow, textvariable=self.burst_style_label_var, style="Muted.TLabel",
        ).grid(row=5, column=0, columnspan=6, sticky="w", pady=(5, 0))
        ttk.Label(follow, text="Окраска бёрста:").grid(
            row=6, column=0, sticky="w", pady=(6, 0)
        )
        self.burst_mode_combo = ttk.Combobox(
            follow,
            state="readonly",
            width=22,
            textvariable=self.burst_color_mode_display_var,
            values=list(BURST_COLOR_MODES.values()),
        )
        self.burst_mode_combo.grid(row=6, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.burst_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_burst_color_mode_changed())
        ttk.Label(
            follow, textvariable=self.burst_color_summary_var, style="Muted.TLabel",
        ).grid(row=6, column=3, columnspan=3, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(
            follow,
            text=(
                "Счётчик берёт красные burst-слоги из ASS. В основном выводе карточка "
                "накладывается после обрезки, справа снизу с отступом 15 px. "
                "Редактор меняет общий ASS-стиль karaoke и счётчика. "
                "Своя итоговая строка имеет приоритет над округлением. "
                "Отдельный режим «Только таблица» идёт от первого бёрста до конца песни "
                "и всегда использует нативный размер карточки."
            ),
            style="Muted.TLabel", wraplength=1040, justify="left",
        ).grid(row=7, column=0, columnspan=6, sticky="w", pady=(5, 0))
        follow.columnconfigure(3, weight=1)

        notes = ttk.Frame(self, padding=(0, 10, 0, 0))
        self.notes_frame = notes
        notes.pack(fill="x")
        ttk.Label(
            notes,
            text=(
                "Авторазмер увеличивает технический прозрачный кадр, пока весь многострочный Dialogue не перестанет обрезаться, "
                "затем берёт реальный alpha-bbox libass и добавляет padding. "
                "Исходный ASS не переписывается. Аудио для MOV кодируется в PCM, для MP4 — в AAC. "
                "Для \\move/\\t будет показано предупреждение: статический bbox не гарантирует всю траекторию."
            ),
            style="Muted.TLabel",
            wraplength=1080,
            justify="left",
        ).pack(anchor="w")

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette = palette

    def set_advanced_mode(self, advanced: bool) -> None:
        self.advanced_mode = bool(advanced)
        if advanced:
            self.layout_settings_frame.pack(fill="x", pady=(8, 6), before=self.overlay_output_frame)
            self.notes_frame.pack(fill="x")
            for widget in self._overlay_advanced_widgets:
                widget.grid()
        else:
            self.layout_settings_frame.pack_forget()
            self.notes_frame.pack_forget()
            for widget in self._overlay_advanced_widgets:
                widget.grid_remove()

    @staticmethod
    def _portable_state_path(raw: str, root: Path) -> str:
        if not raw.strip():
            return ""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            return raw
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return str(path)

    def project_state(self, root: Path) -> dict:
        state = {
            name.removesuffix("_var"): getattr(self, name).get()
            for name in self._PROJECT_STATE_VARS
        }
        state["output"] = self._portable_state_path(str(state.get("output", "")), root)
        state["range_start_id"] = self._range_label_to_id.get(self.range_start_var.get())
        state["range_end_id"] = self._range_label_to_id.get(self.range_end_var.get())
        # Legacy key from the short-lived counter-only editor. Shared style is
        # now stored in the ASS itself and participates in normal Save/Undo.
        state["burst_counter_style"] = None
        return state

    def apply_project_state(self, state: object, root: Path) -> None:
        if not isinstance(state, dict):
            return
        for name in self._PROJECT_STATE_VARS:
            key = name.removesuffix("_var")
            if key not in state:
                continue
            value = state[key]
            if name == "output_var" and value:
                path = Path(str(value))
                value = str((root / path).resolve()) if not path.is_absolute() else str(path)
            try:
                getattr(self, name).set(value)
            except (tk.TclError, TypeError, ValueError):
                continue
        self.burst_style_override = None
        self._refresh_range_choices()
        start_id = state.get("range_start_id")
        end_id = state.get("range_end_id")
        if start_id in self._range_id_to_label:
            self.range_start_var.set(self._range_id_to_label[start_id])
        if end_id in self._range_id_to_label:
            self.range_end_var.set(self._range_id_to_label[end_id])
        self._update_range_summary()
        self._update_overlay_audio_label()
        self._update_burst_style_label()
        self.burst_color_mode_display_var.set(BURST_COLOR_MODES.get(self.burst_color_mode_var.get(), "Один цвет"))
        self._update_burst_color_summary()
        self._follow_changed()
        self._update_romanization_entry_states()

    def refresh_source(self, *, reset_measurement: bool = True) -> None:
        doc = self.session.document
        if doc is None:
            self.playres_var.set("PlayRes: —")
        else:
            x, y = ass_playres(doc)
            self.playres_var.set(f"PlayRes: {x}×{y}")
        self._update_overlay_audio_label()
        self._refresh_range_choices()
        self._update_burst_style_label()
        if reset_measurement:
            self._generation += 1
            self.measurement = None
            self.crop = None
            self.measure_var.set("Размещение текста ещё не проверено")
            self._update_crop_label()

    @staticmethod
    def _range_label(index: int, syllable) -> str:
        text = (syllable.text or "").strip().replace("\n", " ")
        if len(text) > 28:
            text = text[:27] + "…"
        return f"{index + 1:04d} · {syllable.start:.2f}s · {text or '∅'}"

    def _refresh_range_choices(self) -> None:
        old_start = self._range_label_to_id.get(self.range_start_var.get())
        old_end = self._range_label_to_id.get(self.range_end_var.get())
        usable = [s for s in self.session.syllables if not getattr(s, "is_gap", False) and (s.text or "").strip()]
        self._range_label_to_id.clear()
        self._range_id_to_label.clear()
        labels: list[str] = []
        for i, syllable in enumerate(usable):
            label = self._range_label(i, syllable)
            labels.append(label)
            self._range_label_to_id[label] = syllable.id
            self._range_id_to_label[syllable.id] = label
        self.range_start_combo.configure(values=labels)
        self.range_end_combo.configure(values=labels)
        if labels:
            self.range_start_var.set(self._range_id_to_label.get(old_start, labels[0]))
            self.range_end_var.set(self._range_id_to_label.get(old_end, labels[-1]))
        else:
            self.range_start_var.set("")
            self.range_end_var.set("")
        self._update_range_summary()

    def _range_from_selection(self) -> None:
        selected = set(self.selected_syllables() or set())
        if not selected:
            messagebox.showinfo("Нет выделения", "Выделите один или несколько слогов во вкладке «Караоке».", parent=self)
            return
        ordered = [s for s in self.session.syllables if s.id in selected and not getattr(s, "is_gap", False)]
        if not ordered:
            messagebox.showinfo("Нет karaoke-слогов", "В выделении нет видимых karaoke-слогов.", parent=self)
            return
        first, last = ordered[0], ordered[-1]
        if first.id not in self._range_id_to_label or last.id not in self._range_id_to_label:
            self._refresh_range_choices()
        self.range_start_var.set(self._range_id_to_label.get(first.id, self.range_start_var.get()))
        self.range_end_var.set(self._range_id_to_label.get(last.id, self.range_end_var.get()))
        self.range_enabled_var.set(True)
        self._range_geometry_changed()

    def _range_geometry_changed(self) -> None:
        # A different syllable subset can have a different libass alpha bbox.
        self.measurement = None
        self.crop = None
        self.measure_var.set("Размещение текста ещё не проверено")
        self._update_crop_label()
        self._update_range_summary()

    def _update_range_summary(self) -> None:
        if not self.range_enabled_var.get():
            self.range_summary_var.set("Диапазон: весь ASS")
            return
        start_id = self._range_label_to_id.get(self.range_start_var.get())
        end_id = self._range_label_to_id.get(self.range_end_var.get())
        by_id = {s.id: s for s in self.session.syllables}
        first, last = by_id.get(start_id), by_id.get(end_id)
        if first is None or last is None:
            self.range_summary_var.set("Диапазон: выберите начальный и конечный слог")
            return
        self.range_summary_var.set(
            f"Содержимое: {first.start:.3f}–{last.end:.3f} с · "
            f"длительность слогов {max(0.0, last.end - first.start):.3f} с"
        )

    def _range_request(self) -> Optional[RenderRangeSettings]:
        if not self.range_enabled_var.get():
            return None
        start_id = self._range_label_to_id.get(self.range_start_var.get())
        end_id = self._range_label_to_id.get(self.range_end_var.get())
        try:
            pre = float(self.range_pre_var.get().replace(",", "."))
            post = float(self.range_post_var.get().replace(",", "."))
        except ValueError as exc:
            raise RenderRangeError("Время до/после фрагмента должно быть числом") from exc
        return RenderRangeSettings(start_id or "", end_id or "", pre, post).validate()

    def _resolved_range(
        self,
        *,
        ffmpeg: Optional[Path] = None,
        source_media: Optional[Path] = None,
    ) -> Optional[ResolvedRenderRange]:
        request = self._range_request()
        if request is None:
            return None
        document = self.session.document
        if document is None:
            raise RenderRangeError("ASS не открыт")
        if source_media is None:
            return resolve_render_range(document, request)
        if ffmpeg is None:
            raise RenderRangeError("FFmpeg не настроен")
        media_duration = probe_media_duration(source_media, ffmpeg)
        if media_duration is None:
            raise RenderRangeError(
                "Не удалось определить длительность медиа через ffprobe. "
                "Без неё нельзя безопасно проверить границы фрагмента."
            )
        audio_bounds = probe_audio_bounds(source_media, ffmpeg)
        return resolve_render_range(
            document, request, media_duration=media_duration, audio_bounds=audio_bounds
        )

    def _layout_settings(self) -> RenderLayoutSettings:
        try:
            max_words = int(self.max_words_var.get())
            max_chars = int(self.max_chars_var.get())
            spacing = float(self.spacing_var.get().replace(",", "."))
            origin = float(self.origin_var.get().replace(",", "."))
            padding = int(self.padding_var.get())
            enable_rom = bool(self.enable_romanization_var.get())
            rom_size_raw = self.romanization_size_percent_var.get().strip().replace(",", ".")
            rom_size = float(rom_size_raw) if rom_size_raw else 55.0
            rom_offset_raw = self.romanization_offset_y_var.get().strip().replace(",", ".")
            rom_offset = int(float(rom_offset_raw)) if rom_offset_raw else 0
            burst_mode = self.burst_color_mode_var.get()
            burst_base = self.burst_base_color_var.get()
            burst_alt = self.burst_alt_color_var.get()
            burst_hue_raw = self.burst_hue_offset_var.get().strip().replace(",", ".")
            burst_hue = float(burst_hue_raw) if burst_hue_raw else 30.0
            burst_pulse_hz_raw = self.burst_pulse_hz_var.get().strip().replace(",", ".")
            burst_pulse_hz = float(burst_pulse_hz_raw) if burst_pulse_hz_raw else 2.0
            text_case = self.text_case_var.get()
            if text_case not in TEXT_CASE_CHOICES:
                text_case = TEXT_CASE_LABELS.get(self.text_case_display_var.get(), "as_is")
            romaji_case = self.romanization_case_var.get()
            if romaji_case not in TEXT_CASE_CHOICES:
                romaji_case = TEXT_CASE_LABELS.get(self.romanization_case_display_var.get(), "as_is")
        except ValueError as exc:
            raise ValueError("Параметры layout должны быть числами") from exc
        return RenderLayoutSettings(
            max_words_per_line=max_words,
            max_chars_per_line=max_chars,
            remove_original_line_breaks=bool(self.remove_original_breaks_var.get()),
            line_spacing_px=spacing,
            far_origin_x=origin,
            padding_left=padding,
            padding_right=padding,
            padding_top=padding,
            padding_bottom=padding,
            even_dimensions=self.even_var.get(),
            enable_romanization=enable_rom,
            romanization_size_percent=rom_size,
            romanization_offset_y=rom_offset,
            text_case=text_case,
            romanization_case=romaji_case,
            burst_color_mode=burst_mode,
            burst_base_color=burst_base,
            burst_alt_color=burst_alt,
            burst_hue_offset=burst_hue,
            burst_pulse_hz=burst_pulse_hz,
        ).validate()

    def _output_settings(self) -> RenderOutputSettings:
        try:
            fps = float(self.fps_var.get().replace(",", "."))
            resolution_scale = float(self.resolution_scale_var.get().replace(",", "."))
        except ValueError as exc:
            raise ValueError("FPS и масштаб разрешения должны быть числами") from exc
        profile = PROFILE_LABELS[self.profile_var.get()]
        return RenderOutputSettings(
            fps=fps, profile=profile, resolution_scale=resolution_scale
        ).validate()

    def _vertical_follow_settings(self) -> VerticalFollowSettings:
        if not self.follow_enabled_var.get():
            return VerticalFollowSettings()
        try:
            visible_lines = int(self.follow_lines_var.get())
            easing = float(self.follow_easing_var.get().replace(",", "."))
            smooth = float(self.follow_smooth_var.get().replace(",", "."))
        except (ValueError, TypeError) as exc:
            raise ValueError("Количество строк должно быть целым, easing и сглаживание — числами") from exc
        if visible_lines < 1:
            raise ValueError("Для динамической обрезки нужно показывать хотя бы одну строку")
        return VerticalFollowSettings(
            visible_lines=visible_lines,
            easing_seconds=easing,
            continuous=self.follow_motion_var.get() == "Непрерывное скольжение",
            smooth_percent=smooth,
        ).validate()

    def _burst_timing_overrides(self) -> dict[str, tuple[float, float]]:
        """Return only user-adjusted exact-SPS boundaries from the sidecar."""
        overrides: dict[str, tuple[float, float]] = {}
        sidecar = self.session.measurement_sidecar_path()
        if sidecar is not None and sidecar.exists():
            try:
                overrides.update({
                    syllable_id: (float(record.measured_start), float(record.measured_end))
                    for syllable_id, record in read_measurements(sidecar).items()
                })
            except (OSError, ValueError, TypeError):
                # A loaded live timeline still provides valid measurements; a
                # malformed sidecar will be reported by the SPS import UI.
                pass
        timeline = self.session.sps_timeline
        if timeline is not None:
            overrides.update({
                item.id: (float(item.effective_start), float(item.effective_end))
                for item in timeline.syllables
                if item.measurement_changed
            })
        return overrides

    def _burst_counter_settings(self) -> BurstCounterSettings:
        # The core resolves the active karaoke event style directly from ASS.
        try:
            font_offset_y = int(self.burst_font_offset_y_var.get())
        except (TypeError, ValueError, tk.TclError):
            font_offset_y = 0
        return BurstCounterSettings(
            round_summary_seconds=bool(self.burst_round_summary_var.get()),
            custom_summary=self.burst_custom_summary_var.get().strip(),
            font_offset_y=font_offset_y,
        ).validate()

    def _update_burst_style_label(self) -> None:
        document = self.session.document
        if document is None:
            self.burst_style_label_var.set("Общий стиль karaoke и счётчика: —")
            return
        style = karaoke_text_style(document)
        self.burst_style_label_var.set(
            f"Общий стиль «{style.name}» · {style.font_name}, {style.font_size:g}px"
        )

    def _on_burst_color_mode_changed(self) -> None:
        mode_key = BURST_COLOR_MODES_INV.get(self.burst_color_mode_display_var.get(), "single")
        self.burst_color_mode_var.set(mode_key)
        self._update_burst_color_summary()

    def _update_burst_color_summary(self) -> None:
        mode = self.burst_color_mode_var.get()
        base = self.burst_base_color_var.get()
        alt = self.burst_alt_color_var.get()
        hue = self.burst_hue_offset_var.get()
        if mode == "alternate":
            self.burst_color_summary_var.set(f"{base} ↔ {alt} ({hue}°)")
        elif mode == "gradient":
            self.burst_color_summary_var.set(f"{base} → {alt} ({hue}°)")
        elif mode == "dynamic":
            try:
                hz = float(self.burst_pulse_hz_var.get().replace(",", "."))
            except Exception:
                hz = 2.0
            self.burst_color_summary_var.set(f"{base} ↝ {alt} ({hue}°, {hz:g} Гц)")
        else:
            self.burst_color_summary_var.set(f"{base}")

    def open_burst_style_editor(self) -> None:
        if not self.prepare_source():
            return
        document = self.session.document
        if document is None:
            return
        ffmpeg = self.session.resolved_ffmpeg()
        source_style = karaoke_text_style(document)

        def applied(style: AssTextStyle) -> bool:
            try:
                self.session.edit_ass_style(source_style.name, style)
            except Exception as exc:
                messagebox.showerror("Не удалось изменить ASS-стиль", str(exc), parent=self)
                return False
            self.burst_style_override = None
            self.document_changed()
            self.refresh_source(reset_measurement=True)
            self.set_status(
                f"Стиль karaoke и Burst SPS изменён: {style.font_name}, {style.font_size:g}px · ASS ещё не сохранён"
            )
            return True

        def burst_colors_applied(
            mode: str, base: str, alt: str, hue: float,
            pulse_hz: float = 2.0, font_offset_y: int = 0,
        ) -> None:
            self.burst_color_mode_var.set(mode)
            self.burst_color_mode_display_var.set(BURST_COLOR_MODES.get(mode, "Один цвет"))
            self.burst_base_color_var.set(base)
            self.burst_alt_color_var.set(alt)
            self.burst_hue_offset_var.set(f"{hue:g}")
            self.burst_pulse_hz_var.set(f"{pulse_hz:g}")
            self.burst_font_offset_y_var.set(str(font_offset_y))
            self._update_burst_color_summary()
            self.refresh_source(reset_measurement=False)
            self.set_status(
                f"Окраска бёрста изменена: {BURST_COLOR_MODES.get(mode, mode)} · базовый {base} · {pulse_hz:g} Гц"
            )

        try:
            hue_val = float(self.burst_hue_offset_var.get().replace(",", "."))
        except ValueError:
            hue_val = 30.0
        try:
            pulse_hz_val = float(self.burst_pulse_hz_var.get().replace(",", "."))
        except ValueError:
            pulse_hz_val = 2.0
        try:
            font_offset_y_val = int(self.burst_font_offset_y_var.get())
        except ValueError:
            font_offset_y_val = 0

        BurstStyleEditorDialog(
            self,
            source_style=source_style,
            initial_style=source_style,
            ffmpeg=ffmpeg,
            on_apply=applied,
            burst_color_mode=self.burst_color_mode_var.get(),
            burst_base_color=self.burst_base_color_var.get(),
            burst_alt_color=self.burst_alt_color_var.get(),
            burst_hue_offset=hue_val,
            burst_pulse_hz=pulse_hz_val,
            font_offset_y=font_offset_y_val,
            on_apply_burst_colors=burst_colors_applied,
        )

    def measure_async(self) -> None:
        if not self.prepare_source():
            return
        document = self.session.document
        if document is None:
            messagebox.showinfo("Нет ASS", "Сначала откройте ASS-файл.", parent=self)
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            messagebox.showerror("FFmpeg не найден", "Настройте FFmpeg кнопкой «FFmpeg…». PATH/Conda автоматически не используются.", parent=self)
            return
        try:
            settings = self._layout_settings()
            render_range = self._resolved_range()
        except Exception as exc:
            messagebox.showerror("Некорректные настройки", str(exc), parent=self)
            return
        snapshot = document.dumps()
        from karaoke_core.ass import AssDocument
        work_doc = AssDocument.from_text(snapshot)
        self._generation += 1
        generation = self._generation
        self.measure_var.set("libass: считаю alpha-bbox…")
        self.set_status("Рассчитываю точный размер karaoke через libass…")
        task = self.task_center.start("FFmpeg", "Расчёт libass bbox", stage="Подготовка render-копии", progress=10) if self.task_center else None

        def work():
            try:
                if task:
                    task.update(35, "Рендер тестового RGBA-кадра")
                result = measure_render_layout(work_doc, settings, ffmpeg=ffmpeg, render_range=render_range)
                if task:
                    task.update(90, "Проверка полного текста на расширенном кадре")
            except Exception as exc:
                if task:
                    task.fail(str(exc))
                self.after(0, lambda exc=exc: self._measure_failed(generation, exc))
                return
            if task:
                task.done("Размер рассчитан")
            self.after(0, lambda: self._measure_finished(generation, result))

        threading.Thread(target=work, name="karaoke-layout-measure", daemon=True).start()

    def _measure_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._generation:
            return
        self.measure_var.set("Ошибка расчёта")
        self.set_status(f"Не удалось рассчитать karaoke bbox: {exc}")
        messagebox.showerror("Ошибка libass preview", str(exc), parent=self)

    def _measure_finished(self, generation: int, result: RenderMeasurement) -> None:
        if generation != self._generation:
            return
        self.measurement = result
        self.crop = result.crop
        self.measure_var.set(
            f"Исходный PlayRes {result.source_playres_x}×{result.source_playres_y}; "
            f"необрезанный технический кадр {result.playres_x}×{result.playres_y}; "
            f"текст {result.content_bbox.width}×{result.content_bbox.height}, строк: {result.line_count}"
        )
        self._update_crop_label()
        suffix = " · есть \\move/\\t" if result.dynamic_geometry else ""
        self.set_status(
            f"libass crop рассчитан по полному, не обрезанному пререндеру{suffix}"
        )
        if result.dynamic_geometry:
            messagebox.showwarning(
                "Динамическая геометрия ASS",
                "В ASS найдены \\move или \\t. Диагностическая рамка измеряет статический worst-case layout в одном кадре. "
                "Проверьте crop вручную, если движение выходит за статические границы.",
                parent=self,
            )

    def open_crop_preview(self) -> None:
        if self.measurement is None:
            messagebox.showinfo("Сначала рассчитайте crop", "Нажмите «Рассчитать crop».", parent=self)
            return
        CropPreviewDialog(
            self,
            self.measurement,
            initial_crop=self.crop or self.measurement.crop,
            auto_crop=self.measurement.crop,
            on_apply=self._apply_preview_crop,
            output_scale=self._resolution_scale_value(),
            follow_enabled=self.follow_enabled_var.get(),
        )

    def _apply_preview_crop(self, crop: CropRect) -> None:
        if self.measurement is None:
            return
        self.crop = crop.clamp(self.measurement.playres_x, self.measurement.playres_y)
        self._update_crop_label()
        self.set_status("Ручной crop применён к следующему standalone-рендеру")

    def _resolution_scale_value(self) -> float:
        try:
            return max(1.0, min(4.0, float(self.resolution_scale_var.get().replace(",", "."))))
        except (TypeError, ValueError, tk.TclError):
            return 2.0

    def _update_crop_label(self) -> None:
        if self.measurement is None or self.crop is None:
            self.crop_var.set("Итоговый кадр: сначала рассчитайте crop")
            return
        scale = self._resolution_scale_value()
        profile = PROFILE_LABELS.get(self.profile_var.get(), "transparent_mov")
        display_crop = self.crop
        follow_note = ""
        try:
            follow = self._vertical_follow_settings()
            if follow.enabled:
                display_crop = vertical_viewport_crop(
                    self.crop, self.measurement.content_bbox,
                    self.measurement.line_count, follow.visible_lines,
                    self.measurement.playres_x, self.measurement.playres_y,
                    base_crop=self.measurement.crop,
                )
                follow_note = f"; динамически {min(follow.visible_lines, self.measurement.line_count)} строк"
        except (ValueError, tk.TclError):
            follow_note = "; некорректные настройки следования"
        output_crop = scaled_crop_rect(
            display_crop, self.measurement.playres_x, self.measurement.playres_y, scale,
            even_dimensions=profile == "black_mp4",
        )
        self.crop_var.set(
            f"Crop: {display_crop.width}×{display_crop.height}{follow_note}; "
            f"итог при {scale:g}×: {output_crop.width}×{output_crop.height} px"
        )

    def _resolution_scale_changed(self) -> None:
        # Both comboboxes share one variable; refresh the explanatory size
        # immediately so the displayed output dimensions cannot go stale.
        self._update_crop_label()

    def _layout_geometry_changed(self) -> None:
        # Layout changes alter the libass bbox and line count. A stale crop was
        # the reason changing "words per line" could clip or break the render.
        self._generation += 1
        self.measurement = None
        self.crop = None
        self.measure_var.set("Параметры строк изменены — пересчитайте crop")
        self._update_crop_label()

    def _on_enable_romanization_toggled(self) -> None:
        self._update_romanization_entry_states()
        self._layout_geometry_changed()

    def _update_romanization_entry_states(self) -> None:
        state = "normal" if self.enable_romanization_var.get() else "disabled"
        if hasattr(self, "romanization_size_entry"):
            self.romanization_size_entry.configure(state=state)
        if hasattr(self, "romanization_offset_entry"):
            self.romanization_offset_entry.configure(state=state)

    def _follow_changed(self) -> None:
        continuous = self.follow_motion_var.get() == "Непрерывное скольжение"
        if continuous:
            self.follow_easing_label.configure(text="Сглаживание, %:")
            self.follow_easing_entry.configure(textvariable=self.follow_smooth_var, state="normal")
        else:
            self.follow_easing_label.configure(text="Easing, с:")
            self.follow_easing_entry.configure(textvariable=self.follow_easing_var, state="normal")
        self._update_crop_label()

    def _update_overlay_audio_label(self) -> None:
        if not self.include_audio_var.get():
            self.overlay_audio_var.set("Аудио: выключено — выходной файл будет без звука")
            return
        media = self.session.media_path
        if media is None:
            self.overlay_audio_var.set("Аудио: включено, но медиа проекта не выбрано")
            return
        profile = PROFILE_LABELS.get(self.profile_var.get(), "transparent_mov")
        codec = "PCM s16le (без потерь)" if profile == "transparent_mov" else "AAC 192 кбит/с"
        self.overlay_audio_var.set(f"Аудио: будет взято из {media.name} и перекодировано в {codec}")

    def _default_output(self) -> Path:
        ext = ".mov" if PROFILE_LABELS[self.profile_var.get()] == "transparent_mov" else ".mp4"
        stem = self.session.subtitle_path.stem if self.session.subtitle_path else "karaoke"
        if self.session.project_root is not None:
            return self.session.project_root / "exports" / f"{stem}-karaoke{ext}"
        base = self.session.subtitle_path.parent if self.session.subtitle_path else Path.cwd()
        return base / f"{stem}-karaoke{ext}"

    def _profile_changed(self) -> None:
        self._update_overlay_audio_label()
        self._update_crop_label()
        current = self.output_var.get().strip()
        if not current:
            return
        target = Path(current)
        ext = ".mov" if PROFILE_LABELS[self.profile_var.get()] == "transparent_mov" else ".mp4"
        self.output_var.set(str(target.with_suffix(ext)))

    def choose_output(self) -> None:
        default = Path(self.output_var.get()) if self.output_var.get().strip() else self._default_output()
        profile = PROFILE_LABELS[self.profile_var.get()]
        ext = ".mov" if profile == "transparent_mov" else ".mp4"
        types = (("QuickTime MOV", "*.mov"), ("Все файлы", "*.*")) if ext == ".mov" else (("MPEG-4", "*.mp4"), ("Все файлы", "*.*"))
        path = filedialog.asksaveasfilename(
            title="Файл karaoke render",
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=ext,
            filetypes=types,
        )
        if path:
            self.output_var.set(path)

    def render_burst_counter_async(self) -> None:
        """Export the information card as a frame-sized standalone video."""
        if not self.prepare_source():
            return
        document = self.session.document
        if document is None:
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            messagebox.showerror(
                "FFmpeg не найден",
                "Настройте FFmpeg кнопкой «FFmpeg…».",
                parent=self,
            )
            return
        if not burst_counter_regions(document):
            messagebox.showinfo(
                "Нет окрашенного бёрста",
                "Сначала отметьте бёрст кнопкой «Окрасить бёрст» во вкладке «Точный SPS».",
                parent=self,
            )
            return
        try:
            output_settings = self._output_settings()
            counter_settings = self._burst_counter_settings()
        except Exception as exc:
            messagebox.showerror("Некорректные настройки", str(exc), parent=self)
            return
        profile = output_settings.profile
        ext = ".mov" if profile == "transparent_mov" else ".mp4"
        stem = self.session.subtitle_path.stem if self.session.subtitle_path else "karaoke"
        if self.session.project_root is not None:
            default = self.session.project_root / "exports" / f"{stem}-burst-sps{ext}"
        else:
            base = self.session.subtitle_path.parent if self.session.subtitle_path else Path.cwd()
            default = base / f"{stem}-burst-sps{ext}"
        types = (
            (("QuickTime MOV", "*.mov"), ("Все файлы", "*.*"))
            if ext == ".mov"
            else (("MPEG-4", "*.mp4"), ("Все файлы", "*.*"))
        )
        path = filedialog.asksaveasfilename(
            title="Рендер Burst SPS отдельно",
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=ext,
            filetypes=types,
        )
        if not path:
            return
        output = Path(path)
        if output.suffix.lower() != ext:
            output = output.with_suffix(ext)

        from karaoke_core.ass import AssDocument
        work_doc = AssDocument.from_text(document.dumps())
        media = self.session.media_path
        media = media if media is not None and media.exists() else None
        active_only = self.burst_counter_interval_var.get() == "Только таблица"
        burst_timings = self._burst_timing_overrides()
        self._render_generation += 1
        generation = self._render_generation
        self._render_cancel_event = threading.Event()
        self.render_btn.configure(state="disabled")
        self.stop_render_btn.configure(state="normal")
        self.set_status(f"Рендерю отдельный Burst SPS: {output.name}…")
        task = (
            self.task_center.start(
                "FFmpeg", "Отдельный Burst SPS", stage="Измерение карточки", progress=0
            )
            if self.task_center else None
        )
        if task:
            task.log(f"Output: {output}")
            task.log(
                "Interval: "
                + ("from first burst to song end" if active_only else "full song")
            )
            task.log(f"Exact SPS timing overrides: {len(burst_timings)}")

        def work():
            try:
                duration = probe_media_duration(media, ffmpeg) if media is not None else None
                if duration is None:
                    duration = max_dialogue_end(work_doc)
                target = render_burst_counter_video(
                    work_doc,
                    output,
                    ffmpeg=ffmpeg,
                    output_settings=output_settings,
                    settings=counter_settings,
                    duration=duration,
                    active_interval_only=active_only,
                    burst_timing_overrides=burst_timings,
                    progress=(lambda value, stage: task.update(value, stage)) if task else None,
                    log=(lambda line: task.log(line)) if task else None,
                    cancel_event=self._render_cancel_event,
                )
            except Exception as exc:
                if task:
                    task.fail(str(exc))
                self.after(0, lambda exc=exc: self._render_failed(generation, exc))
                return
            if task:
                task.done(f"Burst SPS готов: {target.name}")
            self.after(0, lambda: self._burst_counter_finished(generation, target))

        threading.Thread(target=work, name="burst-sps-render", daemon=True).start()

    def export_ass(self) -> None:
        if not self.prepare_source():
            return
        if self.session.document is None:
            return
        try:
            settings = self._layout_settings()
            render_range = self._resolved_range()
        except Exception as exc:
            messagebox.showerror("Некорректные настройки", str(exc), parent=self)
            return
        stem = self.session.subtitle_path.stem if self.session.subtitle_path else "karaoke"
        path = filedialog.asksaveasfilename(
            title="Экспортировать render-копию ASS",
            initialfile=f"{stem}-render.ass",
            defaultextension=".ass",
            filetypes=(("Advanced SubStation Alpha", "*.ass"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        try:
            ffmpeg = self.session.resolved_ffmpeg()
            if (
                ffmpeg is None
                and settings.enable_romanization
                and any(item.romanization for item in self.session.document.karaoke_syllables())
            ):
                raise RuntimeError("Для позиционирования romanization нужен настроенный FFmpeg/libass")
            target = export_render_ass(
                self.session.document, settings, path,
                render_range=render_range, ffmpeg=ffmpeg or "ffmpeg",
            )
        except Exception as exc:
            messagebox.showerror("Не удалось экспортировать render ASS", str(exc), parent=self)
            return
        self.set_status(f"Render-копия ASS сохранена: {target}")

    def render_async(self) -> None:
        if not self.prepare_source():
            return
        if self.session.document is None:
            return
        if self.measurement is None or self.crop is None:
            messagebox.showinfo(
                "Сначала рассчитайте crop",
                "Нажмите «Рассчитать crop»: пререндер сначала расширит технический кадр, "
                "а затем найдёт полные границы всего текста.",
                parent=self,
            )
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            messagebox.showerror("FFmpeg не найден", "Настройте FFmpeg кнопкой «FFmpeg…». PATH/Conda автоматически не используются.", parent=self)
            return
        try:
            layout = self._layout_settings()
            output_settings = self._output_settings()
            follow_settings = self._vertical_follow_settings()
            selected_media = self.session.media_path
            selected_media = selected_media if selected_media is not None and selected_media.exists() else None
            audio_media = selected_media if self.include_audio_var.get() else None
            render_range = self._resolved_range(
                ffmpeg=ffmpeg if audio_media is not None else None,
                source_media=audio_media,
            )
        except Exception as exc:
            messagebox.showerror("Некорректные настройки", str(exc), parent=self)
            return
        output = Path(self.output_var.get().strip()) if self.output_var.get().strip() else self._default_output()
        expected_ext = ".mov" if output_settings.profile == "transparent_mov" else ".mp4"
        if output.suffix.lower() != expected_ext:
            output = output.with_suffix(expected_ext)
            self.output_var.set(str(output))
        from karaoke_core.ass import AssDocument
        work_doc = AssDocument.from_text(self.session.document.dumps())
        burst_settings = self._burst_counter_settings() if self.show_burst_sps_var.get() else None
        burst_timings = self._burst_timing_overrides() if burst_settings is not None else {}
        if burst_settings is not None and not burst_counter_regions(work_doc):
            messagebox.showinfo(
                "Нет окрашенного бёрста",
                "Show burst SPS включён, но в ASS нет красных burst-слогов. "
                "Отметьте их кнопкой «Окрасить бёрст» во вкладке «Точный SPS».",
                parent=self,
            )
            return
        measurement = self.measurement
        crop = self.crop
        self._render_generation += 1
        generation = self._render_generation
        self._render_cancel_event = threading.Event()
        self.render_btn.configure(state="disabled")
        self.stop_render_btn.configure(state="normal")
        self.set_status(f"Рендерю karaoke: {output.name}…")
        task = self.task_center.start("FFmpeg", "Standalone karaoke render", stage="Подготовка", progress=0) if self.task_center else None
        if task:
            task.log(f"Output: {output}")
            task.log(
                f"Preview canvas: {measurement.playres_x}×{measurement.playres_y}; "
                f"crop: {crop.x},{crop.y} {crop.width}×{crop.height}; "
                f"scale: {output_settings.resolution_scale:g}×"
            )
            if follow_settings.enabled:
                motion = (
                    f"continuous glide ({follow_settings.smooth_percent:g}% smooth)"
                    if follow_settings.continuous
                    else f"cubic easing {follow_settings.easing_seconds:g} s"
                )
                task.log(f"Vertical follow: {follow_settings.visible_lines} lines, {motion}")
            if burst_settings is not None:
                task.log(
                    "Burst SPS: enabled; compositing after vertical crop; "
                    f"exact timing overrides {len(burst_timings)}"
                )
            if audio_media is not None:
                task.log(f"Audio source: {audio_media}")
            else:
                task.log("Audio: disabled or no project media selected")

        def work():
            try:
                target = render_karaoke_video(
                    work_doc, layout, output,
                    crop=crop,
                    base_crop=measurement.crop,
                    render_canvas=(measurement.playres_x, measurement.playres_y),
                    ffmpeg=ffmpeg, output_settings=output_settings, render_range=render_range,
                    audio_source=audio_media,
                    vertical_follow_settings=follow_settings,
                    burst_counter_settings=burst_settings,
                    burst_timing_overrides=burst_timings,
                    content_bbox=measurement.content_bbox,
                    progress=(lambda value, stage: task.update(value, stage)) if task else None,
                    log=(lambda line: task.log(line)) if task else None,
                    cancel_event=self._render_cancel_event,
                )
            except Exception as exc:
                if task:
                    task.fail(str(exc))
                self.after(0, lambda exc=exc: self._render_failed(generation, exc))
                return
            if task:
                task.done(f"Render готов: {target.name}")
            self.after(0, lambda: self._render_finished(generation, target))

        threading.Thread(target=work, name="karaoke-video-render", daemon=True).start()

    def stop_render(self) -> None:
        if self._render_cancel_event is not None and not self._render_cancel_event.is_set():
            self._render_cancel_event.set()
            self.set_status("Останавливаю рендер (сигнал 'q')…")
            self.stop_render_btn.configure(state="disabled")

    def _render_failed(self, generation: int, exc: Exception) -> None:
        was_canceled = (
            (self._render_cancel_event is not None and self._render_cancel_event.is_set())
            or "отменён пользователем" in str(exc).lower()
        )
        self._render_cancel_event = None
        self.render_btn.configure(state="normal")
        self.stop_render_btn.configure(state="disabled")
        if generation != self._render_generation:
            return
        if was_canceled:
            self.set_status("Рендер остановлен пользователем.")
            return
        self.set_status(f"Рендер завершился ошибкой: {exc}")
        messagebox.showerror("Ошибка FFmpeg render", str(exc), parent=self)

    def _render_finished(self, generation: int, target: Path) -> None:
        self._render_cancel_event = None
        self.render_btn.configure(state="normal")
        self.stop_render_btn.configure(state="disabled")
        if generation != self._render_generation:
            return
        self.set_status(f"Karaoke render готов: {target}")
        messagebox.showinfo("Рендер завершён", f"Файл сохранён:\n{target}", parent=self)

    def _burst_counter_finished(self, generation: int, target: Path) -> None:
        self._render_cancel_event = None
        self.render_btn.configure(state="normal")
        self.stop_render_btn.configure(state="disabled")
        if generation != self._render_generation:
            return
        self.set_status(f"Отдельный Burst SPS готов: {target}")
        messagebox.showinfo(
            "Рендер счётчика завершён",
            f"Файл сохранён:\n{target}",
            parent=self,
        )
