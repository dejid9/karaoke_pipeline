"""Unit tests for mobile display and DPI scaling settings."""

import sys
from pathlib import Path
import unittest

# Ensure mobile src is on sys.path
mobile_src = Path(__file__).resolve().parent.parent / "karaoke_mobile" / "src"
if str(mobile_src) not in sys.path:
    sys.path.insert(0, str(mobile_src))

from ui.display_settings import DisplaySettings


class TestDisplaySettings(unittest.TestCase):
    def test_default_values(self):
        ds = DisplaySettings()
        self.assertEqual(ds.ui_scale, 1.0)
        self.assertEqual(ds.aspect_ratio, "auto")
        self.assertEqual(ds.fit_mode, "width")
        self.assertTrue(ds.compact_landscape)
        self.assertFalse(ds.hide_top_bar)
        self.assertFalse(ds.hide_bottom_bar)
        self.assertFalse(ds.timeline_collapsed)

    def test_scaling_helpers(self):
        ds = DisplaySettings(ui_scale=0.8)
        self.assertEqual(ds.font_size(12), 9.6)
        # Check minimum font clamp
        self.assertEqual(ds.font_size(6), 8.0)

        # Icon size
        self.assertEqual(ds.icon_size(20), 16.0)
        self.assertEqual(ds.icon_size(10), 14.0)  # clamped to 14

        # Timeline height
        self.assertEqual(ds.timeline_height(80), 64)
        ds.timeline_collapsed = True
        self.assertEqual(ds.timeline_height(80), 24)

    def test_compute_bounds(self):
        ds = DisplaySettings(aspect_ratio="auto")
        w, h = ds.compute_bounds(800, 360)
        self.assertIsNone(w)
        self.assertIsNone(h)

        # 20:9 landscape with fit_mode="height"
        ds_land = DisplaySettings(aspect_ratio="20:9", fit_mode="height")
        # page: 1000 x 360. Target w = min(1000, 360 * 20/9) = 800
        w, h = ds_land.compute_bounds(1000, 360)
        self.assertEqual(w, 800.0)
        self.assertIsNone(h)

        # 20:9 portrait with fit_mode="width"
        ds_port = DisplaySettings(aspect_ratio="20:9", fit_mode="width")
        # page: 360 x 1000. Target ratio = 9/20 = 0.45. Target h = min(1000, 360 / 0.45) = 800
        w, h = ds_port.compute_bounds(360, 1000)
        self.assertIsNone(w)
        self.assertEqual(h, 800.0)

        # Fixed width
        ds_fixed = DisplaySettings(aspect_ratio="fixed_460")
        w, h = ds_fixed.compute_bounds(800, 400)
        self.assertEqual(w, 460.0)
        self.assertIsNone(h)

        # Fixed width when page is narrower
        w, h = ds_fixed.compute_bounds(380, 700)
        self.assertEqual(w, 380.0)
        self.assertIsNone(h)

    def test_open_display_settings_dialog_no_crash(self):
        from ui.display_settings import open_display_settings_dialog
        import flet as ft

        class MockPage:
            overlay = []
            height = 800
            width = 360
            def update(self):
                pass

        page = MockPage()
        open_display_settings_dialog(page, on_changed=lambda: None)
        self.assertEqual(len(page.overlay), 1)
        self.assertIsInstance(page.overlay[0], ft.BottomSheet)


if __name__ == "__main__":
    unittest.main()
