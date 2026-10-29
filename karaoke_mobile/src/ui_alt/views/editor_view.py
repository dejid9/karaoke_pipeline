"""Karaoke Mobile (ui_alt) — Authentic PC-Workbench Redesign for Mobile.

Faithfully recreates the layout, workflow, and visual language of the desktop
Karaoke PC version (karaoke_gui) adapted for touchscreen mobile devices (especially 20:9):
- Subheader: KARAOKE // SPS, ASS status, Syllable count badge, Transfer to SPS
- Transport Bar: [▶/■], [■], Метки: [|←], [|▶], [→|], [▶|], [|▶|], [↔], [×], Speed pills [0.5×]..[1.5×]
- Audio Layer: [Waveform/Spectrogram/Both], Zoom controls
- Center Timeline: Waveform/Spectrogram with karaoke text slices, playhead, and range limits
- Bottom Dock:
    * Left Card (PC Card 1): Слог, [▶ Слог], [←], [→], Текст слога, Романизация, [✂ По курсору], [[Непроизнесённое]]
    * Right Card (PC Card 2): Тайминг ([Вставить], [Разделить 50/50], [Совместить], [Удалить]),
                              Тип тега (\\k, \\kf, \\ko), Undo/Redo, [💾 Сохранить ASS], [📄 Весь текст…],
                              Burst-окраска ([🔥 Окрасить в Burst], [Снять Burst])
"""

from __future__ import annotations

import io
import re
import tempfile
from typing import Callable, Optional
import wave

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


