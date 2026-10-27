"""Mobile-optimized Karaoke Syllable & Burst Editor with PC-parity Ergonomics."""

from __future__ import annotations

import re
from typing import Callable, Optional

import flet as ft

from core.ass import AssDocument, KaraokeSyllable, KaraokeTagType, format_ass_time
from core.editor import (
    colour_burst,
    delete_syllable,
    insert_after,
    merge_syllables,
    nudge_syllable_duration,
    redistribute_boundary,
    set_syllable_duration,
    set_syllable_end_at_time,
    set_syllable_romanization,
    set_syllable_start_at_time,
    set_syllable_text,
    set_tag_type,
    shift_syllable,
    split_syllable,
    split_syllable_at_time,
    uncolour_burst,
)
from core.sps import MeasurementTimeline
from ui.components.audio_timeline import AudioTimelineWidget
from ui.display_settings import get_display_settings
from ui.theme import ThemePalette, get_current_palette


class EditorView(ft.Container):
    """Touch-friendly view for viewing, modifying, splitting, merging, and marking karaoke syllables."""

    def __init__(
        self,
        on_document_changed: Optional[Callable[[AssDocument], None]] = None,
        on_jump_to_sps: Optional[Callable[[str], None]] = None,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[object], Optional[object]], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 6
        self.on_document_changed = on_document_changed
        self.on_jump_to_sps = on_jump_to_sps
        self.on_audio_loaded_cb = on_audio_loaded

        self.document: Optional[AssDocument] = None
        self._selected_syllable_ids: list[str] = []
        self.multi_select_mode: bool = False
        self._page: Optional[ft.Page] = None
        self.ass_picker = ft.FilePicker(on_result=self._on_ass_picked)

        # Audio Timeline (Waveform & Spectrogram) with Syllable Selection
        self.audio_timeline = AudioTimelineWidget(
            on_audio_loaded=self._handle_audio_loaded,
            on_syllable_clicked=self._on_timeline_syllable_clicked,
        )

        # Undo/Redo history stack
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []

        self._build_controls()

    @property
    def selected_syllable_id(self) -> Optional[str]:
        return self._selected_syllable_ids[0] if self._selected_syllable_ids else None

    @selected_syllable_id.setter
    def selected_syllable_id(self, val: Optional[str]):
        self._selected_syllable_ids = [val] if val else []

    @property
    def selected_syllable_ids(self) -> list[str]:
        return self._selected_syllable_ids

    @selected_syllable_ids.setter
    def selected_syllable_ids(self, val: list[str]):
        self._selected_syllable_ids = list(val)

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

    def _open_dialog(self, dialog: ft.AlertDialog):
        p = self._get_page()
        if not p:
            return
        if hasattr(p, "show_dialog"):
            try:
                p.show_dialog(dialog)
                return
            except Exception:
                pass
        if hasattr(p, "open"):
            try:
                p.open(dialog)
                return
            except Exception:
                pass
        if hasattr(p, "overlay"):
            p.overlay.append(dialog)
            dialog.open = True
            try:
                p.update()
            except Exception:
                pass

    def _close_dialog(self, dialog: Optional[ft.AlertDialog] = None):
        p = self._get_page()
        if not p:
            if dialog:
                dialog.open = False
            return
        if hasattr(p, "pop_dialog"):
            try:
                p.pop_dialog()
                return
            except Exception:
                pass
        if hasattr(p, "close") and dialog:
            try:
                p.close(dialog)
                return
            except Exception:
                pass
        if dialog:
            dialog.open = False
        try:
            p.update()
        except Exception:
            pass

    def _handle_audio_loaded(self, name: str, data: bytes, waveform, spectrogram):
        if self.on_audio_loaded_cb:
            self.on_audio_loaded_cb(name, data, waveform, spectrogram)

    def get_services(self) -> list[ft.Service]:
        return [self.ass_picker] + self.audio_timeline.get_services()

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def apply_theme(self, pal: ThemePalette):
        """Update colors dynamically when theme changes."""
        self.audio_timeline.apply_theme(pal)
        self._build_controls()
        self._refresh_ui()
        self._safe_update()

    def _push_undo(self):
        """Record current document state into undo history before mutation."""
        if self.document:
            self._undo_stack.append(self.document.dumps())
            if len(self._undo_stack) > 50:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def undo(self, e=None):
        if not self._undo_stack or not self.document:
            self._show_snack("Нечего отменять (история пуста)")
            return
        self._redo_stack.append(self.document.dumps())
        prev_text = self._undo_stack.pop()
        try:
            self.document = AssDocument.from_text(prev_text)
            self._refresh_ui()
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._show_snack("Действие отменено (Undo)")
        except Exception as ex:
            self._show_snack(f"Ошибка отмены: {ex}", is_error=True)

    def redo(self, e=None):
        if not self._redo_stack or not self.document:
            self._show_snack("Нечего повторять (история пуста)")
            return
        self._undo_stack.append(self.document.dumps())
        next_text = self._redo_stack.pop()
        try:
            self.document = AssDocument.from_text(next_text)
            self._refresh_ui()
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._show_snack("Действие повторено (Redo)")
        except Exception as ex:
            self._show_snack(f"Ошибка повтора: {ex}", is_error=True)

    def load_ass_text(self, ass_text: str):
        """Load an ASS script into the editor."""
        try:
            self.document = AssDocument.from_text(ass_text)
            self.selected_syllable_ids = []
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._refresh_ui()
            if self.on_document_changed:
                self.on_document_changed(self.document)
        except Exception as e:
            self._show_snack(f"Ошибка чтения ASS: {e}", is_error=True)

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
        f_title = ds.font_size(13)
        f_stats = ds.font_size(10.5)
        ic_size = ds.icon_size(18)

        self.stats_text = ft.Text("Слогов: 0 | Бёрст: 0", size=f_stats, color=pal.muted)

        # Native FilePicker Action
        self.open_file_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Открыть файл субтитров (.ass)",
            icon_size=ic_size,
            icon_color=pal.accent,
            action=ft.PickFiles(self.ass_picker, with_data=True),
        )

        self.undo_btn = ft.IconButton(
            icon=ft.Icons.UNDO,
            tooltip="Отменить (Undo)",
            icon_size=ic_size,
            icon_color=pal.fg,
            on_click=self.undo,
        )
        self.redo_btn = ft.IconButton(
            icon=ft.Icons.REDO,
            tooltip="Повторить (Redo)",
            icon_size=ic_size,
            icon_color=pal.fg,
            on_click=self.redo,
        )

        self.multi_select_btn = ft.IconButton(
            icon=ft.Icons.CHECK_BOX if self.multi_select_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            tooltip="Режим мульти-выбора слогов",
            icon_size=ic_size,
            icon_color=pal.accent if self.multi_select_mode else pal.muted,
            on_click=lambda e: self._toggle_multi_select(),
        )

        self.full_text_btn = ft.IconButton(
            icon=ft.Icons.ARTICLE,
            tooltip="Просмотр полного текста песни",
            icon_size=ic_size,
            icon_color=pal.fg,
            on_click=lambda e: self._open_full_text_dialog(),
        )

        self.sps_jump_top_btn = ft.IconButton(
            icon=ft.Icons.SPEED,
            tooltip="Перейти в точный SPS",
            icon_size=ic_size,
            icon_color=pal.accent,
            on_click=lambda e: self._transfer_to_sps(),
        )

        top_header_row = ft.Row(
            [
                ft.Row(
                    [
                        ft.Text("Караоке", size=f_title, weight=ft.FontWeight.BOLD, color=pal.fg),
                        self.stats_text,
                    ],
                    spacing=5,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                ),
                ft.Row(
                    [
                        self.undo_btn,
                        self.redo_btn,
                        self.multi_select_btn,
                        self.full_text_btn,
                        self.open_file_btn,
                        self.sps_jump_top_btn,
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        top_bar = ft.Container(
            content=top_header_row,
            bgcolor=pal.panel,
            padding=ft.Padding(8, 4, 8, 4),
            border_radius=8,
            border=ft.Border.all(1, pal.border),
        )

        self.syllables_list = ft.ListView(expand=True, spacing=5)

        self.empty_placeholder = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SUBTITLES_OFF, size=ds.icon_size(44), color=pal.muted),
                    ft.Text("Субтитры не загружены", size=ds.font_size(14), weight=ft.FontWeight.BOLD, color=pal.muted),
                    ft.Text("Выровняйте аудио через Colab или откройте .ass файл", size=ds.font_size(11), color=pal.muted),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        # Bottom docked panel for touch manipulation of selected syllable
        self.docked_toolbar = ft.Container(visible=False)

        # Check orientation: on wide displays (landscape 20:9), provide split layout
        p = self._get_page()
        is_landscape = bool(p and getattr(p, "width", 0) and getattr(p, "height", 0) and p.width > p.height)

        if is_landscape:
            # 2-column landscape layout
            left_col = ft.Container(
                content=ft.Column(
                    [
                        self.audio_timeline,
                        self.docked_toolbar,
                    ],
                    spacing=4,
                    scroll=ft.ScrollMode.AUTO,
                ),
                expand=5,
            )
            right_col = ft.Container(
                content=ft.Column(
                    [
                        top_bar,
                        ft.Container(content=self.syllables_list, expand=True),
                    ],
                    spacing=4,
                    expand=True,
                ),
                expand=5,
            )
            self.content = ft.Row([left_col, right_col], spacing=6, expand=True)
        else:
            # Standard portrait layout
            self.content = ft.Column(
                [
                    top_bar,
                    self.audio_timeline,
                    ft.Container(content=self.syllables_list, expand=True),
                    self.docked_toolbar,
                ],
                expand=True,
                spacing=3,
            )

    def _transfer_to_sps(self):
        target_id = self.selected_syllable_id
        if not target_id and self.document:
            first_syl = next(self.document.karaoke_syllables(), None)
            if first_syl:
                target_id = first_syl.id
        if self.on_jump_to_sps:
            self.on_jump_to_sps(target_id or "")

    def _toggle_multi_select(self):
        self.multi_select_mode = not self.multi_select_mode
        if hasattr(self, "multi_select_btn"):
            pal = get_current_palette()
            self.multi_select_btn.icon = ft.Icons.CHECK_BOX if self.multi_select_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK
            self.multi_select_btn.icon_color = pal.accent if self.multi_select_mode else pal.muted
        self._refresh_ui()

    def _refresh_ui(self):
        pal = get_current_palette()
        ds = get_display_settings()
        if not self.document:
            self.syllables_list.controls.clear()
            self.syllables_list.controls.append(self.empty_placeholder)
            self.stats_text.value = "Слогов: 0 | Бёрст: 0"
            self.stats_text.color = pal.muted
            self.docked_toolbar.visible = False
            self.audio_timeline.set_active_bounds(None, None)
            self._safe_update()
            return

        all_syllables = list(self.document.karaoke_syllables())
        total_syls = len(all_syllables)
        burst_syls = sum(1 for s in all_syllables if s.burst_marked)
        self.stats_text.value = f"| {total_syls} сл (🔥 {burst_syls})"
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

        # Sync all syllables to audio timeline for spectrogram & waveform visualization
        mt = MeasurementTimeline.from_karaoke(all_syllables)
        first_sel_id = self.selected_syllable_ids[0] if self.selected_syllable_ids else None
        self.audio_timeline.set_syllables(mt.syllables, first_sel_id)

        # Update docked toolbar if any syllable is currently selected
        selected_syls = [s for s in all_syllables if s.id in self.selected_syllable_ids]
        if selected_syls:
            self._update_docked_toolbar(selected_syls, all_syllables)
            self.docked_toolbar.visible = True
            min_st = min(s.start for s in selected_syls)
            max_en = max(s.end for s in selected_syls)
            self.audio_timeline.focus_syllable(min_st, max_en, syllable_id=selected_syls[0].id)
        else:
            self._selected_syllable_ids = []
            self.docked_toolbar.visible = False
            self.audio_timeline.set_active_bounds(None, None)

        self._safe_update()

    def _on_timeline_syllable_clicked(self, sid: str):
        if self.multi_select_mode:
            if sid in self.selected_syllable_ids:
                self.selected_syllable_ids.remove(sid)
            else:
                self.selected_syllable_ids.append(sid)
        else:
            self.selected_syllable_ids = [sid]
        self._refresh_ui()

    def _build_line_card(self, ev, syls: list[KaraokeSyllable]) -> ft.Container:
        pal = get_current_palette()
        ds = get_display_settings()
        dur_line_ms = int(round((ev.end - ev.start) * 1000))
        time_badge = ft.Text(
            f"Строка {ev.line_index} | {format_ass_time(ev.start)} ➔ {format_ass_time(ev.end)} ({dur_line_ms}мс)",
            size=ds.font_size(10),
            color=pal.muted,
        )

        def _select_line(e):
            self.selected_syllable_ids = [s.id for s in syls]
            self._refresh_ui()

        line_top = ft.Row(
            [
                time_badge,
                ft.TextButton(
                    "☑ Вся строка",
                    style=ft.ButtonStyle(
                        padding=ds.button_padding(3, 1),
                        color=pal.accent,
                    ),
                    tooltip="Выбрать все слоги строки",
                    on_click=_select_line,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        chips = [self._build_syllable_chip(s) for s in syls]

        return ft.Container(
            content=ft.Column(
                [
                    line_top,
                    ft.Row(chips, wrap=True, spacing=ds.icon_size(4), run_spacing=ds.icon_size(4)),
                ],
                spacing=2,
            ),
            bgcolor=pal.panel,
            padding=ds.button_padding(7, 4),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
        )

    def _build_syllable_chip(self, s: KaraokeSyllable) -> ft.Container:
        pal = get_current_palette()
        ds = get_display_settings()
        is_selected = s.id in self.selected_syllable_ids
        is_burst = s.burst_marked
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10
        tag_val = s.tag_type.value

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
            if self.multi_select_mode:
                if s.id in self.selected_syllable_ids:
                    self.selected_syllable_ids.remove(s.id)
                else:
                    self.selected_syllable_ids.append(s.id)
                self._refresh_ui()
            else:
                if self.selected_syllable_ids == [s.id]:
                    self._open_text_dialog(s)
                else:
                    self.selected_syllable_ids = [s.id]
                    self._refresh_ui()

        tag_badge = f"\\{tag_val}" if tag_val != "k" else ""
        prefix = "✓ " if (is_selected and len(self.selected_syllable_ids) > 1) else ("🔥 " if is_burst else "")
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(f"{prefix}{text}", size=ds.font_size(11.5), weight=ft.FontWeight.BOLD, color=chip_fg),
                    ft.Text(f"{dur_ms}ms{(' ' + tag_badge) if tag_badge else ''}", size=ds.font_size(9), color=chip_fg if (is_burst or is_selected) else pal.muted),
                ],
                spacing=2,
                tight=True,
            ),
            bgcolor=chip_bg,
            border=chip_border,
            padding=ds.button_padding(5, 3),
            border_radius=6,
            ink=True,
            on_click=_on_chip_tap,
        )

    def _update_docked_toolbar(self, selected_input, all_syllables: list[KaraokeSyllable]):
        """Render touch controls for the selected syllable(s) matching PC functionality."""
        pal = get_current_palette()
        ds = get_display_settings()
        pad = ds.button_padding(4, 2)

        if isinstance(selected_input, list):
            selected_syls = selected_input
        else:
            selected_syls = [selected_input] if selected_input else []

        if not selected_syls:
            self.docked_toolbar.visible = False
            return

        # ----------------- CASE A: Multiple Syllables Selected -----------------
        if len(selected_syls) > 1:
            total_dur_ms = sum(item.duration_cs * 10 for item in selected_syls)
            combined_text = "".join(item.visible_text.strip() or item.raw_text.strip() for item in selected_syls)
            min_st = min(item.start for item in selected_syls)
            max_en = max(item.end for item in selected_syls)

            first_line = selected_syls[0].event_line_index
            same_line = [item for item in all_syllables if item.event_line_index == first_line]
            ordered_ids = [item.id for item in same_line if item.id in self.selected_syllable_ids]

            def _merge_multi(e):
                if not self.document:
                    return
                if len(ordered_ids) < 2:
                    self._show_snack("Выберите минимум 2 слога для слияния", is_error=True)
                    return
                try:
                    self._push_undo()
                    res = merge_syllables(self.document, ordered_ids)
                    if self.on_document_changed:
                        self.on_document_changed(self.document)
                    self.selected_syllable_ids = list(res.selected_ids)
                    self._refresh_ui()
                    self._show_snack(f"Объединено {len(ordered_ids)} слогов в один")
                except Exception as ex:
                    self._show_snack(f"Ошибка слияния: {ex}", is_error=True)

            def _burst_multi(e):
                if not self.document:
                    return
                self._push_undo()
                all_burst = all(item.burst_marked for item in selected_syls)
                if all_burst:
                    uncolour_burst(self.document, ordered_ids)
                else:
                    colour_burst(self.document, ordered_ids)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()

            def _delete_multi(e):
                if not self.document:
                    return
                try:
                    self._push_undo()
                    for sid in reversed(ordered_ids):
                        delete_syllable(self.document, sid)
                    if self.on_document_changed:
                        self.on_document_changed(self.document)
                    self.selected_syllable_ids = []
                    self._refresh_ui()
                    self._show_snack(f"Удалено {len(ordered_ids)} слогов")
                except Exception as ex:
                    self._show_snack(f"Ошибка удаления: {ex}", is_error=True)

            all_burst = all(item.burst_marked for item in selected_syls)

            m_row1 = ft.Row(
                [
                    ft.Text(
                        f"Выбрано: {len(selected_syls)} слогов ({total_dur_ms}мс) «{combined_text[:16]}»",
                        size=ds.font_size(11),
                        weight=ft.FontWeight.BOLD,
                        color=pal.accent,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.PLAY_CIRCLE_FILL,
                        tooltip="Воспроизвести диапазон выбранных слогов",
                        icon_size=ds.icon_size(19),
                        icon_color=pal.accent,
                        on_click=lambda e: self.audio_timeline.play_range(min_st, max_en),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CHECK_BOX if self.multi_select_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                        tooltip="Режим выбора нескольких слогов",
                        icon_size=ds.icon_size(17),
                        icon_color=pal.accent if self.multi_select_mode else pal.muted,
                        on_click=lambda e: self._toggle_multi_select(),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip="Снять выделение",
                        icon_size=ds.icon_size(17),
                        icon_color=pal.muted,
                        on_click=lambda e: self._deselect(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

            m_row2 = ft.Row(
                [
                    ft.FilledButton(
                        f"🔗 Слить {len(ordered_ids)}",
                        style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg, padding=pad),
                        on_click=_merge_multi,
                    ),
                    ft.FilledButton(
                        "Снять 🔥" if all_burst else "🔥 Бёрст все",
                        style=ft.ButtonStyle(bgcolor=pal.danger if not all_burst else pal.panel, color=pal.accent_fg if not all_burst else pal.fg, padding=pad),
                        on_click=_burst_multi,
                    ),
                    ft.FilledButton(
                        f"🗑 Удалить ({len(ordered_ids)})",
                        style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.danger, padding=pad),
                        on_click=_delete_multi,
                    ),
                    ft.FilledButton(
                        "✕ Снять выбор",
                        style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad),
                        on_click=lambda e: self._deselect(),
                    ),
                ],
                spacing=2,
                scroll=ft.ScrollMode.AUTO,
            )

            self.docked_toolbar.content = ft.Container(
                content=ft.Column([m_row1, m_row2], spacing=2, tight=True),
                bgcolor=pal.panel,
                padding=ft.Padding(7, 3, 7, 3),
                border_radius=7,
                border=ft.Border.all(1.5, pal.accent),
            )
            return

        # ----------------- CASE B: Single Syllable Selected -----------------
        s = selected_syls[0]
        is_burst = s.burst_marked
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10
        idx = next((i for i, item in enumerate(all_syllables) if item.id == s.id), -1)

        same_line = [item for item in all_syllables if item.event_line_index == s.event_line_index]
        ord_idx = next((i for i, item in enumerate(same_line) if item.id == s.id), -1)
        prev_s = same_line[ord_idx - 1] if ord_idx > 0 else None
        next_s = same_line[ord_idx + 1] if (ord_idx >= 0 and ord_idx + 1 < len(same_line)) else None

        if not hasattr(self, "toolbar_mode"):
            self.toolbar_mode = "dur"

        def _nav(step: int):
            new_idx = idx + step
            if 0 <= new_idx < len(all_syllables):
                self.selected_syllable_ids = [all_syllables[new_idx].id]
                self._refresh_ui()

        title_text = ft.Text(
            f"«{text}» ({dur_ms}мс, \\{s.tag_type.value})",
            size=ds.font_size(11.5),
            weight=ft.FontWeight.BOLD,
            color=pal.fg,
        )
        time_text = ft.Text(
            f"{format_ass_time(s.start)} - {format_ass_time(s.end)}",
            size=ds.font_size(9),
            color=pal.muted,
        )

        header_row = ft.Row(
            [
                ft.Row([title_text, time_text], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.PLAY_CIRCLE_FILL,
                            tooltip="Прослушать слог",
                            icon_size=ds.icon_size(19),
                            icon_color=pal.accent,
                            on_click=lambda e: self.audio_timeline.play_range(s.start, s.end),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            tooltip="Предыдущий слог",
                            icon_size=ds.icon_size(16),
                            icon_color=pal.fg if idx > 0 else pal.muted,
                            disabled=idx <= 0,
                            on_click=lambda e: _nav(-1),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_FORWARD,
                            tooltip="Следующий слог",
                            icon_size=ds.icon_size(16),
                            icon_color=pal.fg if idx < len(all_syllables) - 1 else pal.muted,
                            disabled=idx >= len(all_syllables) - 1,
                            on_click=lambda e: _nav(1),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHECK_BOX if self.multi_select_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                            tooltip="Режим мульти-выбора",
                            icon_size=ds.icon_size(16),
                            icon_color=pal.accent if self.multi_select_mode else pal.muted,
                            on_click=lambda e: self._toggle_multi_select(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=ds.icon_size(16),
                            tooltip="Снять выделение",
                            icon_color=pal.muted,
                            on_click=lambda e: self._deselect(),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Timing Steppers
        def _nudge_dur(delta_cs: int):
            if not self.document:
                return
            try:
                self._push_undo()
                nudge_syllable_duration(self.document, s.id, delta_cs)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()
            except Exception as ex:
                self._show_snack(f"Ошибка длительности: {ex}", is_error=True)

        def _nudge_boundary(delta_cs: int):
            if not self.document or not next_s:
                self._show_snack("Нет следующего слога для смещения границы", is_error=True)
                return
            try:
                self._push_undo()
                new_boundary = next_s.start + (delta_cs / 100.0)
                redistribute_boundary(self.document, s.id, next_s.id, new_boundary)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()
                self._show_snack(f"Граница сдвинута на {delta_cs*10:+d}мс")
            except Exception as ex:
                self._show_snack(f"Ошибка границы: {ex}", is_error=True)

        def _shift(delta_cs: int):
            if not self.document:
                return
            try:
                self._push_undo()
                shift_syllable(self.document, s.id, delta_cs)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()
                self._show_snack(f"Слог сдвинут на {delta_cs*10:+d}мс")
            except Exception as ex:
                self._show_snack(f"Ошибка сдвига: {ex}", is_error=True)

        def _snap_start_to_cursor(e):
            if not self.document:
                return
            try:
                self._push_undo()
                set_syllable_start_at_time(self.document, s.id, self.audio_timeline.center_time)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()
                self._show_snack(f"Start привязан к курсору: {self.audio_timeline.center_time:.3f}с")
            except Exception as ex:
                self._show_snack(f"Ошибка привязки Start: {ex}", is_error=True)

        def _snap_end_to_cursor(e):
            if not self.document:
                return
            try:
                self._push_undo()
                set_syllable_end_at_time(self.document, s.id, self.audio_timeline.center_time)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._refresh_ui()
                self._show_snack(f"End привязан к курсору: {self.audio_timeline.center_time:.3f}с")
            except Exception as ex:
                self._show_snack(f"Ошибка привязки End: {ex}", is_error=True)

        def _set_mode(m: str):
            self.toolbar_mode = m
            self._update_docked_toolbar(s, all_syllables)
            self._safe_update()

        def make_tab(label: str, mode_val: str):
            is_active = (self.toolbar_mode == mode_val)
            return ft.Container(
                content=ft.Text(
                    label,
                    size=ds.font_size(9),
                    weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                    color=pal.accent_fg if is_active else pal.fg,
                ),
                bgcolor=pal.accent if is_active else pal.panel,
                border_radius=4,
                padding=ds.button_padding(4, 2),
                on_click=lambda e, mv=mode_val: _set_mode(mv),
            )

        mode_tabs = [
            make_tab("⏱ Длит", "dur"),
            make_tab("⇥ Шов", "seam"),
            make_tab("⇄ Сдвиг", "shift"),
            make_tab("🎯 Курсор", "snap"),
        ]

        if self.toolbar_mode == "seam":
            stepper_btns = [
                ft.FilledButton("⇥ -50ms", disabled=not next_s, style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_boundary(-5)),
                ft.FilledButton("⇥ -10ms", disabled=not next_s, style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_boundary(-1)),
                ft.FilledButton("+10ms ⇤", disabled=not next_s, style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_boundary(1)),
                ft.FilledButton("+50ms ⇤", disabled=not next_s, style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_boundary(5)),
            ]
        elif self.toolbar_mode == "shift":
            stepper_btns = [
                ft.FilledButton("-50ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _shift(-5)),
                ft.FilledButton("-10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _shift(-1)),
                ft.FilledButton("+10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _shift(1)),
                ft.FilledButton("+50ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _shift(5)),
            ]
        elif self.toolbar_mode == "snap":
            stepper_btns = [
                ft.FilledButton("🎯 Start = Курсор", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.accent, padding=pad), on_click=_snap_start_to_cursor),
                ft.FilledButton("🎯 End = Курсор", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.accent, padding=pad), on_click=_snap_end_to_cursor),
            ]
        else:
            stepper_btns = [
                ft.FilledButton("-100ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_dur(-10)),
                ft.FilledButton("-50ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_dur(-5)),
                ft.FilledButton("-10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_dur(-1)),
                ft.FilledButton("+10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_dur(1)),
                ft.FilledButton("+50ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_dur(5)),
                ft.FilledButton("+100ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _nudge_dur(10)),
            ]

        timing_row = ft.Row(
            mode_tabs + [ft.Container(width=4)] + stepper_btns,
            spacing=2,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Action handlers
        def _toggle_burst(e):
            self._push_undo()
            if is_burst:
                uncolour_burst(self.document, [s.id])
            else:
                colour_burst(self.document, [s.id])
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()

        # PC FEATURE: Split syllable at cursor position
        def _split_at_cursor(e):
            if not self.document:
                return
            cursor_t = round(self.audio_timeline.center_time, 3)
            if not (s.start < cursor_t < s.end):
                self._show_snack(f"Курсор ({cursor_t:.3f}с) вне слога ({s.start:.3f}с..{s.end:.3f}с)", is_error=True)
                return
            try:
                self._push_undo()
                res = split_syllable_at_time(self.document, s.id, cursor_t)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                if res.selected_ids:
                    self.selected_syllable_ids = list(res.selected_ids)
                self._refresh_ui()
                self._show_snack(f"Слог разделён по курсору ({cursor_t:.3f}с)")
            except Exception as ex:
                self._show_snack(f"Не удалось разделить: {ex}", is_error=True)

        def _split_half(e):
            try:
                self._push_undo()
                res = split_syllable(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                if res.selected_ids:
                    self.selected_syllable_ids = list(res.selected_ids)
                self._refresh_ui()
                self._show_snack("Слог разделён пополам")
            except Exception as ex:
                self._show_snack(f"Не удалось разделить: {ex}", is_error=True)

        def _merge(e):
            if next_s:
                try:
                    self._push_undo()
                    res = merge_syllables(self.document, [s.id, next_s.id])
                    if self.on_document_changed:
                        self.on_document_changed(self.document)
                    if res.selected_ids:
                        self.selected_syllable_ids = list(res.selected_ids)
                    self._refresh_ui()
                    self._show_snack("Слоги объединены")
                except Exception as ex:
                    self._show_snack(f"Ошибка объединения: {ex}", is_error=True)
            else:
                self._show_snack("Нет следующего слога в строке для слияния", is_error=True)

        def _insert(e):
            try:
                self._push_undo()
                res = insert_after(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                if res.selected_ids:
                    self.selected_syllable_ids = list(res.selected_ids)
                self._refresh_ui()
                self._show_snack("Вставлен новый слог")
            except Exception as ex:
                self._show_snack(f"Ошибка вставки: {ex}", is_error=True)

        def _delete(e):
            try:
                self._push_undo()
                res = delete_syllable(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self.selected_syllable_ids = list(res.selected_ids) if res.selected_ids else []
                self._refresh_ui()
                self._show_snack("Слог удалён")
            except Exception as ex:
                self._show_snack(f"Ошибка удаления: {ex}", is_error=True)

        actions_row = ft.Row(
            [
                ft.FilledButton("✏ Текст", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=lambda e: self._open_text_dialog(s)),
                ft.FilledButton("✂ По курсору", tooltip="Разрезать слог в точке курсора аудио", style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg, padding=pad), on_click=_split_at_cursor),
                ft.FilledButton("✂ 50/50", tooltip="Разрезать слог пополам", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=_split_half),
                ft.FilledButton("🔗 Слить", disabled=not next_s, style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=_merge),
                ft.FilledButton(
                    "Снять 🔥" if is_burst else "🔥 Бёрст",
                    style=ft.ButtonStyle(
                        bgcolor=pal.panel if is_burst else pal.danger,
                        color=pal.fg if is_burst else pal.accent_fg,
                        padding=pad,
                    ),
                    on_click=_toggle_burst,
                ),
                ft.FilledButton("➕ Вставить", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=pad), on_click=_insert),
                ft.FilledButton("🗑", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.danger, padding=pad), on_click=_delete),
                ft.FilledButton("🎯 В SPS", style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg, padding=pad), on_click=lambda e: self._transfer_to_sps()),
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=2,
        )

        self.docked_toolbar.content = ft.Container(
            content=ft.Column(
                [
                    header_row,
                    actions_row,
                    timing_row,
                ],
                spacing=2,
                tight=True,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(7, 3, 7, 3),
            border_radius=7,
            border=ft.Border.all(1.5, pal.accent),
        )

    def _deselect(self):
        self.selected_syllable_ids = []
        self._refresh_ui()

    def _open_text_dialog(self, s: KaraokeSyllable):
        pal = get_current_palette()
        ds = get_display_settings()
        text_input = ft.TextField(
            label="Текст слога",
            value=s.visible_text.strip() or s.raw_text.strip(),
            autofocus=True,
            text_size=ds.font_size(13),
        )
        rom_input = ft.TextField(
            label="Ромадзи (чтение)",
            value=s.romanization or "",
            text_size=ds.font_size(13),
        )
        tag_dropdown = ft.Dropdown(
            label="Тип караоке тега",
            options=[
                ft.dropdown.Option("k", "\\k (резкий)"),
                ft.dropdown.Option("kf", "\\kf (плавный)"),
                ft.dropdown.Option("ko", "\\ko (outline)"),
                ft.dropdown.Option("K", "\\K (плавный alias)"),
            ],
            value=s.tag_type.value,
            text_size=ds.font_size(13),
        )

        def _toggle_unspoken(e):
            val = text_input.value.strip()
            if val.startswith("[") and val.endswith("]"):
                text_input.value = val[1:-1].strip()
            else:
                text_input.value = f"[{val}]"
            try:
                text_input.update()
            except Exception:
                p = self._get_page()
                if p:
                    p.update()

        unspoken_btn = ft.OutlinedButton(
            "[...] Непроизнесённое",
            tooltip="Пометить как [непроизнесённый] слог (исключается из анализа SPS)",
            on_click=_toggle_unspoken,
        )

        def _save(e):
            try:
                self._push_undo()
                if text_input.value != s.visible_text:
                    set_syllable_text(self.document, s.id, text_input.value)
                if rom_input.value != s.romanization:
                    set_syllable_romanization(self.document, s.id, rom_input.value)
                if tag_dropdown.value != s.tag_type.value:
                    set_tag_type(self.document, [s.id], tag_dropdown.value)

                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._close_dialog(dialog)
                self._refresh_ui()
                self._show_snack("Слог успешно обновлён")
            except Exception as ex:
                self._show_snack(f"Ошибка сохранения: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text(f"Редактирование {s.id}", color=pal.fg, size=ds.font_size(15), weight=ft.FontWeight.BOLD),
            content=ft.Column([text_input, unspoken_btn, rom_input, tag_dropdown], tight=True, spacing=8),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self._close_dialog(dialog)),
                ft.FilledButton("Сохранить", on_click=_save),
            ],
        )
        self._open_dialog(dialog)

    def _open_timing_dialog(self, s: KaraokeSyllable):
        pal = get_current_palette()
        ds = get_display_settings()
        pad = ds.button_padding(4, 2)

        dur_ms = s.duration_cs * 10
        dur_input = ft.TextField(
            label="Длительность (мс)",
            value=str(dur_ms),
            keyboard_type=ft.KeyboardType.NUMBER,
            text_size=ds.font_size(13),
        )

        def _quick_nudge(delta_ms: int):
            try:
                val = int(dur_input.value or "0") + delta_ms
                dur_input.value = str(max(10, val))
                try:
                    dur_input.update()
                except Exception:
                    p = self._get_page()
                    if p:
                        p.update()
            except Exception:
                pass

        nudge_row = ft.Row(
            [
                ft.FilledButton("-100ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _quick_nudge(-100)),
                ft.FilledButton("-50ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _quick_nudge(-50)),
                ft.FilledButton("-10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _quick_nudge(-10)),
                ft.FilledButton("+10ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _quick_nudge(10)),
                ft.FilledButton("+50ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _quick_nudge(50)),
                ft.FilledButton("+100ms", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.fg, padding=pad), on_click=lambda e: _quick_nudge(100)),
            ],
            spacing=2,
            wrap=True,
        )

        def _snap_start_to_cursor(e):
            try:
                self._push_undo()
                set_syllable_start_at_time(self.document, s.id, self.audio_timeline.center_time)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._close_dialog(dialog)
                self._refresh_ui()
                self._show_snack(f"Start слога привязан к курсору ({self.audio_timeline.center_time:.3f}с)")
            except Exception as ex:
                self._show_snack(f"Ошибка привязки Start: {ex}", is_error=True)

        def _snap_end_to_cursor(e):
            try:
                self._push_undo()
                set_syllable_end_at_time(self.document, s.id, self.audio_timeline.center_time)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._close_dialog(dialog)
                self._refresh_ui()
                self._show_snack(f"End слога привязан к курсору ({self.audio_timeline.center_time:.3f}с)")
            except Exception as ex:
                self._show_snack(f"Ошибка привязки End: {ex}", is_error=True)

        snap_row = ft.Row(
            [
                ft.FilledButton("🎯 Start = Курсор", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.accent, padding=pad), on_click=_snap_start_to_cursor),
                ft.FilledButton("🎯 End = Курсор", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.accent, padding=pad), on_click=_snap_end_to_cursor),
            ],
            spacing=4,
        )

        def _save(e):
            try:
                val = int(dur_input.value or "0")
                if val <= 0:
                    self._show_snack("Длительность должна быть больше 0", is_error=True)
                    return
                cs_val = max(1, int(round(val / 10.0)))
                self._push_undo()
                set_syllable_duration(self.document, s.id, cs_val)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._close_dialog(dialog)
                self._refresh_ui()
                self._show_snack(f"Длительность установлена: {cs_val*10}мс")
            except Exception as ex:
                self._show_snack(f"Ошибка изменения длительности: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text(f"Точный тайминг: {s.id}", color=pal.fg, size=ds.font_size(15), weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text(f"Текущее: {format_ass_time(s.start)} - {format_ass_time(s.end)} ({dur_ms}мс)", size=12, color=pal.muted),
                    dur_input,
                    nudge_row,
                    ft.Divider(height=1, color=pal.border),
                    ft.Text(f"Курсор аудиоплеера: {self.audio_timeline.center_time:.3f}с", size=11, color=pal.muted),
                    snap_row,
                ],
                tight=True,
                spacing=8,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self._close_dialog(dialog)),
                ft.FilledButton("Применить", on_click=_save),
            ],
        )
        self._open_dialog(dialog)

    def _open_full_text_dialog(self):
        """PC Parity: Open Full Script / Lyrics overview dialog with line jumping."""
        if not self.document:
            self._show_snack("Загрузите субтитры для просмотра текста")
            return

        pal = get_current_palette()
        ds = get_display_settings()
        events = [e for e in self.document.events() if e.kind == "Dialogue"]

        lines_controls = []
        for ev in events:
            # Extract plain text
            clean_text = re.sub(r"\{[^}]*\}", "", ev.text).strip()
            time_str = f"{format_ass_time(ev.start)} - {format_ass_time(ev.end)}"

            def _jump_to_line(e, line_idx=ev.line_index):
                syls = [s for s in self.document.karaoke_syllables() if s.event_line_index == line_idx]
                if syls:
                    self.selected_syllable_ids = [s.id for s in syls]
                    self._refresh_ui()
                self._close_dialog(dialog)

            lines_controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"#{ev.line_index}", size=10, weight=ft.FontWeight.BOLD, color=pal.accent),
                            ft.Text(time_str, size=10, color=pal.muted),
                            ft.Text(clean_text or "...", size=12, color=pal.fg, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.IconButton(icon=ft.Icons.ARROW_FORWARD, icon_size=16, icon_color=pal.accent, tooltip="Перейти к строке", on_click=_jump_to_line),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=pal.raised,
                    padding=ft.Padding(8, 4, 8, 4),
                    border_radius=6,
                    border=ft.Border.all(1, pal.border),
                )
            )

        dialog = ft.AlertDialog(
            title=ft.Text("Текст песни (Диалоги)", color=pal.fg, size=ds.font_size(15), weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.ListView(lines_controls, spacing=4, expand=True),
                width=500,
                height=380,
            ),
            actions=[
                ft.FilledButton("Закрыть", on_click=lambda e: self._close_dialog(dialog)),
            ],
        )
        self._open_dialog(dialog)

    def _on_ass_picked(self, result: ft.FilePickerResultEvent):
        if not result.files:
            return
        picked = result.files[0]
        data = getattr(picked, "bytes", None)
        path = getattr(picked, "path", None)

        ass_text = ""
        if data:
            try:
                ass_text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    ass_text = data.decode("cp1251")
                except UnicodeDecodeError:
                    ass_text = data.decode("latin-1", errors="replace")
        elif path:
            try:
                with open(path, "r", encoding="utf-8-sig") as fp:
                    ass_text = fp.read()
            except Exception:
                try:
                    with open(path, "r", encoding="cp1251") as fp:
                        ass_text = fp.read()
                except Exception as ex:
                    self._show_snack(f"Не удалось прочитать файл: {ex}", is_error=True)
                    return

        if ass_text:
            self.load_ass_text(ass_text)
            self._show_snack(f"Загружен: {picked.name}")
