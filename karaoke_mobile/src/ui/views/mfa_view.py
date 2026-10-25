"""MFA Alignment View with Google Colab integration."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import flet as ft

from colab_client import ColabClientError, ColabMFAClient
from ui.theme import (
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


class MFAView(ft.Container):
    """View for configuring and running Montreal Forced Alignment via Google Colab."""

    def __init__(self, on_alignment_success: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.expand = True
        self.padding = 16
        self.on_alignment_success = on_alignment_success
        self.client = ColabMFAClient()

        # Selected audio & lyrics
        self.selected_audio_path: Optional[str] = None
        self.selected_audio_name: Optional[str] = None
        self.selected_audio_bytes: Optional[bytes] = None

        # Pre-instantiated Services
        self.audio_picker = ft.FilePicker(on_result=self._on_audio_picked)

        # Build UI controls
        self._build_controls()

    def get_services(self) -> list[ft.Service]:
        return [self.audio_picker]

    def apply_theme(self, pal: ThemePalette):
        """Update colors dynamically when theme changes."""
        self._build_controls()
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_controls(self):
        # 1. Colab Server Connection Section
        self.status_icon = ft.Icon(ft.Icons.CLOUD_OFF, color=COLOR_WARNING, size=24)
        self.status_text = ft.Text("Не подключено к Colab", color=TEXT_SECONDARY, size=14, weight=ft.FontWeight.BOLD)

        self.url_input = ft.TextField(
            label="URL сервера Google Colab (Cloudflare tunnel)",
            hint_text="https://xxxx.trycloudflare.com",
            prefix_icon=ft.Icons.LINK,
            border_radius=10,
            text_size=13,
            dense=True,
            expand=True,
        )

        self.ping_btn = ft.FilledButton(
            "Проверить",
            icon=ft.Icons.REFRESH,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_ping_click,
        )

        server_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.status_icon, self.status_text], alignment=ft.MainAxisAlignment.START),
                    ft.Text(
                        "Запустите блокнот colab_mfa_server.ipynb в Google Colab и вставьте сюда полученную ссылку:",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                    ft.Row([self.url_input, self.ping_btn]),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 2. File Selection & Transcript Section
        self.audio_info_text = ft.Text("Аудиофайл не выбран", size=13, color=TEXT_MUTED)

        self.audio_picker_btn = ft.FilledButton(
            "Выбрать аудио (.wav / .mp3)",
            icon=ft.Icons.AUDIO_FILE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=self._on_pick_audio,
        )

        self.transcript_input = ft.TextField(
            label="Текст песни / реплик (построчно)",
            hint_text="Вставьте текст песни здесь...",
            multiline=True,
            min_lines=4,
            max_lines=8,
            border_radius=10,
            text_size=13,
        )

        self.lang_dropdown = ft.Dropdown(
            label="Язык выравнивания (MFA)",
            options=[
                ft.dropdown.Option("russian", "Русский (russian_mfa)"),
                ft.dropdown.Option("english", "Английский (english_mfa)"),
                ft.dropdown.Option("japanese", "Японский (japanese_mfa)"),
            ],
            value="russian",
            border_radius=10,
            text_size=13,
        )

        input_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Исходные данные", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Row([self.audio_picker_btn, self.audio_info_text], wrap=True),
                    self.transcript_input,
                    self.lang_dropdown,
                ],
                spacing=12,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 3. Action Section
        self.progress_bar = ft.ProgressBar(visible=False, color=COLOR_PRIMARY)
        self.log_text = ft.Text("", size=12, color=TEXT_SECONDARY)

        self.align_btn = ft.FilledButton(
            "🚀 Выровнять через Colab MFA",
            icon=ft.Icons.AUTO_AWESOME,
            style=ft.ButtonStyle(
                color="#11111b",
                bgcolor=COLOR_PRIMARY,
                padding=ft.Padding(24, 14, 24, 14),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            width=380,
            on_click=self._on_align_click,
        )

        self.content = ft.ListView(
            controls=[
                ft.Text("MFA Выравнивание", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ft.Text("Удалённый фонемный расчет через облачный Google Colab", size=13, color=TEXT_MUTED),
                ft.Divider(height=16, color=ft.Colors.TRANSPARENT),
                server_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                input_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                self.progress_bar,
                self.log_text,
                self.align_btn,
            ],
            spacing=10,
        )

    def _on_ping_click(self, e):
        url = self.url_input.value.strip()
        if not url:
            self._set_status(False, "Введите URL сервера Colab")
            return

        self.client.set_url(url)
        self.status_text.value = "Проверка связи..."
        self.status_icon.color = COLOR_WARNING
        self.update()

        def _worker():
            try:
                res = self.client.ping()
                mfa_v = res.get("mfa_version", "MFA Online")
                self._set_status(True, f"Подключено! ({mfa_v})")
            except ColabClientError as ex:
                self._set_status(False, str(ex))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_status(self, ok: bool, msg: str):
        self.status_icon.name = ft.Icons.CLOUD_DONE if ok else ft.Icons.CLOUD_OFF
        self.status_icon.color = COLOR_SUCCESS if ok else COLOR_ERROR
        self.status_text.value = msg
        self.status_text.color = COLOR_SUCCESS if ok else COLOR_ERROR
        self.update()

    def _on_pick_audio(self, e):
        self.audio_picker.pick_files(
            dialog_title="Выберите аудиофайл",
            allowed_extensions=["wav", "mp3", "m4a", "flac", "ogg"],
            with_data=True,
        )

    def _on_audio_picked(self, result: ft.FilePickerResultEvent):
        if result.files:
            f = result.files[0]
            self.selected_audio_path = f.path
            self.selected_audio_name = f.name
            self.selected_audio_bytes = f.bytes
            self.audio_info_text.value = f"Файл: {f.name}"
            self.audio_info_text.color = COLOR_SUCCESS
            self.update()

    def _on_align_click(self, e):
        url = self.url_input.value.strip()
        if not url:
            self.log_text.value = "Ошибка: укажите URL сервера Google Colab"
            self.log_text.color = COLOR_ERROR
            self.update()
            return

        if not self.selected_audio_path and not self.selected_audio_bytes:
            self.log_text.value = "Ошибка: выберите аудиофайл"
            self.log_text.color = COLOR_ERROR
            self.update()
            return

        transcript = self.transcript_input.value.strip()
        if not transcript:
            self.log_text.value = "Ошибка: введите текст песни для выравнивания"
            self.log_text.color = COLOR_ERROR
            self.update()
            return

        self.client.set_url(url)
        self.progress_bar.visible = True
        self.align_btn.disabled = True
        self.log_text.value = "Отправка аудио и текста на Google Colab..."
        self.log_text.color = COLOR_PRIMARY
        self.update()

        def _worker():
            try:
                lang = self.lang_dropdown.value or "russian"
                res = self.client.align(
                    audio_path_or_bytes=self.selected_audio_bytes or self.selected_audio_path,
                    filename=self.selected_audio_name or "audio.wav",
                    transcript=transcript,
                    language=lang,
                )
                ass_content = res.get("ass_content")
                words_cnt = len(res.get("words", []))
                dur = res.get("duration_seconds", 0.0)

                self.progress_bar.visible = False
                self.align_btn.disabled = False
                self.log_text.value = f"Успех! Выровнено {words_cnt} слов ({dur:.1f} сек). Переход в редактор..."
                self.log_text.color = COLOR_SUCCESS
                self.update()

                if ass_content and self.on_alignment_success:
                    self.on_alignment_success(ass_content)

            except Exception as ex:
                self.progress_bar.visible = False
                self.align_btn.disabled = False
                self.log_text.value = f"Ошибка выравнивания: {ex}"
                self.log_text.color = COLOR_ERROR
                self.update()

        threading.Thread(target=_worker, daemon=True).start()
