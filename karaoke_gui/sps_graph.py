from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import textwrap
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable, Optional, Sequence

from karaoke_core.sps import SPSGraphPoint
from karaoke_gui.timeline import Viewport, format_clock
from karaoke_gui.theme import DEFAULT_THEME, ThemePalette, get_theme


@dataclass(slots=True)
class GraphSeries:
    name: str
    points: list[SPSGraphPoint]
    colour: str


@dataclass(slots=True, frozen=True)
class GraphExportSettings:
    width: int = 1920
    height: int = 1080
    scope: str = "visible"  # visible | all
    y_step: float | None = None
    x_step: float | None = None
    time_format: str = "clock"  # clock | seconds
    show_grid: bool = True
    show_points: bool = True
    show_legend: bool = True
    show_axis_labels: bool = True
    x_axis_label: str = "Время"
    y_axis_label: str = "SPS"
    show_peak: bool = False
    show_title: bool = True
    title: str = "SPS"
    show_subtitle: bool = True
    subtitle: str = "Legacy 1–2 s"

    def validate(self) -> "GraphExportSettings":
        if self.width < 320 or self.height < 180:
            raise ValueError("Размер SPS-графика должен быть не меньше 320×180")
        if self.scope not in {"visible", "all"}:
            raise ValueError("Неизвестный диапазон экспорта SPS-графика")
        if self.y_step is not None and (not math.isfinite(self.y_step) or self.y_step <= 0):
            raise ValueError("Шаг шкалы Y должен быть положительным числом")
        if self.x_step is not None and (not math.isfinite(self.x_step) or self.x_step <= 0):
            raise ValueError("Шаг шкалы X должен быть положительным числом")
        if self.time_format not in {"clock", "seconds"}:
            raise ValueError("Неизвестный формат времени оси X")
        return self


