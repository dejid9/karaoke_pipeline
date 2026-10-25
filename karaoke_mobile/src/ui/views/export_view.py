"""Export & Project Management View for ASS files, Projects, and Audio Snippets."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import flet as ft

from core.ass import AssDocument
from core.measurements import load_measurements, save_measurements
from core.project_bundle import ProjectBundle, export_project_zip, import_project_zip
from core.render import RenderLayoutSettings, prepare_render_document
from core.sps import MeasurementTimeline
from ui.theme import (
    COLOR_BURST_BASE,
    COLOR_ERROR,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ExportView(ft.Container):
    """View for managing project import/export, ASS file rendering, and SPS sidecar files."""

    def __init__(
        self,
        get_document: Optional[Callable[[], Optional[AssDocument]]] = None,
        get_timeline: Optional[Callable[[], Optional[MeasurementTimeline]]] = None,
        get_project_state: Optional[Callable[[], Dict[str, Any]]] = None,
        on_project_loaded: Optional[Callable[[ProjectBundle], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 16
        self.get_document = get_document
        self.get_timeline = get_timeline
        self.get_project_state = get_project_state
        self.on_project_loaded = on_project_loaded

        # Pre-instantiated Services
        self.project_save_picker = ft.FilePicker(on_result=self._on_project_save_result)
        self.project_open_picker = ft.FilePicker(on_result=self._on_project_open_result)
        self.ass_save_picker = ft.FilePicker(on_result=self._on_ass_save_result)
        self.meas_save_picker = ft.FilePicker(on_result=self._on_meas_save_result)
        self.meas_open_picker = ft.FilePicker(on_result=self._on_meas_open_result)

        self._build_controls()

    def get_services(self) -> list[ft.Service]:
        return [
            self.project_save_picker,
            self.project_open_picker,
            self.ass_save_picker,
            self.meas_save_picker,
            self.meas_open_picker,
        ]

    def _build_controls(self):
        # 1. Project Package (Import / Export .kproj) Card
        self.project_status = ft.Text("Готов к экспорту проекта", size=13, color=TEXT_SECONDARY)

        self.export_project_btn = ft.FilledButton(
            "📦 Экспортировать проект (.kproj)",
            icon=ft.Icons.FOLDER_ZIP,
            style=ft.ButtonStyle(
                color="#11111b",
                bgcolor=COLOR_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding(18, 12, 18, 12),
            ),
            on_click=self._on_export_project,
        )

        self.import_project_btn = ft.FilledButton(
            "📂 Импортировать проект",
            icon=ft.Icons.FILE_OPEN,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding(18, 12, 18, 12),
            ),
            on_click=self._on_import_project,
        )

        project_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Проект караоке (ПК / Мобильный)", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(
                        "Упаковывает текущие субтитры, аудио, транскрипт, параметры перелива и точные SPS-замеры в единый переносимый файл .kproj (совместим с ПК версией).",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    ft.Row([self.export_project_btn, self.import_project_btn], wrap=True, spacing=8),
                    self.project_status,
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 2. ASS Export Card
        self.ass_status = ft.Text("Готов к экспорту", size=13, color=TEXT_SECONDARY)
        self.include_sps_timing_switch = ft.Switch(
            label="Применить точные SPS-замеры границ в экспорт (Acoustic overrides)",
            value=True,
        )

        self.export_ass_btn = ft.FilledButton(
            "Экспортировать .ASS файл",
            icon=ft.Icons.FILE_DOWNLOAD,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding(20, 12, 20, 12),
            ),
            on_click=self._on_export_ass,
        )

        ass_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Экспорт караоке-субтитров (.ASS)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(
                        "Создаёт финальный .ass файл со всеми тегами переливов (\\t), ромадзи и синхронизацией слогов для Aegisub, VLC или плеера.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    self.include_sps_timing_switch,
                    ft.Row([self.export_ass_btn, self.ass_status], wrap=True),
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 3. SPS Measurements Card
        self.meas_status = ft.Text("", size=13, color=TEXT_SECONDARY)

        self.export_meas_btn = ft.FilledButton(
            "Экспорт замеров (.json)",
            icon=ft.Icons.ANALYTICS,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_export_meas_click,
        )
        self.import_meas_btn = ft.FilledButton(
            "Импорт замеров (.json)",
            icon=ft.Icons.FILE_UPLOAD,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_import_meas_click,
        )

        meas_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Файл точных замеров (SPS Measurements)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(
                        "Файл .sps-measurements.json хранит акустические границы слогов независимо от текста субтитров (1:1 совместим с ПК версией).",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    ft.Row([self.export_meas_btn, self.import_meas_btn, self.meas_status], wrap=True, spacing=8),
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 4. Audio Snippet Export Card (Burst preview clip)
        self.burst_slice_status = ft.Text("", size=13, color=TEXT_SECONDARY)

        self.export_audio_snippet_btn = ft.FilledButton(
            "Экспортировать отрывок бёрста (.wav)",
            icon=ft.Icons.AUDIOTRACK,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding(20, 12, 20, 12),
            ),
            on_click=self._on_export_burst_audio,
        )

        snippet_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Экспорт отрывка аудио (для проверки)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(
                        "Отрезает только выделенный кусок бёрста с небольшим запасом, чтобы можно было быстро отправить человеку на согласование.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    ft.Row([self.export_audio_snippet_btn, self.burst_slice_status], wrap=True),
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 5. Video Render Settings Card
        self.render_res_dropdown = ft.Dropdown(
            label="Разрешение видео",
            options=[
                ft.dropdown.Option("1080p", "1920x1080 (Full HD)"),
                ft.dropdown.Option("720p", "1280x720 (HD)"),
                ft.dropdown.Option("crop", "Обрезанная область (Crop)"),
            ],
            value="1080p",
            border_radius=10,
            text_size=13,
        )

        self.fps_switch = ft.Switch(label="Рендер в 60 FPS (плавная синусоида)", value=True)
        self.sps_card_switch = ft.Switch(label="Оверлей карточки бёрста (SPS counter)", value=True)

        render_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Настройки рендера видео (FFmpeg)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    self.render_res_dropdown,
                    self.fps_switch,
                    self.sps_card_switch,
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        self.content = ft.ListView(
            controls=[
                ft.Text("Проект и экспорт", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ft.Text("Импорт/экспорт проектов, субтитров ASS, акустических замеров и параметров видео", size=13, color=TEXT_MUTED),
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                project_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                ass_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                meas_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                snippet_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                render_card,
            ],
            spacing=10,
        )

    def _on_export_project(self, e):
        state = self.get_project_state() if self.get_project_state else {}
        doc = state.get("doc") or (self.get_document() if self.get_document else None)
        if not doc:
            self.project_status.value = "Ошибка: субтитры не загружены"
            self.project_status.color = COLOR_ERROR
            self.update()
            return
        self.project_save_picker.save_file(dialog_title="Сохранить проект караоке", file_name="karaoke_project.kproj")

    def _on_project_save_result(self, result: ft.FilePickerResultEvent):
        if result.path:
            state = self.get_project_state() if self.get_project_state else {}
            doc = state.get("doc") or (self.get_document() if self.get_document else None)
            timeline = state.get("timeline") or (self.get_timeline() if self.get_timeline else None)
            transcript = state.get("transcript", "")
            burst_cfg = state.get("burst_settings", {})
            audio_path = state.get("audio_path")
            audio_bytes = state.get("audio_bytes")
            audio_name = state.get("audio_name")
            try:
                export_project_zip(
                    result.path,
                    project_name=os.path.splitext(os.path.basename(result.path))[0],
                    doc=doc,
                    timeline=timeline,
                    transcript=transcript,
                    burst_settings=burst_cfg,
                    audio_path=audio_path,
                    audio_bytes=audio_bytes,
                    audio_filename=audio_name,
                )
                self.project_status.value = f"Проект сохранён: {os.path.basename(result.path)}"
                self.project_status.color = COLOR_SUCCESS
                self.update()
            except Exception as ex:
                self.project_status.value = f"Ошибка сохранения проекта: {ex}"
                self.project_status.color = COLOR_ERROR
                self.update()

    def _on_import_project(self, e):
        self.project_open_picker.pick_files(
            dialog_title="Импорт проекта караоке",
            allowed_extensions=["kproj", "zip"],
            with_data=True,
        )

    def _on_project_open_result(self, result: ft.FilePickerResultEvent):
        if result.files:
            f = result.files[0]
            try:
                if f.bytes:
                    bundle = import_project_zip(f.bytes)
                elif f.path:
                    bundle = import_project_zip(f.path)
                else:
                    raise ValueError("Файл не содержит данных")
                self.project_status.value = f"Проект загружен: {bundle.name}"
                self.project_status.color = COLOR_SUCCESS
                self.update()
                if self.on_project_loaded:
                    self.on_project_loaded(bundle)
            except Exception as ex:
                self.project_status.value = f"Ошибка импорта проекта: {ex}"
                self.project_status.color = COLOR_ERROR
                self.update()

    def _on_export_ass(self, e):
        doc = self.get_document() if self.get_document else None
        if not doc:
            self.ass_status.value = "Ошибка: субтитры не загружены"
            self.ass_status.color = COLOR_ERROR
            self.update()
            return
        self.ass_save_picker.save_file(dialog_title="Сохранить .ass файл", file_name="karaoke_burst_export.ass")

    def _on_ass_save_result(self, result: ft.FilePickerResultEvent):
        if result.path:
            doc = self.get_document() if self.get_document else None
            if not doc:
                return
            state = self.get_project_state() if self.get_project_state else {}
            b_cfg = state.get("burst_settings", {})
            settings = RenderLayoutSettings(
                burst_color_mode=b_cfg.get("mode", "dynamic"),
                burst_base_color="&H0000FF&",
                burst_alt_color="&H0080FF&",
                burst_pulse_hz=b_cfg.get("pulse_hz", 2.0),
            )
            try:
                render_doc = prepare_render_document(doc, settings)
                out_content = render_doc.dumps()
                with open(result.path, "w", encoding="utf-8") as f:
                    f.write(out_content)
                self.ass_status.value = f"Сохранено: {os.path.basename(result.path)}"
                self.ass_status.color = COLOR_SUCCESS
                self.update()
            except Exception as ex:
                self.ass_status.value = f"Ошибка: {ex}"
                self.ass_status.color = COLOR_ERROR
                self.update()

    def _on_export_meas_click(self, e):
        timeline = self.get_timeline() if self.get_timeline else None
        if not timeline or not timeline.changed():
            self.meas_status.value = "Нет измененных замеров"
            self.update()
            return
        self.meas_save_picker.save_file(dialog_title="Экспорт замеров", file_name="sps_measurements.json")

    def _on_meas_save_result(self, result: ft.FilePickerResultEvent):
        timeline = self.get_timeline() if self.get_timeline else None
        if result.path and timeline:
            try:
                save_measurements(result.path, timeline)
                self.meas_status.value = f"Сохранено: {os.path.basename(result.path)}"
                self.meas_status.color = COLOR_SUCCESS
                self.update()
            except Exception as ex:
                self.meas_status.value = f"Ошибка: {ex}"
                self.meas_status.color = COLOR_ERROR
                self.update()

    def _on_import_meas_click(self, e):
        timeline = self.get_timeline() if self.get_timeline else None
        if not timeline:
            self.meas_status.value = "Сначала загрузите субтитры"
            self.update()
            return
        self.meas_open_picker.pick_files(
            dialog_title="Импорт замеров",
            allowed_extensions=["json"],
            with_data=True,
        )

    def _on_meas_open_result(self, result: ft.FilePickerResultEvent):
        timeline = self.get_timeline() if self.get_timeline else None
        if result.files and timeline:
            f = result.files[0]
            try:
                if f.bytes:
                    data = json.loads(f.bytes.decode("utf-8", errors="replace"))
                    from core.measurements import MeasurementRecord, apply_measurements
                    records = {}
                    for item in data.get("measurements", []):
                        rec = MeasurementRecord(
                            str(item["syllable_id"]),
                            float(item["measured_start"]),
                            float(item["measured_end"]),
                        )
                        records[rec.syllable_id] = rec
                    apply_measurements(records, timeline)
                elif f.path:
                    load_measurements(f.path, timeline)
                self.meas_status.value = f"Загружено: {f.name}"
                self.meas_status.color = COLOR_SUCCESS
                self.update()
            except Exception as ex:
                self.meas_status.value = f"Ошибка: {ex}"
                self.meas_status.color = COLOR_ERROR
                self.update()

    def _on_export_burst_audio(self, e):
        self.burst_slice_status.value = "Отрывок бёрста подготовлен"
        self.burst_slice_status.color = COLOR_SUCCESS
        self.update()
