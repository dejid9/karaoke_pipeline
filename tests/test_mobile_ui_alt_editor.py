"""Comprehensive unit tests for ui_alt (Authentic PC-Workbench Karaoke Editor for Mobile)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

mobile_src = Path(__file__).resolve().parent.parent / "karaoke_mobile" / "src"
if str(mobile_src) not in sys.path:
    sys.path.insert(0, str(mobile_src))

from core.ass import AssDocument
from ui_alt.views.editor_view import EditorView as AltEditorView


class TestMobileUIAltEditor(unittest.TestCase):
    def setUp(self):
        self.ass_text = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\k50}Hel{\\k50}lo{\\k100} World\n"
        )

    def test_pc_editor_initialization_and_sync(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor._refresh_ui()

        # PC Subheader status and badges
        self.assertEqual(len(editor.audio_timeline.syllables), 3)
        self.assertEqual(editor.badge_syl_count.content.value, "3 слогов")
        self.assertEqual(editor.lbl_logo.value, "KARAOKE // SPS")

    def test_pc_transport_bar_controls(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor._refresh_ui()

        # Speed setting
        editor._set_speed(1.25)
        self.assertEqual(editor.audio_timeline.playback_speed, 1.25)
        self.assertEqual(editor.lbl_speed_text.value, "1.25×")

        # Range marker limits
        editor.audio_timeline.center_time = 1.20
        editor.audio_timeline.set_range_in()
        self.assertEqual(editor.audio_timeline.range_start, 1.20)

        editor.audio_timeline.center_time = 2.80
        editor.audio_timeline.set_range_out()
        self.assertEqual(editor.audio_timeline.range_end, 2.80)

        editor.audio_timeline.clear_range()
        self.assertIsNone(editor.audio_timeline.range_start)
        self.assertIsNone(editor.audio_timeline.range_end)

    def test_pc_card1_text_navigation_and_split_at_cursor(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0"]
        editor._refresh_ui()

        # Initial syllable is L2:S0 (Hel, 500ms)
        self.assertIn("L2:S0", editor.card1_title.value)
        self.assertEqual(editor.txt_syllable_editor.value, "Hel")

        # Navigation to next syllable
        editor._navigate_syllable(1)
        self.assertEqual(editor.selected_syllable_id, "L2:S1")
        self.assertEqual(editor.txt_syllable_editor.value, "lo")

        # Navigation back
        editor._navigate_syllable(-1)
        self.assertEqual(editor.selected_syllable_id, "L2:S0")

        # Split at cursor: s0 is 1.00 .. 1.50s. Place cursor at 1.25s
        editor.audio_timeline.center_time = 1.250
        editor._split_at_cursor()

        all_syls = list(editor.document.karaoke_syllables())
        self.assertEqual(len(all_syls), 4)

    def test_pc_card1_toggle_unspoken(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0"]
        editor._refresh_ui()

        # Mark as unspoken: "Hel" -> "[Hel]"
        editor._toggle_unspoken()
        syl = editor._get_selected_syl()
        self.assertEqual(syl.visible_text, "[Hel]")

        # Toggle back: "[Hel]" -> "Hel"
        editor._toggle_unspoken()
        syl2 = editor._get_selected_syl()
        self.assertEqual(syl2.visible_text, "Hel")

    def test_pc_card2_timing_and_merge(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0", "L2:S1"]
        editor._refresh_ui()

        # Merge selected syllables
        editor._merge_current()
        syls = list(editor.document.karaoke_syllables())
        self.assertEqual(len(syls), 2)
        self.assertEqual(syls[0].visible_text, "Hello")
        self.assertEqual(syls[0].duration_cs, 100)

    def test_pc_card2_burst_and_tags(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0"]
        editor._refresh_ui()

        # Tag switch to \ko
        editor.dd_tag_type.value = "ko"
        editor._apply_tag_type()
        syl = editor._get_selected_syl()
        self.assertEqual(syl.tag_type.value, "ko")

        # Apply Burst
        editor._color_burst(True)
        syl = editor._get_selected_syl()
        self.assertTrue(syl.burst_marked)

        # Remove Burst
        editor._color_burst(False)
        syl = editor._get_selected_syl()
        self.assertFalse(syl.burst_marked)

    def test_layout_rebuild_portrait_vs_landscape(self):
        import flet as ft
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor._refresh_ui()

        # Portrait layout produces Column with tab bar and active card
        editor._rebuild_layout(is_landscape=False)
        self.assertIsInstance(editor.body_container.content, ft.Column)

        # Landscape layout produces 2-column Row (Widescreen PC Workbench)
        editor._rebuild_layout(is_landscape=True)
        self.assertIsInstance(editor.body_container.content, ft.Row)

    def test_undo_redo_stack(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = AltEditorView()
        editor.document = doc
        editor.selected_syllable_ids = ["L2:S0"]
        editor._refresh_ui()

        initial_text = doc.dumps()

        # Change text
        editor.txt_syllable_editor.value = "Modified"
        editor._on_syllable_text_changed(None)
        self.assertEqual(editor._get_selected_syl().visible_text, "Modified")

        # Undo
        editor._undo()
        self.assertEqual(editor.document.dumps(), initial_text)

        # Redo
        editor._redo()
        self.assertEqual(editor._get_selected_syl().visible_text, "Modified")


if __name__ == "__main__":
    unittest.main()
