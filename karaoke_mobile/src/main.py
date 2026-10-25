"""Karaoke Mobile — Main Application Entrypoint with Exact SPS, Project Management, and PC Themes."""

from __future__ import annotations

from typing import Any, Dict, Optional

import flet as ft

from core.ass import AssDocument
from core.measurements import apply_measurements
from core.project_bundle import ProjectBundle
from core.sps import MeasurementTimeline
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
    current_transcript: str = ""
    current_burst_settings: Dict[str, Any] = {
        "mode": "dynamic",
        "base_color": "#FF0000",
        "alt_color": "#FF8000",
        "pulse_hz": 2.0,
    }

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
        }

    # Initialize Views
    mfa_view = MFAView(on_alignment_success=on_alignment_success)
    editor_view = EditorView(
        on_document_changed=on_document_changed,
        on_jump_to_sps=jump_to_sps,
    )
    sps_view = SPSView(
        on_document_changed=on_document_changed,
        on_measurements_changed=on_measurements_changed,
    )
    burst_view = BurstView(on_settings_changed=on_burst_settings_changed)
    export_view = ExportView(
        get_document=lambda: current_document,
        get_timeline=lambda: current_timeline,
        get_project_state=get_project_state,
        on_project_loaded=on_project_loaded,
    )

    views = [mfa_view, editor_view, sps_view, burst_view, export_view]

    # Register all view services (Native FilePickers, etc.) in page.services before user interaction
    for v in views:
        if hasattr(v, "get_services"):
            for service in v.get_services():
                if hasattr(page, "services") and service not in page.services:
                    page.services.append(service)
                if hasattr(page, "overlay") and service not in page.overlay:
                    page.overlay.append(service)

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

    app_icon = ft.Icon(ft.Icons.MIC, color=pal.accent, size=20)
    app_title = ft.Text("Karaoke Mobile", size=17, weight=ft.FontWeight.BOLD, color=pal.fg)

    top_bar = ft.Container(
        content=ft.Row(
            [
                ft.Row([app_icon, app_title], spacing=8),
                theme_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=pal.panel,
        padding=ft.Padding(14, 8, 14, 8),
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

    # Wrapped in SafeArea so Android status bar (clock/notch/battery) never overlaps the app
    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    top_bar,
                    page_container,
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


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    elif hasattr(ft, "app"):
        ft.app(target=main)
    else:
        import flet.app as flet_app
        flet_app.run(main)