def ask_sps_graph_export_settings(
    parent,
    initial: GraphExportSettings,
) -> GraphExportSettings | None:
    """Open the modal PNG export options window."""
    initial.validate()
    dialog = tk.Toplevel(parent)
    dialog.title("Параметры экспорта SPS-графика")
    dialog.transient(parent)
    dialog.resizable(False, False)

    resolution_var = tk.StringVar(value=f"{initial.width}×{initial.height}")
    scope_var = tk.StringVar(value="Текущий вид" if initial.scope == "visible" else "Весь график")
    y_step_var = tk.StringVar(value="Авто" if initial.y_step is None else f"{initial.y_step:g}")
    x_step_var = tk.StringVar(value="Авто" if initial.x_step is None else f"{initial.x_step:g}")
    time_format_var = tk.StringVar(
        value="Тайминг (MM:SS.xx)" if initial.time_format == "clock" else "Секунды (123.45)"
    )
    show_grid_var = tk.BooleanVar(value=initial.show_grid)
    show_points_var = tk.BooleanVar(value=initial.show_points)
    show_legend_var = tk.BooleanVar(value=initial.show_legend)
    show_axis_labels_var = tk.BooleanVar(value=initial.show_axis_labels)
    x_axis_label_var = tk.StringVar(value=initial.x_axis_label)
    y_axis_label_var = tk.StringVar(value=initial.y_axis_label)
    show_peak_var = tk.BooleanVar(value=initial.show_peak)
    show_title_var = tk.BooleanVar(value=initial.show_title)
    title_var = tk.StringVar(value=initial.title)
    show_subtitle_var = tk.BooleanVar(value=initial.show_subtitle)
    subtitle_var = tk.StringVar(value=initial.subtitle)
    result: GraphExportSettings | None = None

    body = ttk.Frame(dialog, padding=12)
    body.grid(row=0, column=0, sticky="nsew")
    ttk.Label(body, text="Разрешение 16:9:").grid(row=0, column=0, sticky="w", pady=3)
    ttk.Combobox(
        body, textvariable=resolution_var, state="readonly", width=18,
        values=("1280×720", "1920×1080", "2560×1440", "3840×2160"),
    ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
    ttk.Label(body, text="Диапазон:").grid(row=1, column=0, sticky="w", pady=3)
    ttk.Combobox(
        body, textvariable=scope_var, state="readonly", width=18,
        values=("Текущий вид", "Весь график"),
    ).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
    ttk.Label(body, text="Шаг делений Y, SPS:").grid(row=2, column=0, sticky="w", pady=3)
    ttk.Combobox(
        body, textvariable=y_step_var, width=18,
        values=("Авто", "0.5", "1", "2", "5", "10"),
    ).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
    ttk.Label(body, text="Шаг делений X, секунд:").grid(row=3, column=0, sticky="w", pady=3)
    ttk.Combobox(
        body, textvariable=x_step_var, width=18,
        values=("Авто", "0.1", "0.25", "0.5", "1", "2", "5", "10", "30", "60"),
    ).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)
    ttk.Label(body, text="Формат времени X:").grid(row=4, column=0, sticky="w", pady=3)
    ttk.Combobox(
        body, textvariable=time_format_var, state="readonly", width=18,
        values=("Тайминг (MM:SS.xx)", "Секунды (123.45)"),
    ).grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=3)

    appearance = ttk.LabelFrame(body, text="Элементы графика", padding=8)
    appearance.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(9, 5))
    ttk.Checkbutton(appearance, text="Сетка", variable=show_grid_var).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(appearance, text="Точки", variable=show_points_var).grid(row=0, column=1, sticky="w", padx=(16, 0))
    ttk.Checkbutton(appearance, text="Легенда", variable=show_legend_var).grid(row=1, column=0, sticky="w", pady=(3, 0))
    ttk.Checkbutton(appearance, text="Подписи осей", variable=show_axis_labels_var).grid(row=1, column=1, sticky="w", padx=(16, 0), pady=(3, 0))
    ttk.Checkbutton(
        appearance, text="Выделить максимальный бёрст и показать текст",
        variable=show_peak_var,
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

    text_frame = ttk.LabelFrame(body, text="Название и подпись", padding=8)
    text_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(5, 8))
    title_check = ttk.Checkbutton(text_frame, text="Название", variable=show_title_var)
    title_check.grid(row=0, column=0, sticky="w")
    title_entry = ttk.Entry(text_frame, textvariable=title_var, width=48)
    title_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
    subtitle_check = ttk.Checkbutton(text_frame, text="Подпись", variable=show_subtitle_var)
    subtitle_check.grid(row=1, column=0, sticky="w", pady=(5, 0))
    subtitle_entry = ttk.Entry(text_frame, textvariable=subtitle_var, width=48)
    subtitle_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(5, 0))
    ttk.Label(text_frame, text="Ось X:").grid(row=2, column=0, sticky="w", pady=(5, 0))
    x_axis_entry = ttk.Entry(text_frame, textvariable=x_axis_label_var, width=48)
    x_axis_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(5, 0))
    ttk.Label(text_frame, text="Ось Y:").grid(row=3, column=0, sticky="w", pady=(5, 0))
    y_axis_entry = ttk.Entry(text_frame, textvariable=y_axis_label_var, width=48)
    y_axis_entry.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(5, 0))
    text_frame.columnconfigure(1, weight=1)

    def sync_text_states(*_args) -> None:
        title_entry.configure(state="normal" if show_title_var.get() else "disabled")
        subtitle_entry.configure(state="normal" if show_subtitle_var.get() else "disabled")
        axis_state = "normal" if show_axis_labels_var.get() else "disabled"
        x_axis_entry.configure(state=axis_state)
        y_axis_entry.configure(state=axis_state)

    show_title_var.trace_add("write", sync_text_states)
    show_subtitle_var.trace_add("write", sync_text_states)
    show_axis_labels_var.trace_add("write", sync_text_states)
    sync_text_states()

    def accept() -> None:
        nonlocal result
        try:
            width_raw, height_raw = resolution_var.get().replace("x", "×").split("×", 1)
            y_raw = y_step_var.get().strip().replace(",", ".")
            x_raw = x_step_var.get().strip().replace(",", ".")
            result = GraphExportSettings(
                width=int(width_raw), height=int(height_raw),
                scope="visible" if scope_var.get() == "Текущий вид" else "all",
                y_step=None if not y_raw or y_raw.casefold() == "авто" else float(y_raw),
                x_step=None if not x_raw or x_raw.casefold() == "авто" else float(x_raw),
                time_format=(
                    "clock" if time_format_var.get().startswith("Тайминг") else "seconds"
                ),
                show_grid=show_grid_var.get(), show_points=show_points_var.get(),
                show_legend=show_legend_var.get(),
                show_axis_labels=show_axis_labels_var.get(),
                x_axis_label=x_axis_label_var.get().strip(),
                y_axis_label=y_axis_label_var.get().strip(),
                show_peak=show_peak_var.get(),
                show_title=show_title_var.get(), title=title_var.get().strip(),
                show_subtitle=show_subtitle_var.get(), subtitle=subtitle_var.get().strip(),
            ).validate()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Некорректные параметры", str(exc), parent=dialog)
            return
        dialog.destroy()

    buttons = ttk.Frame(body)
    buttons.grid(row=7, column=0, columnspan=2, sticky="e")
    ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right")
    ttk.Button(buttons, text="Продолжить…", command=accept).pack(side="right", padx=(0, 7))
    body.columnconfigure(1, weight=1)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    dialog.bind("<Return>", lambda _event: accept())
    dialog.update_idletasks()
    try:
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dialog.winfo_reqheight()) // 2)
        dialog.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    dialog.grab_set()
    parent.wait_window(dialog)
    return result


