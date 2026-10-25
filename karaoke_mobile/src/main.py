"""Karaoke Mobile — Main Application Entrypoint."""

from __future__ import annotations

import flet as ft

from core.ass import AssDocument
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


def main(page: ft.Page):
    """Flet application entrypoint."""
    apply_mobile_theme(page)

    # Shared State
    current_document: AssDocument | None = None

    def on_alignment_success(ass_text: str):
        editor_view.load_ass_text(ass_text)
        # Switch to editor tab
        nav_bar.selected_index = 1
        page_container.content = editor_view
        page.update()

    def on_document_changed(doc: AssDocument):
        nonlocal current_document
        current_document = doc

    # Views
    mfa_view = MFAView(on_alignment_success=on_alignment_success)
    editor_view = EditorView(on_document_changed=on_document_changed)
    burst_view = BurstView()
    export_view = ExportView(get_document=lambda: current_document)

    views = [mfa_view, editor_view, burst_view, export_view]

    # Container holding active view
    page_container = ft.Container(content=views[0], expand=True)

    def on_nav_change(e):
        idx = nav_bar.selected_index
        page_container.content = views[idx]
        page.update()

    # Mobile bottom navigation bar
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
                icon=ft.Icons.AUTO_AWESOME_OUTLINED,
                selected_icon=ft.Icons.AUTO_AWESOME,
                label="Бёрст",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.DOWNLOAD_OUTLINED,
                selected_icon=ft.Icons.DOWNLOAD,
                label="Экспорт",
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
