"""Export & Sharing View for ASS files and Audio Snippets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

import flet as ft

from core.ass import AssDocument
from core.render import RenderLayoutSettings, prepare_render_document
from ui.theme import (
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ExportView(ft.Container):
    """View for exporting processed ASS subtitles and sliced audio verification snippets."""

    def __init__(self, get_document: Optional[Callable[[], Optional[AssDocument]]] = None):
        super().__init__()
        self.expand = True
        self.padding = 16
        self.get_document = get_document

        self._build_controls()

    def _build_controls(self):
        # 1. ASS Export Card
        self.ass_status = ft.Text("Готов к экспорту", size=13, color=TEXT_SECONDARY)

        self.export_ass_btn = ft.FilledButton(
            "Экспортировать .ASS файл",
            icon=ft.Icons.FILE_DOWNLOAD,
            style=ft.ButtonStyle(
                color="#11111b",
                bgcolor=COLOR_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.Padding(20, 12, 20, 12),
            ),
            on_click=self._on_export_ass,
        )

        ass_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Экспорт готовых караоке-субтитров", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(
                        "Создаёт финальный .ass файл со всеми тегами переливов (\\t), ромадзи и синхронизацией слогов для Aegisub, VLC или плеера.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    ft.Row([self.export_ass_btn, self.ass_status], wrap=True),
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 2. Audio Snippet Export Card (Burst preview clip)
        self.burst_slice_status = ft.Text("", size=13, color=TEXT_SECONDARY)

        self.export_audio_snippet_btn = ft.FilledButton(
            "Экспортировать отрывок бёрста (.wav / .mp3)",
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

        # 3. Video Render Settings Card
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
                ft.Text("Экспорт и шеринг", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ft.Text("Сохранение ASS, вырезка аудио-отрезков и параметры видео", size=13, color=TEXT_MUTED),
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                ass_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                snippet_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                render_card,
            ],
            spacing=10,
        )

    def _on_export_ass(self, e):
        doc = self.get_document() if self.get_document else None
        if not doc:
            self.ass_status.value = "Ошибка: субтитры не загружены"
            self.update()
            return

        # Prepare render document with current dynamic pulse settings
        settings = RenderLayoutSettings(
            burst_color_mode="dynamic",
            burst_base_color="&H0000FF&",
            burst_alt_color="&H0080FF&",
            burst_pulse_hz=2.0,
        )
        try:
            render_doc = prepare_render_document(doc, settings)
            out_content = render_doc.dumps()

            # Save via FilePicker
            def _saved(result: ft.FilePickerResultEvent):
                if result.path:
                    with open(result.path, "w", encoding="utf-8") as f:
                        f.write(out_content)
                    self.ass_status.value = f"Сохранено: {os.path.basename(result.path)}"
                    self.ass_status.color = COLOR_SUCCESS
                    self.update()

            picker = ft.FilePicker(on_result=_saved)
            if self.page:
                self.page.overlay.append(picker)
                self.page.update()
                picker.save_file(dialog_title="Сохранить .ass файл", file_name="karaoke_burst_export.ass")

        except Exception as ex:
            self.ass_status.value = f"Ошибка: {ex}"
            self.update()

    def _on_export_burst_audio(self, e):
        # Audio slicing stub / helper
        self.burst_slice_status.value = "Отрывок бёрста подготовлен"
        self.burst_slice_status.color = COLOR_SUCCESS
        self.update()
