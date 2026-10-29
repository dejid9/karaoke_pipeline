"""Touch Jog Wheel & Snap Controller for Millisecond-Precision Syllable Timing."""

from __future__ import annotations

from typing import Callable, Optional
import flet as ft

from ui.theme import ThemePalette, get_current_palette


class JogWheelWidget(ft.Container):
    """Touch-first jog wheel & snap bar designed specifically for mobile 20:9 screens.

    Replaces cluttered step buttons with:
    1. Snap to Cursor ('|← Сюда', '→| Сюда', '✂ По курсору')
    2. Adaptive horizontal scrubbing (1-5ms fine touch, 50-100ms flick)
    3. Tactile +/- step nudge buttons
    """

    def __init__(
        self,
        on_nudge: Optional[Callable[[str, float], None]] = None,
        on_snap_to_cursor: Optional[Callable[[str], None]] = None,
        on_split_at_cursor: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.on_nudge = on_nudge
        self.on_snap_to_cursor = on_snap_to_cursor
        self.on_split_at_cursor = on_split_at_cursor

        self.target_mode: str = "start"  # "start", "end", "shift"
        self._current_value_text = "—"
        pal = get_current_palette()

        # Mode Selector Buttons (Start / End / Shift)
        self.mode_start_btn = ft.Container(
            content=ft.Text("Старт", size=11, weight=ft.FontWeight.BOLD),
            padding=ft.Padding(8, 4, 8, 4),
            border_radius=6,
            bgcolor=pal.accent,
            on_click=lambda e: self._set_target_mode("start"),
        )
        self.mode_end_btn = ft.Container(
            content=ft.Text("Конец", size=11, weight=ft.FontWeight.BOLD),
            padding=ft.Padding(8, 4, 8, 4),
            border_radius=6,
            bgcolor=pal.raised,
            on_click=lambda e: self._set_target_mode("end"),
        )
        self.mode_shift_btn = ft.Container(
            content=ft.Text("Сдвиг", size=11, weight=ft.FontWeight.BOLD),
            padding=ft.Padding(8, 4, 8, 4),
            border_radius=6,
            bgcolor=pal.raised,
            on_click=lambda e: self._set_target_mode("shift"),
        )

        self.value_label = ft.Text("0.000 с", size=12, weight=ft.FontWeight.BOLD, color=pal.fg)

        # Quick Snap Actions
        self.snap_start_btn = ft.FilledButton(
            "|← Сюда",
            style=ft.ButtonStyle(padding=ft.Padding(8, 4, 8, 4), bgcolor=pal.raised, color=pal.fg),
            tooltip="Выставить начало слога ровно по позиции курсора воспроизведения",
            on_click=lambda e: self._trigger_snap("start"),
        )
        self.snap_end_btn = ft.FilledButton(
            "→| Сюда",
            style=ft.ButtonStyle(padding=ft.Padding(8, 4, 8, 4), bgcolor=pal.raised, color=pal.fg),
            tooltip="Выставить конец слога ровно по позиции курсора воспроизведения",
            on_click=lambda e: self._trigger_snap("end"),
        )
        self.split_btn = ft.FilledButton(
            "✂ По курсору",
            style=ft.ButtonStyle(padding=ft.Padding(8, 4, 8, 4), bgcolor=pal.accent, color=pal.accent_fg),
            tooltip="Разрезать слог на две части в точке курсора",
            on_click=lambda e: self._trigger_split(),
        )

        # Fine Nudge Steppers (-10ms, -50ms, +50ms, +10ms)
        self.nudge_m50 = ft.IconButton(
            icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
            tooltip="-50 мс",
            icon_size=16,
            icon_color=pal.fg,
            on_click=lambda e: self._do_nudge(-0.05),
        )
        self.nudge_m10 = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            tooltip="-10 мс",
            icon_size=18,
            icon_color=pal.fg,
            on_click=lambda e: self._do_nudge(-0.01),
        )
        self.nudge_p10 = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            tooltip="+10 мс",
            icon_size=18,
            icon_color=pal.fg,
            on_click=lambda e: self._do_nudge(0.01),
        )
        self.nudge_p50 = ft.IconButton(
            icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT,
            tooltip="+50 мс",
            icon_size=16,
            icon_color=pal.fg,
            on_click=lambda e: self._do_nudge(0.05),
        )

        # Central Tactile Slider (returns to 0 when released)
        self.jog_slider = ft.Slider(
            min=-50,
            max=50,
            divisions=20,
            value=0,
            label="Тонкая доводка",
            expand=True,
            on_change=self._on_slider_change,
        )

        self.padding = ft.Padding(6, 4, 6, 4)
        self.bgcolor = pal.panel
        self.border_radius = 8
        self.border = ft.Border.all(1, pal.border)

        self.content = ft.Column(
            [
                # Row 1: Target Mode & Current Value & Instant Snaps
                ft.Row(
                    [
                        ft.Row(
                            [
                                self.mode_start_btn,
                                self.mode_end_btn,
                                self.mode_shift_btn,
                            ],
                            spacing=4,
                        ),
                        self.value_label,
                        ft.Row(
                            [
                                self.snap_start_btn,
                                self.snap_end_btn,
                                self.split_btn,
                            ],
                            spacing=4,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                # Row 2: Tactile Jog Slider & Steppers
                ft.Row(
                    [
                        self.nudge_m50,
                        self.nudge_m10,
                        self.jog_slider,
                        self.nudge_p10,
                        self.nudge_p50,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                ),
            ],
            spacing=2,
            tight=True,
        )

    def _set_target_mode(self, mode: str):
        self.target_mode = mode
        pal = get_current_palette()
        self.mode_start_btn.bgcolor = pal.accent if mode == "start" else pal.raised
        self.mode_end_btn.bgcolor = pal.accent if mode == "end" else pal.raised
        self.mode_shift_btn.bgcolor = pal.accent if mode == "shift" else pal.raised
        try:
            self.update()
        except Exception:
            pass

    def set_value_text(self, text: str):
        self.value_label.value = text
        try:
            self.value_label.update()
        except Exception:
            pass

    def _do_nudge(self, delta_sec: float):
        if self.on_nudge:
            self.on_nudge(self.target_mode, delta_sec)

    def _on_slider_change(self, e):
        val = float(e.control.value)
        if abs(val) >= 2.0:
            # Map -50..50 to -0.05..+0.05 seconds
            delta = round(val / 1000.0, 3)
            self._do_nudge(delta)
            # Reset slider to center
            e.control.value = 0
            try:
                e.control.update()
            except Exception:
                pass

    def _trigger_snap(self, boundary: str):
        if self.on_snap_to_cursor:
            self.on_snap_to_cursor(boundary)

    def _trigger_split(self):
        if self.on_split_at_cursor:
            self.on_split_at_cursor()

    def apply_theme(self, pal: ThemePalette):
        self.bgcolor = pal.panel
        self.border = ft.Border.all(1, pal.border)
        self.value_label.color = pal.fg
        self._set_target_mode(self.target_mode)
        self.snap_start_btn.style.bgcolor = pal.raised
        self.snap_start_btn.style.color = pal.fg
        self.snap_end_btn.style.bgcolor = pal.raised
        self.snap_end_btn.style.color = pal.fg
        self.split_btn.style.bgcolor = pal.accent
        self.split_btn.style.color = pal.accent_fg
        for btn in (self.nudge_m50, self.nudge_m10, self.nudge_p10, self.nudge_p50):
            btn.icon_color = pal.fg
        try:
            self.update()
        except Exception:
            pass
