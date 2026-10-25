"""Interactive Burst & Pulse Styling View with Live Animation."""

from __future__ import annotations

import colorsys
import math
import time
import threading
from typing import Callable, Optional

import flet as ft

from core.render import RenderLayoutSettings
from ui.theme import (
    COLOR_PRIMARY,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class BurstView(ft.Container):
    """View for visually configuring burst colors, gradients, and dynamic sinusoidal pulse."""

    def __init__(self, on_settings_changed: Optional[Callable[[RenderLayoutSettings], None]] = None):
        super().__init__()
        self.expand = True
        self.padding = ft.padding.all(16)
        self.on_settings_changed = on_settings_changed

        # State
        self.current_mode = "dynamic"
        self.base_color_hex = "#FF0000"
        self.alt_color_hex = "#FF8000"
        self.pulse_hz = 2.0
        self.anim_running = True

        self._build_controls()
        self._start_preview_animation()

    def _build_controls(self):
        # 1. Mode Selector
        self.mode_radio = ft.RadioGroup(
            content=ft.Column(
                [
                    ft.Radio(value="dynamic", label="Динамическая синусоидальная пульсация (60 FPS)"),
                    ft.Radio(value="gradient", label="Градиент по граням RGB-куба"),
                    ft.Radio(value="alternate", label="Чередование слогов (Базовый / Альт)"),
                    ft.Radio(value="single", label="Одиночный цвет"),
                ],
                spacing=6,
            ),
            value=self.current_mode,
            on_change=self._on_mode_change,
        )

        mode_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Режим перелива бёрста", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    self.mode_radio,
                ],
                spacing=10,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        # 2. Live Animated Preview Widget
        self.preview_syllable_1 = ft.Text("БЁРСТ", size=24, weight=ft.FontWeight.BOLD, color=self.base_color_hex)
        self.preview_syllable_2 = ft.Text("ПЕРЕЛИВ", size=24, weight=ft.FontWeight.BOLD, color=self.alt_color_hex)
        self.preview_syllable_3 = ft.Text("СИММЕТРИЧНЫЙ", size=24, weight=ft.FontWeight.BOLD, color=self.base_color_hex)
        self.preview_normal_text = ft.Text("обычный белый", size=20, color="#FFFFFF")

        preview_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Интерактивный предпросмотр (Live Preview)", size=13, color=TEXT_MUTED),
                    ft.Row(
                        [
                            self.preview_syllable_1,
                            self.preview_syllable_2,
                            self.preview_syllable_3,
                            self.preview_normal_text,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        wrap=True,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            bgcolor="#11111b",
            padding=20,
            border_radius=12,
            border=ft.border.all(1, SURFACE_ELEVATED),
        )

        # 3. Settings controls
        self.hz_slider = ft.Slider(
            min=0.5,
            max=8.0,
            divisions=15,
            value=self.pulse_hz,
            label="{value} Гц",
            on_change=self._on_hz_change,
        )
        self.hz_label = ft.Text(f"Частота пульсации: {self.pulse_hz:.1f} Гц ({(self.pulse_hz * 60):.0f} BPM)", size=13, color=TEXT_SECONDARY)

        self.base_color_btn = ft.ElevatedButton(
            "Базовый: Красный",
            icon=ft.Icons.COLOR_LENS,
            style=ft.ButtonStyle(bgcolor="#FF0000", color="#FFFFFF"),
            on_click=self._on_pick_base_color,
        )
        self.alt_color_btn = ft.ElevatedButton(
            "Второй: Оранжевый",
            icon=ft.Icons.COLOR_LENS,
            style=ft.ButtonStyle(bgcolor="#FF8000", color="#FFFFFF"),
            on_click=self._on_pick_alt_color,
        )

        settings_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Параметры цвета и ритма", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Row([self.base_color_btn, self.alt_color_btn], wrap=True),
                    self.hz_label,
                    self.hz_slider,
                ],
                spacing=12,
            ),
            bgcolor=SURFACE_CARD,
            padding=16,
            border_radius=12,
        )

        self.content = ft.ListView(
            controls=[
                ft.Text("Настройка бёрст-стиля", size=22, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ft.Text("Плавные гармонические синусоидальные переливы по цветовому кубу", size=13, color=TEXT_MUTED),
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                preview_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                mode_card,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                settings_card,
            ],
            spacing=10,
        )

    def _start_preview_animation(self):
        """Run smooth sinusoidal interpolation animation on preview labels."""
        def _anim_loop():
            start_time = time.time()
            while self.anim_running:
                if self.current_mode == "dynamic":
                    elapsed = time.time() - start_time
                    # Sinusoidal factor: 0.5 * (1 - cos(2*pi * hz * t))
                    factor = 0.5 * (1.0 - math.cos(2.0 * math.pi * self.pulse_hz * elapsed))
                    curr_color = self._interpolate_color(self.base_color_hex, self.alt_color_hex, factor)

                    # Update colors on UI thread
                    self.preview_syllable_1.color = curr_color
                    self.preview_syllable_2.color = curr_color
                    self.preview_syllable_3.color = curr_color
                    if self.page:
                        self.preview_syllable_1.update()
                        self.preview_syllable_2.update()
                        self.preview_syllable_3.update()
                time.sleep(0.033)  # ~30-60 FPS UI tick

        threading.Thread(target=_anim_loop, daemon=True).start()

    def _interpolate_color(self, hex1: str, hex2: str, t: float) -> str:
        """Interpolate between two hex colors along the HSV hue arc."""
        h1 = hex1.lstrip("#")
        h2 = hex2.lstrip("#")
        r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
        r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)

        hv1, s1, v1 = colorsys.rgb_to_hsv(r1 / 255.0, g1 / 255.0, b1 / 255.0)
        hv2, s2, v2 = colorsys.rgb_to_hsv(r2 / 255.0, g2 / 255.0, b2 / 255.0)

        dh = (hv2 - hv1) % 1.0
        if dh > 0.5:
            dh -= 1.0
        elif dh < -0.5:
            dh += 1.0

        h = (hv1 + t * dh) % 1.0
        s = s1 + t * (s2 - s1)
        v = v1 + t * (v2 - v1)

        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return f"#{int(round(r * 255)):02X}{int(round(g * 255)):02X}{int(round(b * 255)):02X}"

    def _on_mode_change(self, e):
        self.current_mode = self.mode_radio.value
        if self.current_mode == "single":
            self.preview_syllable_1.color = self.base_color_hex
            self.preview_syllable_2.color = self.base_color_hex
            self.preview_syllable_3.color = self.base_color_hex
        elif self.current_mode == "alternate":
            self.preview_syllable_1.color = self.base_color_hex
            self.preview_syllable_2.color = self.alt_color_hex
            self.preview_syllable_3.color = self.base_color_hex
        elif self.current_mode == "gradient":
            self.preview_syllable_1.color = self.base_color_hex
            self.preview_syllable_2.color = self._interpolate_color(self.base_color_hex, self.alt_color_hex, 0.5)
            self.preview_syllable_3.color = self.alt_color_hex
        self.update()

    def _on_hz_change(self, e):
        self.pulse_hz = float(self.hz_slider.value)
        bpm = self.pulse_hz * 60
        self.hz_label.value = f"Частота пульсации: {self.pulse_hz:.1f} Гц ({bpm:.0f} BPM)"
        self.update()

    def _on_pick_base_color(self, e):
        # Rotate through common presets
        presets = ["#FF0000", "#FF007F", "#00FF00", "#00F0FF", "#FFFF00"]
        idx = (presets.index(self.base_color_hex) + 1) % len(presets) if self.base_color_hex in presets else 0
        self.base_color_hex = presets[idx]
        self.base_color_btn.style.bgcolor = self.base_color_hex
        self.update()

    def _on_pick_alt_color(self, e):
        presets = ["#FF8000", "#FF00FF", "#0080FF", "#7FFF00", "#FFD700"]
        idx = (presets.index(self.alt_color_hex) + 1) % len(presets) if self.alt_color_hex in presets else 0
        self.alt_color_hex = presets[idx]
        self.alt_color_btn.style.bgcolor = self.alt_color_hex
        self.update()