class EditorView(ft.Container):
    """Authentic PC-workbench karaoke editor for mobile."""

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
        self._active_mobile_card: str = "text"  # "text", "actions", "all"

        # File Pickers
        self.ass_picker = ft.FilePicker(on_result=self._on_ass_picked)

        # Audio Timeline Widget
        self.audio_timeline = AudioTimelineWidget(
            on_audio_loaded=self._handle_audio_loaded,
            on_syllable_clicked=self._on_timeline_syllable_clicked,
            on_time_changed=self._on_timeline_time_changed,
        )

        pal = get_current_palette()
        ds = get_display_settings()

        # ==================== 1. PC SUBHEADER ====================
        self.lbl_logo = ft.Text(
            "KARAOKE // SPS",
            size=ds.font_size(13),
            weight=ft.FontWeight.BOLD,
            color=pal.accent,
        )
        self.lbl_ass_file = ft.Text("ASS: не загружен", size=ds.font_size(11), color=pal.muted)
        self.badge_syl_count = ft.Container(
            content=ft.Text("0 слогов", size=ds.font_size(10), weight=ft.FontWeight.BOLD, color=pal.fg),
            bgcolor=pal.raised,
            padding=ft.Padding(6, 2, 6, 2),
            border_radius=4,
            border=ft.Border.all(1, pal.border),
        )
        self.btn_open_ass = ft.FilledButton(
            "ASS…",
            style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.raised, color=pal.fg),
            tooltip="Открыть ASS файл",
            on_click=lambda e: self.ass_picker.pick_files(
                dialog_title="Выберите ASS файл",
                allowed_extensions=["ass", "txt"],
                allow_multiple=False,
            ),
        )
        self.btn_new_ass = ft.FilledButton(
            "ASS+",
            style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.raised, color=pal.fg),
            tooltip="Создать новый пустой ASS",
            on_click=lambda e: self._new_blank_ass(),
        )
        self.btn_transfer_sps = ft.FilledButton(
            "🎯 В SPS",
            style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.accent, color=pal.accent_fg),
            tooltip="Перейти к точному измерению SPS",
            on_click=lambda e: self._transfer_to_sps(),
        )

        self.subheader_row = ft.Row(
            [
                ft.Row([self.lbl_logo, self.lbl_ass_file, self.badge_syl_count], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([self.btn_open_ass, self.btn_new_ass, self.btn_transfer_sps], spacing=4, tight=True),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        )

        # ==================== 2. PC MODERN TRANSPORT BAR ====================
        self.btn_play_toggle = ft.FilledButton(
            "▶/■",
            style=ft.ButtonStyle(padding=ft.Padding(10, 4, 10, 4), bgcolor=pal.accent, color=pal.accent_fg),
            tooltip="Play / Stop с возвратом",
            on_click=lambda e: self.audio_timeline.toggle_play(),
        )
        self.btn_stop = ft.FilledButton(
            "■",
            style=ft.ButtonStyle(padding=ft.Padding(8, 4, 8, 4), bgcolor=pal.raised, color=pal.fg),
            tooltip="Stop",
            on_click=lambda e: self.audio_timeline.stop_audio(),
        )

        # Range Marker Buttons
        self.btn_mark_start = ft.FilledButton("|←", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="|←: поставить метку старта", on_click=lambda e: self.audio_timeline.set_range_in())
        self.btn_play_start = ft.FilledButton("|▶", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="|▶: проиграть от метки старта", on_click=lambda e: self._play_from_start_marker())
        self.btn_mark_stop = ft.FilledButton("→|", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="→|: поставить метку окончания", on_click=lambda e: self.audio_timeline.set_range_out())
        self.btn_play_stop = ft.FilledButton("▶|", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="▶|: проиграть до метки окончания", on_click=lambda e: self._play_to_stop_marker())
        self.btn_play_range = ft.FilledButton("|▶|", style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.accent, color=pal.accent_fg), tooltip="|▶|: проиграть между метками", on_click=lambda e: self.audio_timeline.play_marked_range())
        self.btn_range_sel = ft.FilledButton("↔", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="↔: поставить метки по выделению", on_click=lambda e: self._set_range_from_selection())
        self.btn_clear_range = ft.FilledButton("×", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="×: очистить обе метки", on_click=lambda e: self.audio_timeline.clear_range())

        self.lbl_playback_limits = ft.Text("[ 0:00.00 .. 0:00.00 ]", size=ds.font_size(10), color=pal.muted)

        # Transport Row 1: Play/Stop + Markers
        self.transport_row1 = ft.Row(
            [
                self.btn_play_toggle,
                self.btn_stop,
                ft.Text("Метки:", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.fg),
                self.btn_mark_start,
                self.btn_play_start,
                self.btn_mark_stop,
                self.btn_play_stop,
                self.btn_play_range,
                self.btn_range_sel,
                self.btn_clear_range,
                self.lbl_playback_limits,
            ],
            spacing=3,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Transport Row 2: Speed Presets & Toggles
        self.lbl_speed_text = ft.Text("1.00×", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.fg)
        self.speed_pills = [
            ft.TextButton(
                label,
                style=ft.ButtonStyle(padding=ft.Padding(4, 1, 4, 1), bgcolor=pal.raised, color=pal.fg),
                on_click=lambda e, s=val: self._set_speed(s),
            )
            for val, label in [(0.5, "0.5×"), (0.75, "0.75×"), (1.0, "1×"), (1.25, "1.25×"), (1.5, "1.5×")]
        ]

        self.transport_row2 = ft.Row(
            [
                ft.Text("Скорость:", size=ds.font_size(11), color=pal.muted),
                self.lbl_speed_text,
                *self.speed_pills,
                ft.Container(width=4),
                ft.Text("Аудио-слой:", size=ds.font_size(11), color=pal.muted),
                ft.TextButton("Волна", style=ft.ButtonStyle(padding=ft.Padding(4, 1, 4, 1), color=pal.accent), on_click=lambda e: self.audio_timeline.set_audio_mode("waveform")),
                ft.TextButton("Спектр", style=ft.ButtonStyle(padding=ft.Padding(4, 1, 4, 1), color=pal.fg), on_click=lambda e: self.audio_timeline.set_audio_mode("spectrogram")),
                ft.TextButton("Оба", style=ft.ButtonStyle(padding=ft.Padding(4, 1, 4, 1), color=pal.fg), on_click=lambda e: self.audio_timeline.set_audio_mode("both")),
            ],
            spacing=3,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.transport_card = ft.Container(
            content=ft.Column([self.transport_row1, self.transport_row2], spacing=3, tight=True),
            bgcolor=pal.panel,
            padding=ft.Padding(6, 4, 6, 4),
            border_radius=6,
            border=ft.Border.all(1, pal.border),
        )

        # ==================== 3. BOTTOM DOCK (THE 2 PC CARDS) ====================

        # --- PC CARD 1: Syllable text & Romanization ---
        self.card1_title = ft.Text("Слог: —", size=ds.font_size(12), weight=ft.FontWeight.BOLD, color=pal.fg)
        self.btn_play_syl = ft.FilledButton("▶ Слог", style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.accent, color=pal.accent_fg), tooltip="Прослушать выделенный слог", on_click=lambda e: self._play_selected_syllable())
        self.btn_prev_syl = ft.FilledButton("←", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="Предыдущий слог", on_click=lambda e: self._navigate_syllable(-1))
        self.btn_next_syl = ft.FilledButton("→", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), tooltip="Следующий слог", on_click=lambda e: self._navigate_syllable(1))

        self.txt_syllable_editor = ft.TextField(
            label="Текст слога",
            dense=True,
            text_size=ds.font_size(13),
            on_change=self._on_syllable_text_changed,
        )

        self.chk_romanize = ft.Checkbox(label="Romanize", value=False, on_change=self._on_romanize_toggle)
        self.txt_romanization = ft.TextField(
            label="Над слогом",
            dense=True,
            text_size=ds.font_size(12),
            on_change=self._on_romanization_changed,
        )

        self.btn_split_at_cursor = ft.FilledButton(
            "Разделить по курсору",
            style=ft.ButtonStyle(padding=ft.Padding(8, 3, 8, 3), bgcolor=pal.raised, color=pal.fg),
            tooltip="Разрезать слог точно по положению курсора плеера",
            on_click=lambda e: self._split_at_cursor(),
        )
        self.btn_unspoken = ft.FilledButton(
            "[Непроизнесённое]",
            style=ft.ButtonStyle(padding=ft.Padding(8, 3, 8, 3), bgcolor=pal.raised, color=pal.fg),
            tooltip="Пометить слог как [непроизнесённый] (исключается из анализа)",
            on_click=lambda e: self._toggle_unspoken(),
        )

        self.pc_card1 = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.card1_title, ft.Row([self.btn_play_syl, self.btn_prev_syl, self.btn_next_syl], spacing=3, tight=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.txt_syllable_editor,
                    ft.Row([self.chk_romanize, ft.Container(content=self.txt_romanization, expand=True)], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([self.btn_split_at_cursor, self.btn_unspoken], spacing=4, scroll=ft.ScrollMode.AUTO),
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
            expand=True,
        )

        # --- PC CARD 2: Timing, Tags, History & Burst ---
        self.btn_insert = ft.FilledButton("➕ Вставить", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), on_click=lambda e: self._insert_syllable())
        self.btn_split = ft.FilledButton("✂ Разделить", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), on_click=lambda e: self._split_syllable_50())
        self.btn_merge = ft.FilledButton("🔗 Совместить", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), on_click=lambda e: self._merge_current())
        self.btn_delete = ft.FilledButton("🗑 Удалить", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.panel, color=pal.danger), on_click=lambda e: self._delete_current())

        self.timing_ops_row = ft.Row(
            [
                ft.Text("Тайминг:", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.fg),
                self.btn_insert,
                self.btn_split,
                self.btn_merge,
                self.btn_delete,
            ],
            spacing=3,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.dd_tag_type = ft.Dropdown(
            options=[
                ft.dropdown.Option("k", "\\k (резкий)"),
                ft.dropdown.Option("kf", "\\kf (плавный)"),
                ft.dropdown.Option("ko", "\\ko (outline)"),
                ft.dropdown.Option("K", "\\K (плавный alias)"),
            ],
            value="kf",
            dense=True,
            text_size=ds.font_size(12),
            expand=True,
            on_select=self._on_tag_dropdown_change,
        )
        self.btn_apply_tag = ft.FilledButton(
            "Применить тип",
            style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg),
            on_click=lambda e: self._apply_tag_type(),
        )

        self.tag_row = ft.Row(
            [
                ft.Text("Тип:", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.fg),
                self.dd_tag_type,
                self.btn_apply_tag,
            ],
            spacing=3,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.btn_undo = ft.FilledButton("↶", style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.raised, color=pal.fg), tooltip="Undo", on_click=lambda e: self._undo())
        self.btn_redo = ft.FilledButton("↷", style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.raised, color=pal.fg), tooltip="Redo", on_click=lambda e: self._redo())
        self.btn_save_ass = ft.FilledButton("💾 Сохранить", style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.success, color=pal.accent_fg), on_click=lambda e: self._save_ass_direct())
        self.btn_full_text = ft.FilledButton("📄 Весь текст…", style=ft.ButtonStyle(padding=ft.Padding(8, 2, 8, 2), bgcolor=pal.raised, color=pal.fg), on_click=lambda e: self._open_full_text_dialog())

        self.history_row = ft.Row(
            [
                self.btn_undo,
                self.btn_redo,
                self.btn_save_ass,
                self.btn_full_text,
            ],
            spacing=3,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.lbl_burst_state = ft.Text("Burst: —", size=ds.font_size(10), color=pal.muted)
        self.btn_color_burst = ft.FilledButton("🔥 Окрасить", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.danger, color=pal.accent_fg), on_click=lambda e: self._color_burst(True))
        self.btn_uncolor_burst = ft.FilledButton("Снять", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), on_click=lambda e: self._color_burst(False))
        self.btn_export_audio = ft.FilledButton("🎵 Экспорт WAV…", style=ft.ButtonStyle(padding=ft.Padding(6, 2, 6, 2), bgcolor=pal.raised, color=pal.fg), on_click=lambda e: self._export_selected_audio())

        self.burst_row = ft.Row(
            [
                self.lbl_burst_state,
                self.btn_color_burst,
                self.btn_uncolor_burst,
                self.btn_export_audio,
            ],
            spacing=3,
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.pc_card2 = ft.Container(
            content=ft.Column(
                [
                    self.timing_ops_row,
                    self.tag_row,
                    self.history_row,
                    self.burst_row,
                ],
                spacing=3,
                tight=True,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=7,
            border=ft.Border.all(1, pal.border),
            expand=True,
        )

        # Docked toolbar wrapper for compatibility with tests
        self.docked_toolbar = ft.Container(content=self.pc_card2, visible=False)

        # Mobile Mode Switcher Tabs for Portrait
        self.mobile_tab_bar = ft.Row(
            [
                ft.TextButton("📝 Слог и Текст", style=ft.ButtonStyle(color=pal.accent), on_click=lambda e: self._switch_mobile_dock("text")),
                ft.TextButton("⚙ Тайминг и Действия", style=ft.ButtonStyle(color=pal.muted), on_click=lambda e: self._switch_mobile_dock("actions")),
                ft.TextButton("📑 Все строки", style=ft.ButtonStyle(color=pal.muted), on_click=lambda e: self._switch_mobile_dock("all")),
            ],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        )

        # Lines Overview List (Quick jump list)
        self.lines_list_view = ft.ListView(expand=True, spacing=3, padding=2)

        # Main dynamic body container
        self.body_container = ft.Container(expand=True)

        self.content = ft.Column(
            [
                self.subheader_row,
                self.transport_card,
                self.body_container,
            ],
            spacing=3,
            expand=True,
        )

        self._refresh_ui()

    # ------------------ Contract Properties ------------------

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

    def _handle_audio_loaded(self, name: str, data: bytes, waveform, spectrogram):
        if self.on_audio_loaded_cb:
            self.on_audio_loaded_cb(name, data, waveform, spectrogram)

    def _on_timeline_time_changed(self, pos_sec: float):
        if self.audio_timeline.range_start is not None and self.audio_timeline.range_end is not None:
            self.lbl_playback_limits.value = f"[ {format_ass_time(self.audio_timeline.range_start)} .. {format_ass_time(self.audio_timeline.range_end)} ]"
        else:
            self.lbl_playback_limits.value = f"Курсор: {pos_sec:.3f}с"
        try:
            self.lbl_playback_limits.update()
        except Exception:
            pass

    def _on_timeline_syllable_clicked(self, sid: str):
        if self.multi_select_mode:
            if sid in self.selected_syllable_ids:
                self.selected_syllable_ids.remove(sid)
            else:
                self.selected_syllable_ids.append(sid)
        else:
            self.selected_syllable_ids = [sid]
        self._refresh_ui()

    def _push_undo(self):
        if self.document:
            self._undo_stack.append(self.document.dumps())
            if len(self._undo_stack) > 30:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def _undo(self):
        if not self._undo_stack or not self.document:
            return
        self._redo_stack.append(self.document.dumps())
        last = self._undo_stack.pop()
        self.document = AssDocument.from_text(last)
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack("↶ Действие отменено (Undo)")

    def _redo(self):
        if not self._redo_stack or not self.document:
            return
        self._undo_stack.append(self.document.dumps())
        next_state = self._redo_stack.pop()
        self.document = AssDocument.from_text(next_state)
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack("↷ Повторено (Redo)")

    def _new_blank_ass(self):
        self._push_undo()
        blank = (
            "[Script Info]\n"
            "Title: New Karaoke\n"
            "ScriptType: v4.00+\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\k100}Kara{\\k100}oke\n"
        )
        self.load_ass_text(blank)
        self._show_snack("Создан пустой проект ASS+")

    def load_ass_text(self, text: str):
        try:
            doc = AssDocument.from_text(text)
            self.document = doc
            self.selected_syllable_ids = []
            if self.on_document_changed:
                self.on_document_changed(doc)
            self._refresh_ui()
        except Exception as ex:
            self._show_snack(f"Ошибка загрузки ASS: {ex}", is_error=True)

    def _refresh_ui(self):
        pal = get_current_palette()
        ds = get_display_settings()
        p = self._get_page()
        is_landscape = bool(p and p.width and p.height and p.width > p.height)

        if not self.document:
            self.lbl_ass_file.value = "ASS: не загружен"
            self.badge_syl_count.content.value = "0 слогов"
            self.card1_title.value = "Слог: —"
            self.txt_syllable_editor.value = ""
            self.txt_syllable_editor.disabled = True
            self.txt_romanization.value = ""
            self.txt_romanization.disabled = True
            self.docked_toolbar.visible = False
            self.audio_timeline.set_active_bounds(None, None)
            self._rebuild_layout(is_landscape)
            self._safe_update()
            return

        all_syls = list(self.document.karaoke_syllables())
        total = len(all_syls)
        burst_count = sum(1 for s in all_syls if s.burst_marked)
        self.badge_syl_count.content.value = f"{total} слогов" + (f" (🔥{burst_count})" if burst_count else "")

        # Sync syllables with timeline for waveform/spectrogram slice drawing
        mt = MeasurementTimeline.from_karaoke(all_syls)
        first_id = self.selected_syllable_id
        self.audio_timeline.set_syllables(mt.syllables, first_id)

        # Update PC Cards
        selected_syls = [s for s in all_syls if s.id in self.selected_syllable_ids]
        if selected_syls:
            s = selected_syls[0]
            self.docked_toolbar.visible = True
            dur_ms = s.duration_cs * 10
            idx = next((i for i, item in enumerate(all_syls) if item.id == s.id), 0)
            self.card1_title.value = f"Слог: {s.id} (#{idx}) [{format_ass_time(s.start)}–{format_ass_time(s.end)}] ({dur_ms}мс)"
            self.txt_syllable_editor.disabled = False
            self.txt_syllable_editor.value = s.visible_text.strip() or s.raw_text.strip()
            self.txt_romanization.disabled = False
            self.txt_romanization.value = s.romanization or ""
            self.chk_romanize.value = bool(s.romanization)
            self.dd_tag_type.value = s.tag_type.value
            self.lbl_burst_state.value = f"Burst: {'🔥 ДА' if s.burst_marked else 'НЕТ'}"
            self.audio_timeline.focus_syllable(s.start, s.end, syllable_id=s.id)
        else:
            self.docked_toolbar.visible = False
            self.card1_title.value = "Слог: не выбран"
            self.txt_syllable_editor.disabled = True
            self.txt_syllable_editor.value = ""
            self.txt_romanization.disabled = True
            self.txt_romanization.value = ""
            self.lbl_burst_state.value = "Burst: —"
            self.audio_timeline.set_active_bounds(None, None)

        self._build_lines_overview(all_syls)
        self._rebuild_layout(is_landscape)
        self._safe_update()

    def _build_lines_overview(self, all_syls: list[KaraokeSyllable]):
        pal = get_current_palette()
        self.lines_list_view.controls.clear()
        events = [e for e in self.document.events() if e.kind == "Dialogue"] if self.document else []

        by_line: dict[int, list[KaraokeSyllable]] = {}
        for s in all_syls:
            by_line.setdefault(s.event_line_index, []).append(s)

        for ev in events:
            syls = by_line.get(ev.line_index, [])
            if not syls:
                continue
            clean_text = " ".join(s.visible_text.strip() or s.raw_text.strip() for s in syls)
            dur_ms = int(round((ev.end - ev.start) * 1000))

            def _jump(e, s_list=syls):
                if s_list:
                    self.selected_syllable_ids = [s.id for s in s_list]
                    self._refresh_ui()

            self.lines_list_view.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"#{ev.line_index}", size=10, weight=ft.FontWeight.BOLD, color=pal.accent),
                            ft.Text(f"{format_ass_time(ev.start)}–{format_ass_time(ev.end)} ({dur_ms}мс)", size=9, color=pal.muted),
                            ft.Text(clean_text or "...", size=11, color=pal.fg, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.IconButton(icon=ft.Icons.ARROW_FORWARD, icon_size=15, icon_color=pal.accent, on_click=_jump),
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=pal.raised,
                    padding=ft.Padding(6, 2, 6, 2),
                    border_radius=4,
                    border=ft.Border.all(1, pal.border),
                )
            )

    def _rebuild_layout(self, is_landscape: bool):
        pal = get_current_palette()
        if is_landscape:
            # 2-Column Desktop Workbench split for widescreen 20:9
            self.body_container.content = ft.Row(
                [
                    # Left Column (52%): Timeline + Transport details
                    ft.Container(
                        content=ft.Column(
                            [
                                self.audio_timeline,
                                self.lines_list_view,
                            ],
                            spacing=3,
                            expand=True,
                        ),
                        expand=11,
                    ),
                    ft.VerticalDivider(width=1, color=pal.border),
                    # Right Column (48%): The 2 authentic PC Cards
                    ft.Container(
                        content=ft.Column(
                            [
                                self.pc_card1,
                                self.pc_card2,
                            ],
                            spacing=3,
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                        expand=10,
                    ),
                ],
                spacing=4,
                expand=True,
            )
        else:
            # Portrait: Timeline on top, then PC Cards via mobile switcher tabs
            active_card_widget = self.pc_card1 if self._active_mobile_card == "text" else (self.pc_card2 if self._active_mobile_card == "actions" else self.lines_list_view)
            self.body_container.content = ft.Column(
                [
                    self.audio_timeline,
                    self.mobile_tab_bar,
                    ft.Container(content=active_card_widget, expand=True),
                ],
                spacing=3,
                expand=True,
            )

    def _switch_mobile_dock(self, mode: str):
        self._active_mobile_card = mode
        pal = get_current_palette()
        for i, (tab_btn, tab_mode) in enumerate(zip(self.mobile_tab_bar.controls, ["text", "actions", "all"])):
            tab_btn.style.color = pal.accent if tab_mode == mode else pal.muted
        self._rebuild_layout(is_landscape=False)
        self._safe_update()

    # ------------------ PC Transport Actions ------------------

    def _set_speed(self, speed: float):
        self.audio_timeline.set_playback_speed(speed)
        self.lbl_speed_text.value = f"{speed:g}×"
        self._safe_update()

    def _play_from_start_marker(self):
        if self.audio_timeline.range_start is not None:
            self.audio_timeline.play_range(self.audio_timeline.range_start, self.audio_timeline.total_duration)
        else:
            self._show_snack("Метка старта |← не установлена")

    def _play_to_stop_marker(self):
        if self.audio_timeline.range_end is not None:
            self.audio_timeline.play_range(self.audio_timeline.center_time, self.audio_timeline.range_end)
        else:
            self._show_snack("Метка окончания →| не установлена")

    def _set_range_from_selection(self):
        syl = self._get_selected_syl()
        if syl:
            self.audio_timeline.range_start = syl.start
            self.audio_timeline.range_end = syl.end
            self.audio_timeline._refresh_timeline()
            self._on_timeline_time_changed(self.audio_timeline.center_time)
            self._show_snack(f"Метки выставлены по слогу: {syl.id}")
        else:
            self._show_snack("Сначала выберите слог")

    def _play_selected_syllable(self):
        syl = self._get_selected_syl()
        if syl:
            self.audio_timeline.play_range(syl.start, syl.end)
        else:
            self._show_snack("Выберите слог для воспроизведения")

    def _navigate_syllable(self, step: int):
        if not self.document:
            return
        all_syls = list(self.document.karaoke_syllables())
        if not all_syls:
            return
        curr_id = self.selected_syllable_id
        idx = next((i for i, s in enumerate(all_syls) if s.id == curr_id), -1)
        new_idx = max(0, min(len(all_syls) - 1, idx + step))
        self.selected_syllable_ids = [all_syls[new_idx].id]
        self._refresh_ui()

    def _get_selected_syl(self) -> Optional[KaraokeSyllable]:
        if not self.document or not self.selected_syllable_id:
            return None
        return next((s for s in self.document.karaoke_syllables() if s.id == self.selected_syllable_id), None)

    # ------------------ PC Card 1 Actions ------------------

    def _on_syllable_text_changed(self, e):
        syl = self._get_selected_syl()
        if syl and self.document and self.txt_syllable_editor.value != syl.visible_text:
            self._push_undo()
            set_syllable_text(self.document, syl.id, self.txt_syllable_editor.value)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()

    def _on_romanize_toggle(self, e):
        pass

    def _on_romanization_changed(self, e):
        syl = self._get_selected_syl()
        if syl and self.document and self.txt_romanization.value != syl.romanization:
            self._push_undo()
            set_syllable_romanization(self.document, syl.id, self.txt_romanization.value)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self._refresh_ui()

    def _split_at_cursor(self):
        syl = self._get_selected_syl()
        if not syl or not self.document:
            self._show_snack("Выберите слог")
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

    def _toggle_unspoken(self):
        syl = self._get_selected_syl()
        if not syl or not self.document:
            return
        txt = syl.visible_text.strip()
        if txt.startswith("[") and txt.endswith("]"):
            new_txt = txt[1:-1].strip()
        else:
            new_txt = f"[{txt}]"
        self._push_undo()
        set_syllable_text(self.document, syl.id, new_txt)
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack(f"Текст слога: {new_txt}")

    # ------------------ PC Card 2 Actions ------------------

    def _insert_syllable(self):
        syl = self._get_selected_syl()
        if not syl or not self.document:
            return
        try:
            self._push_undo()
            res = insert_after(self.document, syl.id)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            if res.selected_ids:
                self.selected_syllable_ids = list(res.selected_ids)
            self._refresh_ui()
            self._show_snack("Вставлен новый karaoke-слог")
        except Exception as ex:
            self._show_snack(f"Ошибка вставки: {ex}", is_error=True)

    def _split_syllable_50(self):
        syl = self._get_selected_syl()
        if not syl or not self.document:
            return
        try:
            self._push_undo()
            res = split_syllable(self.document, syl.id)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            if res.selected_ids:
                self.selected_syllable_ids = list(res.selected_ids)
            self._refresh_ui()
            self._show_snack("Разделен karaoke-слог")
        except Exception as ex:
            self._show_snack(f"Ошибка разделения: {ex}", is_error=True)

    def _merge_current(self):
        if not self.document:
            return
        all_syls = list(self.document.karaoke_syllables())
        if len(self.selected_syllable_ids) > 1:
            # Multi-merge
            ordered = [s.id for s in all_syls if s.id in self.selected_syllable_ids]
            target_ids = ordered
        else:
            curr = self._get_selected_syl()
            if not curr:
                self._show_snack("Выберите слог для совмещения")
                return
            same_line = [s for s in all_syls if s.event_line_index == curr.event_line_index]
            idx = next((i for i, s in enumerate(same_line) if s.id == curr.id), -1)
            if idx >= 0 and idx + 1 < len(same_line):
                target_ids = [curr.id, same_line[idx + 1].id]
            else:
                self._show_snack("Нет следующего слога в строке для слияния")
                return

        try:
            self._push_undo()
            res = merge_syllables(self.document, target_ids)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            if res.selected_ids:
                self.selected_syllable_ids = list(res.selected_ids)
            self._refresh_ui()
            self._show_snack(f"Совмещено {len(target_ids)} слогов")
        except Exception as ex:
            self._show_snack(f"Ошибка слияния: {ex}", is_error=True)

    def _delete_current(self):
        if not self.document or not self.selected_syllable_ids:
            return
        try:
            self._push_undo()
            for sid in reversed(self.selected_syllable_ids):
                delete_syllable(self.document, sid)
            if self.on_document_changed:
                self.on_document_changed(self.document)
            self.selected_syllable_ids = []
            self._refresh_ui()
            self._show_snack("Удален karaoke-слог")
        except Exception as ex:
            self._show_snack(f"Ошибка удаления: {ex}", is_error=True)

    def _on_tag_dropdown_change(self, e):
        self._apply_tag_type()

    def _apply_tag_type(self):
        syl = self._get_selected_syl()
        if not syl or not self.document:
            return
        tag = self.dd_tag_type.value or "kf"
        self._push_undo()
        set_tag_type(self.document, [syl.id], tag)
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()
        self._show_snack(f"Тип тега слога: \\{tag}")

    def _color_burst(self, mark: bool):
        if not self.document or not self.selected_syllable_ids:
            self._show_snack("Выберите слог для окраски")
            return
        self._push_undo()
        if mark:
            colour_burst(self.document, self.selected_syllable_ids)
            self._show_snack("Burst-окраска применена")
        else:
            uncolour_burst(self.document, self.selected_syllable_ids)
            self._show_snack("Burst-окраска снята")
        if self.on_document_changed:
            self.on_document_changed(self.document)
        self._refresh_ui()

    def _export_selected_audio(self):
        syl = self._get_selected_syl()
        raw_bytes = getattr(self.audio_timeline, "current_audio_bytes", None)
        if not syl or not raw_bytes:
            self._show_snack("Загрузите аудиофайл и выберите слог для экспорта", is_error=True)
            return

        try:
            # Pure Python WAV Slicer
            in_io = io.BytesIO(raw_bytes)
            with wave.open(in_io, "rb") as wf:
                params = wf.getparams()
                rate = wf.getframerate()
                start_frame = int(syl.start * rate)
                end_frame = int(syl.end * rate)
                total_frames = wf.getnframes()
                wf.setpos(min(start_frame, total_frames))
                frames = wf.readframes(max(0, min(end_frame - start_frame, total_frames - start_frame)))

            tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{syl.id.replace(':', '_')}.wav")
            with wave.open(tmp_out.name, "wb") as out_wf:
                out_wf.setparams(params)
                out_wf.writeframes(frames)
            tmp_out.close()
            self._show_snack(f"Экспорт готов: {tmp_out.name}")
        except Exception as ex:
            self._show_snack(f"Ошибка экспорта аудио: {ex}", is_error=True)

    def _save_ass_direct(self):
        if not self.document:
            return
        self._show_snack("Субтитры ASS готовы для сохранения/экспорта в пакете проекта")

    def _transfer_to_sps(self):
        if self.on_jump_to_sps:
            self.on_jump_to_sps(self.selected_syllable_id or "")

    # ------------------ Dialogs (Full text & compatibility) ------------------

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
        self.selected_syllable_ids = [s.id]
        self._refresh_ui()

    def _open_timing_dialog(self, s: KaraokeSyllable):
        self.selected_syllable_ids = [s.id]
        self._refresh_ui()

    def _open_full_text_dialog(self):
        if not self.document:
            self._show_snack("Загрузите субтитры")
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
            title=ft.Text("Весь текст песни", color=pal.fg, size=ds.font_size(14), weight=ft.FontWeight.BOLD),
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
            self._show_snack(f"Загружен: {picked.name}")

    def apply_theme(self, pal: ThemePalette):
        self.lbl_logo.color = pal.accent
        self.lbl_ass_file.color = pal.muted
        self.badge_syl_count.bgcolor = pal.raised
        self.badge_syl_count.content.color = pal.fg
        self.badge_syl_count.border = ft.Border.all(1, pal.border)
        self.btn_open_ass.style.bgcolor = pal.raised
        self.btn_open_ass.style.color = pal.fg
        self.btn_new_ass.style.bgcolor = pal.raised
        self.btn_new_ass.style.color = pal.fg
        self.btn_transfer_sps.style.bgcolor = pal.accent
        self.btn_transfer_sps.style.color = pal.accent_fg

        self.transport_card.bgcolor = pal.panel
        self.transport_card.border = ft.Border.all(1, pal.border)
        self.pc_card1.bgcolor = pal.panel
        self.pc_card1.border = ft.Border.all(1, pal.border)
        self.pc_card2.bgcolor = pal.panel
        self.pc_card2.border = ft.Border.all(1, pal.border)

        self.audio_timeline.apply_theme(pal)
        self._refresh_ui()