def _smoothed_graph_points(
    points: list[SPSGraphPoint], smoothing: int,
) -> list[tuple[SPSGraphPoint, float]]:
    smoothing = max(1, int(smoothing))
    if smoothing <= 1 or len(points) <= 2:
        return [(point, point.speed) for point in points]
    radius = smoothing // 2
    result: list[tuple[SPSGraphPoint, float]] = []
    for index, point in enumerate(points):
        start = max(0, index - radius)
        end = min(len(points), index + radius + 1)
        result.append((point, sum(item.speed for item in points[start:end]) / (end - start)))
    return result


def _format_graph_time(value: float, mode: str) -> str:
    if mode == "seconds":
        return f"{float(value):.2f}"
    return format_clock(value)


def _image_font(size: int, *, bold: bool = False):
    try:
        from PIL import ImageFont
    except ImportError as exc:  # pragma: no cover - handled by caller too
        raise RuntimeError("Экспорт PNG требует Pillow (pip install Pillow)") from exc
    names = ("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")
    candidates = [Path("C:/Windows/Fonts") / name for name in names]
    candidates.append(
        Path("/usr/share/fonts/truetype/dejavu")
        / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), max(8, int(size)))
            except OSError:
                continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", max(8, int(size)))
    except OSError:
        return ImageFont.load_default()


