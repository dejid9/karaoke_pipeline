"""MFA Alignment View with Google Colab integration and Native File Picking."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import flet as ft

from colab_client import ColabClientError, ColabMFAClient
from ui.theme import ThemePalette, get_current_palette


class MFAView(ft.Container):
    """View for configuring and running Montreal Forced Alignment via Google Colab."""

    def __init__(self, on_alignment_success: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.expand = True
        self.padding = 12
        self.on_alignment_success = on_alignment_success
        self.client = ColabMFAClient()

        # Selected audio & lyrics
        self.selected_audio_path: Optional[str] = None
        self.selected_audio_name: Optional[str] = None
        self.selected_audio_bytes: Optional[bytes] = None

        # Native FilePicker
        self.audio_picker = ft.FilePicker(on_result=self._on_audio_picked)

        # Build UI controls
        self._build_controls()

    def get_services(self) -> list[ft.Service]:
        return [self.audio_picker]

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

        # 1. Colab Server Connection Section
        self.status_icon = ft.Icon(ft.Icons.CLOUD_OFF, color=pal.warning, size=24)
        self.status_text = ft.Text("Не подключено к Colab", color=pal.muted, size=14, weight=ft.FontWeight.BOLD)

        self.url_input = ft.TextField(
            label="URL сервера Google Colab (Cloudflare tunnel)",
            hint_text="https://xxxx.trycloudflare.com",
            prefix_icon=ft.Icons.LINK,
            border_radius=8,
            text_size=13,
            dense=True,
            expand=True,
        )

        self.ping_btn = ft.FilledButton(
            "Проверить",
            icon=ft.Icons.REFRESH,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
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
                        color=pal.muted,
                    ),
                    ft.Row([self.url_input, self.ping_btn]),
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        # 2. File Selection & Transcript Section
        self.audio_info_text = ft.Text("Аудиофайл не выбран", size=13, color=pal.muted)

        self.audio_picker_btn = ft.FilledButton(
            "Выбрать аудио (.wav / .mp3)",
            icon=ft.Icons.AUDIO_FILE,
            style=ft.ButtonStyle(
                bgcolor=pal.raised,
                color=pal.fg,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            action=ft.PickFiles(self.audio_picker, with_data=True),
        )

        self.transcript_input = ft.TextField(
            label="Текст песни / реплик (построчно)",
            hint_text="Вставьте текст песни здесь...",
            multiline=True,
            min_lines=4,
            max_lines=8,
            border_radius=8,
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
            border_radius=8,
            text_size=13,
        )

        input_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Исходные данные", size=15, weight=ft.FontWeight.BOLD, color=pal.fg),
                    ft.Row([self.audio_picker_btn, self.audio_info_text], wrap=True),
                    self.transcript_input,
                    self.lang_dropdown,
                ],
                spacing=10,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        # 3. Action Section
        self.progress_bar = ft.ProgressBar(visible=False, color=pal.accent)
        self.log_text = ft.Text("", size=12, color=pal.muted)

        self.align_btn = ft.FilledButton(
            "🚀 Выровнять через Colab MFA",
            icon=ft.Icons.AUTO_AWESOME,
            style=ft.ButtonStyle(
                color=pal.accent_fg,
                bgcolor=pal.accent,
                padding=ft.Padding(20, 12, 20, 12),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            width=380,
            on_click=self._on_align_click,
        )

        self.content = ft.ListView(
            controls=[
                ft.Text("MFA Выравнивание", size=20, weight=ft.FontWeight.BOLD, color=pal.fg),
                ft.Text("Удалённый фонемный расчет через облачный Google Colab", size=12, color=pal.muted),
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                server_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                input_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                self.progress_bar,
                self.log_text,
                self.align_btn,
            ],
            spacing=8,
        )

    def _on_ping_click(self, e):
        url = self.url_input.value.strip()
        pal = get_current_palette()
        if not url:
            self._show_snack("Введите URL сервера Colab", is_error=True)
            return

        self.status_text.value = "Проверка соединения..."
        self.status_icon.name = ft.Icons.HOURGLASS_EMPTY
        self.status_icon.color = pal.warning
        self._safe_update()

        def _do_ping():
            self.client.set_server_url(url)
            ok = self.client.ping()
            self.status_icon.name = ft.Icons.CLOUD_DONE if ok else ft.Icons.CLOUD_OFF
            self.status_icon.color = pal.success if ok else pal.danger
            self.status_text.value = "Colab сервер подключен!" if ok else "Ошибка связи с сервером"
            self.status_text.color = pal.success if ok else pal.danger
            self._safe_update()

        threading.Thread(target=_do_ping, daemon=True).start()

    def _on_audio_picked(self, result: ft.FilePickerResultEvent):
        pal = get_current_palette()
        if result.files:
            f = result.files[0]
            self.selected_audio_name = f.name
            self.selected_audio_path = f.path
            self.selected_audio_bytes = f.bytes
            self.audio_info_text.value = f"Выбран файл: {f.name}"
            self.audio_info_text.color = pal.success
            self._safe_update()
            self._show_snack(f"Аудио выбрано: {f.name}")

    def _on_align_click(self, e):
        pal = get_current_palette()
        url = self.url_input.value.strip()
        if not url:
            self._show_snack("Укажите URL сервера Google Colab", is_error=True)
            return

        if not self.selected_audio_path and not self.selected_audio_bytes:
            self._show_snack("Выберите аудиофайл", is_error=True)
            return

        transcript = self.transcript_input.value.strip()
        if not transcript:
            self._show_snack("Введите текст песни", is_error=True)
            return

        lang = self.lang_dropdown.value

        # Start alignment process in background thread
        self.progress_bar.visible = True
        self.log_text.value = "Загрузка аудио и запуск выравнивания в Colab..."
        self.log_text.color = pal.accent
        self.align_btn.disabled = True
        self._safe_update()

        def _worker():
            try:
                self.client.set_server_url(url)
                ass_result = self.client.align(
                    audio_source=self.selected_audio_path or self.selected_audio_bytes,
                    filename=self.selected_audio_name or "audio.wav",
                    lyrics=transcript,
                    language=lang,
                )
                self.progress_bar.visible = False
                self.log_text.value = "Выравнивание успешно завершено!"
                self.log_text.color = pal.success
                self.align_btn.disabled = False
                self._safe_update()

                if self.on_alignment_success:
                    self.on_alignment_success(ass_result)

            except Exception as ex:
                self.progress_bar.visible = False
                self.log_text.value = f"Ошибка выравнивания: {ex}"
                self.log_text.color = pal.danger
                self.align_btn.disabled = False
                self._safe_update()

        threading.Thread(target=_worker, daemon=True).start()
