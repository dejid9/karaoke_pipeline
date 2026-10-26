"""Karaoke Mobile — Main Application Entrypoint with Exact SPS, Project Management, and PC Themes."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional

import flet as ft

from core.ass import AssDocument
from core.measurements import apply_measurements
from core.media import WaveformData, load_waveform
from core.project_bundle import ProjectBundle
from core.spectrogram import SpectrogramData, load_spectrogram
from core.sps import MeasurementTimeline
from ui.display_settings import get_display_settings, open_display_settings_dialog
from ui.theme import (
    DEFAULT_THEME,
    apply_mobile_theme,
    get_current_palette,
    theme_names,
)
from ui.views.burst_view import BurstView
from ui.views.editor_view import EditorView
from ui.views.export_view import ExportView
from ui.views.mfa_view import MFAView
from ui.views.sps_view import SPSView


def main(page: ft.Page):
    """Flet application entrypoint."""
    pal = apply_mobile_theme(page, DEFAULT_THEME)

    # Shared State
    current_document: AssDocument | None = None
    current_timeline: MeasurementTimeline | None = None
    current_audio_path: Optional[str] = None
    current_audio_name: Optional[str] = None
    current_audio_bytes: Optional[bytes] = None
    current_waveform: Optional[WaveformData] = None
    current_spectrogram: Optional[SpectrogramData] = None
    current_transcript: str = ""
    current_burst_settings: Dict[str, Any] = {
        "mode": "dynamic",
        "base_color": "#FF0000",
        "alt_color": "#FF8000",
        "pulse_hz": 2.0,
    }

    def sync_audio(
        name: str,
        data: Optional[bytes] = None,
        waveform: Optional[WaveformData] = None,
        spectrogram: Optional[SpectrogramData] = None,
    ):
        nonlocal current_audio_name, current_audio_bytes, current_waveform, current_spectrogram
        current_audio_name = name
        if data is not None:
            current_audio_bytes = data
        if waveform is not None:
            current_waveform = waveform
        if spectrogram is not None:
            current_spectrogram = spectrogram

        editor_view.audio_timeline.set_audio(name, data, current_waveform, current_spectrogram)
        sps_view.audio_timeline.set_audio(name, data, current_waveform, current_spectrogram)

    def sync_document(doc: AssDocument, timeline: Optional[MeasurementTimeline] = None):
        nonlocal current_document, current_timeline
        current_document = doc
        if timeline is not None:
            current_timeline = timeline
        elif current_timeline is None or len(current_timeline.syllables) != len(list(doc.karaoke_syllables())):
            current_timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
        editor_view.document = doc
        editor_view._refresh_ui()
        sps_view.set_document(doc, current_timeline)

    def on_alignment_success(ass_text: str):
        try:
            doc = AssDocument.from_text(ass_text)
            sync_document(doc)
            # Switch to editor tab
            nav_bar.selected_index = 1
            cur_pal = get_current_palette()
            editor_view.apply_theme(cur_pal)
            page_container.content = editor_view
            page.update()
        except Exception as e:
            if page:
                page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка парсинга ASS: {e}"))
                page.snack_bar.open = True
                page.update()

    def on_document_changed(doc: AssDocument):
        nonlocal current_document
        current_document = doc
        if sps_view.timeline is None or sps_view.document != doc:
            sps_view.set_document(doc, current_timeline)

    def on_measurements_changed(tl: MeasurementTimeline):
        nonlocal current_timeline
        current_timeline = tl

    def on_burst_settings_changed(settings):
        pass

    def jump_to_sps(syllable_id: str):
        """Navigate directly from Editor to Exact SPS view focusing on syllable."""
        if current_document:
            sps_view.set_document(current_document, current_timeline)
            sps_view.focus_syllable(syllable_id)
        nav_bar.selected_index = 2
        cur_pal = get_current_palette()
        sps_view.apply_theme(cur_pal)
        page_container.content = views[2]
        page.update()

    def on_return_to_editor(syllable_id: str):
        """Navigate back from Exact SPS to Editor focusing on syllable."""
        if current_document:
            editor_view.selected_syllable_id = syllable_id
            editor_view._refresh_ui()
        nav_bar.selected_index = 1
        cur_pal = get_current_palette()
        editor_view.apply_theme(cur_pal)
        page_container.content = views[1]
        page.update()

    def on_project_loaded(bundle: ProjectBundle):
        nonlocal current_transcript, current_audio_name, current_burst_settings
        current_transcript = bundle.transcript or ""
        current_audio_name = bundle.audio_filename
        if bundle.burst_settings:
            current_burst_settings.update(bundle.burst_settings)

        # Update MFA transcript
        if bundle.transcript:
            mfa_view.transcript_input.value = bundle.transcript
            mfa_view._safe_update()

        # Update Audio, Waveform & Spectrogram
        if bundle.audio_bytes or bundle.waveform_bytes or bundle.spectrogram_bytes:
            wfm = None
            spg = None
            if bundle.waveform_bytes:
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wfm")
                    tmp.write(bundle.waveform_bytes)
                    tmp.close()
                    wfm = load_waveform(tmp.name)
                    os.unlink(tmp.name)
                except Exception:
                    pass
            if bundle.spectrogram_bytes:
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".spg")
                    tmp.write(bundle.spectrogram_bytes)
                    tmp.close()
                    spg = load_spectrogram(tmp.name)
                    os.unlink(tmp.name)
                except Exception:
                    pass
            sync_audio(bundle.audio_filename or "audio.wav", bundle.audio_bytes, wfm, spg)

        # Update Subtitles & Measurements
        if bundle.ass_text:
            try:
                doc = AssDocument.from_text(bundle.ass_text)
                tl = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
                if bundle.measurements:
                    apply_measurements(bundle.measurements, tl)
                sync_document(doc, tl)
                # Switch to Editor tab
                nav_bar.selected_index = 1
                cur_pal = get_current_palette()
                editor_view.apply_theme(cur_pal)
                page_container.content = editor_view
                page.update()
            except Exception as ex:
                if page:
                    page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка загрузки субтитров проекта: {ex}"))
                    page.snack_bar.open = True
                    page.update()

        if page:
            page.snack_bar = ft.SnackBar(ft.Text(f"Проект «{bundle.name}» успешно открыт!"))
            page.snack_bar.open = True
            page.update()

    def get_project_state() -> Dict[str, Any]:
        return {
            "doc": current_document,
            "timeline": current_timeline,
            "transcript": mfa_view.transcript_input.value or current_transcript,
            "burst_settings": {
                "mode": burst_view.current_mode,
                "base_color": burst_view.base_color_hex,
                "alt_color": burst_view.alt_color_hex,
                "pulse_hz": burst_view.pulse_hz,
            },
            "audio_path": mfa_view.selected_audio_path or current_audio_path,
            "audio_name": mfa_view.selected_audio_name or current_audio_name,
            "audio_bytes": current_audio_bytes,
        }

    # Initialize Views
    mfa_view = MFAView(on_alignment_success=on_alignment_success)
    editor_view = EditorView(
        on_document_changed=on_document_changed,
        on_jump_to_sps=jump_to_sps,
        on_audio_loaded=sync_audio,
    )
    sps_view = SPSView(
        on_document_changed=on_document_changed,
        on_measurements_changed=on_measurements_changed,
        on_return_to_karaoke=on_return_to_editor,
        on_audio_loaded=sync_audio,
    )
    burst_view = BurstView(on_settings_changed=on_burst_settings_changed)
    export_view = ExportView(
        get_document=lambda: current_document,
        get_timeline=lambda: current_timeline,
        get_project_state=get_project_state,
        on_project_loaded=on_project_loaded,
    )

    views = [mfa_view, editor_view, sps_view, burst_view, export_view]

    # Register all view services (FilePickers) in page.services (NEVER in page.overlay, as Services are not visual controls)
    for v in views:
        if hasattr(v, "get_services"):
            for service in v.get_services():
                if hasattr(page, "_services") and hasattr(page._services, "register_service"):
                    try:
                        page._services.register_service(service)
                    except Exception:
                        pass
                if hasattr(page, "services") and service not in page.services:
                    page.services.append(service)

    # Initial palette apply across all views
    for v in views:
        if hasattr(v, "apply_theme"):
            v.apply_theme(pal)

    # Container holding active view
    page_container = ft.Container(content=views[0], expand=True)

    def on_nav_change(e):
        idx = nav_bar.selected_index
        cur_pal = get_current_palette()
        # If switching to SPS or Editor view, ensure state is synced
        if idx == 2 and current_document:
            sps_view.set_document(current_document, current_timeline)
        elif idx == 1 and current_document:
            editor_view._refresh_ui()

        if hasattr(views[idx], "apply_theme"):
            views[idx].apply_theme(cur_pal)
        page_container.content = views[idx]
        page.update()

    def change_theme(theme_name: str):
        new_pal = apply_mobile_theme(page, theme_name)
        top_bar.bgcolor = new_pal.panel
        top_bar.border = ft.Border(bottom=ft.BorderSide(1, new_pal.border))
        app_title.color = new_pal.fg
        app_icon.color = new_pal.accent
        nav_bar.bgcolor = new_pal.panel
        nav_bar.indicator_color = new_pal.raised
        for v in views:
            if hasattr(v, "apply_theme"):
                v.apply_theme(new_pal)
        if page:
            page.snack_bar = ft.SnackBar(ft.Text(f"Тема оформления: {theme_name}"))
            page.snack_bar.open = True
            page.update()

    # Theme selector menu items matching all 14 PC themes
    theme_menu_items = [
        ft.PopupMenuItem(
            content=t_name,
            on_click=lambda e, name=t_name: change_theme(name),
        )
        for t_name in theme_names()
    ]

    theme_btn = ft.PopupMenuButton(
        icon=ft.Icons.COLOR_LENS_OUTLINED,
        tooltip="Выбор темы (14 вариантов оформления)",
        items=theme_menu_items,
    )

    settings_btn = ft.IconButton(
        icon=ft.Icons.TUNE,
        tooltip="Настройки экрана, DPI и панелей",
        icon_color=pal.accent,
        on_click=lambda e: open_display_settings_dialog(page, update_layout),
    )

    app_icon = ft.Icon(ft.Icons.MIC, color=pal.accent, size=20)
    app_title = ft.Text("Karaoke Mobile", size=16, weight=ft.FontWeight.BOLD, color=pal.fg)

    top_bar = ft.Container(
        content=ft.Row(
            [
                ft.Row([app_icon, app_title], spacing=6),
                ft.Row([theme_btn, settings_btn], spacing=0, tight=True),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=pal.panel,
        padding=ft.Padding(12, 6, 12, 6),
        border=ft.Border(bottom=ft.BorderSide(1, pal.border)),
    )

    # Mobile bottom navigation bar (5 destinations)
    nav_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor=pal.panel,
        indicator_color=pal.raised,
        on_change=on_nav_change,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.CLOUD_QUEUE,
                selected_icon=ft.Icons.CLOUD,
                label="Colab MFA",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.EDIT_OUTLINED,
                selected_icon=ft.Icons.EDIT,
                label="Редактор",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.SPEED,
                selected_icon=ft.Icons.SPEED,
                label="Точный SPS",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.AUTO_AWESOME_OUTLINED,
                selected_icon=ft.Icons.AUTO_AWESOME,
                label="Бёрст",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.FOLDER_ZIP_OUTLINED,
                selected_icon=ft.Icons.FOLDER_ZIP,
                label="Проект",
            ),
        ],
    )

    def switch_nav_tab(target_idx: int):
        nav_bar.selected_index = target_idx
        cur_pal = get_current_palette()
        if target_idx == 2 and current_document:
            sps_view.set_document(current_document, current_timeline)
        elif target_idx == 1 and current_document:
            editor_view._refresh_ui()

        if hasattr(views[target_idx], "apply_theme"):
            views[target_idx].apply_theme(cur_pal)
        page_container.content = views[target_idx]
        page.update()

    def open_quick_nav_modal(e=None):
        cur_pal = get_current_palette()

        def _pick(idx):
            bs.open = False
            page.update()
            switch_nav_tab(idx)

        bs = ft.BottomSheet(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Разделы приложения", size=15, weight=ft.FontWeight.BOLD, color=cur_pal.fg),
                        ft.ListTile(leading=ft.Icon(ft.Icons.CLOUD, color=cur_pal.accent), title=ft.Text("Colab MFA", color=cur_pal.fg), on_click=lambda e: _pick(0)),
                        ft.ListTile(leading=ft.Icon(ft.Icons.EDIT, color=cur_pal.accent), title=ft.Text("Редактор караоке", color=cur_pal.fg), on_click=lambda e: _pick(1)),
                        ft.ListTile(leading=ft.Icon(ft.Icons.SPEED, color=cur_pal.accent), title=ft.Text("Точный SPS", color=cur_pal.fg), on_click=lambda e: _pick(2)),
                        ft.ListTile(leading=ft.Icon(ft.Icons.AUTO_AWESOME, color=cur_pal.accent), title=ft.Text("Параметры бёрста", color=cur_pal.fg), on_click=lambda e: _pick(3)),
                        ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER_ZIP, color=cur_pal.accent), title=ft.Text("Пакет проекта", color=cur_pal.fg), on_click=lambda e: _pick(4)),
                    ],
                    tight=True,
                    spacing=2,
                ),
                bgcolor=cur_pal.panel,
                padding=12,
                border_radius=ft.BorderRadius(16, 16, 0, 0),
            )
        )
        page.overlay.append(bs)
        bs.open = True
        page.update()

    floating_nav_btn = ft.FloatingActionButton(
        icon=ft.Icons.MENU,
        tooltip="Меню разделов (нижняя панель скрыта)",
        mini=True,
        on_click=open_quick_nav_modal,
        visible=False,
    )
    page.floating_action_button = floating_nav_btn

    def update_layout(e=None):
        ds = get_display_settings()
        cur_pal = get_current_palette()
        is_landscape = bool(page.width and page.height and page.width > page.height)

        # 1. Top and Bottom bar visibility
        top_bar.visible = not ds.hide_top_bar
        nav_bar.visible = not ds.hide_bottom_bar
        floating_nav_btn.visible = ds.hide_bottom_bar

        # 2. Landscape and compact bars
        if is_landscape and ds.compact_landscape:
            top_bar.padding = ft.Padding(10, 4, 10, 4)
            app_title.size = ds.font_size(12)
            app_icon.size = ds.icon_size(16)
            nav_bar.height = 42
            nav_bar.label_behavior = ft.NavigationBarLabelBehavior.ALWAYS_HIDE
        else:
            top_bar.padding = ft.Padding(12, 6, 12, 6)
            app_title.size = ds.font_size(16)
            app_icon.size = ds.icon_size(20)
            nav_bar.height = 68
            nav_bar.label_behavior = ft.NavigationBarLabelBehavior.ALWAYS_SHOW

        # 3. Aspect Ratio and Max Bounds
        max_w, max_h = ds.compute_bounds(page.width, page.height)
        page_container.width = max_w
        page_container.height = max_h

        # 4. Propagate theme and scale to active view
        idx = nav_bar.selected_index
        if hasattr(views[idx], "apply_theme"):
            views[idx].apply_theme(cur_pal)

        page.update()

    page.on_resize = update_layout

    centered_body = ft.Container(
        content=page_container,
        alignment=ft.Alignment.CENTER,
        expand=True,
    )

    # Wrapped in SafeArea so Android status bar (clock/notch/battery) never overlaps the app
    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    top_bar,
                    centered_body,
                    nav_bar,
                ],
                expand=True,
                spacing=0,
            ),
            expand=True,
            avoid_intrusions_top=True,
            avoid_intrusions_bottom=True,
        )
    )

    # Initial layout calculation
    update_layout()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    elif hasattr(ft, "app"):
        ft.app(target=main)
    else:
        import flet.app as flet_app
        flet_app.run(main)
