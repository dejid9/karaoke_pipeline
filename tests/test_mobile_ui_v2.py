"""Unit tests for ui_v2 (Touch-first mobile karaoke editor)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

mobile_src = Path(__file__).resolve().parent.parent / "karaoke_mobile" / "src"
if str(mobile_src) not in sys.path:
    sys.path.insert(0, str(mobile_src))

import flet as ft
from ui_v2.editor import EditorState, DEMO_ASS
from ui_v2.timeline import Timeline
from ui_v2.app import main, ASPECTS, SCALES


class TestUIv2EditorState(unittest.TestCase):
    def setUp(self):
        self.state = EditorState()

    def test_initial_state(self):
        self.assertEqual(len(self.state.syllables), 7)
        self.assertIsNone(self.state.selected)
        self.assertEqual(self.state.cursor, 0.0)
        self.assertIsNone(self.state.in_point)
        self.assertIsNone(self.state.out_point)

    def test_select_at_time(self):
        self.state.select_at(0.5)
        self.assertIsNotNone(self.state.selected)
        self.assertEqual(self.state.selected.visible_text, "Ka")
        self.assertEqual(self.state.cursor, 0.5)

    def test_edit_text_and_undo_redo(self):
        self.state.select_at(0.5)
        self.state.set_text("Custom")
        self.assertEqual(self.state.selected.visible_text, "Custom")

        self.state.undo()
        self.assertEqual(self.state.selected.visible_text, "Ka")

        self.state.redo()
        self.assertEqual(self.state.selected.visible_text, "Custom")

    def test_burst_marking(self):
        self.state.select_at(0.5)
        self.assertFalse(self.state.selected.burst_marked)

        self.state.burst(True)
        self.assertTrue(self.state.selected.burst_marked)

        self.state.burst(False)
        self.assertFalse(self.state.selected.burst_marked)

    def test_split_and_merge(self):
        self.state.select_at(0.5)
        initial_count = len(self.state.syllables)
        self.state.split_half()
        self.assertEqual(len(self.state.syllables), initial_count + 1)

        # Merge back
        self.state.select_at(0.6)
        self.state.merge()
        self.assertEqual(len(self.state.syllables), initial_count)

    def test_insert_and_delete(self):
        self.state.select_at(0.5)
        count_before = len(self.state.syllables)
        self.state.insert()
        self.assertEqual(len(self.state.syllables), count_before + 1)

        self.state.delete()
        self.assertEqual(len(self.state.syllables), count_before)


class TestUIv2Timeline(unittest.TestCase):
    def test_timeline_initialization_and_refresh(self):
        state = EditorState()
        selected_times = []
        played_times = []

        timeline = Timeline(
            state=state,
            on_select=lambda t: selected_times.append(t),
            on_play=lambda t: played_times.append(t),
        )

        self.assertEqual(len(timeline.overview_row.controls), len(state.syllables))
        self.assertEqual(len(timeline.detail.controls), len(state.syllables))

        # Select a syllable and refresh
        state.select_at(0.5)
        timeline.refresh()
        self.assertEqual(len(timeline.detail.controls), len(state.syllables))


class TestUIv2App(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock(spec=ft.Page)
        self.page.services = []
        self.page.add = MagicMock()
        self.page.show_dialog = MagicMock()
        self.page.pop_dialog = MagicMock()
        self.page.update = MagicMock()

    def test_app_main_initialization(self):
        main(self.page)
        self.assertTrue(self.page.add.called)
        wrapper = self.page.add.call_args[0][0]
        self.assertIsInstance(wrapper, ft.Container)
        self.assertEqual(wrapper.bgcolor, "#000000")

    def test_aspect_ratio_and_dpi_settings_dialog(self):
        main(self.page)
        wrapper = self.page.add.call_args[0][0]
        frame = wrapper.content

        # Initial full screen and 1.0 scale
        self.assertIsNone(frame.aspect_ratio)
        self.assertEqual(frame.scale, 1.0)

        # Find the Settings (Tune) icon button in the header
        header_row = frame.content.content.controls[0]
        tune_btn = header_row.controls[2]
        tune_btn.on_click(None)

        self.assertTrue(self.page.show_dialog.called)
        dialog = self.page.show_dialog.call_args[0][0]
        self.assertIsInstance(dialog, ft.AlertDialog)

        # Change to 16:9 and 80% DPI
        ratio_dd = dialog.content.controls[1]
        scale_dd = dialog.content.controls[3]
        ratio_dd.value = "16:9"
        scale_dd.value = "80%"

        apply_btn = dialog.actions[1]
        apply_btn.on_click(None)

        # Verify letterbox aspect ratio and scale are applied to the workspace frame
        self.assertEqual(frame.aspect_ratio, 16 / 9)
        self.assertEqual(frame.scale, 0.80)
        self.assertFalse(frame.expand)


if __name__ == "__main__":
    unittest.main()
