from __future__ import annotations

import flet as ft


class Timeline(ft.Container):
    """Touch-friendly overview and syllable detail lane for Android and web."""

    def __init__(self, state, on_select, on_play):
        super().__init__(expand=True)
        self.state = state
        self.on_select = on_select
        self.on_play = on_play
        self.zoom = 70.0
        self.overview_row = ft.Row([], spacing=1)
        self.detail = ft.Row([], spacing=2, scroll=ft.ScrollMode.ALWAYS, expand=True)
        self.gesture = ft.GestureDetector(
            content=ft.Container(self.detail, height=170), on_double_tap=self.double_tap
        )
        self.content = ft.Column([
            ft.Container(self.overview_row, bgcolor="#0f172a", padding=6, height=28, border_radius=4),
            self.gesture
        ], spacing=6, expand=True)
        self.refresh()

    def refresh(self) -> None:
        # Update overview lane
        self.overview_row.controls = [
            ft.Container(
                width=max(4.0, (s.end - s.start) * 8.0), height=12,
                bgcolor="#2563eb" if s.id == self.state.selected_id else ("#dc2626" if s.burst_marked else "#475569"),
                border_radius=2,
            ) for s in self.state.syllables
        ]

        # Update detail lane
        self.detail.controls = []
        for syllable in self.state.syllables:
            self.detail.controls.append(ft.GestureDetector(
                content=ft.Container(
                    ft.Text(syllable.visible_text or "·", color="#f8fafc", size=14, weight=ft.FontWeight.W_500),
                    width=max(36.0, (syllable.end - syllable.start) * self.zoom),
                    height=90, padding=8,
                    bgcolor="#dc2626" if syllable.burst_marked else (
                        "#2563eb" if syllable.id == self.state.selected_id else "#334155"
                    ), border_radius=6,
                ),
                on_tap=lambda e, item=syllable: self.on_select(item.start),
                on_double_tap=lambda e, item=syllable: self.on_play(item.start),
            ))
        try:
            self.update()
        except RuntimeError:
            pass

    def double_tap(self, e) -> None:
        self.on_play(self.state.cursor)
