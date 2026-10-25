"""Karaoke Mobile — Main Application Entrypoint with Exact SPS and Project Management."""

from __future__ import annotations

from typing import Any, Dict, Optional

import flet as ft

from core.ass import AssDocument
from core.measurements import apply_measurements
from core.project_bundle import ProjectBundle
from core.sps import MeasurementTimeline
from ui.theme import (
    COLOR_PRIMARY,
    SURFACE_DARK,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    apply_mobile_theme,
)
from ui.views.burst_view import BurstView
from ui.views.editor_view import EditorView
from ui.views.export_view import ExportView
from ui.views.mfa_view import MFAView
from ui.views.sps_view import SPSView


def main(page: ft.Page):
    """Flet application entrypoint."""
    apply_mobile_theme(page)

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

    def on_project_loaded(bundle: ProjectBundle):
        nonlocal current_transcript, current_audio_name, current_burst_settings
        current_transcript = bundle.transcript or ""
        current_audio_name = bundle.audio_filename
        if bundle.burst_settings:
            current_burst_settings.update(bundle.burst_settings)

        # Update MFA transcript
        if bundle.transcript:
            mfa_view.transcript_input.value = bundle.transcript
            mfa_view.update()

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
    editor_view = EditorView(on_document_changed=on_document_changed)
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

    # Register all view services (FilePicker, etc.) in page.services before user interaction
    for v in views:
        if hasattr(v, "get_services"):
            for service in v.get_services():
                if hasattr(page, "services"):
                    if service not in page.services:
                        page.services.append(service)
                elif hasattr(page, "overlay"):
                    if service not in page.overlay:
                        page.overlay.append(service)

    # Container holding active view
    page_container = ft.Container(content=views[0], expand=True)

    def on_nav_change(e):
        idx = nav_bar.selected_index
        # If switching to SPS or Editor view, ensure state is synced
        if idx == 2 and current_document:
            sps_view.set_document(current_document, current_timeline)
        elif idx == 1 and current_document:
            editor_view._refresh_ui()
        page_container.content = views[idx]
        page.update()

    # Mobile bottom navigation bar (5 destinations)
    nav_bar = ft.NavigationBar(
        selected_index=0,
        bgcolor=SURFACE_DARK,
        indicator_color=SURFACE_ELEVATED,
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

    page.add(
        ft.Column(
            [
                page_container,
                nav_bar,
            ],
            expand=True,
            spacing=0,
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
