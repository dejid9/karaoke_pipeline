"""Precise SPS (Exact Perceptual Measurements & Burst Analyzer) View with PC-parity Ergonomics."""

from __future__ import annotations

import base64
import json
import math
from typing import Callable, Dict, List, Optional

import flet as ft

from core.ass import AssDocument, format_ass_time
from core.editor import colour_burst, uncolour_burst
from core.measurements import (
    MeasurementRecord,
    apply_measurements,
    load_measurements,
)
from core.sps import (
    BurstCandidate,
    MeasurementTimeline,
    SPSGraphPoint,
    detect_bursts,
    fastest_legacy_window,
    sps_graph_points,
)
from ui.components.audio_timeline import AudioTimelineWidget, hex_to_rgb, rgb_to_bmp
from ui.display_settings import get_display_settings
from ui.theme import ThemePalette, get_current_palette


def _draw_line(
    buf: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    rgb: tuple[int, int, int],
    thickness: int = 1,
):
    """Draw Bresenham anti-aliased or multi-pixel line into raw 24-bit RGB bytearray."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        for ox in range(thickness):
            for oy in range(thickness):
                px = x0 + ox
                py = y0 + oy
                if 0 <= px < width and 0 <= py < height:
                    idx = (py * width + px) * 3
                    buf[idx] = rgb[0]
                    buf[idx + 1] = rgb[1]
                    buf[idx + 2] = rgb[2]
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def render_sps_graph_bmp(
    points_ass: list[SPSGraphPoint],
    points_meas: list[SPSGraphPoint],
    v_start: float,
    v_end: float,
    threshold: float,
    cursor_time: float,
    width: int,
    height: int,
    pal: ThemePalette,
) -> str:
    """Render 24-bit BMP image of the Syllables-Per-Second curve matching PC SPSGraph."""
    bg_rgb = hex_to_rgb(pal.canvas, (18, 18, 26))
    grid_rgb = hex_to_rgb(pal.border, (45, 45, 62))
    ass_rgb = (0, 229, 255)      # Cyan for ASS
    meas_rgb = (255, 179, 0)     # Amber for Measured
    thresh_rgb = (255, 75, 75)   # Red for Threshold
    cursor_rgb = (255, 235, 59)  # Yellow for Playhead

    all_speeds = [p.speed for p in points_ass + points_meas if math.isfinite(p.speed)]
    max_speed = max([threshold * 1.4, 12.0] + all_speeds)
    span = max(1e-6, v_end - v_start)

    def t_to_x(t: float) -> int:
        return int(round((t - v_start) / span * (width - 1)))

    def s_to_y(s: float) -> int:
        ratio = max(0.0, min(1.0, s / max_speed))
        return int(round((1.0 - ratio) * (height - 1)))

    buf = bytearray(width * height * 3)

    # Fill background
    for i in range(0, len(buf), 3):
        buf[i], buf[i + 1], buf[i + 2] = bg_rgb

    # Draw horizontal grid lines at 5, 10, 15 SPS
    for g_val in (5.0, 10.0, 15.0):
        if g_val < max_speed:
            y_g = s_to_y(g_val)
            if 0 <= y_g < height:
                for x in range(0, width, 3):
                    idx = (y_g * width + x) * 3
                    if idx + 2 < len(buf):
                        buf[idx], buf[idx + 1], buf[idx + 2] = grid_rgb

    # Draw threshold dashed line
    y_th = s_to_y(threshold)
    if 0 <= y_th < height:
        for x in range(0, width, 4):
            idx = (y_th * width + x) * 3
            if idx + 2 < len(buf):
                buf[idx], buf[idx + 1], buf[idx + 2] = thresh_rgb

    # Draw ASS line segments
    if points_ass:
        vis_ass = [p for p in points_ass if (v_start - 2.0 <= p.time <= v_end + 2.0)]
        for i in range(len(vis_ass) - 1):
            p0, p1 = vis_ass[i], vis_ass[i + 1]
            x0, y0 = t_to_x(p0.time), s_to_y(p0.speed)
            x1, y1 = t_to_x(p1.time), s_to_y(p1.speed)
            _draw_line(buf, width, height, x0, y0, x1, y1, ass_rgb, thickness=1)

    # Draw Measured line segments
    if points_meas:
        vis_meas = [p for p in points_meas if (v_start - 2.0 <= p.time <= v_end + 2.0)]
        for i in range(len(vis_meas) - 1):
            p0, p1 = vis_meas[i], vis_meas[i + 1]
            x0, y0 = t_to_x(p0.time), s_to_y(p0.speed)
            x1, y1 = t_to_x(p1.time), s_to_y(p1.speed)
            _draw_line(buf, width, height, x0, y0, x1, y1, meas_rgb, thickness=1)

    # Highlight burst points above threshold with dots
    for p in points_ass:
        if p.speed >= threshold and (v_start <= p.time <= v_end):
            cx, cy = t_to_x(p.time), s_to_y(p.speed)
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    px, py = cx + ox, cy + oy
                    if 0 <= px < width and 0 <= py < height:
                        idx = (py * width + px) * 3
                        buf[idx], buf[idx + 1], buf[idx + 2] = thresh_rgb

    # Draw playhead cursor
    cx = t_to_x(cursor_time)
    if 0 <= cx < width:
        for y in range(height):
            idx = (y * width + cx) * 3
            buf[idx], buf[idx + 1], buf[idx + 2] = cursor_rgb

    bmp_data = rgb_to_bmp(bytes(buf), width, height)
    return base64.b64encode(bmp_data).decode("ascii")


class SPSView(ft.Container):
    """View providing exact perceptual syllable timing measurements and burst detection matching PC workbench."""

    def __init__(
        self,
        on_document_changed: Optional[Callable[[AssDocument], None]] = None,
        on_measurements_changed: Optional[Callable[[MeasurementTimeline], None]] = None,
        on_return_to_karaoke: Optional[Callable[[str], None]] = None,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[object], Optional[object]], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 6
        self.on_document_changed = on_document_changed
        self.on_measurements_changed = on_measurements_changed
        self.on_return_to_karaoke = on_return_to_karaoke
        self.on_audio_loaded_cb = on_audio_loaded

        self.document: Optional[AssDocument] = None
        self.timeline: Optional[MeasurementTimeline] = None
        self.bursts: List[BurstCandidate] = []
        self.selected_burst: Optional[BurstCandidate] = None
        self.selected_syllable_id: Optional[str] = None
        self.min_peak_sps: float = 6.0
        self.show_sps_graph: bool = True
        self.graph_render_width: int = 360
        self._page: Optional[ft.Page] = None

        # Audio Timeline (Waveform & Spectrogram) with Syllable Selection
        self.audio_timeline = AudioTimelineWidget(
            on_audio_loaded=self._handle_audio_loaded,
            on_syllable_clicked=self.focus_syllable,
            on_time_changed=self._on_timeline_time_changed,
        )

        # Measurement Undo/Redo history
        self._meas_undo_stack: list[dict[str, tuple[float, float]]] = []
        self._meas_redo_stack: list[dict[str, tuple[float, float]]] = []

        # Native FilePickers
        self.meas_save_picker = ft.FilePicker()
        self.meas_open_picker = ft.FilePicker(on_result=self._on_meas_open_result)

        self._build_controls()

    def set_page(self, page: ft.Page):
        self._page = page
        if hasattr(self, "audio_timeline"):
            self.audio_timeline._page = page

    def _get_page(self) -> Optional[ft.Page]:
        if getattr(self, "_page", None):
            return self._page
        try:
            if self.page:
                return self.page
        except Exception:
            pass
        return getattr(self, "_Control__page", None)

    def _handle_audio_loaded(self, name: str, data: bytes, waveform, spectrogram):
        if self.on_audio_loaded_cb:
            self.on_audio_loaded_cb(name, data, waveform, spectrogram)

    def get_services(self) -> list[ft.Service]:
        return [self.meas_save_picker, self.meas_open_picker] + self.audio_timeline.get_services()

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def apply_theme(self, pal: ThemePalette):
        """Dynamic theme update."""
        self.audio_timeline.apply_theme(pal)
        self._build_controls()
        self._refresh_ui()
        self._safe_update()

    def set_document(self, doc: AssDocument, timeline: Optional[MeasurementTimeline] = None):
        """Set the active ASS document and initialize/sync the measurement timeline."""
        self.document = doc
        if timeline is not None:
            self.timeline = timeline
        else:
            self.timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
        self._meas_undo_stack.clear()
        self._meas_redo_stack.clear()
        self._recalculate_bursts()
        if self.timeline:
            self.audio_timeline.set_syllables(self.timeline.syllables, self.selected_syllable_id)
        self._refresh_ui()

    def focus_syllable(self, syllable_id: str):
        """Focus and select a specific syllable ID, selecting its burst if applicable."""
        self.selected_syllable_id = syllable_id
        if self.bursts:
            matching_burst = next((b for b in self.bursts if syllable_id in b.syllable_ids), None)
            if matching_burst:
                self.selected_burst = matching_burst
        self._refresh_ui()

    def _on_timeline_time_changed(self, cur_t: float):
        if self.show_sps_graph:
            self._render_graph()
            self._safe_update()

    def _snapshot_measurements(self) -> dict[str, tuple[float, float]]:
        if not self.timeline:
            return {}
        return {s.id: (s.effective_start, s.effective_end) for s in self.timeline.changed()}

    def _push_meas_undo(self):
        self._meas_undo_stack.append(self._snapshot_measurements())
        if len(self._meas_undo_stack) > 50:
            self._meas_undo_stack.pop(0)
        self._meas_redo_stack.clear()

    def undo_measurement(self, e=None):
        if not self._meas_undo_stack or not self.timeline:
            self._show_snack("Нечего отменять (история замеров пуста)")
            return
        self._meas_redo_stack.append(self._snapshot_measurements())
        target = self._meas_undo_stack.pop()
        self._apply_measurement_snapshot(target)
        self._show_snack("Замер отменен (Undo ↶)")

    def redo_measurement(self, e=None):
        if not self._meas_redo_stack or not self.timeline:
            self._show_snack("Нечего повторять (история замеров пуста)")
            return
        self._meas_undo_stack.append(self._snapshot_measurements())
        target = self._meas_redo_stack.pop()
        self._apply_measurement_snapshot(target)
        self._show_snack("Замер повторен (Redo ↷)")

    def _apply_measurement_snapshot(self, snapshot: dict[str, tuple[float, float]]):
        if not self.timeline:
            return
        for s in list(self.timeline.changed()):
            if s.id not in snapshot:
                self.timeline.clear_measurement(s.id)
        for sid, (st, en) in snapshot.items():
            self.timeline.set_measurement(sid, st, en)
        self._recalculate_bursts()
        self._refresh_ui()
        if self.on_measurements_changed:
            self.on_measurements_changed(self.timeline)

    def _show_snack(self, message: str, is_error: bool = False):
        try:
            p = self._get_page()
            if p:
                pal = get_current_palette()
                p.snack_bar = ft.SnackBar(
                    ft.Text(message, color=pal.accent_fg if not is_error else "#ffffff"),
                    bgcolor=pal.danger if is_error else pal.panel,
                )
                p.snack_bar.open = True
                p.update()
        except Exception:
            pass

    def _build_controls(self):
        pal = get_current_palette()
        ds = get_display_settings()
        pad = ds.button_padding(4, 2)

        # 1. Top Header & Stats matching PC Subheader
        self.summary_badge = ft.Text("Материал не загружен", size=ds.font_size(11), color=pal.muted)
        self.fastest_burst_badge = ft.Text("Быстрейший бёрст: —", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.warning)

        self.back_to_editor_btn = ft.FilledButton(
            "← В Караоке",
            icon=ft.Icons.ARROW_BACK,
            style=ft.ButtonStyle(
                color=pal.accent_fg,
                bgcolor=pal.accent,
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ds.button_padding(6, 3),
            ),
            on_click=lambda e: self._return_to_karaoke(),
        )

        header_row1 = ft.Row(
            [
                ft.Text("Точный SPS (Exact)", size=ds.font_size(14), weight=ft.FontWeight.BOLD, color=pal.fg),
                self.back_to_editor_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        header_row2 = ft.Row([self.summary_badge, self.fastest_burst_badge], wrap=True, spacing=4)

        header_card = ft.Container(
            content=ft.Column(
                [
                    header_row1,
                    header_row2,
                ],
                spacing=3,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(8, 5, 8, 5),
            border_radius=8,
            border=ft.Border.all(1, pal.border),
        )

        # 2. Visual SPS Graph Canvas (PC Parity)
        self.sps_graph_img = ft.Image(
            src="",
            fit="fill",
            height=70,
            border_radius=6,
            expand=True,
            visible=self.show_sps_graph,
        )

        self.sps_graph_gesture = ft.GestureDetector(
            content=self.sps_graph_img,
            on_tap_down=self._on_graph_tap,
            visible=self.show_sps_graph,
        )

        graph_legend = ft.Row(
            [
                ft.Row([ft.Container(width=10, height=3, bgcolor="#00E5FF", border_radius=2), ft.Text("ASS", size=9, color=pal.muted)], spacing=2),
                ft.Row([ft.Container(width=10, height=3, bgcolor="#FFB300", border_radius=2), ft.Text("Замер", size=9, color=pal.muted)], spacing=2),
                ft.Row([ft.Container(width=10, height=3, bgcolor="#FF4B4B", border_radius=2), ft.Text("Порог", size=9, color=pal.muted)], spacing=2),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.END,
        )

        self.graph_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row([ft.Icon(ft.Icons.SHOW_CHART, size=14, color=pal.accent), ft.Text("График SPS (Syllables/Sec)", size=10.5, weight=ft.FontWeight.BOLD, color=pal.fg)], spacing=3),
                            graph_legend,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.sps_graph_gesture,
                ],
                spacing=2,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(7, 4, 7, 4),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
        )

        # 3. Burst Detector Settings & Quick Action Buttons
        self.sps_slider = ft.Slider(
            min=2.0,
            max=16.0,
            divisions=28,
            value=self.min_peak_sps,
            label="{value} SPS",
            on_change=self._on_slider_change,
        )
        self.sps_slider_label = ft.Text(f"Мин. peak SPS: {self.min_peak_sps:.1f}", size=ds.font_size(10.5), color=pal.muted)

        self.select_fastest_btn = ft.FilledButton(
            "🔥 Быстрейший",
            icon=ft.Icons.AUTO_AWESOME,
            style=ft.ButtonStyle(
                color=pal.accent_fg,
                bgcolor=pal.danger,
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=pad,
            ),
            on_click=self._on_select_fastest,
        )

        self.colour_btn = ft.FilledButton(
            "Окрасить бёрст",
            icon=ft.Icons.COLORIZE,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=pad,
            ),
            on_click=self._on_colour_selected,
        )

        self.uncolour_btn = ft.FilledButton(
            "Снять окраску",
            icon=ft.Icons.FORMAT_CLEAR,
            style=ft.ButtonStyle(
                color=pal.muted,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=pad,
            ),
            on_click=self._on_uncolour_selected,
        )

        self.export_meas_btn = ft.IconButton(
            icon=ft.Icons.FILE_DOWNLOAD,
            tooltip="Экспорт замеров (.json)",
            icon_size=ds.icon_size(17),
            icon_color=pal.accent,
            on_click=self._on_export_measurements,
        )
        self.import_meas_btn = ft.IconButton(
            icon=ft.Icons.FILE_UPLOAD,
            tooltip="Импорт замеров (.json)",
            icon_size=ds.icon_size(17),
            icon_color=pal.accent,
            action=ft.PickFiles(self.meas_open_picker, with_data=True),
        )

        controls_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.sps_slider_label, ft.Container(content=self.sps_slider, expand=True)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row(
                        [
                            self.select_fastest_btn,
                            self.colour_btn,
                            self.uncolour_btn,
                            self.import_meas_btn,
                            self.export_meas_btn,
                        ],
                        scroll=ft.ScrollMode.AUTO,
                        spacing=3,
                    ),
                ],
                spacing=3,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(7, 4, 7, 4),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
        )

        # 4. Syllable Perceptual Measurement Inspector & Editor
        self.meas_syllable_label = ft.Text("Выберите слог для точного замера", size=ds.font_size(12), weight=ft.FontWeight.BOLD, color=pal.fg)
        self.meas_info_label = ft.Text("ASS: — | Измерение: —", size=ds.font_size(9.5), color=pal.muted)

        self.meas_start_field = ft.TextField(
            label="Start (сек)",
            text_size=ds.font_size(11.5),
            dense=True,
            border_radius=6,
            on_submit=self._on_meas_apply,
        )
        self.meas_end_field = ft.TextField(
            label="End (сек)",
            text_size=ds.font_size(11.5),
            dense=True,
            border_radius=6,
            on_submit=self._on_meas_apply,
        )

        self.meas_apply_btn = ft.FilledButton("Применить", style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg, padding=pad), on_click=self._on_meas_apply)
        self.meas_reset_btn = ft.FilledButton("Сбросить", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=self._on_meas_reset)
        self.meas_undo_btn = ft.FilledButton("↶", tooltip="Отменить замер", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=ds.button_padding(5, 3)), on_click=self.undo_measurement)
        self.meas_redo_btn = ft.FilledButton("↷", tooltip="Повторить замер", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=ds.button_padding(5, 3)), on_click=self.redo_measurement)

        self.prev_syl_btn = ft.FilledButton("◀", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=lambda e: self._nav_syllable(-1))
        self.next_syl_btn = ft.FilledButton("▶", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=lambda e: self._nav_syllable(1))
        self.play_sps_btn = ft.FilledButton("▶ Замер", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.accent, padding=pad), on_click=self._play_selected_meas)

        self.btn_start_cursor = ft.FilledButton(
            "🎯 Курсор",
            tooltip="Установить Start равным позиции курсора",
            style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.accent, padding=pad),
            on_click=self._set_start_from_cursor,
        )
        self.btn_end_cursor = ft.FilledButton(
            "🎯 Курсор",
            tooltip="Установить End равным позиции курсора",
            style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.accent, padding=pad),
            on_click=self._set_end_from_cursor,
        )

        self.sps_step_ms: int = 10

        self.btn_start_minus = ft.FilledButton("-10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: self._nudge("start", -self.sps_step_ms / 1000.0))
        self.btn_start_plus = ft.FilledButton("+10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: self._nudge("start", self.sps_step_ms / 1000.0))

        self.btn_end_minus = ft.FilledButton("-10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: self._nudge("end", -self.sps_step_ms / 1000.0))
        self.btn_end_plus = ft.FilledButton("+10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: self._nudge("end", self.sps_step_ms / 1000.0))

        # Step selector
        step_btns: dict[int, ft.FilledButton] = {}

        def _set_step(ms: int):
            self.sps_step_ms = ms
            self.btn_start_minus.text = f"-{ms}ms"
            self.btn_start_plus.text = f"+{ms}ms"
            self.btn_end_minus.text = f"-{ms}ms"
            self.btn_end_plus.text = f"+{ms}ms"
            for m_val, b in step_btns.items():
                b.style = ft.ButtonStyle(
                    bgcolor=pal.accent if m_val == ms else pal.panel,
                    color=pal.accent_fg if m_val == ms else pal.fg,
                    padding=ds.button_padding(3, 1),
                )
            p = self._get_page()
            if p:
                try:
                    p.update()
                except Exception:
                    self._safe_update()
            else:
                self._safe_update()

        for ms in [1, 5, 10, 50]:
            btn = ft.FilledButton(
                f"{ms}ms",
                style=ft.ButtonStyle(
                    bgcolor=pal.accent if ms == self.sps_step_ms else pal.panel,
                    color=pal.accent_fg if ms == self.sps_step_ms else pal.fg,
                    padding=ds.button_padding(3, 1),
                ),
                on_click=lambda e, m=ms: _set_step(m),
            )
            step_btns[ms] = btn

        step_selector_row = ft.Row(
            [
                ft.Text("Шаг:", size=10, weight=ft.FontWeight.BOLD, color=pal.muted),
                step_btns[1],
                step_btns[5],
                step_btns[10],
                step_btns[50],
            ],
            spacing=3,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        start_row = ft.Row(
            [
                ft.Text("Start:", size=11, weight=ft.FontWeight.BOLD, color=pal.fg, width=34),
                self.btn_start_minus,
                ft.Container(content=self.meas_start_field, expand=True),
                self.btn_start_plus,
                self.btn_start_cursor,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

        end_row = ft.Row(
            [
                ft.Text("End:  ", size=11, weight=ft.FontWeight.BOLD, color=pal.fg, width=34),
                self.btn_end_minus,
                ft.Container(content=self.meas_end_field, expand=True),
                self.btn_end_plus,
                self.btn_end_cursor,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

        meas_header = ft.Row(
            [
                self.meas_syllable_label,
                step_selector_row,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        )

        meas_actions_row = ft.Row(
            [
                self.prev_syl_btn,
                self.next_syl_btn,
                self.play_sps_btn,
                self.meas_apply_btn,
                self.meas_reset_btn,
                self.meas_undo_btn,
                self.meas_redo_btn,
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=2,
        )

        meas_editor_card = ft.Container(
            content=ft.Column(
                [
                    meas_header,
                    self.meas_info_label,
                    start_row,
                    end_row,
                    meas_actions_row,
                ],
                spacing=2,
                tight=True,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(7, 3, 7, 3),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
        )

        # 5. Syllables in selected burst chip row
        self.syllable_chips_title = ft.Text("Слоги выбранного бёрста", size=ds.font_size(11.5), weight=ft.FontWeight.BOLD, color=pal.fg)
        self.syllable_chips_row = ft.Row(wrap=True, spacing=4, run_spacing=4)
        self.syllable_chips_container = ft.Container(
            content=ft.Column(
                [
                    self.syllable_chips_title,
                    self.syllable_chips_row,
                ],
                spacing=4,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(8, 5, 8, 5),
            border_radius=8,
            border=ft.Border.all(1, pal.border),
        )

        # 6. Burst Candidate Cards List
        self.burst_list_column = ft.Column(spacing=4)

        self.burst_list_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Обнаруженные бёрсты", size=ds.font_size(12), weight=ft.FontWeight.BOLD, color=pal.fg),
                    self.burst_list_column,
                ],
                spacing=4,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(8, 5, 8, 5),
            border_radius=8,
            border=ft.Border.all(1, pal.border),
        )

        self.content = ft.ListView(
            controls=[
                header_card,
                self.graph_card,
                self.audio_timeline,
                controls_card,
                meas_editor_card,
                self.syllable_chips_container,
                self.burst_list_container,
            ],
            spacing=5,
        )

    def _return_to_karaoke(self):
        target_id = self.selected_syllable_id or ""
        if self.on_return_to_karaoke:
            self.on_return_to_karaoke(target_id)

    def _recalculate_bursts(self):
        if not self.timeline or not self.timeline.syllables:
            self.bursts = []
            return
        try:
            self.bursts = detect_bursts(self.timeline.syllables, min_peak_sps=self.min_peak_sps)
        except Exception:
            self.bursts = []

    def _on_graph_tap(self, e: ft.TapEvent):
        """Tap on the SPS graph seeks the audio timeline and focuses the closest syllable."""
        if not self.timeline or not self.timeline.syllables:
            return
        width = self.graph_render_width
        local_x = getattr(e, "local_x", None)
        if local_x is None and hasattr(e, "local_position") and e.local_position:
            local_x = e.local_position.x
        if local_x is None or width <= 0:
            return

        total_dur = max(self.audio_timeline.audio_duration, max((s.effective_end for s in self.timeline.syllables), default=10.0))
        click_ratio = max(0.0, min(1.0, float(local_x) / width))
        t = click_ratio * total_dur

        # Find closest syllable
        closest = min(self.timeline.syllables, key=lambda s: abs(s.effective_start - t))
        if closest:
            self.focus_syllable(closest.id)
            self.audio_timeline.center_time = round(closest.effective_start, 3)
            self.audio_timeline._refresh_timeline()

    def _render_graph(self):
        if not self.timeline or not self.timeline.syllables or not self.show_sps_graph:
            return
        pal = get_current_palette()
        p = self._get_page()
        width = self.graph_render_width
        if p and getattr(p, "width", None):
            width = max(240, min(1200, int(p.width - 24)))
            self.graph_render_width = width

        try:
            pts_ass = sps_graph_points(self.timeline.syllables, metric="legacy", measured=False)
            pts_meas = sps_graph_points(self.timeline.syllables, metric="legacy", measured=True)
            total_dur = max(self.audio_timeline.audio_duration, max((s.effective_end for s in self.timeline.syllables), default=10.0))
            b64_bmp = render_sps_graph_bmp(
                points_ass=pts_ass,
                points_meas=pts_meas,
                v_start=0.0,
                v_end=total_dur,
                threshold=self.min_peak_sps,
                cursor_time=self.audio_timeline.center_time,
                width=width,
                height=70,
                pal=pal,
            )
            self.sps_graph_img.src = f"data:image/bmp;base64,{b64_bmp}"
        except Exception as ex:
            print(f"Error rendering SPS graph: {ex}")

    def _refresh_ui(self):
        pal = get_current_palette()
        if not self.document or not self.timeline:
            self.summary_badge.value = "Материал не загружен"
            self.fastest_burst_badge.value = "Быстрейший бёрст: —"
            self.burst_list_column.controls.clear()
            self.burst_list_column.controls.append(ft.Text("Субтитры не открыты", size=12, color=pal.muted))
            self.syllable_chips_row.controls.clear()
            self._safe_update()
            return

        total_syls = len(self.timeline.syllables)
        changed_meas = len(self.timeline.changed())
        burst_count = len(self.bursts)

        self.summary_badge.value = f"Слогов: {total_syls} | Замеров: {changed_meas} | Бёрстов: {burst_count}"

        if self.bursts:
            fastest = max(self.bursts, key=lambda b: b.peak_sps)
            self.fastest_burst_badge.value = f"Быстрейший: {fastest.peak_sps:.1f} SPS ({format_ass_time(fastest.start)})"
            if self.selected_burst is None:
                self.selected_burst = fastest
        else:
            self.fastest_burst_badge.value = "Бёрстов не найдено (порог высок)"

        # Rebuild burst list cards
        self.burst_list_column.controls.clear()
        if not self.bursts:
            self.burst_list_column.controls.append(
                ft.Text(f"Нет бёрстов со скоростью ≥ {self.min_peak_sps:.1f} SPS. Уменьшите порог слайдером.", size=11, color=pal.muted)
            )
        else:
            for b in self.bursts:
                self.burst_list_column.controls.append(self._build_burst_card(b))

        # Sync syllables with audio timeline visualizer
        if self.timeline and self.timeline.syllables:
            self.audio_timeline.set_syllables(self.timeline.syllables, self.selected_syllable_id)

        # Render visual SPS Graph
        self._render_graph()

        # Rebuild selected syllables chips
        self._refresh_syllable_chips()
        self._refresh_measurement_editor()
        self._safe_update()

    def _build_burst_card(self, b: BurstCandidate) -> ft.Container:
        pal = get_current_palette()
        is_selected = self.selected_burst is not None and self.selected_burst.syllable_ids == b.syllable_ids
        bg = pal.raised if is_selected else pal.panel
        border_col = pal.accent if is_selected else pal.border

        def _on_select(e):
            self.selected_burst = b
            if b.syllable_ids:
                self.selected_syllable_id = b.syllable_ids[0]
            self._refresh_ui()

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"🔥 {b.peak_sps:.1f} Peak SPS", size=12, weight=ft.FontWeight.BOLD, color=pal.danger),
                            ft.Text(f"{b.mean_sps:.1f} Mean", size=11, color=pal.muted),
                            ft.Text(f"{format_ass_time(b.start)} ➔ {format_ass_time(b.end)}", size=10, color=pal.muted),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(b.text or "(бёрст)", size=12, color=pal.fg, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=3,
            ),
            bgcolor=bg,
            padding=ft.Padding(8, 5, 8, 5),
            border_radius=7,
            border=ft.Border.all(1.5 if is_selected else 1, border_col),
            on_click=_on_select,
        )

    def _nav_syllable(self, step: int):
        if not self.timeline or not self.timeline.syllables:
            return
        all_ids = [s.id for s in self.timeline.syllables]
        if self.selected_syllable_id in all_ids:
            cur_idx = all_ids.index(self.selected_syllable_id)
            new_idx = max(0, min(len(all_ids) - 1, cur_idx + step))
            self.selected_syllable_id = all_ids[new_idx]
        elif all_ids:
            self.selected_syllable_id = all_ids[0]
        self._refresh_ui()

    def _refresh_syllable_chips(self):
        pal = get_current_palette()
        self.syllable_chips_row.controls.clear()
        if not self.timeline:
            return

        syl_lookup = {s.id: s for s in self.timeline.syllables}

        if self.selected_burst:
            display_ids = list(self.selected_burst.syllable_ids)
            if self.selected_syllable_id and self.selected_syllable_id not in display_ids:
                display_ids.append(self.selected_syllable_id)
            self.syllable_chips_title.value = f"Слоги выбранного бёрста ({len(display_ids)} шт.)"
        elif self.selected_syllable_id:
            all_ids = [s.id for s in self.timeline.syllables]
            if self.selected_syllable_id in all_ids:
                cur_i = all_ids.index(self.selected_syllable_id)
                start_i = max(0, cur_i - 8)
                end_i = min(len(all_ids), cur_i + 12)
                display_ids = all_ids[start_i:end_i]
            else:
                display_ids = all_ids[:24]
            self.syllable_chips_title.value = "Слоги (контекст выбранного замера)"
        else:
            display_ids = [s.id for s in self.timeline.syllables[:24]]
            self.syllable_chips_title.value = "Слоги (первые 24 шт.)"

        for sid in display_ids:
            s = syl_lookup.get(sid)
            if not s:
                continue
            is_active = self.selected_syllable_id == sid
            is_meas = s.measurement_changed

            chip_color = pal.accent if is_active else (pal.success if is_meas else pal.raised)
            text_color = pal.accent_fg if is_active else (pal.accent_fg if is_meas else pal.fg)

            def _on_chip_tap(e, target_id=sid):
                self.selected_syllable_id = target_id
                self._refresh_measurement_editor()
                self._refresh_syllable_chips()
                self._safe_update()

            txt = s.text.strip() or "..."
            dur_ms = int(round((s.effective_end - s.effective_start) * 1000))
            badge_meas = " ✓" if is_meas else ""

            self.syllable_chips_row.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"{txt}{badge_meas}", size=11, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text(f"{dur_ms}ms", size=9, color=text_color if (is_active or is_meas) else pal.muted),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    bgcolor=chip_color,
                    border=ft.Border.all(1.5 if is_active else 1, pal.accent if is_active else pal.border),
                    padding=ft.Padding(6, 4, 6, 4),
                    border_radius=5,
                    on_click=_on_chip_tap,
                )
            )

    def _refresh_measurement_editor(self):
        pal = get_current_palette()
        if not self.timeline or not self.selected_syllable_id:
            self.meas_syllable_label.value = "Слог не выбран"
            self.meas_info_label.value = "ASS: — | Замер: —"
            self.meas_start_field.value = ""
            self.meas_end_field.value = ""
            self.audio_timeline.set_active_bounds(None, None, None, None)
            return

        lookup = {s.id: s for s in self.timeline.syllables}
        syl = lookup.get(self.selected_syllable_id)
        if not syl:
            self.audio_timeline.set_active_bounds(None, None, None, None)
            return

        ass_dur = int(round((syl.end - syl.start) * 1000))
        eff_dur = int(round((syl.effective_end - syl.effective_start) * 1000))
        delta_start = int(round((syl.effective_start - syl.start) * 1000))
        delta_end = int(round((syl.effective_end - syl.end) * 1000))

        self.meas_syllable_label.value = f"Слог «{syl.text}» ({syl.id})"
        status = " (Точный замер применён ✓)" if syl.measurement_changed else " (По умолчанию из ASS)"
        self.meas_info_label.value = (
            f"ASS: {syl.start:.3f}–{syl.end:.3f}с ({ass_dur}мс) | "
            f"Замер: {syl.effective_start:.3f}–{syl.effective_end:.3f}с ({eff_dur}мс | "
            f"Δstart {delta_start:+d}мс, Δend {delta_end:+d}мс){status}"
        )
        self.meas_start_field.value = f"{syl.effective_start:.3f}"
        self.meas_end_field.value = f"{syl.effective_end:.3f}"
        meas_st = syl.effective_start if syl.measurement_changed else None
        meas_en = syl.effective_end if syl.measurement_changed else None
        self.audio_timeline.focus_syllable(syl.start, syl.end, meas_st, meas_en, syl.id)

    def _set_start_from_cursor(self, e):
        if not self.timeline or not self.selected_syllable_id:
            return
        lookup = {s.id: s for s in self.timeline.syllables}
        s = lookup.get(self.selected_syllable_id)
        if not s:
            return
        cur_t = round(self.audio_timeline.center_time, 3)
        self._push_meas_undo()
        self.timeline.set_measurement(self.selected_syllable_id, cur_t, s.effective_end)
        self._recalculate_bursts()
        self._refresh_ui()
        if self.on_measurements_changed:
            self.on_measurements_changed(self.timeline)
        self._show_snack(f"Start установлен по курсору: {cur_t:.3f}с")

    def _set_end_from_cursor(self, e):
        if not self.timeline or not self.selected_syllable_id:
            return
        lookup = {s.id: s for s in self.timeline.syllables}
        s = lookup.get(self.selected_syllable_id)
        if not s:
            return
        cur_t = round(self.audio_timeline.center_time, 3)
        self._push_meas_undo()
        self.timeline.set_measurement(self.selected_syllable_id, s.effective_start, cur_t)
        self._recalculate_bursts()
        self._refresh_ui()
        if self.on_measurements_changed:
            self.on_measurements_changed(self.timeline)
        self._show_snack(f"End установлен по курсору: {cur_t:.3f}с")

    def _play_selected_meas(self, e=None):
        if not self.timeline or not self.selected_syllable_id:
            return
        syl = next((s for s in self.timeline.syllables if s.id == self.selected_syllable_id), None)
        if syl:
            st = min(syl.effective_start, syl.effective_end)
            en = max(syl.effective_start, syl.effective_end)
            self.audio_timeline.play_range(st, en)

    def _on_meas_apply(self, e):
        if not self.timeline or not self.selected_syllable_id:
            return
        try:
            st = float(self.meas_start_field.value)
            en = float(self.meas_end_field.value)
            self._push_meas_undo()
            self.timeline.set_measurement(self.selected_syllable_id, st, en)
            self._recalculate_bursts()
            self._refresh_ui()
            if self.on_measurements_changed:
                self.on_measurements_changed(self.timeline)
            self._show_snack("Границы замера сохранены")
        except Exception as ex:
            self._show_snack(f"Некорректное значение: {ex}", is_error=True)

    def _on_meas_reset(self, e):
        if not self.timeline or not self.selected_syllable_id:
            return
        self._push_meas_undo()
        self.timeline.clear_measurement(self.selected_syllable_id)
        self._recalculate_bursts()
        self._refresh_ui()
        if self.on_measurements_changed:
            self.on_measurements_changed(self.timeline)
        self._show_snack("Сброшено к оригинальному таймингу ASS")

    def _nudge(self, field_type: str, delta: float):
        if not self.timeline or not self.selected_syllable_id:
            return
        try:
            lookup = {s.id: s for s in self.timeline.syllables}
            s = lookup.get(self.selected_syllable_id)
            if not s:
                return
            self._push_meas_undo()
            st = s.effective_start + (delta if field_type == "start" else 0.0)
            en = s.effective_end + (delta if field_type == "end" else 0.0)
            self.timeline.set_measurement(self.selected_syllable_id, st, en)
            self._recalculate_bursts()
            self._refresh_ui()
            if self.on_measurements_changed:
                self.on_measurements_changed(self.timeline)
        except Exception:
            pass

    def _on_slider_change(self, e):
        self.min_peak_sps = float(self.sps_slider.value)
        self.sps_slider_label.value = f"Мин. peak SPS: {self.min_peak_sps:.1f}"
        self._recalculate_bursts()
        self._refresh_ui()

    def _on_select_fastest(self, e):
        if not self.bursts:
            self._show_snack("Бёрстов не найдено при текущем пороге")
            return
        fastest = max(self.bursts, key=lambda b: b.peak_sps)
        self.selected_burst = fastest
        if fastest.syllable_ids:
            self.selected_syllable_id = fastest.syllable_ids[0]
        self._refresh_ui()
        self._show_snack(f"Выбран быстрейший бёрст ({fastest.peak_sps:.1f} SPS)")

    def _on_colour_selected(self, e):
        if not self.document or not self.selected_burst:
            self._show_snack("Сначала выберите бёрст")
            return
        colour_burst(self.document, list(self.selected_burst.syllable_ids))
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack("Бёрст размечен переливом 🔥")

    def _on_uncolour_selected(self, e):
        if not self.document or not self.selected_burst:
            self._show_snack("Сначала выберите бёрст")
            return
        uncolour_burst(self.document, list(self.selected_burst.syllable_ids))
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack("Разметка бёрста снята")

    async def _on_export_measurements(self, e):
        if not self.timeline or not self.timeline.changed():
            self._show_snack("Нет измененных замеров для экспорта")
            return
        meas_data = {
            "version": 1,
            "measurements": [
                {
                    "syllable_id": s.id,
                    "measured_start": s.effective_start,
                    "measured_end": s.effective_end,
                }
                for s in self.timeline.changed()
            ],
        }
        meas_bytes = json.dumps(meas_data, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            await self.meas_save_picker.save_file(
                dialog_title="Экспорт замеров SPS",
                file_name="sps_measurements.json",
                src_bytes=meas_bytes,
            )
            self._show_snack("Замеры SPS сохранены!")
        except Exception as ex:
            self._show_snack(f"Ошибка сохранения: {ex}", is_error=True)

    def _on_meas_open_result(self, result: ft.FilePickerResultEvent):
        if result.files and self.timeline:
            f = result.files[0]
            try:
                if f.bytes:
                    data = json.loads(f.bytes.decode("utf-8", errors="replace"))
                    records: Dict[str, MeasurementRecord] = {}
                    for item in data.get("measurements", []):
                        rec = MeasurementRecord(
                            str(item["syllable_id"]),
                            float(item["measured_start"]),
                            float(item["measured_end"]),
                        )
                        records[rec.syllable_id] = rec
                    apply_measurements(records, self.timeline)
                elif f.path:
                    load_measurements(f.path, self.timeline)
                self._meas_undo_stack.clear()
                self._meas_redo_stack.clear()
                self._recalculate_bursts()
                self._refresh_ui()
                if self.on_measurements_changed:
                    self.on_measurements_changed(self.timeline)
                self._show_snack(f"Замеры загружены: {f.name}")
            except Exception as ex:
                self._show_snack(f"Ошибка загрузки: {ex}", is_error=True)
