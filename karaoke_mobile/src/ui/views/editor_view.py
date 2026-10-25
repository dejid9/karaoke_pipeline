"""Mobile-optimized Karaoke Syllable & Burst Editor with Touch Ergonomics and Native File Picking."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from core.ass import AssDocument, KaraokeSyllable, format_ass_time
from core.editor import (
    colour_burst,
    delete_syllable,
    insert_after,
    merge_syllables,
    nudge_syllable_duration,
    set_syllable_romanization,
    set_syllable_text,
    split_syllable,
    uncolour_burst,
)
from ui.theme import ThemePalette, get_current_palette


class EditorView(ft.Container):
    """Touch-friendly view for viewing, modifying, splitting, merging, and marking karaoke syllables."""

    def __init__(
        self,
        on_document_changed: Optional[Callable[[AssDocument], None]] = None,
        on_jump_to_sps: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 10
        self.on_document_changed = on_document_changed
        self.on_jump_to_sps = on_jump_to_sps

        self.document: Optional[AssDocument] = None
        self.selected_syllable_id: Optional[str] = None
        self.ass_picker = ft.FilePicker(on_result=self._on_ass_picked)

        self._build_controls()

    def get_services(self) -> list[ft.Service]:
        return [self.ass_picker]

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def apply_theme(self, pal: ThemePalette):
        """Update colors dynamically when theme changes."""
        self._build_controls()
        self._refresh_ui()
        self._safe_update()

    def load_ass_text(self, ass_text: str):
        """Load an ASS script into the editor."""
        try:
            self.document = AssDocument.from_text(ass_text)
            self.selected_syllable_id = None
            self._refresh_ui()
            if self.on_document_changed:
                self.on_document_changed(self.document)
        except Exception as e:
            self._show_snack(f"Ошибка чтения ASS: {e}", is_error=True)

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
        self.stats_text = ft.Text("Слогов: 0 | Бёрст: 0", size=12, color=pal.muted)

        # Native FilePicker Action for reliable mobile triggering
        self.open_file_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Открыть файл субтитров (.ass)",
            icon_color=pal.accent,
            action=ft.PickFiles(self.ass_picker, with_data=True),
        )

        self.romanize_btn = ft.FilledButton(
            "Ромадзи",
            icon=ft.Icons.TRANSLATE,
            style=ft.ButtonStyle(
                color=pal.fg,
                bgcolor=pal.raised,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(12, 8, 12, 8),
            ),
            on_click=self._on_romanize,
        )

        top_bar = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Караоке редактор", size=18, weight=ft.FontWeight.BOLD, color=pal.fg),
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

        self.syllables_list = ft.ListView(expand=True, spacing=8)

        self.empty_placeholder = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SUBTITLES_OFF, size=56, color=pal.muted),
                    ft.Text("Субтитры не загружены", size=16, weight=ft.FontWeight.BOLD, color=pal.muted),
                    ft.Text("Выровняйте аудио через Colab или откройте .ass файл", size=12, color=pal.muted),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        # Bottom docked panel for touch manipulation of selected syllable
        self.docked_toolbar = ft.Container(visible=False)

        self.content = ft.Column(
            [
                top_bar,
                ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                ft.Container(content=self.syllables_list, expand=True),
                self.docked_toolbar,
            ],
            expand=True,
            spacing=4,
        )

    def _refresh_ui(self):
        pal = get_current_palette()
        if not self.document:
            self.syllables_list.controls.clear()
            self.syllables_list.controls.append(self.empty_placeholder)
            self.stats_text.value = "Слогов: 0 | Бёрст: 0"
            self.stats_text.color = pal.muted
            self.docked_toolbar.visible = False
            self._safe_update()
            return

        all_syllables = list(self.document.karaoke_syllables())
        total_syls = len(all_syllables)
        burst_syls = sum(1 for s in all_syllables if s.burst_marked)
        self.stats_text.value = f"Слогов: {total_syls} | В бёрсте: {burst_syls}"
        self.stats_text.color = pal.muted

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

        # Update docked toolbar if a syllable is currently selected
        selected_syl = next((s for s in all_syllables if s.id == self.selected_syllable_id), None)
        if selected_syl:
            self._update_docked_toolbar(selected_syl, all_syllables)
            self.docked_toolbar.visible = True
        else:
            self.selected_syllable_id = None
            self.docked_toolbar.visible = False

        self._safe_update()

    def _build_line_card(self, ev, syls: list[KaraokeSyllable]) -> ft.Container:
        pal = get_current_palette()
        time_badge = ft.Text(
            f"{format_ass_time(ev.start)} ➔ {format_ass_time(ev.end)}",
            size=11,
            color=pal.muted,
        )

        chips = [self._build_syllable_chip(s) for s in syls]

        return ft.Container(
            content=ft.Column(
                [
                    time_badge,
                    ft.Row(chips, wrap=True, spacing=6, run_spacing=6),
                ],
                spacing=6,
            ),
            bgcolor=pal.panel,
            padding=10,
            border_radius=10,
            border=ft.Border.all(1, pal.border),
        )

    def _build_syllable_chip(self, s: KaraokeSyllable) -> ft.Container:
        pal = get_current_palette()
        is_selected = s.id == self.selected_syllable_id
        is_burst = s.burst_marked
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10

        if is_selected:
            chip_bg = pal.raised
            chip_border = ft.Border.all(2, pal.accent)
            chip_fg = pal.accent
        elif is_burst:
            chip_bg = pal.danger
            chip_border = ft.Border.all(1, pal.danger)
            chip_fg = pal.accent_fg
        else:
            chip_bg = pal.raised
            chip_border = ft.Border.all(1, pal.border)
            chip_fg = pal.fg

        def _on_chip_tap(e):
            if self.selected_syllable_id == s.id:
                # Toggle burst if already selected
                if is_burst:
                    uncolour_burst(self.document, [s.id])
                else:
                    colour_burst(self.document, [s.id])
                if self.on_document_changed:
                    self.on_document_changed(self.document)
            else:
                self.selected_syllable_id = s.id
            self._refresh_ui()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(f"{'🔥 ' if is_burst else ''}{text}", size=13, weight=ft.FontWeight.BOLD, color=chip_fg),
                    ft.Text(f"{dur_ms}ms", size=10, color=chip_fg if (is_burst or is_selected) else pal.muted),
                ],
                spacing=3,
                tight=True,
            ),
            bgcolor=chip_bg,
            border=chip_border,
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=8,
            ink=True,
            on_click=_on_chip_tap,
        )

    def _update_docked_toolbar(self, s: KaraokeSyllable, all_syllables: list[KaraokeSyllable]):
        """Render the touch controls for the active selected syllable."""
        pal = get_current_palette()
        is_burst = s.burst_marked
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10
        idx = next((i for i, item in enumerate(all_syllables) if item.id == s.id), -1)

        # 1. Header Row
        title_text = ft.Text(f"Слог: «{text}»  ({dur_ms} мс)", size=14, weight=ft.FontWeight.BOLD, color=pal.fg)
        time_text = ft.Text(f"{format_ass_time(s.start)} - {format_ass_time(s.end)}", size=11, color=pal.muted)

        close_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=18,
            tooltip="Снять выделение",
            icon_color=pal.muted,
            on_click=lambda e: self._deselect(),
        )

        header_row = ft.Row(
            [
                ft.Column([title_text, time_text], spacing=1, expand=True),
                close_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # 2. Duration Nudges (-50ms, -10ms, +10ms, +50ms)
        def _nudge(delta_cs: int):
            if not self.document:
                return
            try:
                nudge_syllable_duration(self.document, s.id, delta_cs)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()
            except Exception as ex:
                self._show_snack(f"Ошибка длительности: {ex}", is_error=True)

        nudge_btns = ft.Row(
            [
                ft.FilledButton(
                    "-50мс",
                    style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=ft.Padding(8, 4, 8, 4)),
                    on_click=lambda e: _nudge(-5),
                ),
                ft.FilledButton(
                    "-10мс",
                    style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=ft.Padding(8, 4, 8, 4)),
                    on_click=lambda e: _nudge(-1),
                ),
                ft.FilledButton(
                    "+10мс",
                    style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=ft.Padding(8, 4, 8, 4)),
                    on_click=lambda e: _nudge(1),
                ),
                ft.FilledButton(
                    "+50мс",
                    style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=ft.Padding(8, 4, 8, 4)),
                    on_click=lambda e: _nudge(5),
                ),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        # 3. Action Buttons (Burst, Split, Merge, Insert, Delete)
        def _toggle_burst(e):
            if is_burst:
                uncolour_burst(self.document, [s.id])
            else:
                colour_burst(self.document, [s.id])
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()

        def _split(e):
            try:
                res = split_syllable(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                if res.selected_ids:
                    self.selected_syllable_id = res.selected_ids[0]
                self._refresh_ui()
                self._show_snack("Слог разделён пополам")
            except Exception as ex:
                self._show_snack(f"Не удалось разделить: {ex}", is_error=True)

        def _merge(e):
            same_line = [item for item in all_syllables if item.event_line_index == s.event_line_index]
            ord_idx = next((i for i, item in enumerate(same_line) if item.id == s.id), -1)
            if ord_idx >= 0 and ord_idx + 1 < len(same_line):
                next_s = same_line[ord_idx + 1]
                try:
                    res = merge_syllables(self.document, [s.id, next_s.id])
                    if self.on_document_changed:
                        self.on_document_changed(self.document)
                    if res.selected_ids:
                        self.selected_syllable_id = res.selected_ids[0]
                    self._refresh_ui()
                    self._show_snack("Слоги объединены")
                except Exception as ex:
                    self._show_snack(f"Ошибка объединения: {ex}", is_error=True)
            else:
                self._show_snack("Нет следующего слога в этой строке для слияния", is_error=True)

        def _insert(e):
            try:
                res = insert_after(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                if res.selected_ids:
                    self.selected_syllable_id = res.selected_ids[0]
                self._refresh_ui()
                self._show_snack("Вставлен новый слог")
            except Exception as ex:
                self._show_snack(f"Ошибка вставки: {ex}", is_error=True)

        def _delete(e):
            try:
                res = delete_syllable(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self.selected_syllable_id = res.selected_ids[0] if res.selected_ids else None
                self._refresh_ui()
                self._show_snack("Слог удалён")
            except Exception as ex:
                self._show_snack(f"Ошибка удаления: {ex}", is_error=True)

        actions_row = ft.Row(
            [
                ft.FilledButton(
                    "Снять бёрст" if is_burst else "🔥 Бёрст",
                    style=ft.ButtonStyle(
                        bgcolor=pal.panel if is_burst else pal.danger,
                        color=pal.fg if is_burst else pal.accent_fg,
                        padding=ft.Padding(10, 6, 10, 6),
                    ),
                    on_click=_toggle_burst,
                ),
                ft.FilledButton(
                    "✂ Разрезать",
                    style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(10, 6, 10, 6)),
                    on_click=_split,
                ),
                ft.FilledButton(
                    "🔗 Слить",
                    style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(10, 6, 10, 6)),
                    on_click=_merge,
                ),
                ft.FilledButton(
                    "➕ Вставить",
                    style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(10, 6, 10, 6)),
                    on_click=_insert,
                ),
                ft.FilledButton(
                    "🗑",
                    style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.danger, padding=ft.Padding(10, 6, 10, 6)),
                    on_click=_delete,
                ),
            ],
            wrap=True,
            spacing=6,
        )

        # 4. Navigation & Text Editing Row
        def _nav(step: int):
            new_idx = idx + step
            if 0 <= new_idx < len(all_syllables):
                self.selected_syllable_id = all_syllables[new_idx].id
                self._refresh_ui()

        def _open_edit_text(e):
            self._open_text_dialog(s)

        def _jump_to_sps(e):
            if self.on_jump_to_sps:
                self.on_jump_to_sps(s.id)

        nav_row = ft.Row(
            [
                ft.FilledButton(
                    "◀ Пред",
                    disabled=idx <= 0,
                    style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(8, 4, 8, 4)),
                    on_click=lambda e: _nav(-1),
                ),
                ft.FilledButton(
                    "След ▶",
                    disabled=idx >= len(all_syllables) - 1,
                    style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(8, 4, 8, 4)),
                    on_click=lambda e: _nav(1),
                ),
                ft.FilledButton(
                    "✏ Текст",
                    style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(10, 4, 10, 4)),
                    on_click=_open_edit_text,
                ),
                ft.FilledButton(
                    "🎯 В точный SPS",
                    style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg, padding=ft.Padding(10, 4, 10, 4)),
                    on_click=_jump_to_sps,
                ),
            ],
            wrap=True,
            spacing=6,
        )

        self.docked_toolbar.content = ft.Container(
            content=ft.Column(
                [
                    header_row,
                    nudge_btns,
                    actions_row,
                    nav_row,
                ],
                spacing=6,
            ),
            bgcolor=pal.raised,
            padding=10,
            border_radius=12,
            border=ft.Border.all(1.5, pal.accent),
        )

    def _deselect(self):
        self.selected_syllable_id = None
        self._refresh_ui()

    def _open_text_dialog(self, s: KaraokeSyllable):
        pal = get_current_palette()
        text_input = ft.TextField(
            label="Текст слога",
            value=s.visible_text.strip() or s.raw_text.strip(),
            autofocus=True,
        )
        rom_input = ft.TextField(
            label="Ромадзи (чтение)",
            value=s.romanization or "",
        )

        def _save(e):
            try:
                if text_input.value != s.visible_text:
                    set_syllable_text(self.document, s.id, text_input.value)
                if rom_input.value != s.romanization:
                    set_syllable_romanization(self.document, s.id, rom_input.value)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                dialog.open = False
                self._refresh_ui()
                self._show_snack("Текст слога обновлен")
            except Exception as ex:
                self._show_snack(f"Ошибка сохранения: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text("Редактирование слога", color=pal.fg),
            content=ft.Column([text_input, rom_input], tight=True, spacing=10),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: setattr(dialog, "open", False) or self.page.update()),
                ft.FilledButton("Сохранить", on_click=_save),
            ],
        )
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

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
                self._show_snack(f"Субтитры загружены: {f.name}")
            except Exception as ex:
                self._show_snack(f"Ошибка чтения: {ex}", is_error=True)

    def _on_romanize(self, e):
        if not self.document:
            return
        self._refresh_ui()
        self._show_snack("Ромадзи обработано")
