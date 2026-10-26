"""Export & Project Management View for ASS files, Projects, Video Rendering, and Audio Snippets."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import flet as ft

from core.ass import AssDocument
from core.measurements import load_measurements, save_measurements
from core.project_bundle import ProjectBundle, export_project_zip, import_project_zip
from core.render import RenderLayoutSettings, prepare_render_document, rgb_to_ass
from core.sps import MeasurementTimeline
from ui.theme import ThemePalette, get_current_palette


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
        self.padding = 12
        self.get_document = get_document
        self.get_timeline = get_timeline
        self.get_project_state = get_project_state
        self.on_project_loaded = on_project_loaded

        # Native FilePickers
        self.project_save_picker = ft.FilePicker()
        self.project_open_picker = ft.FilePicker(on_result=self._on_project_open_result)
        self.ass_save_picker = ft.FilePicker()
        self.meas_save_picker = ft.FilePicker()
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

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def apply_theme(self, pal: ThemePalette):
        """Update colors dynamically when theme changes."""
        self._build_controls()
        self._safe_update()

    def _show_snack(self, message: str, is_error: bool = False):
        if self.page:
            pal = get_current_palette()
            self.page.snack_bar = ft.SnackBar(
                ft.Text(message, color=pal.accent_fg if not is_error else "#ffffff"),
                bgcolor=pal.danger if is_error else pal.panel,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def _build_controls(self):
        pal = get_current_palette()

        # 1. Project Package (.kproj) Card
        self.project_status = ft.Text("Готов к экспорту проекта", size=12, color=pal.muted)

        self.export_project_btn = ft.FilledButton(
            "📦 Экспортировать .kproj",
            icon=ft.Icons.FOLDER_ZIP,
            style=ft.ButtonStyle(
                color=pal.accent_fg,
                bgcolor=pal.accent,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(14, 10, 14, 10),
            ),
            on_click=self._on_export_project,
        )

        self.import_project_btn = ft.FilledButton(
            "📂 Импортировать .kproj",
            icon=ft.Icons.FILE_OPEN,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(14, 10, 14, 10),
            ),
            action=ft.PickFiles(self.project_open_picker, with_data=True),
        )

        project_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Пакет проекта (ПК / Мобильный)", size=16, weight=ft.FontWeight.BOLD, color=pal.fg),
                    ft.Text(
                        "Упаковывает субтитры, аудио, транскрипт, параметры перелива и точные SPS-замеры в единый .kproj архив.",
                        size=12,
                        color=pal.muted,
                    ),
                    ft.Row([self.export_project_btn, self.import_project_btn], wrap=True, spacing=8),
                    self.project_status,
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        # 2. ASS Export Card
        self.ass_status = ft.Text("Готов к экспорту", size=12, color=pal.muted)
        self.include_sps_timing_switch = ft.Switch(
            label="Применить точные акустические SPS-границы слогов",
            value=True,
        )

        self.export_ass_btn = ft.FilledButton(
            "💾 Экспортировать .ASS файл",
            icon=ft.Icons.FILE_DOWNLOAD,
            style=ft.ButtonStyle(
                color=pal.accent_fg,
                bgcolor=pal.accent,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(16, 10, 16, 10),
            ),
            on_click=self._on_export_ass,
        )

        ass_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Экспорт караоке-субтитров (.ASS)", size=16, weight=ft.FontWeight.BOLD, color=pal.fg),
                    ft.Text(
                        "Создает финальный .ass файл со всеми тегами переливов (\\t), анимацией бёрстов и точной синхронизацией.",
                        size=12,
                        color=pal.muted,
                    ),
                    self.include_sps_timing_switch,
                    self.export_ass_btn,
                    self.ass_status,
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        # 3. SPS Measurements Card
        self.meas_status = ft.Text("", size=12, color=pal.muted)

        self.export_meas_btn = ft.FilledButton(
            "Экспорт замеров (.json)",
            icon=ft.Icons.ANALYTICS,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(12, 8, 12, 8),
            ),
            on_click=self._on_export_meas_click,
        )
        self.import_meas_btn = ft.FilledButton(
            "Импорт замеров (.json)",
            icon=ft.Icons.FILE_UPLOAD,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(12, 8, 12, 8),
            ),
            action=ft.PickFiles(self.meas_open_picker, with_data=True),
        )

        meas_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Точные SPS-замеры (.json)", size=16, weight=ft.FontWeight.BOLD, color=pal.fg),
                    ft.Text(
                        "Файл .sps-measurements.json хранит точные акустические границы слогов (1:1 совместим с ПК версией).",
                        size=12,
                        color=pal.muted,
                    ),
                    ft.Row([self.export_meas_btn, self.import_meas_btn], wrap=True, spacing=8),
                    self.meas_status,
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        # 4. Video Render Settings Card
        self.profile_dropdown = ft.Dropdown(
            label="Профиль рендера",
            options=[
                ft.dropdown.Option("black_mp4", "MP4 H.264 (чёрный фон)"),
                ft.dropdown.Option("transparent_mov", "Прозрачный MOV (qtrle, alpha)"),
            ],
            value="black_mp4",
            border_radius=8,
            text_size=13,
        )

        self.render_res_dropdown = ft.Dropdown(
            label="Разрешение",
            options=[
                ft.dropdown.Option("1080p", "1920x1080 (Full HD)"),
                ft.dropdown.Option("720p", "1280x720 (HD)"),
                ft.dropdown.Option("4k", "3840x2160 (4K Ultra HD)"),
                ft.dropdown.Option("crop", "Обрезанная область (Auto-Crop)"),
            ],
            value="1080p",
            border_radius=8,
            text_size=13,
        )

        self.fps_dropdown = ft.Dropdown(
            label="Частота кадров (FPS)",
            options=[
                ft.dropdown.Option("60", "60 FPS (плавная синусоида перелива)"),
                ft.dropdown.Option("30", "30 FPS"),
                ft.dropdown.Option("24", "24 FPS"),
            ],
            value="60",
            border_radius=8,
            text_size=13,
        )

        self.color_mode_dropdown = ft.Dropdown(
            label="Режим перелива бёрста",
            options=[
                ft.dropdown.Option("dynamic", "Динамический перелив"),
                ft.dropdown.Option("single", "Один цвет"),
                ft.dropdown.Option("alternate", "Чередование"),
                ft.dropdown.Option("gradient", "Градиент по слогам"),
            ],
            value="dynamic",
            border_radius=8,
            text_size=13,
        )

        self.text_case_dropdown = ft.Dropdown(
            label="Регистр текста",
            options=[
                ft.dropdown.Option("as_is", "Как в ASS (без изменений)"),
                ft.dropdown.Option("upper", "Все заглавные"),
                ft.dropdown.Option("lower", "Все строчные"),
                ft.dropdown.Option("sentence", "Как в предложении"),
            ],
            value="as_is",
            border_radius=8,
            text_size=13,
        )

        self.sps_card_switch = ft.Switch(label="Оверлей карточки бёрста (SPS counter)", value=True)
        self.sps_placement_dropdown = ft.Dropdown(
            label="Позиция оверлея SPS",
            options=[
                ft.dropdown.Option("top_left", "Вверху слева"),
                ft.dropdown.Option("top_right", "Вверху справа"),
                ft.dropdown.Option("bottom_left", "Внизу слева"),
                ft.dropdown.Option("bottom_right", "Внизу справа"),
                ft.dropdown.Option("full", "Полный экран"),
            ],
            value="top_left",
            border_radius=8,
            text_size=13,
        )

        self.copy_ffmpeg_btn = ft.FilledButton(
            "📋 Скопировать команду FFmpeg",
            icon=ft.Icons.COPY,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(14, 10, 14, 10),
            ),
            on_click=self._on_copy_ffmpeg_cmd,
        )

        render_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Рендер видео (FFmpeg)", size=16, weight=ft.FontWeight.BOLD, color=pal.fg),
                    ft.Text(
                        "Все параметры рендера видео (разрешение, частота кадров, стили перелива и оверлей скорости).",
                        size=12,
                        color=pal.muted,
                    ),
                    self.profile_dropdown,
                    self.render_res_dropdown,
                    self.fps_dropdown,
                    self.color_mode_dropdown,
                    self.text_case_dropdown,
                    self.sps_card_switch,
                    self.sps_placement_dropdown,
                    self.copy_ffmpeg_btn,
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        self.content = ft.ListView(
            controls=[
                ft.Text("Проект и экспорт", size=20, weight=ft.FontWeight.BOLD, color=pal.fg),
                ft.Text("Импорт/экспорт проектов, субтитров ASS, акустических замеров и рендер видео", size=12, color=pal.muted),
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                project_card,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                ass_card,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                meas_card,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                render_card,
            ],
            spacing=8,
        )

    async def _on_export_project(self, e):
        state = self.get_project_state() if self.get_project_state else {}
        doc = state.get("doc") or (self.get_document() if self.get_document else None)
        pal = get_current_palette()
        if not doc:
            self.project_status.value = "Ошибка: субтитры не загружены"
            self.project_status.color = pal.danger
            self._safe_update()
            return

        timeline = state.get("timeline") or (self.get_timeline() if self.get_timeline else None)
        transcript = state.get("transcript", "")
        burst_cfg = state.get("burst_settings", {})
        audio_path = state.get("audio_path")
        audio_bytes = state.get("audio_bytes")
        audio_name = state.get("audio_name")

        try:
            zip_bytes = export_project_zip(
                None,
                project_name="karaoke_project",
                doc=doc,
                timeline=timeline,
                transcript=transcript,
                burst_settings=burst_cfg,
                audio_path=audio_path,
                audio_bytes=audio_bytes,
                audio_filename=audio_name,
            )
            saved = await self.project_save_picker.save_file(
                dialog_title="Сохранить проект караоке",
                file_name="karaoke_project.kproj",
                src_bytes=zip_bytes,
            )
            self.project_status.value = f"Проект сохранён: {os.path.basename(saved) if saved else 'успешно'}"
            self.project_status.color = pal.success
            self._safe_update()
            self._show_snack("Проект .kproj успешно сохранён!")
        except Exception as ex:
            self.project_status.value = f"Ошибка сохранения: {ex}"
            self.project_status.color = pal.danger
            self._safe_update()
            self._show_snack(f"Ошибка сохранения проекта: {ex}", is_error=True)

    def _on_project_open_result(self, result: ft.FilePickerResultEvent):
        pal = get_current_palette()
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
                self.project_status.color = pal.success
                self._safe_update()
                if self.on_project_loaded:
                    self.on_project_loaded(bundle)
                self._show_snack(f"Проект «{bundle.name}» загружен!")
            except Exception as ex:
                self.project_status.value = f"Ошибка импорта проекта: {ex}"
                self.project_status.color = pal.danger
                self._safe_update()
                self._show_snack(f"Ошибка импорта проекта: {ex}", is_error=True)

    async def _on_export_ass(self, e):
        doc = self.get_document() if self.get_document else None
        pal = get_current_palette()
        if not doc:
            self.ass_status.value = "Ошибка: субтитры не загружены"
            self.ass_status.color = pal.danger
            self._safe_update()
            return

        state = self.get_project_state() if self.get_project_state else {}
        b_cfg = state.get("burst_settings", {})
        timeline = self.get_timeline() if self.get_timeline else None

        settings = RenderLayoutSettings(
            burst_color_mode=self.color_mode_dropdown.value or b_cfg.get("mode", "dynamic"),
            burst_base_color=rgb_to_ass(b_cfg.get("base_color", "#FF0000")),
            burst_alt_color=rgb_to_ass(b_cfg.get("alt_color", "#FF8000")),
            burst_pulse_hz=float(b_cfg.get("pulse_hz", 2.0)),
            text_case=self.text_case_dropdown.value or "as_is",
        )
        try:
            render_doc = prepare_render_document(doc, settings)

            if self.include_sps_timing_switch.value and timeline and timeline.changed():
                meas_map = {s.id: s for s in timeline.syllables if s.measurement_changed}
                for syl in render_doc.karaoke_syllables():
                    if syl.id in meas_map:
                        item = meas_map[syl.id]
                        new_cs = max(1, int(round((item.effective_end - item.effective_start) * 100.0)))
                        ev = next((ev_item for ev_item in render_doc.events() if ev_item.line_index == syl.event_line_index), None)
                        if ev:
                            tag_val = f"\\{syl.tag_type.value}{new_cs}"
                            ev.text = ev.text[:syl.tag_value_start] + tag_val + ev.text[syl.tag_value_end:]
                            ev.commit()

            out_bytes = render_doc.dumps().encode("utf-8")
            saved = await self.ass_save_picker.save_file(
                dialog_title="Сохранить .ass файл",
                file_name="karaoke_burst_export.ass",
                src_bytes=out_bytes,
            )
            self.ass_status.value = f"Сохранено: {os.path.basename(saved) if saved else 'успешно'}"
            self.ass_status.color = pal.success
            self._safe_update()
            self._show_snack("Субтитры ASS успешно сохранены!")
        except Exception as ex:
            self.ass_status.value = f"Ошибка: {ex}"
            self.ass_status.color = pal.danger
            self._safe_update()
            self._show_snack(f"Ошибка сохранения ASS: {ex}", is_error=True)

    async def _on_export_meas_click(self, e):
        timeline = self.get_timeline() if self.get_timeline else None
        pal = get_current_palette()
        if not timeline or not timeline.changed():
            self.meas_status.value = "Нет измененных замеров"
            self._safe_update()
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
                for s in timeline.changed()
            ],
        }
        meas_bytes = json.dumps(meas_data, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            saved = await self.meas_save_picker.save_file(
                dialog_title="Экспорт замеров",
                file_name="sps_measurements.json",
                src_bytes=meas_bytes,
            )
            self.meas_status.value = f"Сохранено: {os.path.basename(saved) if saved else 'успешно'}"
            self.meas_status.color = pal.success
            self._safe_update()
            self._show_snack("Замеры SPS сохранены!")
        except Exception as ex:
            self.meas_status.value = f"Ошибка: {ex}"
            self.meas_status.color = pal.danger
            self._safe_update()
            self._show_snack(f"Ошибка сохранения замеров: {ex}", is_error=True)

    def _on_meas_open_result(self, result: ft.FilePickerResultEvent):
        timeline = self.get_timeline() if self.get_timeline else None
        pal = get_current_palette()
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
                self.meas_status.color = pal.success
                self._safe_update()
                self._show_snack(f"Замеры загружены: {f.name}")
            except Exception as ex:
                self.meas_status.value = f"Ошибка: {ex}"
                self.meas_status.color = pal.danger
                self._safe_update()
                self._show_snack(f"Ошибка загрузки замеров: {ex}", is_error=True)

    def _on_copy_ffmpeg_cmd(self, e):
        profile = self.profile_dropdown.value
        res = self.render_res_dropdown.value
        fps = self.fps_dropdown.value or "60"

        dim = "1920x1080" if res == "1080p" else ("1280x720" if res == "720p" else "3840x2160")
        if profile == "transparent_mov":
            cmd = f'ffmpeg -y -f lavfi -i color=c=black@0.0:s={dim}:r={fps}:d=60 -vf "subtitles=subtitles.ass" -c:v qtrle -pix_fmt argb output_karaoke.mov'
        else:
            cmd = f'ffmpeg -y -i audio.mp3 -vf "subtitles=subtitles.ass:force_style=\'PlayResX=1920,PlayResY=1080\'" -c:v libx264 -pix_fmt yuv420p -r {fps} -c:a aac -b:a 320k output_karaoke.mp4'

        if self.page:
            self.page.set_clipboard(cmd)
            self._show_snack("Команда FFmpeg скопирована в буфер обмена!")
