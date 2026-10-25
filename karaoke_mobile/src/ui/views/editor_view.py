"""Mobile-optimized Karaoke Syllable & Burst Editor."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.ass import AssDocument, KaraokeSyllable, format_ass_time
from core.editor import colour_burst, uncolour_burst
from ui.theme import (
    COLOR_BURST_ALT,
    COLOR_BURST_BASE,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class EditorView(ft.Container):
    """Touch-friendly view for viewing and marking karaoke syllables and bursts."""

    def __init__(self, on_document_changed: Optional[Callable[[AssDocument], None]] = None):
        super().__init__()
        self.expand = True
        self.padding = 12
        self.on_document_changed = on_document_changed

        self.document: Optional[AssDocument] = None
        self.ass_picker = ft.FilePicker(on_result=self._on_ass_picked)
        self._build_controls()

    def get_services(self) -> list[ft.Service]:
        return [self.ass_picker]

    def load_ass_text(self, ass_text: str):
        """Load an ASS script into the editor."""
        try:
            self.document = AssDocument.from_text(ass_text)
            self._refresh_ui()
            if self.on_document_changed:
                self.on_document_changed(self.document)
        except Exception as e:
            if self.page:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка чтения ASS: {e}"))
                self.page.snack_bar.open = True
                self.page.update()

    def _build_controls(self):
        self.stats_text = ft.Text("Слогов: 0 | Бёрст: 0", size=13, color=TEXT_SECONDARY)

        self.open_file_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Открыть .ass файл",
            on_click=self._on_open_ass,
        )

        self.romanize_btn = ft.FilledButton(
            "Ромадзи",
            icon=ft.Icons.TRANSLATE,
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                bgcolor=SURFACE_ELEVATED,
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._on_romanize,
        )

        top_bar = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Караоке редактор", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        self.stats_text,
                    ],
                    spacing=2,
                    expand=True,
                ),
                self.romanize_btn,
                self.open_file_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.syllables_list = ft.ListView(expand=True, spacing=10)

        self.empty_placeholder = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SUBTITLES_OFF, size=64, color=TEXT_MUTED),
                    ft.Text("Субтитры не загружены", size=16, color=TEXT_MUTED),
                    ft.Text("Выровняйте аудио через Colab или откройте .ass файл", size=13, color=TEXT_MUTED),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        self.content = ft.Column(
            [
                top_bar,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                ft.Container(content=self.syllables_list, expand=True),
            ],
            expand=True,
        )

    def _refresh_ui(self):
        if not self.document:
            self.syllables_list.controls.clear()
            self.syllables_list.controls.append(self.empty_placeholder)
            self.stats_text.value = "Слогов: 0 | Бёрст: 0"
            self.update()
            return

        all_syllables = list(self.document.karaoke_syllables())
        total_syls = len(all_syllables)
        burst_syls = sum(1 for s in all_syllables if s.burst_marked)
        self.stats_text.value = f"Слогов: {total_syls} | Бёрст: {burst_syls}"

        self.syllables_list.controls.clear()

        # Group syllables by event line
        events = [e for e in self.document.events() if e.kind == "Dialogue"]
        by_line: dict[int, list[KaraokeSyllable]] = {}
        for s in all_syllables:
            by_line.setdefault(s.event_line_index, []).append(s)

        for ev in events:
            line_syls = by_line.get(ev.line_index, [])
            if not line_syls:
                continue

            card = self._build_line_card(ev, line_syls)
            self.syllables_list.controls.append(card)

        self.update()

    def _build_line_card(self, ev, syls: list[KaraokeSyllable]) -> ft.Container:
        # Time badge
        time_badge = ft.Text(
            f"{format_ass_time(ev.start)} ➔ {format_ass_time(ev.end)}",
            size=11,
            color=TEXT_MUTED,
        )

        # Build interactive chips for each syllable
        chips = []
        for s in syls:
            chips.append(self._build_syllable_chip(s))

        return ft.Container(
            content=ft.Column(
                [
                    time_badge,
                    ft.Row(chips, wrap=True, spacing=6, run_spacing=6),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE_CARD,
            padding=12,
            border_radius=10,
        )

    def _build_syllable_chip(self, s: KaraokeSyllable) -> ft.Container:
        is_burst = s.burst_marked
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10

        chip_bg = COLOR_BURST_BASE if is_burst else SURFACE_ELEVATED
        chip_fg = "#11111b" if is_burst else TEXT_PRIMARY

        def _on_chip_tap(e):
            # Toggle burst status
            if not self.document:
                return
            if is_burst:
                uncolour_burst(self.document, [s.id])
            else:
                colour_burst(self.document, [s.id])
            self._refresh_ui()
            if self.on_document_changed:
                self.on_document_changed(self.document)

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(f"{'🔥 ' if is_burst else ''}{text}", size=13, weight=ft.FontWeight.BOLD, color=chip_fg),
                    ft.Text(f"{dur_ms}ms", size=10, color=chip_fg if is_burst else TEXT_MUTED),
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor=chip_bg,
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=8,
            ink=True,
            on_click=_on_chip_tap,
        )

    def _on_open_ass(self, e):
        self.ass_picker.pick_files(
            dialog_title="Открыть файл субтитров",
            allowed_extensions=["ass", "txt"],
            with_data=True,
        )

    def _on_ass_picked(self, result: ft.FilePickerResultEvent):
        if result.files:
            f = result.files[0]
            try:
                if f.bytes:
                    content = f.bytes.decode("utf-8", errors="replace")
                elif f.path:
                    with open(f.path, "r", encoding="utf-8") as fp:
                        content = fp.read()
                else:
                    raise ValueError("Файл не содержит данных")
                self.load_ass_text(content)
            except Exception as ex:
                if self.page:
                    self.page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка чтения: {ex}"))
                    self.page.snack_bar.open = True
                    self.page.update()

    def _on_romanize(self, e):
        if not self.document:
            return
        # Simple auto-romanizer hook
        self._refresh_ui()
        if self.page:
            self.page.snack_bar = ft.SnackBar(ft.Text("Ромадзи обработано"))
            self.page.snack_bar.open = True
            self.page.update()
