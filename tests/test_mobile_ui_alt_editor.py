"""Comprehensive unit tests for ui_alt (modern Touch-First mobile karaoke editor)."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

mobile_src = Path(__file__).resolve().parent.parent / "karaoke_mobile" / "src"
if str(mobile_src) not in sys.path:
    sys.path.insert(0, str(mobile_src))

from core.ass import AssDocument
from ui_alt.components.jog_wheel import JogWheelWidget
from ui_alt.views.editor_view import EditorView as AltEditorView


class TestMobileUIAltEditor(unittest.TestCase):
    def setUp(self):
        self.ass_text = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\k50}Hel{\\k50}lo{\\k100} World\n"
        )

    def test_alt_editor_initialization_and_sync(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor._refresh_ui()

        # Audio timeline syllables synced
        self.assertEqual(len(editor.audio_timeline.syllables), 3)
        self.assertEqual(editor.stats_text.value, "3 сл (🔥0)")

    def test_jog_wheel_target_modes_and_readout(self):
        jog = JogWheelWidget()
        self.assertEqual(jog.target_mode, "start")

        jog._set_target_mode("end")
        self.assertEqual(jog.target_mode, "end")

        jog._set_target_mode("shift")
        self.assertEqual(jog.target_mode, "shift")

        jog.set_value_text("Start: 1.250с")
        self.assertEqual(jog.value_label.value, "Start: 1.250с")

    def test_snap_to_cursor_start_and_end(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S1"]
        editor._refresh_ui()

        # s1: 1.50 .. 2.00
        # Set cursor to 1.650s and snap Start
        editor.audio_timeline.center_time = 1.650
        editor._on_jog_snap("start")
        syl = editor._find_syllable("L2:S1")
        self.assertAlmostEqual(syl.start, 1.650, places=3)

        # Set cursor to 2.200s and snap End
        editor.audio_timeline.center_time = 2.200
        editor._on_jog_snap("end")
        syl2 = editor._find_syllable("L2:S1")
        self.assertAlmostEqual(syl2.end, 2.200, places=3)

    def test_split_at_cursor(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0"]
        editor._refresh_ui()

        # s0 is 1.00 .. 1.50s. Place cursor at 1.25s
        editor.audio_timeline.center_time = 1.250
        editor._on_jog_split()

        # Now document has 4 syllables
        all_syls = list(editor.document.karaoke_syllables())
        self.assertEqual(len(all_syls), 4)

    def test_jog_nudge_start_end_shift(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S1"]
        editor._refresh_ui()

        # Initial: s1 start is 1.50s
        editor._on_jog_nudge("start", 0.05)
        syl = editor._find_syllable("L2:S1")
        self.assertAlmostEqual(syl.start, 1.55, places=2)

        # Nudge end: initial was 2.00s -> +0.10s = 2.10s
        editor._on_jog_nudge("end", 0.10)
        syl2 = editor._find_syllable("L2:S1")
        self.assertAlmostEqual(syl2.end, 2.10, places=2)

    def test_multi_selection_and_merge(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0", "L2:S1"]
        editor._refresh_ui()

        # Floating bar is visible, single toolbar is hidden
        self.assertTrue(editor.floating_multi_bar.visible)
        self.assertFalse(editor.docked_toolbar.visible)

        # Trigger merge on ordered_ids
        ordered_ids = ["L2:S0", "L2:S1"]
        res = editor._push_undo()
        from core.editor import merge_syllables
        merge_res = merge_syllables(editor.document, ordered_ids)
        self.assertTrue(merge_res.selected_ids)

        syls = list(editor.document.karaoke_syllables())
        self.assertEqual(len(syls), 2)
        self.assertEqual(syls[0].visible_text, "Hello")

    def test_layout_rebuild_portrait_vs_landscape(self):
        import flet as ft
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor._refresh_ui()

        # Portrait layout produces Column
        editor._rebuild_layout(is_landscape=False)
        self.assertIsInstance(editor.body_container.content, ft.Column)

        # Landscape layout produces 2-column Row (Split view)
        editor._rebuild_layout(is_landscape=True)
        self.assertIsInstance(editor.body_container.content, ft.Row)

    def test_undo_stack(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0"]
        editor._refresh_ui()

        initial_text = doc.dumps()

        # Change something (snap start to 1.10s)
        editor.audio_timeline.center_time = 1.10
        editor._on_jog_snap("start")
        self.assertFalse(editor.btn_undo.disabled)

        # Undo the change
        editor._undo()
        self.assertEqual(editor.document.dumps(), initial_text)
        self.assertTrue(editor.btn_undo.disabled)


if __name__ == "__main__":
    unittest.main()