def render_sps_graph_png(
    path: str | Path,
    series: Sequence[GraphSeries],
    *,
    viewport: Viewport,
    palette: ThemePalette,
    smoothing: int = 1,
    width: int = 1920,
    height: int = 1080,
    title: str = "SPS · Legacy 1–2 s",
    settings: GraphExportSettings | None = None,
) -> Path:
    """Render the selected SPS graph and current viewport to a 16:9 PNG.

    This draws from graph data rather than taking a screen capture, so the
    exported image keeps its requested resolution even when the GUI graph is
    currently short or partly obscured by another pane.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Экспорт PNG требует Pillow (pip install Pillow)") from exc
    if settings is None:
        settings = GraphExportSettings(
            width=int(width), height=int(height), title=title,
            subtitle=(
                f"Видимый диапазон: {format_clock(viewport.view_start)}–"
                f"{format_clock(viewport.view_end)} · сглаживание {max(1, int(smoothing))}"
            ),
        )
    settings.validate()
    width, height = settings.width, settings.height

    image = Image.new("RGB", (width, height), palette.canvas)
    draw = ImageDraw.Draw(image)
    scale = min(width / 1920.0, height / 1080.0)
    title_font = _image_font(round(34 * scale), bold=True)
    label_font = _image_font(round(22 * scale))
    small_font = _image_font(round(18 * scale))
    left = max(78, round(width * 0.075))
    right = width - max(30, round(width * 0.025))
    top = max(82, round(height * 0.11))
    bottom = height - max(72, round(height * 0.09))
    line_width = max(2, round(3 * scale))

    if settings.show_title and settings.title:
        draw.text(
            (left, max(16, round(24 * scale))), settings.title,
            fill=palette.fg, font=title_font,
        )
    if settings.show_subtitle and settings.subtitle:
        draw.text(
            (left, top - max(34, round(38 * scale))), settings.subtitle,
            fill=palette.muted, font=small_font,
        )
    draw.rectangle((left, top, right, bottom), fill=palette.canvas_alt, outline=palette.border, width=max(1, round(2 * scale)))

    visible = [
        point for item in series for point in item.points
        if viewport.view_start - 1e-9 <= point.time <= viewport.view_end + 1e-9
    ]
    maximum_speed = max((point.speed for point in visible), default=1.0)
    if settings.y_step is None:
        step = 2.0 if maximum_speed <= 20 else 5.0
        ymax = max(2.0, (int(maximum_speed / 2.0) + 2) * 2.0)
    else:
        step = settings.y_step
        ymax = max(step * 2, math.ceil(maximum_speed / step + 0.5) * step)
    graph_width = max(1, right - left)
    graph_height = max(1, bottom - top)
    span = max(1e-9, viewport.span)

    def x_coord(time_value: float) -> float:
        return left + (time_value - viewport.view_start) / span * graph_width

    def y_coord(speed: float) -> float:
        return bottom - max(0.0, min(ymax, speed)) / ymax * graph_height

    value = 0.0
    while value <= ymax + 1e-9:
        y = y_coord(value)
        if settings.show_grid:
            draw.line((left, y, right, y), fill=palette.grid, width=max(1, round(scale)))
        label = f"{value:g}"
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((left - 10 - (box[2] - box[0]), y - (box[3] - box[1]) / 2), label, fill=palette.muted, font=small_font)
        value += step
    if settings.show_axis_labels:
        if settings.y_axis_label:
            y_box = draw.textbbox((0, 0), settings.y_axis_label, font=label_font)
            y_padding = max(3, round(4 * scale))
            y_layer = Image.new(
                "RGBA",
                (
                    y_box[2] - y_box[0] + y_padding * 2,
                    y_box[3] - y_box[1] + y_padding * 2,
                ),
                (0, 0, 0, 0),
            )
            ImageDraw.Draw(y_layer).text(
                (y_padding - y_box[0], y_padding - y_box[1]),
                settings.y_axis_label, fill=palette.fg, font=label_font,
            )
            y_layer = y_layer.rotate(90, expand=True)
            y_label_x = max(2, left - max(64, round(70 * scale)) - y_layer.width)
            y_label_y = round((top + bottom - y_layer.height) / 2)
            image.paste(y_layer, (y_label_x, y_label_y), y_layer)
        time_label = settings.x_axis_label
        time_box = draw.textbbox((0, 0), time_label, font=label_font)
        draw.text(
            (right - (time_box[2] - time_box[0]), bottom + max(38, round(42 * scale))),
            time_label, fill=palette.fg, font=label_font,
        )

    if settings.x_step is None:
        time_ticks = [viewport.view_start + division / 4 * span for division in range(5)]
    else:
        tick_count = int(math.floor(span / settings.x_step)) + 2
        if tick_count > 250:
            raise ValueError(
                "Для выбранного диапазона шаг X создаёт больше 250 делений; увеличьте шаг"
            )
        first_tick = math.ceil((viewport.view_start - 1e-9) / settings.x_step) * settings.x_step
        time_ticks = []
        time_value = first_tick
        while time_value <= viewport.view_end + 1e-9:
            time_ticks.append(time_value)
            time_value += settings.x_step
    for time_value in time_ticks:
        x = x_coord(time_value)
        if settings.show_grid:
            draw.line((x, top, x, bottom), fill=palette.grid, width=max(1, round(scale)))
        label = _format_graph_time(time_value, settings.time_format)
        box = draw.textbbox((0, 0), label, font=small_font)
        draw.text((x - (box[2] - box[0]) / 2, bottom + 10), label, fill=palette.muted, font=small_font)

    legend_x = left + max(12, round(14 * scale))
    legend_y = top + max(16, round(18 * scale))
    peak_candidate: tuple[float, SPSGraphPoint, str, float, float, str] | None = None
    for graph_series in series:
        points = [
            point for point in graph_series.points
            if viewport.view_start - 1e-9 <= point.time <= viewport.view_end + 1e-9
        ]
        points.sort(key=lambda point: point.time)
        limit = max(500, graph_width * 2)
        if len(points) > limit:
            sample_step = max(1, len(points) // limit)
            subset = points[::sample_step]
            if subset and subset[-1] is not points[-1]:
                subset.append(points[-1])
            points = subset
        smoothed = _smoothed_graph_points(points, smoothing)
        coordinates = [(x_coord(point.time), y_coord(speed)) for point, speed in smoothed]
        if smoothed:
            peak_point, peak_value = max(smoothed, key=lambda item: item[1])
            if peak_candidate is None or peak_value > peak_candidate[0]:
                peak_candidate = (
                    peak_value, peak_point, graph_series.name,
                    x_coord(peak_point.time), y_coord(peak_value), graph_series.colour,
                )
        if len(coordinates) >= 2:
            draw.line(coordinates, fill=graph_series.colour, width=line_width, joint="curve")
        if settings.show_points and len(coordinates) <= 400:
            radius = max(2, round(3 * scale))
            for x, y in coordinates:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=graph_series.colour)

        if settings.show_legend:
            draw.line(
                (legend_x, legend_y, legend_x + round(34 * scale), legend_y),
                fill=graph_series.colour, width=max(3, round(5 * scale)),
            )
            draw.text(
                (legend_x + round(44 * scale), legend_y), graph_series.name,
                anchor="lm", fill=palette.fg, font=label_font,
            )
            label_box = draw.textbbox((0, 0), graph_series.name, font=label_font)
            legend_x += round(64 * scale) + label_box[2] - label_box[0]

    if settings.show_peak and peak_candidate is not None:
        peak_value, peak_point, series_name, peak_x, peak_y, series_colour = peak_candidate
        marker_radius = max(7, round(9 * scale))
        draw.ellipse(
            (
                peak_x - marker_radius, peak_y - marker_radius,
                peak_x + marker_radius, peak_y + marker_radius,
            ),
            fill=palette.warning, outline=palette.fg, width=max(2, round(2 * scale)),
        )
        draw.ellipse(
            (peak_x - 3, peak_y - 3, peak_x + 3, peak_y + 3),
            fill=series_colour,
        )
        snippet = " ".join(peak_point.text.replace("\n", " ").split())
        snippet = textwrap.shorten(snippet, width=110, placeholder="…") if snippet else "(без текста)"
        wrapped = textwrap.wrap(snippet, width=58)[:2]
        heading = (
            f"Макс. {series_name}: {peak_value:.3f} SPS · "
            f"{peak_point.count} сл. / {peak_point.duration:.3f} с"
        )
        callout = "\n".join([heading, *wrapped])
        text_box = draw.multiline_textbbox(
            (0, 0), callout, font=small_font, spacing=max(3, round(4 * scale)),
        )
        padding = max(8, round(10 * scale))
        card_width = text_box[2] - text_box[0] + padding * 2
        card_height = text_box[3] - text_box[1] + padding * 2
        card_x = peak_x + marker_radius + padding
        if card_x + card_width > right - padding:
            card_x = peak_x - marker_radius - padding - card_width
        card_x = max(left + padding, min(right - padding - card_width, card_x))
        card_y = peak_y - card_height - marker_radius - padding
        if card_y < top + padding:
            card_y = peak_y + marker_radius + padding
        card_y = max(top + padding, min(bottom - padding - card_height, card_y))
        draw.rounded_rectangle(
            (card_x, card_y, card_x + card_width, card_y + card_height),
            radius=max(4, round(7 * scale)), fill=palette.panel,
            outline=palette.warning, width=max(2, round(2 * scale)),
        )
        draw.multiline_text(
            (card_x + padding, card_y + padding), callout,
            fill=palette.fg, font=small_font, spacing=max(3, round(4 * scale)),
        )

    if not visible:
        message = "Нет данных SPS-графика в текущем диапазоне"
        box = draw.textbbox((0, 0), message, font=label_font)
        draw.text(
            ((left + right - (box[2] - box[0])) / 2, (top + bottom - (box[3] - box[1])) / 2),
            message, fill=palette.muted, font=label_font,
        )

    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG", optimize=True)
    return target


class SPSGraph(ttk.Frame):
    """SPS plot linked to the exact same viewport as the SPS timeline.

    The graph deliberately owns no independent horizontal navigation state.
    Zoom/pan performed here updates the shared Viewport, while navigation in the
    waveform/spectrogram timeline immediately redraws this graph.
    """

    def __init__(
        self,
        master,
        *,
        viewport: Viewport,
        on_view_changed: Optional[Callable[[], None]] = None,
        on_point_selected: Optional[Callable[[SPSGraphPoint], None]] = None,
    ):
        super().__init__(master)
        self.viewport = viewport
        self.on_view_changed = on_view_changed
        self.on_point_selected = on_point_selected
        self.series: list[GraphSeries] = []
        self.smoothing = 1
        self.selected: Optional[SPSGraphPoint] = None
        self._hover: Optional[SPSGraphPoint] = None
        self._middle_x: Optional[int] = None
        self._redraw_job: Optional[str] = None
        self._resize_job: Optional[str] = None
        self._needs_redraw_on_map = False
        self.palette: ThemePalette = get_theme(DEFAULT_THEME)

        self.canvas = tk.Canvas(self, height=185, highlightthickness=0, background=self.palette.canvas)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._configure_redraw)
        self.canvas.bind("<Map>", self._mapped_redraw, add="+")
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda _e: self._clear_hover())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Shift-MouseWheel>", lambda e: self._wheel(e, force_pan=True))
        self.canvas.bind("<Button-4>", lambda e: self._linux_wheel(e, -1))
        self.canvas.bind("<Button-5>", lambda e: self._linux_wheel(e, 1))
        self.canvas.bind("<ButtonPress-2>", self._pan_start)
        self.canvas.bind("<B2-Motion>", self._pan_drag)

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette = palette
        self.canvas.configure(background=palette.canvas)
        # Reuse already calculated SPS points.  Rebuilding the series here used
        # to make a theme change look frozen for several seconds on long ASS
        # files.  Only the two display colours need to change.
        for series in self.series:
            if series.name == "ASS":
                series.colour = palette.accent
            elif series.name == "Measured":
                series.colour = palette.accent_alt
        self.request_redraw(delay_ms=1)

    def set_series(self, series: Sequence[GraphSeries], *, smoothing: int = 1) -> None:
        self.series = [GraphSeries(s.name, list(s.points), s.colour) for s in series]
        self.smoothing = max(1, int(smoothing))
        if self.selected is not None:
            valid = {p for s in self.series for p in s.points}
            if self.selected not in valid:
                self.selected = None
        self.redraw()

    def clear(self) -> None:
        self.series = []
        self.selected = None
        self._hover = None
        self.redraw()

    def _visible_points(self) -> list[SPSGraphPoint]:
        lo, hi = self.viewport.view_start, self.viewport.view_end
        return [p for s in self.series for p in s.points if lo - 1e-9 <= p.time <= hi + 1e-9]

    def _smooth(self, points: list[SPSGraphPoint]) -> list[tuple[SPSGraphPoint, float]]:
        return _smoothed_graph_points(points, self.smoothing)

    def _bounds(self) -> tuple[int, int, int, int, float]:
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        left, right, top, bottom = 48, max(58, w - 8), 8, max(25, h - 25)
        visible = self._visible_points()
        ymax = max((p.speed for p in visible), default=1.0)
        # Keep some visual headroom and stable useful integer scale.
        ymax = max(2.0, (int(ymax / 2.0) + 2) * 2.0)
        return left, right, top, bottom, ymax

    def _x(self, time_value: float, left: int, right: int) -> float:
        span = max(1e-9, self.viewport.span)
        return left + (time_value - self.viewport.view_start) / span * (right - left)

    @staticmethod
    def _y(speed: float, top: int, bottom: int, ymax: float) -> float:
        return bottom - max(0.0, min(ymax, speed)) / ymax * (bottom - top)

    def _is_drawable(self) -> bool:
        try:
            if not self.winfo_exists():
                return False
            top = self.winfo_toplevel()
            if top.wm_state() in {"withdrawn", "iconic"}:
                return False
            parent = self._nametowidget(self.winfo_parent())
            while parent and parent != top:
                if parent.winfo_class() == "TNotebook":
                    return bool(self.winfo_ismapped())
                parent = getattr(parent, "master", None)
            return True
        except tk.TclError:
            return False

    def request_redraw(self, delay_ms: int = 16, *, force: bool = False) -> None:
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
        self._needs_redraw_on_map = False
        self.request_redraw(delay_ms=1, force=True)

    def _configure_redraw(self, _event=None) -> None:
        if not self._is_drawable():
            self._needs_redraw_on_map = True
            return
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

    @staticmethod
    def _display_subset(points: list[SPSGraphPoint], pixel_width: int) -> list[SPSGraphPoint]:
        """Limit line geometry at whole-song scale without changing source data."""
        limit = max(500, int(pixel_width) * 2)
        if len(points) <= limit:
            return points
        step = max(1, len(points) // limit)
        subset = points[::step]
        if subset and subset[-1] is not points[-1]:
            subset.append(points[-1])
        return subset

    def redraw(self) -> None:
        if not self._is_drawable():
            self._needs_redraw_on_map = True
            return
        self._needs_redraw_on_map = False
        c = self.canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill=self.palette.canvas, outline="")
        left, right, top, bottom, ymax = self._bounds()
        c.create_rectangle(left, top, right, bottom, fill=self.palette.canvas_alt, outline=self.palette.border)

        # Horizontal SPS grid.
        step = 2.0 if ymax <= 20 else 5.0
        yv = 0.0
        while yv <= ymax + 1e-9:
            y = self._y(yv, top, bottom, ymax)
            c.create_line(left, y, right, y, fill=self.palette.grid)
            c.create_text(left - 6, y, text=f"{yv:g}", anchor="e", fill=self.palette.muted, font=("TkDefaultFont", 8))
            yv += step
        c.create_text(7, top + 2, text="SPS", anchor="nw", fill=self.palette.fg, font=("TkDefaultFont", 8))

        # Time labels: 0, 25, 50, 75, 100% of viewport.
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = left + frac * (right - left)
            t = self.viewport.view_start + frac * self.viewport.span
            c.create_line(x, top, x, bottom, fill=self.palette.grid)
            c.create_text(x, bottom + 5, text=format_clock(t), anchor="n", fill=self.palette.muted, font=("TkDefaultFont", 7))

        for series in self.series:
            points = [p for p in series.points if self.viewport.view_start - 1e-9 <= p.time <= self.viewport.view_end + 1e-9]
            points.sort(key=lambda p: p.time)
            points = self._display_subset(points, max(1, right - left))
            smooth = self._smooth(points)
            coords: list[float] = []
            for p, value in smooth:
                coords.extend((self._x(p.time, left, right), self._y(value, top, bottom, ymax)))
            if len(coords) >= 4:
                c.create_line(*coords, fill=series.colour, width=2, smooth=False)
            if len(points) <= 400:
                for p, value in smooth:
                    x, y = self._x(p.time, left, right), self._y(value, top, bottom, ymax)
                    c.create_oval(x - 2, y - 2, x + 2, y + 2, fill=series.colour, outline="")

        # Legend.
        lx = left + 6
        for series in self.series:
            c.create_line(lx, top + 10, lx + 18, top + 10, fill=series.colour, width=3)
            c.create_text(lx + 23, top + 10, text=series.name, anchor="w", fill=self.palette.fg, font=("TkDefaultFont", 8))
            lx += 23 + max(65, len(series.name) * 7)

        point = self._hover or self.selected
        if point is not None and self.viewport.view_start <= point.time <= self.viewport.view_end:
            x = self._x(point.time, left, right)
            y = self._y(point.speed, top, bottom, ymax)
            c.create_line(x, top, x, bottom, fill=self.palette.fg, dash=(3, 3))
            c.create_oval(x - 5, y - 5, x + 5, y + 5, outline=self.palette.fg, width=2)
            text = (
                f"{point.source_label}: {point.speed:.3f} SPS · {point.count} сл. / {point.duration:.3f} с\n"
                f"окно {format_clock(point.window_start)}–{format_clock(point.window_end)}"
            )
            if point.text:
                snippet = point.text.replace("\n", " ")
                if len(snippet) > 90:
                    snippet = snippet[:89] + "…"
                text += "\n" + snippet
            tx = min(right - 5, x + 10)
            anchor = "ne" if tx > right - 220 else "nw"
            if anchor == "ne":
                tx = x - 10
            ty = max(top + 3, y - 8)
            item = c.create_text(tx, ty, text=text, anchor=anchor, fill=self.palette.fg, font=("TkDefaultFont", 8), width=330)
            box = c.bbox(item)
            if box:
                rect = c.create_rectangle(box[0] - 5, box[1] - 4, box[2] + 5, box[3] + 4, fill=self.palette.panel, outline=self.palette.border)
                c.tag_raise(item, rect)

        if not any(s.points for s in self.series):
            c.create_text((left + right) / 2, (top + bottom) / 2, text="Нет данных SPS-графика", fill=self.palette.muted)

    def _nearest(self, x: int, y: int) -> Optional[SPSGraphPoint]:
        left, right, top, bottom, ymax = self._bounds()
        candidates = self._visible_points()
        if not candidates:
            return None
        best = None
        best_dist = float("inf")
        for p in candidates:
            px = self._x(p.time, left, right)
            py = self._y(p.speed, top, bottom, ymax)
            dx = (px - x) / max(1.0, right - left)
            dy = (py - y) / max(1.0, bottom - top)
            d = (dx * dx + dy * dy) ** 0.5
            if d < best_dist:
                best, best_dist = p, d
        return best if best_dist <= 0.055 else None

    def _motion(self, event) -> None:
        point = self._nearest(event.x, event.y)
        if point != self._hover:
            self._hover = point
            self.request_redraw()

    def _clear_hover(self) -> None:
        if self._hover is not None:
            self._hover = None
            self.request_redraw()

    def _click(self, event) -> None:
        point = self._nearest(event.x, event.y)
        if point is not None:
            self.selected = point
            if self.on_point_selected:
                self.on_point_selected(point)
            self.request_redraw()
            return
        left, right, _top, _bottom, _ymax = self._bounds()
        frac = max(0.0, min(1.0, (event.x - left) / max(1, right - left)))
        self.viewport.center_on(self.viewport.view_start + frac * self.viewport.span)
        self._notify_view()

    @staticmethod
    def _wheel_steps(delta: int | float) -> float:
        value = float(delta or 0.0)
        if value == 0:
            return 0.0
        if abs(value) < 10:
            return value
        return value / 120.0

    def _wheel(self, event, force_pan: bool = False) -> str:
        steps = self._wheel_steps(getattr(event, "delta", 0))
        shift = bool(getattr(event, "state", 0) & 0x0001)
        if force_pan or shift:
            self.viewport.pan(-steps * self.viewport.span * 0.08)
            self._notify_view()
            return "break"
        if steps:
            self._zoom(event.x, 0.8 ** steps)
        return "break"

    def _linux_wheel(self, event, direction: int) -> str:
        if bool(getattr(event, "state", 0) & 0x0001):
            self.viewport.pan(float(direction) * self.viewport.span * 0.08)
            self._notify_view()
            return "break"
        self._zoom(event.x, 0.8 if direction < 0 else 1.25)
        return "break"

    def _horizontal_wheel(self, direction: float) -> str:
        self.viewport.pan(float(direction) * self.viewport.span * 0.08)
        self._notify_view()
        return "break"

    def _zoom(self, x: int, factor: float) -> None:
        left, right, _top, _bottom, _ymax = self._bounds()
        frac = max(0.0, min(1.0, (x - left) / max(1, right - left)))
        anchor = self.viewport.view_start + frac * self.viewport.span
        self.viewport.zoom(factor, anchor)
        self._notify_view()

    def _pan_start(self, event) -> None:
        self._middle_x = event.x

    def _pan_drag(self, event) -> None:
        if self._middle_x is None:
            self._middle_x = event.x
            return
        left, right, _top, _bottom, _ymax = self._bounds()
        dx = event.x - self._middle_x
        self._middle_x = event.x
        self.viewport.pan(-dx / max(1, right - left) * self.viewport.span)
        self._notify_view()

    def _notify_view(self) -> None:
        if self.on_view_changed:
            self.on_view_changed()
        self.request_redraw()
