from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from karaoke_gui.theme import DEFAULT_THEME, THEMES, get_theme, load_ui_preferences, save_ui_preferences, theme_names


class ThemeCatalogTests(unittest.TestCase):
    def test_seven_families_have_light_and_night_variants(self):
        names = theme_names()
        self.assertEqual(len(names), 14)
        families = {}
        for palette in THEMES.values():
            families.setdefault(palette.family, set()).add(palette.mode)
            self.assertRegex(palette.accent, r"^#[0-9a-fA-F]{6}$")
            self.assertRegex(palette.bg, r"^#[0-9a-fA-F]{6}$")
        self.assertEqual(
            set(families),
            {"navy", "purple", "red", "green", "yellow", "vaporwave", "cappuccino"},
        )
        self.assertTrue(all(modes == {"light", "night"} for modes in families.values()))


    def test_dark_input_surfaces_follow_each_theme_family(self):
        purple = get_theme("Фиолетовая · ночная")
        red = get_theme("Красная · ночная")
        green = get_theme("Зелёная · ночная")
        self.assertEqual(purple.input_bg, purple.panel)
        self.assertEqual(red.input_bg, red.panel)
        self.assertEqual(green.input_bg, green.panel)
        self.assertEqual(len({purple.input_bg, red.input_bg, green.input_bg}), 3)

    def test_unknown_theme_falls_back_to_default(self):
        self.assertEqual(get_theme("definitely-missing").name, DEFAULT_THEME)

    def test_preferences_roundtrip_and_invalid_theme_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui.json"
            save_ui_preferences(
                "Вэйпорвэйв · ночная", True, path,
                ffmpeg_mode="custom", ffmpeg_path=r"C:\tools\ffmpeg.exe",
            )
            loaded = load_ui_preferences(path)
            self.assertEqual(loaded["theme"], "Вэйпорвэйв · ночная")
            self.assertTrue(loaded["advanced"])
            self.assertEqual(loaded["ffmpeg_mode"], "custom")
            self.assertEqual(loaded["ffmpeg_path"], r"C:\tools\ffmpeg.exe")
            self.assertTrue(loaded["playback_preserve_pitch"])
            path.write_text('{"theme":"bad","advanced":false}', encoding="utf-8")
            self.assertEqual(load_ui_preferences(path)["theme"], DEFAULT_THEME)


if __name__ == "__main__":
    unittest.main()
