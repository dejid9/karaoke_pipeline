"""Unit tests for karaoke_mobile_new unified workbench."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

new_mobile_dir = Path(__file__).resolve().parent.parent / "karaoke_mobile_new"
if str(new_mobile_dir) not in sys.path:
    sys.path.insert(0, str(new_mobile_dir))

import flet as ft
from core.ass import AssDocument
from main import Workbench, main


class TestMobileNewWorkbench(unittest.TestCase):
    def setUp(self):
        self.ass_text = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\k50}Hel{\\k50}lo{\\k100} World\n"
        )
        self.doc = AssDocument.from_text(self.ass_text)
        self.page = MagicMock(spec=ft.Page)
        self.page.overlay = []
        self.page.services = []
        self.page.update = MagicMock()
        self.page.show_dialog = MagicMock()
        self.page.pop_dialog = MagicMock()

    def test_workbench_initialization(self):
        wb = Workbench(self.page)
        self.assertIsNone(wb.doc)
        self.assertEqual(len(wb.syllables()), 0)
        self.assertEqual(wb.aspect, "Полный экран")
        self.assertEqual(wb.dpi, 1.0)

    def test_load_document_and_selection(self):
        wb = Workbench(self.page)
        wb.doc = self.doc
        wb.refresh()

        self.assertEqual(len(wb.syllables()), 3)
        self.assertEqual(wb.count.value, "3 слогов")

        # Select first syllable
        syl1 = wb.syllables()[0]
        wb.select_syllable(syl1.id)
        self.assertEqual(wb.selected, [syl1.id])
        self.assertEqual(wb.selected_item().visible_text, "Hel")

    def test_split_and_merge_syllables(self):
        wb = Workbench(self.page)
        wb.doc = AssDocument.from_text(self.ass_text)
        wb.refresh()

        wb.select_syllable(wb.syllables()[0].id)
        wb.split_half(None)
        self.assertEqual(len(wb.syllables()), 4)

        # Undo split
        wb.undo(None)
        self.assertEqual(len(wb.syllables()), 3)

        # Redo split
        wb.redo(None)
        self.assertEqual(len(wb.syllables()), 4)

    def test_burst_marking(self):
        wb = Workbench(self.page)
        wb.doc = AssDocument.from_text(self.ass_text)
        wb.refresh()

        wb.select_syllable(wb.syllables()[0].id)
        self.assertFalse(wb.selected_item().burst_marked)

        wb.burst(None)
        self.assertTrue(wb.selected_item().burst_marked)

        wb.unburst(None)
        self.assertFalse(wb.selected_item().burst_marked)

    def test_letterbox_and_dpi_settings(self):
        wb = Workbench(self.page)
        wb.aspect = "16:9"
        wb.dpi = 0.80
        wb.refresh()

        self.assertEqual(wb.workspace.aspect_ratio, 16 / 9)
        self.assertEqual(wb.workspace.scale, 0.80)


if __name__ == "__main__":
    unittest.main()
