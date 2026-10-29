"""Modern Touch-First Karaoke Syllable & Timing Editor for Mobile (ui_alt).

Features:
- Snap to Playhead ('|← Сюда', '→| Сюда', '✂ По курсору')
- Touch Jog Wheel Controller for millisecond precision
- Full 20:9 screen adaptation (No vertical text stretching, adaptive landscape 2-column split)
- Floating multi-selection action bar
- Full lyrics / song text overview dialog
"""

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
from ui.display_settings import get_display_settings
from ui.theme import ThemePalette, get_current_palette
from ui_alt.components.audio_timeline import AudioTimelineWidget
from ui_alt.components.jog_wheel import JogWheelWidget


class EditorView(ft.Container):
    """Flagship touch-first mobile karaoke editor."""

    def __init__(
        self,
        on_document_changed: Optional[Callable[[AssDocument], None]] = None,
        on_jump_to_sps: Optional[Callable[[str], None]] = None,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[object], Optional[object]], None]] = None,
    ):
        super().__init__()
        self.expand = True
        self.padding = 4
        self.on_document_changed = on_document_changed
        self.on_jump_to_sps = on_jump_to_sps
        self.on_audio_loaded_cb = on_audio_loaded

        self.document: Optional[AssDocument] = None
        self._selected_syllable_ids: list[str] = []
        self.multi_select_mode: bool = False
        self._page: Optional[ft.Page] = None
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []
        self.toolbar_mode: str = "dur"

        # File Pickers
        self.ass_picker = ft.FilePicker(on_result=self._on_ass_picked)

        # Audio Timeline Widget
        self.audio_timeline = AudioTimelineWidget(
            on_audio_loaded=self._handle_audio_loaded,
            on_syllable_clicked=self._on_timeline_syllable_clicked,
            on_cursor_moved=self._on_cursor_moved,
        )

        # Touch Jog Wheel Controller
        self.jog_wheel = JogWheelWidget(
            on_nudge=self._on_jog_nudge,
            on_snap_to_cursor=self._on_jog_snap,
            on_split_at_cursor=self._on_jog_split,
        )

        pal = get_current_palette()
        ds = get_display_settings()

        # Top Bar: Single line (prevents 20:9 vertical wrapping bug!)
        self.app_title_text = ft.Text(
            "Караоке",
            size=ds.font_size(14),
            weight=ft.FontWeight.BOLD,
            color=pal.fg,
        )
        self.stats_text = ft.Text("0 сл", size=ds.font_size(11), color=pal.muted)

        self.btn_open_ass = ft.FilledButton(
            "ASS",
            icon=ft.Icons.FILE_OPEN_OUTLINED,
            style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg),
            tooltip="Открыть субтитры ASS",
            on_click=lambda e: self.ass_picker.pick_files(
                dialog_title="Выберите ASS файл",
                allowed_extensions=["ass", "txt"],
                allow_multiple=False,
            ),
        )

        self.btn_lyrics = ft.IconButton(
            icon=ft.Icons.ARTICLE_OUTLINED,
            tooltip="Полный текст песни (все строки)",
            icon_size=ds.icon_size(18),
            icon_color=pal.fg,
            on_click=lambda e: self._open_full_text_dialog(),
        )

        self.btn_undo = ft.IconButton(
            icon=ft.Icons.UNDO,
            tooltip="Отменить (Undo)",
            icon_size=ds.icon_size(18),
            icon_color=pal.muted,
            disabled=True,
            on_click=lambda e: self._undo(),
        )

        self.btn_multi_select = ft.IconButton(
            icon=ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            tooltip="Режим выбора нескольких слогов",
            icon_size=ds.icon_size(18),
            icon_color=pal.muted,
            on_click=lambda e: self._toggle_multi_select(),
        )

        self.top_header = ft.Row(
            [
                ft.Row([self.app_title_text, self.stats_text], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row(
                    [
                        self.btn_undo,
                        self.btn_multi_select,
                        self.btn_lyrics,
                        self.btn_open_ass,
                    ],
                    spacing=2,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Active Syllable Docked Toolbar
        self.docked_toolbar = ft.Container(visible=False)

        # Floating Multi-Selection Action Bar
        self.floating_multi_bar = ft.Container(
            visible=False,
            padding=ft.Padding(8, 4, 8, 4),
            border_radius=8,
            bgcolor=pal.panel,
            border=ft.Border.all(1.5, pal.accent),
        )

        # Syllables List
        self.syllables_list = ft.ListView(
            expand=True,
            spacing=4,
            padding=ft.Padding(2, 2, 2, 2),
        )

        self.empty_placeholder = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.AUDIO_FILE_OUTLINED, size=36, color=pal.muted),
                    ft.Text("Откройте ASS или аудиофайл для начала работы", size=ds.font_size(12), color=pal.muted),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            padding=20,
        )

        # Left / Right Split Containers for 20:9 Landscape
        self.left_column = ft.Column(
            [
                self.audio_timeline,
                self.jog_wheel,
            ],
            spacing=4,
            expand=True,
        )

        self.right_column = ft.Column(
            [
                self.docked_toolbar,
                self.floating_multi_bar,
                self.syllables_list,
            ],
            spacing=4,
            expand=True,
        )

        # Main Layout Container
        self.body_container = ft.Container(expand=True)
        self.content = ft.Column(
            [
                self.top_header,
                self.body_container,
            ],
            spacing=2,
            expand=True,
        )

        self._refresh_ui()

    @property
    def selected_syllable_id(self) -> Optional[str]:
        return self._selected_syllable_ids[0] if self._selected_syllable_ids else None

    @selected_syllable_id.setter
    def selected_syllable_id(self, sid: Optional[str]):
        if sid:
            self._selected_syllable_ids = [sid]
        else:
            self._selected_syllable_ids = []

    @property
    def selected_syllable_ids(self) -> list[str]:
        return list(self._selected_syllable_ids)

    @selected_syllable_ids.setter
    def selected_syllable_ids(self, sids: list[str]):
        self._selected_syllable_ids = list(sids)

    def _get_page(self) -> Optional[ft.Page]:
        if getattr(self, "_page", None):
            return self._page
        try:
            if self.page:
                return self.page
        except Exception:
            pass
        return getattr(self, "_Control__page", None)

    def set_page(self, page: ft.Page):
        self._page = page
        self.audio_timeline.set_page(page)

    def get_services(self) -> list[ft.Service]:
        return [self.ass_picker] + self.audio_timeline.get_services()

    def _safe_update(self):
        try:
            self.update()
        except Exception:
            pass

    def _show_snack(self, message: str, is_error: bool = False):
        p = self._get_page()
        if p:
            pal = get_current_palette()
            sb = ft.SnackBar(
                content=ft.Text(message, color=pal.accent_fg if is_error else pal.fg),
                bgcolor=pal.danger if is_error else pal.panel,
                duration=2500,
            )
            p.snack_bar = sb
            sb.open = True
            p.update()

    def _push_undo(self):
        if self.document:
            self._undo_stack.append(self.document.dumps())
            if len(self._undo_stack) > 30:
                self._undo_stack.pop(0)
            self.btn_undo.disabled = False
            self.btn_undo.icon_color = get_current_palette().accent
            self._safe_update()

    def _undo(self):
        if not self._undo_stack or not self.document:
            return
        last_state = self._undo_stack.pop()
        self.document = AssDocument.from_text(last_state)
        if not self._undo_stack:
            self.btn_undo.disabled = True
            self.btn_undo.icon_color = get_current_palette().muted
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack("Действие отменено (Undo)")

    def _toggle_multi_select(self):
        self.multi_select_mode = not self.multi_select_mode
        pal = get_current_palette()
        self.btn_multi_select.icon = ft.Icons.CHECK_BOX if self.multi_select_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK
        self.btn_multi_select.icon_color = pal.accent if self.multi_select_mode else pal.muted
        if not self.multi_select_mode and len(self.selected_syllable_ids) > 1:
            self.selected_syllable_ids = self.selected_syllable_ids[:1]
        self._refresh_ui()

    def _deselect(self):
        self.selected_syllable_ids = []
        self._refresh_ui()

    def _handle_audio_loaded(self, name: str, data: bytes, waveform, spectrogram):
        if self.on_audio_loaded_cb:
            self.on_audio_loaded_cb(name, data, waveform, spectrogram)

    def _on_cursor_moved(self, pos_sec: float):
        if self.selected_syllable_id and self.document:
            syl = self._find_syllable(self.selected_syllable_id)
            if syl:
                self._update_jog_readout(syl)

    def _find_syllable(self, sid: str) -> Optional[KaraokeSyllable]:
        if not self.document:
            return None
        return next((s for s in self.document.karaoke_syllables() if s.id == sid), None)

    def _update_jog_readout(self, syl: KaraokeSyllable):
        mode = self.jog_wheel.target_mode
        if mode == "start":
            self.jog_wheel.set_value_text(f"Start: {syl.start:.3f}с")
        elif mode == "end":
            self.jog_wheel.set_value_text(f"End: {syl.end:.3f}с")
        else:
            self.jog_wheel.set_value_text(f"Dur: {syl.duration_cs * 10}мс")

    def _on_jog_nudge(self, mode: str, delta_sec: float):
        if not self.document or not self.selected_syllable_id:
            return
        syl = self._find_syllable(self.selected_syllable_id)
        if not syl:
            return

        delta_cs = int(round(delta_sec * 100))
        if delta_cs == 0:
            delta_cs = 1 if delta_sec > 0 else -1

        try:
            self._push_undo()
            if mode == "start":
                new_start = round(syl.start + delta_sec, 3)
                set_syllable_start_at_time(self.document, syl.id, new_start)
            elif mode == "end":
                new_end = round(syl.end + delta_sec, 3)
                set_syllable_end_at_time(self.document, syl.id, new_end)
            else:  # shift
                shift_syllable(self.document, syl.id, delta_cs)

            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()
        except Exception as ex:
            self._show_snack(f"Ошибка тайминга: {ex}", is_error=True)

    def _on_jog_snap(self, boundary: str):
        if not self.document or not self.selected_syllable_id:
            return
        syl = self._find_syllable(self.selected_syllable_id)
        if not syl:
            return
        cursor_t = round(self.audio_timeline.center_time, 3)

        try:
            self._push_undo()
            if boundary == "start":
                set_syllable_start_at_time(self.document, syl.id, cursor_t)
                self._show_snack(f"Начало выставлено по курсору: {cursor_t:.3f}с")
            else:
                set_syllable_end_at_time(self.document, syl.id, cursor_t)
                self._show_snack(f"Конец выставлен по курсору: {cursor_t:.3f}с")

            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()
        except Exception as ex:
            self._show_snack(f"Ошибка привязки: {ex}", is_error=True)

    def _on_jog_split(self):
        if not self.document or not self.selected_syllable_id:
            return
        syl = self._find_syllable(self.selected_syllable_id)
        if not syl:
            return
        cursor_t = round(self.audio_timeline.center_time, 3)
        if not (syl.start < cursor_t < syl.end):
            self._show_snack(f"Курсор ({cursor_t:.3f}с) вне слога ({syl.start:.3f}с..{syl.end:.3f}с)", is_error=True)
            return

        try:
            self._push_undo()
            res = split_syllable_at_time(self.document, syl.id, cursor_t)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            if res.selected_ids:
                self.selected_syllable_ids = list(res.selected_ids)
            self._refresh_ui()
            self._show_snack(f"Слог разделён по курсору ({cursor_t:.3f}с)")
        except Exception as ex:
            self._show_snack(f"Ошибка разделения: {ex}", is_error=True)

    def _on_timeline_syllable_clicked(self, sid: str):
        if self.multi_select_mode:
            if sid in self.selected_syllable_ids:
                self.selected_syllable_ids.remove(sid)
            else:
                self.selected_syllable_ids.append(sid)
        else:
            self.selected_syllable_ids = [sid]
        self._refresh_ui()

    def load_ass_text(self, text: str):
        try:
            doc = AssDocument.from_text(text)
            self.document = doc
            self.selected_syllable_ids = []
            if self.on_document_changed:
                self.on_document_changed(doc)
            self._refresh_ui()
        except Exception as ex:
            self._show_snack(f"Ошибка разбора ASS: {ex}", is_error=True)

    def _refresh_ui(self):
        pal = get_current_palette()
        ds = get_display_settings()
        p = self._get_page()
        is_landscape = bool(p and p.width and p.height and p.width > p.height)

        if not self.document:
            self.syllables_list.controls.clear()
            self.syllables_list.controls.append(self.empty_placeholder)
            self.stats_text.value = "0 сл"
            self.docked_toolbar.visible = False
            self.floating_multi_bar.visible = False
            self.audio_timeline.set_active_bounds(None, None)
            self._rebuild_layout(is_landscape)
            self._safe_update()
            return

        all_syllables = list(self.document.karaoke_syllables())
        total_syls = len(all_syllables)
        burst_syls = sum(1 for s in all_syllables if s.burst_marked)
        self.stats_text.value = f"{total_syls} сл (🔥{burst_syls})"

        # Sync Syllables to Audio Timeline
        mt = MeasurementTimeline.from_karaoke(all_syllables)
        first_sel_id = self.selected_syllable_ids[0] if self.selected_syllable_ids else None
        self.audio_timeline.set_syllables(mt.syllables, first_sel_id)

        # Build Syllable Cards list grouped by dialogue lines
        self.syllables_list.controls.clear()
        events = [e for e in self.document.events() if e.kind == "Dialogue"]
        by_line: dict[int, list[KaraokeSyllable]] = {}
        for s in all_syllables:
            by_line.setdefault(s.event_line_index, []).append(s)

        for ev in events:
            line_syls = by_line.get(ev.line_index, [])
            if not line_syls:
                continue
            self.syllables_list.controls.append(self._build_line_card(ev, line_syls))

        # Update Inspector & Floating Selection Bar
        selected_syls = [s for s in all_syllables if s.id in self.selected_syllable_ids]

        if len(selected_syls) > 1:
            # Case 1: Multi-selection
            self.docked_toolbar.visible = False
            self._update_floating_multi_bar(selected_syls, all_syllables)
            self.floating_multi_bar.visible = True
            min_st = min(s.start for s in selected_syls)
            max_en = max(s.end for s in selected_syls)
            self.audio_timeline.focus_syllable(min_st, max_en, syllable_id=selected_syls[0].id)
        elif len(selected_syls) == 1:
            # Case 2: Single syllable selected
            s = selected_syls[0]
            self.floating_multi_bar.visible = False
            self._update_single_syllable_inspector(s, all_syllables)
            self.docked_toolbar.visible = True
            self.jog_wheel.visible = True
            self._update_jog_readout(s)
            self.audio_timeline.focus_syllable(s.start, s.end, syllable_id=s.id)
        else:
            # Case 3: Nothing selected
            self.docked_toolbar.visible = False
            self.floating_multi_bar.visible = False
            self.jog_wheel.visible = False
            self.audio_timeline.set_active_bounds(None, None)

        self._rebuild_layout(is_landscape)
        self._safe_update()

    def _rebuild_layout(self, is_landscape: bool):
        """Adapt layout dynamically between portrait and 20:9 landscape."""
        if is_landscape:
            # 2-Column Split: Left = Timeline + Jog Wheel, Right = Inspector + Syllables
            self.body_container.content = ft.Row(
                [
                    ft.Container(content=self.left_column, expand=11),
                    ft.VerticalDivider(width=1, color=get_current_palette().border),
                    ft.Container(content=self.right_column, expand=9),
                ],
                spacing=4,
                expand=True,
            )
        else:
            # Vertical Stack: Timeline -> Jog Wheel -> Inspector -> Syllables
            self.body_container.content = ft.Column(
                [
                    self.audio_timeline,
                    self.jog_wheel,
                    self.docked_toolbar,
                    self.floating_multi_bar,
                    self.syllables_list,
                ],
                spacing=2,
                expand=True,
            )

    def _build_line_card(self, ev, syls: list[KaraokeSyllable]) -> ft.Container:
        pal = get_current_palette()
        ds = get_display_settings()
        dur_line_ms = int(round((ev.end - ev.start) * 1000))

        line_header = ft.Row(
            [
                ft.Text(f"#{ev.line_index} | {format_ass_time(ev.start)}–{format_ass_time(ev.end)} ({dur_line_ms}мс)", size=ds.font_size(10), color=pal.muted),
                ft.TextButton(
                    "Строка целиком",
                    style=ft.ButtonStyle(padding=ft.Padding(4, 1, 4, 1), color=pal.accent),
                    on_click=lambda e, s_list=syls: self._select_all_in_line(s_list),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        chips = [self._build_syllable_chip(s) for s in syls]

        return ft.Container(
            content=ft.Column(
                [
                    line_header,
                    ft.Row(chips, wrap=True, spacing=3, run_spacing=3),
                ],
                spacing=2,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(6, 4, 6, 4),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
        )

    def _select_all_in_line(self, syls: list[KaraokeSyllable]):
        self.selected_syllable_ids = [s.id for s in syls]
        self._refresh_ui()

    def _build_syllable_chip(self, s: KaraokeSyllable) -> ft.Container:
        pal = get_current_palette()
        ds = get_display_settings()
        is_selected = s.id in self.selected_syllable_ids
        is_burst = s.burst_marked
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10

        if is_selected:
            bg = pal.raised
            border = ft.Border.all(2, pal.accent)
            fg = pal.accent
        elif is_burst:
            bg = pal.danger
            border = ft.Border.all(1, pal.danger)
            fg = pal.accent_fg
        else:
            bg = pal.raised
            border = ft.Border.all(1, pal.border)
            fg = pal.fg

        def _on_tap(e):
            if self.multi_select_mode:
                if s.id in self.selected_syllable_ids:
                    self.selected_syllable_ids.remove(s.id)
                else:
                    self.selected_syllable_ids.append(s.id)
            else:
                self.selected_syllable_ids = [s.id]
            self._refresh_ui()

        prefix = "✓ " if (is_selected and len(self.selected_syllable_ids) > 1) else ("🔥 " if is_burst else "")

        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(f"{prefix}{text}", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=fg),
                    ft.Text(f"{dur_ms}мс", size=ds.font_size(9), color=fg if (is_selected or is_burst) else pal.muted),
                ],
                spacing=2,
                tight=True,
            ),
            bgcolor=bg,
            border=border,
            padding=ft.Padding(5, 3, 5, 3),
            border_radius=5,
            ink=True,
            on_click=_on_tap,
        )

    def _update_single_syllable_inspector(self, s: KaraokeSyllable, all_syllables: list[KaraokeSyllable]):
        pal = get_current_palette()
        ds = get_display_settings()
        text = s.visible_text.strip() or s.raw_text.strip() or "..."
        dur_ms = s.duration_cs * 10
        idx = next((i for i, item in enumerate(all_syllables) if item.id == s.id), -1)

        def _nav(step: int):
            new_idx = idx + step
            if 0 <= new_idx < len(all_syllables):
                self.selected_syllable_ids = [all_syllables[new_idx].id]
                self._refresh_ui()

        # Action handlers
        def _toggle_burst(e):
            self._push_undo()
            if s.burst_marked:
                uncolour_burst(self.document, [s.id])
            else:
                colour_burst(self.document, [s.id])
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()

        def _split_half(e):
            try:
                self._push_undo()
                res = split_syllable(self.document, s.id)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                if res.selected_ids:
                    self.selected_syllable_ids = list(res.selected_ids)
                self._refresh_ui()
                self._show_snack("Слог разделён 50/50")
            except Exception as ex:
                self._show_snack(f"Ошибка разделения: {ex}", is_error=True)

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

        # Inspector Row 1: Active Syllable Badge & Preview & Navigation
        info_row = ft.Row(
            [
                ft.Row(
                    [
                        ft.Text(f"«{text}»", size=ds.font_size(13), weight=ft.FontWeight.BOLD, color=pal.accent),
                        ft.Text(f"{dur_ms}мс (\\{s.tag_type.value})", size=ds.font_size(10), color=pal.muted),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.PLAY_CIRCLE_FILL,
                            tooltip="Прослушать только этот слог",
                            icon_size=18,
                            icon_color=pal.accent,
                            on_click=lambda e: self.audio_timeline.play_range(s.start, s.end),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            tooltip="Предыдущий слог",
                            icon_size=16,
                            icon_color=pal.fg if idx > 0 else pal.muted,
                            disabled=idx <= 0,
                            on_click=lambda e: _nav(-1),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ARROW_FORWARD,
                            tooltip="Следующий слог",
                            icon_size=16,
                            icon_color=pal.fg if idx < len(all_syllables) - 1 else pal.muted,
                            disabled=idx >= len(all_syllables) - 1,
                            on_click=lambda e: _nav(1),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            tooltip="Снять выделение",
                            icon_size=16,
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

        # Inspector Row 2: Touch Quick Actions
        actions_row = ft.Row(
            [
                ft.FilledButton("✏ Текст", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(6, 2, 6, 2)), on_click=lambda e: self._open_text_dialog(s)),
                ft.FilledButton("⏱ Точный", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(6, 2, 6, 2)), on_click=lambda e: self._open_timing_dialog(s)),
                ft.FilledButton("✂ 50/50", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(6, 2, 6, 2)), on_click=_split_half),
                ft.FilledButton("🔥 Бёрст" if not s.burst_marked else "Снять 🔥", style=ft.ButtonStyle(bgcolor=pal.danger if not s.burst_marked else pal.panel, color=pal.accent_fg if not s.burst_marked else pal.fg, padding=ft.Padding(6, 2, 6, 2)), on_click=_toggle_burst),
                ft.FilledButton("➕ Вставить", style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg, padding=ft.Padding(6, 2, 6, 2)), on_click=_insert),
                ft.FilledButton("🗑", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.danger, padding=ft.Padding(4, 2, 4, 2)), on_click=_delete),
            ],
            spacing=3,
            scroll=ft.ScrollMode.AUTO,
        )

        self.docked_toolbar.content = ft.Container(
            content=ft.Column([info_row, actions_row], spacing=2, tight=True),
            bgcolor=pal.panel,
            padding=ft.Padding(6, 3, 6, 3),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
        )

    def _update_floating_multi_bar(self, selected_syls: list[KaraokeSyllable], all_syllables: list[KaraokeSyllable]):
        pal = get_current_palette()
        ds = get_display_settings()
        total_dur_ms = sum(s.duration_cs * 10 for s in selected_syls)
        first_line = selected_syls[0].event_line_index
        same_line = [item for item in all_syllables if item.event_line_index == first_line]
        ordered_ids = [item.id for item in same_line if item.id in self.selected_syllable_ids]

        def _merge(e):
            if not self.document or len(ordered_ids) < 2:
                self._show_snack("Для слияния нужно минимум 2 слога в одной строке", is_error=True)
                return
            try:
                self._push_undo()
                res = merge_syllables(self.document, ordered_ids)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self.selected_syllable_ids = list(res.selected_ids)
                self._refresh_ui()
                self._show_snack(f"Объединено {len(ordered_ids)} слогов")
            except Exception as ex:
                self._show_snack(f"Ошибка слияния: {ex}", is_error=True)

        def _burst(e):
            if not self.document:
                return
            self._push_undo()
            all_burst = all(s.burst_marked for s in selected_syls)
            if all_burst:
                uncolour_burst(self.document, ordered_ids)
            else:
                colour_burst(self.document, ordered_ids)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()

        def _delete(e):
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

        min_st = min(s.start for s in selected_syls)
        max_en = max(s.end for s in selected_syls)

        row = ft.Row(
            [
                ft.Text(f"Выбрано: {len(selected_syls)} ({total_dur_ms}мс)", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.accent),
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.PLAY_CIRCLE_FILL,
                            tooltip="Проиграть диапазон",
                            icon_size=18,
                            icon_color=pal.accent,
                            on_click=lambda e: self.audio_timeline.play_range(min_st, max_en),
                        ),
                        ft.FilledButton(f"🔗 Слить ({len(ordered_ids)})", style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg, padding=ft.Padding(6, 2, 6, 2)), on_click=_merge),
                        ft.FilledButton("🔥 Бёрст", style=ft.ButtonStyle(bgcolor=pal.danger, color=pal.accent_fg, padding=ft.Padding(6, 2, 6, 2)), on_click=_burst),
                        ft.FilledButton("🗑", style=ft.ButtonStyle(bgcolor=pal.panel, color=pal.danger, padding=ft.Padding(4, 2, 4, 2)), on_click=_delete),
                        ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Снять выбор", icon_size=16, icon_color=pal.muted, on_click=lambda e: self._deselect()),
                    ],
                    spacing=2,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.floating_multi_bar.content = row

    # ------------------ Dialogs (Parity & Test Support) ------------------

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
            label="Тип тега",
            options=[
                ft.dropdown.Option("k", "\\k (резкий)"),
                ft.dropdown.Option("kf", "\\kf (плавный)"),
                ft.dropdown.Option("ko", "\\ko (outline)"),
                ft.dropdown.Option("K", "\\K (плавный alias)"),
            ],
            value=s.tag_type.value,
            text_size=ds.font_size(13),
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
                self._show_snack("Слог обновлён")
            except Exception as ex:
                self._show_snack(f"Ошибка сохранения: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text(f"Редактирование {s.id}", color=pal.fg, size=ds.font_size(14), weight=ft.FontWeight.BOLD),
            content=ft.Column([text_input, rom_input, tag_dropdown], tight=True, spacing=6),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self._close_dialog(dialog)),
                ft.FilledButton("Сохранить", on_click=_save),
            ],
        )
        self._open_dialog(dialog)

    def _open_timing_dialog(self, s: KaraokeSyllable):
        pal = get_current_palette()
        ds = get_display_settings()
        dur_ms = s.duration_cs * 10
        dur_input = ft.TextField(
            label="Длительность (мс)",
            value=str(dur_ms),
            keyboard_type=ft.KeyboardType.NUMBER,
            text_size=ds.font_size(13),
        )

        def _save(e):
            try:
                val = int(dur_input.value or "0")
                if val <= 0:
                    return
                cs_val = max(1, int(round(val / 10.0)))
                self._push_undo()
                set_syllable_duration(self.document, s.id, cs_val)
                if self.on_document_changed:
                    self.on_document_changed(self.document)
                self._close_dialog(dialog)
                self._refresh_ui()
            except Exception as ex:
                self._show_snack(f"Ошибка: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text(f"Тайминг {s.id}", color=pal.fg, size=ds.font_size(14), weight=ft.FontWeight.BOLD),
            content=ft.Column([dur_input], tight=True, spacing=6),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: self._close_dialog(dialog)),
                ft.FilledButton("Применить", on_click=_save),
            ],
        )
        self._open_dialog(dialog)

    def _open_full_text_dialog(self):
        if not self.document:
            self._show_snack("Загрузите субтитры для просмотра текста")
            return
        pal = get_current_palette()
        ds = get_display_settings()
        events = [e for e in self.document.events() if e.kind == "Dialogue"]

        lines = []
        for ev in events:
            clean = re.sub(r"\{[^}]*\}", "", ev.text).strip()

            def _jump(e, l_idx=ev.line_index):
                syls = [s for s in self.document.karaoke_syllables() if s.event_line_index == l_idx]
                if syls:
                    self.selected_syllable_ids = [s.id for s in syls]
                    self._refresh_ui()
                self._close_dialog(dialog)

            lines.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"#{ev.line_index}", size=10, weight=ft.FontWeight.BOLD, color=pal.accent),
                            ft.Text(clean or "...", size=11, color=pal.fg, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.IconButton(icon=ft.Icons.ARROW_FORWARD, icon_size=15, icon_color=pal.accent, on_click=_jump),
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=pal.raised,
                    padding=ft.Padding(6, 3, 6, 3),
                    border_radius=5,
                )
            )

        dialog = ft.AlertDialog(
            title=ft.Text("Текст песни", color=pal.fg, size=ds.font_size(14), weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.ListView(lines, spacing=3, expand=True),
                width=450,
                height=350,
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
            except Exception:
                ass_text = data.decode("latin-1", errors="replace")
        elif path:
            try:
                with open(path, "r", encoding="utf-8-sig") as fp:
                    ass_text = fp.read()
            except Exception:
                with open(path, "r", encoding="latin-1") as fp:
                    ass_text = fp.read()

        if ass_text:
            self.load_ass_text(ass_text)
            self._show_snack(f"Загружен файл: {picked.name}")

    def apply_theme(self, pal: ThemePalette):
        self.app_title_text.color = pal.fg
        self.stats_text.color = pal.muted
        self.btn_open_ass.style.bgcolor = pal.raised
        self.btn_open_ass.style.color = pal.fg
        self.btn_lyrics.icon_color = pal.fg
        self.btn_multi_select.icon_color = pal.accent if self.multi_select_mode else pal.muted
        self.btn_undo.icon_color = pal.accent if not self.btn_undo.disabled else pal.muted

        self.audio_timeline.apply_theme(pal)
        self.jog_wheel.apply_theme(pal)
        self._refresh_ui()
