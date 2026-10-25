"""Interactive Burst & Pulse Styling View with Live Animation."""

from __future__ import annotations

import colorsys
import math
import time
import threading
from typing import Callable, Optional

import flet as ft

from core.render import RenderLayoutSettings
from ui.theme import ThemePalette, get_current_palette


class BurstView(ft.Container):
    """View for visually configuring burst colors, gradients, and dynamic sinusoidal pulse."""

    def __init__(self, on_settings_changed: Optional[Callable[[RenderLayoutSettings], None]] = None):
        super().__init__()
        self.expand = True
        self.padding = 12
        self.on_settings_changed = on_settings_changed

        # State
        self.current_mode = "dynamic"
        self.base_color_hex = "#FF0000"
        self.alt_color_hex = "#FF8000"
        self.pulse_hz = 2.0
        self.anim_running = True

        self._build_controls()
        self._start_preview_animation()

    def _safe_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def apply_theme(self, pal: ThemePalette):
        """Update colors dynamically when theme changes."""
        self._build_controls()
        self._safe_update()

    def _build_controls(self):
        pal = get_current_palette()

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
                    ft.Text("Режим перелива бёрста", size=15, weight=ft.FontWeight.BOLD, color=pal.fg),
                    self.mode_radio,
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        # 2. Live Animated Preview Widget
        self.preview_syllable_1 = ft.Text("БЁРСТ", size=24, weight=ft.FontWeight.BOLD, color=self.base_color_hex)
        self.preview_syllable_2 = ft.Text("ПЕРЕЛИВ", size=24, weight=ft.FontWeight.BOLD, color=self.alt_color_hex)
        self.preview_syllable_3 = ft.Text("СИММЕТРИЧНЫЙ", size=24, weight=ft.FontWeight.BOLD, color=self.base_color_hex)
        self.preview_normal_text = ft.Text("обычный слог", size=20, color=pal.fg)

        preview_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Интерактивный предпросмотр (Live Preview)", size=12, color=pal.muted),
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
                spacing=10,
            ),
            bgcolor=pal.raised,
            padding=16,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
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
        self.hz_label = ft.Text(f"Частота пульсации: {self.pulse_hz:.1f} Гц ({(self.pulse_hz * 60):.0f} BPM)", size=13, color=pal.muted)

        self.base_color_btn = ft.FilledButton(
            "Базовый: Красный",
            icon=ft.Icons.COLOR_LENS,
            style=ft.ButtonStyle(bgcolor=self.base_color_hex, color="#FFFFFF"),
            on_click=self._on_pick_base_color,
        )
        self.alt_color_btn = ft.FilledButton(
            "Второй: Оранжевый",
            icon=ft.Icons.COLOR_LENS,
            style=ft.ButtonStyle(bgcolor=self.alt_color_hex, color="#FFFFFF"),
            on_click=self._on_pick_alt_color,
        )

        settings_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Параметры цвета и ритма", size=15, weight=ft.FontWeight.BOLD, color=pal.fg),
                    ft.Row([self.base_color_btn, self.alt_color_btn], wrap=True),
                    self.hz_label,
                    self.hz_slider,
                ],
                spacing=8,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=12,
            border=ft.Border.all(1, pal.border),
        )

        self.content = ft.ListView(
            controls=[
                ft.Text("Стилизация и пульсация", size=20, weight=ft.FontWeight.BOLD, color=pal.fg),
                ft.Text("Визуальный подбор гармоничных переливов для бёрстов и тайминг синусоиды", size=12, color=pal.muted),
                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                preview_card,
                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                mode_card,
                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                settings_card,
            ],
            spacing=8,
        )

    def _start_preview_animation(self):
        """Background thread updating the live color preview smoothly at ~30 FPS."""
        def _anim_loop():
            start_t = time.time()
            while self.anim_running:
                t = time.time() - start_t
                if self.current_mode == "dynamic":
                    # Sinusoidal pulse wave
                    phase = (t * self.pulse_hz * 2.0 * math.pi)
                    factor_1 = (math.sin(phase) + 1.0) / 2.0
                    factor_2 = (math.sin(phase + math.pi / 2.0) + 1.0) / 2.0
                    factor_3 = (math.sin(phase + math.pi) + 1.0) / 2.0

                    c1 = self._interpolate_color(self.base_color_hex, self.alt_color_hex, factor_1)
                    c2 = self._interpolate_color(self.base_color_hex, self.alt_color_hex, factor_2)
                    c3 = self._interpolate_color(self.base_color_hex, self.alt_color_hex, factor_3)

                    self.preview_syllable_1.color = c1
                    self.preview_syllable_2.color = c2
                    self.preview_syllable_3.color = c3
                    self._safe_update()

                time.sleep(0.033)

        threading.Thread(target=_anim_loop, daemon=True).start()

    def _interpolate_color(self, hex_a: str, hex_b: str, factor: float) -> str:
        """Linear interpolate between two hex colors in HSV space."""
        factor = max(0.0, min(1.0, factor))
        c1 = [int(hex_a[i : i + 2], 16) / 255.0 for i in (1, 3, 5)]
        c2 = [int(hex_b[i : i + 2], 16) / 255.0 for i in (1, 3, 5)]

        h1, s1, v1 = colorsys.rgb_to_hsv(*c1)
        h2, s2, v2 = colorsys.rgb_to_hsv(*c2)

        # Handle hue shortest distance wrapping
        dh = h2 - h1
        if dh > 0.5:
            dh -= 1.0
        elif dh < -0.5:
            dh += 1.0
        h = (h1 + dh * factor) % 1.0
        s = s1 + (s2 - s1) * factor
        v = v1 + (v2 - v1) * factor

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
        self._safe_update()

    def _on_hz_change(self, e):
        self.pulse_hz = float(self.hz_slider.value)
        bpm = self.pulse_hz * 60
        self.hz_label.value = f"Частота пульсации: {self.pulse_hz:.1f} Гц ({bpm:.0f} BPM)"
        self._safe_update()

    def _on_pick_base_color(self, e):
        presets = ["#FF0000", "#FF007F", "#00FF00", "#00F0FF", "#FFFF00"]
        idx = (presets.index(self.base_color_hex) + 1) % len(presets) if self.base_color_hex in presets else 0
        self.base_color_hex = presets[idx]
        self.base_color_btn.style.bgcolor = self.base_color_hex
        self._safe_update()

    def _on_pick_alt_color(self, e):
        presets = ["#FF8000", "#FF00FF", "#0080FF", "#7FFF00", "#FFD700"]
        idx = (presets.index(self.alt_color_hex) + 1) % len(presets) if self.alt_color_hex in presets else 0
        self.alt_color_hex = presets[idx]
        self.alt_color_btn.style.bgcolor = self.alt_color_hex
        self._safe_update()
