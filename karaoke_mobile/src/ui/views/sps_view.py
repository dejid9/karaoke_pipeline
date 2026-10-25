"""Precise SPS (Exact Perceptual Measurements & Burst Analyzer) View."""

from __future__ import annotations

import json
import os
from typing import Callable, Dict, List, Optional, Set

import flet as ft

from core.ass import AssDocument, format_ass_time
from core.editor import colour_burst, uncolour_burst
from core.measurements import (
    MeasurementRecord,
    apply_measurements,
    load_measurements,
    read_measurements,
    save_measurements,
)
from core.sps import BurstCandidate, MeasurementTimeline, TimelineSyllable, detect_bursts
from ui.theme import (
    COLOR_BURST_ALT,
    COLOR_BURST_BASE,
    COLOR_ERROR,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class SPSView(ft.Container):
    """View providing exact perceptual syllable timing measurements and burst detection."""

    def __init__(
        self,
        on_document_changed: Optional[Callable[[AssDocument], None]] = None,
        on_measurements_changed: Optional[Callable[[MeasurementTimeline], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 14
        self.on_document_changed = on_document_changed
        self.on_measurements_changed = on_measurements_changed

        self.document: Optional[AssDocument] = None
        self.timeline: Optional[MeasurementTimeline] = None
        self.bursts: List[BurstCandidate] = []
        self.selected_burst: Optional[BurstCandidate] = None
        self.selected_syllable_id: Optional[str] = None
        self.min_peak_sps: float = 6.0

        self._build_controls()

    def set_document(self, doc: AssDocument, timeline: Optional[MeasurementTimeline] = None):
        """Set the active ASS document and initialize/sync the measurement timeline."""
        self.document = doc
        if timeline is not None:
            self.timeline = timeline
        else:
            self.timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
        self._recalculate_bursts()
        self._refresh_ui()

    def _build_controls(self):
        # 1. Top Header & Stats
        self.summary_badge = ft.Text("Материал не загружен", size=13, color=TEXT_SECONDARY)
        self.fastest_burst_badge = ft.Text("Быстрейший бёрст: —", size=13, weight=ft.FontWeight.BOLD, color=COLOR_BURST_ALT)

        header_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Точный SPS и акустические замеры", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text("Точная подгонка границ слогов и автоматический расчет скорости (SPS)", size=12, color=TEXT_MUTED),
                    ft.Row([self.summary_badge, self.fastest_burst_badge], wrap=True, spacing=10),
                ],
                spacing=4,
            ),
            bgcolor=SURFACE_CARD,
            padding=12,
            border_radius=10,
        )

        # 2. Burst Detector Settings & Quick Action Buttons
        self.sps_slider = ft.Slider(
            min=2.0,
            max=16.0,
            divisions=14,
            value=self.min_peak_sps,
            label="{value} SPS",
            on_change=self._on_slider_change,
        )
        self.sps_slider_label = ft.Text(f"Мин. peak SPS: {self.min_peak_sps:.1f}", size=12, color=TEXT_SECONDARY)

        self.select_fastest_btn = ft.FilledButton(
            "🔥 Быстрейший бёрст",
            icon=ft.Icons.AUTO_AWESOME,
            style=ft.ButtonStyle(
                color="#11111b",
                bgcolor=COLOR_BURST_BASE,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_select_fastest,
        )

        self.colour_btn = ft.FilledButton(
            "Окрасить бёрст",
            icon=ft.Icons.COLORIZE,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_colour_selected,
        )

        self.uncolour_btn = ft.FilledButton(
            "Снять окраску",
            icon=ft.Icons.FORMAT_CLEAR,
            style=ft.ButtonStyle(
                color=TEXT_MUTED,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_uncolour_selected,
        )

        self.export_meas_btn = ft.IconButton(
            icon=ft.Icons.FILE_DOWNLOAD,
            tooltip="Экспорт замеров (.json)",
            on_click=self._on_export_measurements,
        )
        self.import_meas_btn = ft.IconButton(
            icon=ft.Icons.FILE_UPLOAD,
            tooltip="Импорт замеров (.json)",
            on_click=self._on_import_measurements,
        )

        controls_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.sps_slider_label, self.sps_slider], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, expand=True),
                    ft.Row(
                        [
                            self.select_fastest_btn,
                            self.colour_btn,
                            self.uncolour_btn,
                            self.import_meas_btn,
                            self.export_meas_btn,
                        ],
                        wrap=True,
                        spacing=6,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE_CARD,
            padding=12,
            border_radius=10,
        )

        # 3. Burst Candidate Cards List
        self.burst_list_column = ft.Column(spacing=8)

        self.burst_list_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Обнаруженные бёрсты", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    self.burst_list_column,
                ],
                spacing=8,
            ),
            bgcolor=SURFACE_CARD,
            padding=12,
            border_radius=10,
        )

        # 4. Syllable Perceptual Measurement Inspector & Editor
        self.meas_syllable_label = ft.Text("Выберите слог для точного замера", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
        self.meas_info_label = ft.Text("ASS: — | Измерение: —", size=12, color=TEXT_MUTED)

        self.meas_start_field = ft.TextField(
            label="Start (сек)",
            width=110,
            text_size=13,
            dense=True,
            border_radius=8,
            on_submit=self._on_meas_apply,
        )
        self.meas_end_field = ft.TextField(
            label="End (сек)",
            width=110,
            text_size=13,
            dense=True,
            border_radius=8,
            on_submit=self._on_meas_apply,
        )

        self.meas_apply_btn = ft.FilledButton("Применить", on_click=self._on_meas_apply)
        self.meas_reset_btn = ft.FilledButton("Сбросить", on_click=self._on_meas_reset)

        self.nudge_start_minus = ft.FilledButton("-10ms", on_click=lambda e: self._nudge("start", -0.01))
        self.nudge_start_plus = ft.FilledButton("+10ms", on_click=lambda e: self._nudge("start", 0.01))
        self.nudge_end_minus = ft.FilledButton("-10ms", on_click=lambda e: self._nudge("end", -0.01))
        self.nudge_end_plus = ft.FilledButton("+10ms", on_click=lambda e: self._nudge("end", 0.01))

        meas_editor_card = ft.Container(
            content=ft.Column(
                [
                    self.meas_syllable_label,
                    self.meas_info_label,
                    ft.Row(
                        [
                            ft.Text("Начало:", size=12, color=TEXT_SECONDARY),
                            self.nudge_start_minus,
                            self.meas_start_field,
                            self.nudge_start_plus,
                        ],
                        wrap=True,
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.Text("Конец: ", size=12, color=TEXT_SECONDARY),
                            self.nudge_end_minus,
                            self.meas_end_field,
                            self.nudge_end_plus,
                        ],
                        wrap=True,
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([self.meas_apply_btn, self.meas_reset_btn], spacing=8),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE_CARD,
            padding=12,
            border_radius=10,
        )

        # 5. Syllables in selected burst chip row
        self.syllable_chips_row = ft.Row(wrap=True, spacing=6, run_spacing=6)
        self.syllable_chips_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Слоги выбранного фрагмента (нажмите для замера)", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    self.syllable_chips_row,
                ],
                spacing=8,
            ),
            bgcolor=SURFACE_CARD,
            padding=12,
            border_radius=10,
        )

        self.content = ft.ListView(
            controls=[
                header_card,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                controls_card,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                meas_editor_card,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                self.syllable_chips_container,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                self.burst_list_container,
            ],
            spacing=8,
        )

    def _recalculate_bursts(self):
        if not self.timeline or not self.timeline.syllables:
            self.bursts = []
            return
        try:
            self.bursts = detect_bursts(self.timeline.syllables, min_peak_sps=self.min_peak_sps)
        except Exception:
            self.bursts = []

    def _refresh_ui(self):
        if not self.document or not self.timeline:
            self.summary_badge.value = "Материал не загружен"
            self.fastest_burst_badge.value = "Быстрейший бёрст: —"
            self.burst_list_column.controls.clear()
            self.burst_list_column.controls.append(ft.Text("Субтитры не открыты", size=13, color=TEXT_MUTED))
            self.syllable_chips_row.controls.clear()
            self.update()
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
                ft.Text(f"Нет бёрстов со скоростью ≥ {self.min_peak_sps:.1f} SPS. Попробуйте уменьшить порог слайдером.", size=12, color=TEXT_MUTED)
            )
        else:
            for b in self.bursts:
                self.burst_list_column.controls.append(self._build_burst_card(b))

        # Rebuild selected syllables chips
        self._refresh_syllable_chips()
        self._refresh_measurement_editor()
        self.update()

    def _build_burst_card(self, b: BurstCandidate) -> ft.Container:
        is_selected = self.selected_burst is not None and self.selected_burst.syllable_ids == b.syllable_ids
        bg = SURFACE_ELEVATED if is_selected else "#1a1a26"
        border_col = COLOR_PRIMARY if is_selected else ft.Colors.TRANSPARENT

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
                            ft.Text(f"🔥 {b.peak_sps:.1f} Peak SPS", size=13, weight=ft.FontWeight.BOLD, color=COLOR_BURST_BASE),
                            ft.Text(f"{b.mean_sps:.1f} Mean SPS", size=12, color=TEXT_SECONDARY),
                            ft.Text(f"{format_ass_time(b.start)} ➔ {format_ass_time(b.end)}", size=11, color=TEXT_MUTED),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(b.text or "(бёрст)", size=13, color=TEXT_PRIMARY, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=4,
            ),
            bgcolor=bg,
            padding=10,
            border_radius=8,
            border=ft.Border.all(1, border_col),
            on_click=_on_select,
        )

    def _refresh_syllable_chips(self):
        self.syllable_chips_row.controls.clear()
        if not self.timeline:
            return

        # Show syllables of the selected burst, or all syllables if no burst
        syl_lookup = {s.id: s for s in self.timeline.syllables}
        display_ids = self.selected_burst.syllable_ids if self.selected_burst else [s.id for s in self.timeline.syllables[:20]]

        for sid in display_ids:
            s = syl_lookup.get(sid)
            if not s:
                continue
            is_active = self.selected_syllable_id == sid
            is_meas = s.measurement_changed

            chip_color = COLOR_PRIMARY if is_active else (COLOR_SUCCESS if is_meas else SURFACE_ELEVATED)
            text_color = "#11111b" if is_active else TEXT_PRIMARY

            def _on_chip_tap(e, target_id=sid):
                self.selected_syllable_id = target_id
                self._refresh_measurement_editor()
                self._refresh_syllable_chips()
                self.update()

            txt = s.text.strip() or "..."
            dur_ms = int(round(s.effective_duration * 1000))
            badge_meas = " ✓" if is_meas else ""

            self.syllable_chips_row.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"{txt}{badge_meas}", size=12, weight=ft.FontWeight.BOLD, color=text_color),
                            ft.Text(f"{dur_ms}ms", size=10, color=text_color if is_active else TEXT_MUTED),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    bgcolor=chip_color,
                    padding=ft.Padding(8, 5, 8, 5),
                    border_radius=6,
                    on_click=_on_chip_tap,
                )
            )

    def _refresh_measurement_editor(self):
        if not self.timeline or not self.selected_syllable_id:
            self.meas_syllable_label.value = "Слог не выбран"
            self.meas_info_label.value = "ASS: — | Измерение: —"
            self.meas_start_field.value = ""
            self.meas_end_field.value = ""
            return

        lookup = {s.id: s for s in self.timeline.syllables}
        syl = lookup.get(self.selected_syllable_id)
        if not syl:
            return

        self.meas_syllable_label.value = f"Слог «{syl.text}» ({syl.id})"
        status = " (Точный замер применён ✓)" if syl.measurement_changed else " (По умолчанию из ASS)"
        self.meas_info_label.value = f"ASS: {syl.start:.3f}–{syl.end:.3f}с | Эффективно: {syl.effective_start:.3f}–{syl.effective_end:.3f}с{status}"
        self.meas_start_field.value = f"{syl.effective_start:.3f}"
        self.meas_end_field.value = f"{syl.effective_end:.3f}"

    def _on_meas_apply(self, e):
        if not self.timeline or not self.selected_syllable_id:
            return
        try:
            st = float(self.meas_start_field.value)
            en = float(self.meas_end_field.value)
            self.timeline.set_measurement(self.selected_syllable_id, st, en)
            self._recalculate_bursts()
            self._refresh_ui()
            if self.on_measurements_changed:
                self.on_measurements_changed(self.timeline)
        except Exception:
            pass

    def _on_meas_reset(self, e):
        if not self.timeline or not self.selected_syllable_id:
            return
        self.timeline.clear_measurement(self.selected_syllable_id)
        self._recalculate_bursts()
        self._refresh_ui()
        if self.on_measurements_changed:
            self.on_measurements_changed(self.timeline)

    def _nudge(self, field_type: str, delta: float):
        if not self.timeline or not self.selected_syllable_id:
            return
        try:
            lookup = {s.id: s for s in self.timeline.syllables}
            s = lookup.get(self.selected_syllable_id)
            if not s:
                return
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
            return
        fastest = max(self.bursts, key=lambda b: b.peak_sps)
        self.selected_burst = fastest
        if fastest.syllable_ids:
            self.selected_syllable_id = fastest.syllable_ids[0]
        self._refresh_ui()

    def _on_colour_selected(self, e):
        if not self.document or not self.selected_burst:
            return
        colour_burst(self.document, list(self.selected_burst.syllable_ids))
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()

    def _on_uncolour_selected(self, e):
        if not self.document or not self.selected_burst:
            return
        uncolour_burst(self.document, list(self.selected_burst.syllable_ids))
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()

    def _on_export_measurements(self, e):
        if not self.timeline or not self.timeline.changed():
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text("Нет измененных замеров для экспорта"))
                self.page.snack_bar.open = True
                self.page.update()
            return

        def _saved(result: ft.FilePickerResultEvent):
            if result.path:
                try:
                    save_measurements(result.path, self.timeline)
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Замеры сохранены: {os.path.basename(result.path)}"))
                        self.page.snack_bar.open = True
                        self.page.update()
                except Exception as ex:
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка сохранения: {ex}"))
                        self.page.snack_bar.open = True
                        self.page.update()

        picker = ft.FilePicker(on_result=_saved)
        if self.page:
            self.page.overlay.append(picker)
            self.page.update()
            picker.save_file(dialog_title="Экспорт замеров SPS", file_name="sps_measurements.json")

    def _on_import_measurements(self, e):
        def _picked(result: ft.FilePickerResultEvent):
            if result.files and self.timeline:
                p = result.files[0].path
                try:
                    load_measurements(p, self.timeline)
                    self._recalculate_bursts()
                    self._refresh_ui()
                    if self.on_measurements_changed:
                        self.on_measurements_changed(self.timeline)
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Замеры загружены: {result.files[0].name}"))
                        self.page.snack_bar.open = True
                        self.page.update()
                except Exception as ex:
                    if self.page:
                        self.page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка загрузки: {ex}"))
                        self.page.snack_bar.open = True
                        self.page.update()

        picker = ft.FilePicker(on_result=_picked)
        if self.page:
            self.page.overlay.append(picker)
            self.page.update()
            picker.pick_files(dialog_title="Импорт замеров SPS", allowed_extensions=["json"])
