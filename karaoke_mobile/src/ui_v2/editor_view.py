"""Mobile-first production editor shell.

This view retains the proven ASS editing and audio timeline APIs, but replaces the
old dense list-and-toolbar layout with a single-purpose touch workspace:

* audio and transport always stay visible;
* portrait uses large context tabs below the timeline;
* landscape makes lyrics and the selected-syllable inspector adjacent;
* all mutation handlers remain inherited from the production editor.
"""
from __future__ import annotations

import flet as ft

from ui.views.editor_view import EditorView as _BaseEditorView
from ui.display_settings import get_display_settings
from ui.theme import get_current_palette


class EditorView(_BaseEditorView):
    """A mobile-first shell over the established ASS/audio editing controller."""

    def __init__(self, *args, **kwargs):
        self.workspace_tab = "edit"
        super().__init__(*args, **kwargs)

    def _tab_button(self, label: str, icon, tab: str) -> ft.Container:
        pal = get_current_palette()
        ds = get_display_settings()
        active = self.workspace_tab == tab
        return ft.Container(
            content=ft.Row(
                [ft.Icon(icon, size=ds.icon_size(17), color=pal.accent_fg if active else pal.muted),
                 ft.Text(label, size=ds.font_size(11), weight=ft.FontWeight.BOLD,
                         color=pal.accent_fg if active else pal.fg)],
                tight=True, spacing=5, alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=pal.accent if active else pal.panel,
            border=ft.Border.all(1, pal.accent if active else pal.border),
            border_radius=10, padding=ft.Padding(10, 9, 10, 9),
            expand=True, on_click=lambda e: self._set_workspace_tab(tab),
        )

    def _set_workspace_tab(self, tab: str) -> None:
        self.workspace_tab = tab
        self._build_controls()
        self._refresh_ui()

    def _build_controls(self):
        pal = get_current_palette()
        ds = get_display_settings()
        self.padding = 8
        self.stats_text = ft.Text("0 слогов", size=ds.font_size(11), color=pal.muted)

        self.open_file_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN, tooltip="Открыть ASS", icon_color=pal.accent,
            icon_size=ds.icon_size(21), action=ft.PickFiles(self.ass_picker, with_data=True),
        )
        self.undo_btn = ft.IconButton(ft.Icons.UNDO, tooltip="Отменить", on_click=self.undo,
                                      icon_color=pal.fg, icon_size=ds.icon_size(20))
        self.redo_btn = ft.IconButton(ft.Icons.REDO, tooltip="Повторить", on_click=self.redo,
                                      icon_color=pal.fg, icon_size=ds.icon_size(20))
        self.multi_select_btn = ft.IconButton(
            ft.Icons.CHECK_BOX if self.multi_select_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            tooltip="Несколько слогов", icon_color=pal.accent if self.multi_select_mode else pal.muted,
            icon_size=ds.icon_size(20), on_click=lambda e: self._toggle_multi_select(),
        )
        self.full_text_btn = ft.IconButton(ft.Icons.ARTICLE_OUTLINED, tooltip="Все строки",
                                           icon_color=pal.fg, icon_size=ds.icon_size(20),
                                           on_click=lambda e: self._open_full_text_dialog())
        self.sps_jump_top_btn = ft.IconButton(ft.Icons.SPEED, tooltip="Точный SPS",
                                               icon_color=pal.accent, icon_size=ds.icon_size(20),
                                               on_click=lambda e: self._transfer_to_sps())

        header = ft.Container(
            content=ft.Row([
                ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=pal.accent, size=ds.icon_size(21)),
                        ft.Column([ft.Text("Редактор", weight=ft.FontWeight.BOLD, size=ds.font_size(15), color=pal.fg),
                                   self.stats_text], spacing=0, tight=True)], spacing=7),
                ft.Row([self.undo_btn, self.redo_btn, self.open_file_btn], spacing=0, tight=True),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=pal.panel, padding=ft.Padding(10, 7, 7, 7), border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        self.syllables_list = ft.ListView(expand=True, spacing=7, padding=ft.Padding(2, 2, 2, 10))
        self.empty_placeholder = ft.Container(
            content=ft.Column([ft.Icon(ft.Icons.SUBTITLES_OFF, size=42, color=pal.muted),
                               ft.Text("Откройте ASS для начала работы", color=pal.muted)],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            alignment=ft.Alignment.CENTER, expand=True,
        )
        self.docked_toolbar = ft.Container(visible=False)

        tab_bar = ft.Row([
            self._tab_button("Слог", ft.Icons.EDIT_NOTE, "edit"),
            self._tab_button("Строки", ft.Icons.FORMAT_LIST_BULLETED, "lines"),
            self._tab_button("SPS", ft.Icons.SPEED, "sps"),
        ], spacing=6)
        inspector = ft.Container(self.docked_toolbar, padding=ft.Padding(2, 8, 2, 2), expand=True)
        lyrics = ft.Container(self.syllables_list, expand=True)
        sps_hint = ft.Container(
            ft.Column([ft.Icon(ft.Icons.SPEED, color=pal.accent, size=36),
                       ft.Text("Точный анализ SPS", weight=ft.FontWeight.BOLD, color=pal.fg),
                       ft.Text("Выберите слог и нажмите кнопку SPS в шапке приложения.",
                               color=pal.muted, text_align=ft.TextAlign.CENTER)],
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
            alignment=ft.Alignment.CENTER, expand=True,
        )

        page = self._get_page()
        pw = getattr(page, "width", None) if page else None
        ph = getattr(page, "height", None) if page else None
        landscape = bool(isinstance(pw, (int, float)) and isinstance(ph, (int, float)) and pw > ph)
        if landscape:
            workspace = ft.Row([
                ft.Container(lyrics, expand=6, bgcolor=pal.canvas, border_radius=12, padding=6),
                ft.Container(inspector, expand=5, bgcolor=pal.panel, border_radius=12, padding=8),
            ], spacing=8, expand=True)
        else:
            selected_content = inspector if self.workspace_tab == "edit" else (lyrics if self.workspace_tab == "lines" else sps_hint)
            workspace = ft.Column([tab_bar, ft.Container(selected_content, expand=True, bgcolor=pal.canvas,
                                                           border_radius=12, padding=6)], spacing=7, expand=True)

        # Timeline owns the native flet_audio service and core.media waveform rendering.
        self.content = ft.Column([header, self.audio_timeline, workspace], spacing=8, expand=True)

    def _refresh_ui(self):
        # Base controller updates the line cards, selected syllable inspector,
        # MeasurementTimeline and the waveform-backed audio timeline.
        super()._refresh_ui()
