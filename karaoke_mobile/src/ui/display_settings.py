"""Display & UI Scale settings: Aspect ratio, DPI scaling, and landscape optimizations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Callable, Optional

import flet as ft

from ui.theme import get_current_palette


CONFIG_PATH = Path.home() / ".karaoke_mobile_display.json"


@dataclass
class DisplaySettings:
    ui_scale: float = 1.0  # 0.70, 0.80, 0.90, 1.00, 1.15, 1.25
    aspect_ratio: str = "auto"  # "auto", "20:9", "19.5:9", "18:9", "16:9", "fixed_380", "fixed_460", "fixed_600"
    fit_mode: str = "width"  # "width", "height", "both"
    compact_landscape: bool = True  # Automatically compact top and bottom bars in landscape
    hide_top_bar: bool = False  # Completely hide top bar
    hide_bottom_bar: bool = False  # Completely hide bottom bar
    timeline_collapsed: bool = False  # Collapse audio timeline into a slim 24px bar
    use_alt_ui: bool = False  # Alternative UI mode (Claude Opus ui_alt)

    def font_size(self, base_size: float) -> float:
        return max(8.0, round(base_size * self.ui_scale, 1))

    def button_padding(self, h: float = 8.0, v: float = 5.0) -> ft.Padding:
        return ft.Padding(
            max(2, int(round(h * self.ui_scale))),
            max(2, int(round(v * self.ui_scale))),
            max(2, int(round(h * self.ui_scale))),
            max(2, int(round(v * self.ui_scale))),
        )

    def icon_size(self, base_size: float = 20.0) -> float:
        return max(14.0, round(base_size * self.ui_scale, 1))

    def timeline_height(self, base_height: int = 80) -> int:
        if self.timeline_collapsed:
            return 24
        return max(45, int(round(base_height * self.ui_scale)))

    def compute_bounds(self, page_w: Optional[float], page_h: Optional[float]) -> tuple[Optional[float], Optional[float]]:
        if not page_w or not page_h or self.aspect_ratio == "auto":
            return None, None

        if self.aspect_ratio.startswith("fixed_"):
            try:
                fixed_w = float(self.aspect_ratio.split("_")[1])
                return min(page_w, fixed_w), None
            except Exception:
                return None, None

        ratios = {
            "20:9": 20.0 / 9.0,
            "19.5:9": 19.5 / 9.0,
            "18:9": 18.0 / 9.0,
            "16:9": 16.0 / 9.0,
        }
        r = ratios.get(self.aspect_ratio, 20.0 / 9.0)
        is_landscape = page_w > page_h
        target_ratio = r if is_landscape else (1.0 / r)

        max_w: Optional[float] = None
        max_h: Optional[float] = None

        if self.fit_mode in ("height", "both"):
            max_w = min(page_w, round(page_h * target_ratio, 2))
        if self.fit_mode in ("width", "both"):
            max_h = min(page_h, round(page_w / target_ratio, 2))

        return max_w, max_h

    def save(self):
        try:
            CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def load(cls) -> DisplaySettings:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception:
                pass
        return cls()


_CURRENT_DISPLAY: DisplaySettings = DisplaySettings.load()


def get_display_settings() -> DisplaySettings:
    global _CURRENT_DISPLAY
    return _CURRENT_DISPLAY


def open_display_settings_dialog(page: ft.Page, on_changed: Callable[[], None]):
    """Open interactive settings modal for DPI, aspect ratio, and landscape bars."""
    ds = get_display_settings()
    pal = get_current_palette()

    scale_str = f"{ds.ui_scale:.2f}"
    known_scales = ["0.65", "0.75", "0.80", "0.90", "1.00", "1.15", "1.25"]
    if scale_str not in known_scales:
        scale_str = "0.80"

    scale_dropdown = ft.Dropdown(
        label="Масштаб интерфейса (DPI)",
        options=[
            ft.dropdown.Option("0.65", "0.65x (Ультра-компактный — помещается максимум)"),
            ft.dropdown.Option("0.75", "0.75x (Компактный для экранов 20:9)"),
            ft.dropdown.Option("0.80", "0.80x (Компактный 80%)"),
            ft.dropdown.Option("0.90", "0.90x (Уменьшенный)"),
            ft.dropdown.Option("1.00", "1.00x (Стандартный 100%)"),
            ft.dropdown.Option("1.15", "1.15x (Крупный 115%)"),
            ft.dropdown.Option("1.25", "1.25x (Очень крупный 125%)"),
        ],
        value=scale_str,
        text_size=13,
        border_radius=8,
    )

    ratio_dropdown = ft.Dropdown(
        label="Соотношение сторон экрана (Aspect Ratio)",
        options=[
            ft.dropdown.Option("auto", "Авто (По всему экрану — 100%)"),
            ft.dropdown.Option("20:9", "20:9 (Ультравытянутый — Samsung/Xiaomi)"),
            ft.dropdown.Option("19.5:9", "19.5:9 (Современные смартфоны)"),
            ft.dropdown.Option("18:9", "18:9 (2:1 соотношение)"),
            ft.dropdown.Option("16:9", "16:9 (Классический смартфон / видео)"),
            ft.dropdown.Option("fixed_380", "Фиксированная ширина: 380px (Компакт)"),
            ft.dropdown.Option("fixed_460", "Фиксированная ширина: 460px (Стандарт)"),
            ft.dropdown.Option("fixed_600", "Фиксированная ширина: 600px (Широкий)"),
        ],
        value=ds.aspect_ratio,
        text_size=13,
        border_radius=8,
    )

    fit_dropdown = ft.Dropdown(
        label="Способ вписывания интерфейса",
        options=[
            ft.dropdown.Option("width", "По максимальной ширине (Fit Width)"),
            ft.dropdown.Option("height", "По максимальной высоте (Fit Height)"),
            ft.dropdown.Option("both", "По обоим измерениям (Fit Both)"),
        ],
        value=ds.fit_mode,
        text_size=13,
        border_radius=8,
    )

    compact_landscape_switch = ft.Switch(
        label="Компактные шапка и навигация в ландшафте (20:9)",
        value=ds.compact_landscape,
    )

    hide_top_bar_switch = ft.Switch(
        label="Скрыть верхнюю шапку (освобождает 50px высоты)",
        value=ds.hide_top_bar,
    )

    hide_bottom_bar_switch = ft.Switch(
        label="Скрыть нижнюю навигацию (парящее меню)",
        value=ds.hide_bottom_bar,
    )

    timeline_collapsed_switch = ft.Switch(
        label="Свернуть вейвформу/спектрограмму в тонкую строку (24px)",
        value=ds.timeline_collapsed,
    )

    use_alt_ui_switch = ft.Switch(
        label="Альтернативный UI (Claude Opus ui_alt)",
        value=ds.use_alt_ui or os.getenv("KARAOKE_UI_ALT", "0").lower() in ("1", "true", "yes"),
        tooltip="Переключить на экспериментальный интерфейс из папки ui_alt (требуется перезапуск экрана)",
    )

    def on_save_click(e):
        try:
            ds.ui_scale = float(scale_dropdown.value)
        except Exception:
            ds.ui_scale = 1.0

        ds.aspect_ratio = str(ratio_dropdown.value)
        ds.fit_mode = str(fit_dropdown.value)
        ds.compact_landscape = bool(compact_landscape_switch.value)
        ds.hide_top_bar = bool(hide_top_bar_switch.value)
        ds.hide_bottom_bar = bool(hide_bottom_bar_switch.value)
        ds.timeline_collapsed = bool(timeline_collapsed_switch.value)
        ds.use_alt_ui = bool(use_alt_ui_switch.value)
        os.environ["KARAOKE_UI_ALT"] = "1" if ds.use_alt_ui else "0"

        ds.save()
        bs.open = False
        page.update()
        on_changed()

        msg = "Настройки сохранены!" + (" (Режим ui_alt включен)" if ds.use_alt_ui else "")
        page.snack_bar = ft.SnackBar(ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    def on_reset_click(e):
        ds.ui_scale = 0.80  # Default to 0.80 for 20:9 mobile screens
        ds.aspect_ratio = "auto"
        ds.fit_mode = "width"
        ds.compact_landscape = True
        ds.hide_top_bar = False
        ds.hide_bottom_bar = False
        ds.timeline_collapsed = False
        ds.use_alt_ui = False
        os.environ["KARAOKE_UI_ALT"] = "0"
        ds.save()
        bs.open = False
        page.update()
        on_changed()

    bs = ft.BottomSheet(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.TUNE, color=pal.accent, size=22),
                            ft.Text("Настройки экрана, DPI и панелей", size=16, weight=ft.FontWeight.BOLD, color=pal.fg),
                        ],
                        spacing=8,
                    ),
                    ft.Text(
                        "Настройте масштаб (DPI), соотношение сторон (20:9) и видимость панелей для удобства в вертикальном и горизонтальном положении.",
                        size=11,
                        color=pal.muted,
                    ),
                    ft.Divider(height=1, color=pal.border),
                    scale_dropdown,
                    ratio_dropdown,
                    fit_dropdown,
                    compact_landscape_switch,
                    hide_top_bar_switch,
                    hide_bottom_bar_switch,
                    timeline_collapsed_switch,
                    use_alt_ui_switch,
                    ft.Divider(height=1, color=pal.border),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Сброс (20:9)",
                                style=ft.ButtonStyle(bgcolor=pal.raised, color=pal.fg),
                                on_click=on_reset_click,
                            ),
                            ft.FilledButton(
                                "Сохранить",
                                style=ft.ButtonStyle(bgcolor=pal.accent, color=pal.accent_fg),
                                on_click=on_save_click,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    ),
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=pal.panel,
            padding=14,
            border_radius=ft.BorderRadius(16, 16, 0, 0),
            border=ft.Border.all(1, pal.border),
            height=min(520, int(page.height * 0.85)) if (getattr(page, "height", None) and page.height > 200) else 480,
        ),
        scrollable=True,
    )

    if hasattr(page, "overlay"):
        for item in list(page.overlay):
            if getattr(item, "_is_display_settings", False):
                try:
                    page.overlay.remove(item)
                except Exception:
                    pass
    bs._is_display_settings = True
    page.overlay.append(bs)
    bs.open = True
    page.update()
