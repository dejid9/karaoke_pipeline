import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent.parent / "karaoke_mobile" / "src"))

from core.ass import AssDocument
from core.editor import (
    shift_syllable,
    set_syllable_duration,
    set_syllable_start_at_time,
    set_syllable_end_at_time,
    nudge_syllable_duration,
    redistribute_boundary,
    merge_syllables,
    colour_burst,
    uncolour_burst,
    KaraokeEditError,
)
from core.sps import MeasurementTimeline
from ui.views.sps_view import SPSView
from ui.views.editor_view import EditorView


class TestMobileTimingEditor(unittest.TestCase):
    def setUp(self):
        self.ass_text = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\k50}Hel{\\k50}lo{\\k100} World\n"
        )

    def test_shift_syllable_middle(self):
        doc = AssDocument.from_text(self.ass_text)
        syls = doc.karaoke_syllables()
        self.assertEqual(len(syls), 3)

        # Shift middle syllable (L2:S1) +10cs (+100ms) to the right
        res = shift_syllable(doc, "L2:S1", 10)
        self.assertEqual(res.action, "shift")

        new_syls = doc.karaoke_syllables()
        # s0 expands by +10cs
        self.assertEqual(new_syls[0].duration_cs, 60)
        self.assertEqual(new_syls[0].start, 1.0)
        self.assertAlmostEqual(new_syls[0].end, 1.6)

        # s1 shifts start by +10cs, same duration 50cs
        self.assertEqual(new_syls[1].duration_cs, 50)
        self.assertAlmostEqual(new_syls[1].start, 1.6)
        self.assertAlmostEqual(new_syls[1].end, 2.1)

        # s2 shrinks by -10cs to keep line end
        self.assertEqual(new_syls[2].duration_cs, 90)
        self.assertAlmostEqual(new_syls[2].start, 2.1)
        self.assertAlmostEqual(new_syls[2].end, 3.0)

    def test_shift_syllable_first_and_last(self):
        doc = AssDocument.from_text(self.ass_text)

        # Shift first syllable (L2:S0) right by +5cs (+50ms)
        shift_syllable(doc, "L2:S0", 5)
        new_syls = doc.karaoke_syllables()
        self.assertAlmostEqual(new_syls[0].start, 1.05)
        self.assertAlmostEqual(new_syls[0].end, 1.55)
        self.assertEqual(new_syls[0].duration_cs, 50)
        # next syllable compensates
        self.assertEqual(new_syls[1].duration_cs, 45)

        # Shift last syllable (L2:S2) right by +10cs (+100ms)
        shift_syllable(doc, "L2:S2", 10)
        new_syls2 = doc.karaoke_syllables()
        # prev syllable expands by 10cs
        self.assertEqual(new_syls2[1].duration_cs, 55)
        # last syllable duration stays 100cs, but ends later
        self.assertEqual(new_syls2[2].duration_cs, 100)

    def test_shift_syllable_boundary_limit(self):
        doc = AssDocument.from_text(self.ass_text)
        # Shifting s1 by -60cs exceeds s0's duration (50cs)
        with self.assertRaises(KaraokeEditError):
            shift_syllable(doc, "L2:S1", -60)

    def test_set_syllable_duration(self):
        doc = AssDocument.from_text(self.ass_text)
        set_syllable_duration(doc, "L2:S0", 80)
        new_syls = doc.karaoke_syllables()
        self.assertEqual(new_syls[0].duration_cs, 80)

    def test_set_syllable_start_and_end_at_time(self):
        doc = AssDocument.from_text(self.ass_text)

        # Snap start of s1 to 1.70s
        set_syllable_start_at_time(doc, "L2:S1", 1.70)
        new_syls = doc.karaoke_syllables()
        self.assertAlmostEqual(new_syls[0].end, 1.70)
        self.assertAlmostEqual(new_syls[1].start, 1.70)

        # Snap end of s1 to 2.20s
        set_syllable_end_at_time(doc, "L2:S1", 2.20)
        new_syls2 = doc.karaoke_syllables()
        self.assertAlmostEqual(new_syls2[1].end, 2.20)
        self.assertAlmostEqual(new_syls2[2].start, 2.20)

    def test_sps_view_fine_steppers_and_cursor_snap(self):
        doc = AssDocument.from_text(self.ass_text)
        sps_view = SPSView()
        sps_view.set_document(doc)

        self.assertIsNotNone(sps_view.timeline)
        s1_id = sps_view.timeline.syllables[0].id
        sps_view.focus_syllable(s1_id)

        # Initial values: start = 1.0, end = 1.5
        find_syl = lambda sid: next((s for s in sps_view.timeline.syllables if s.id == sid), None)
        syl = find_syl(s1_id)
        self.assertAlmostEqual(syl.effective_start, 1.0)
        self.assertAlmostEqual(syl.effective_end, 1.5)

        # Nudge start by +1ms
        sps_view._nudge("start", 0.001)
        syl_after = find_syl(s1_id)
        self.assertAlmostEqual(syl_after.effective_start, 1.001, places=3)

        # Nudge start by -5ms
        sps_view._nudge("start", -0.005)
        syl_after2 = find_syl(s1_id)
        self.assertAlmostEqual(syl_after2.effective_start, 0.996, places=3)

        # Test cursor snap for Start and End
        sps_view.audio_timeline.center_time = 1.123
        sps_view._set_start_from_cursor(None)
        syl_cur_start = find_syl(s1_id)
        self.assertAlmostEqual(syl_cur_start.effective_start, 1.123, places=3)

        sps_view.audio_timeline.center_time = 1.678
        sps_view._set_end_from_cursor(None)
        syl_cur_end = find_syl(s1_id)
        self.assertAlmostEqual(syl_cur_end.effective_end, 1.678, places=3)

    def test_editor_view_syllable_sync(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = EditorView()
        editor.document = doc
        editor._refresh_ui()

        # Check syllables synced to audio_timeline
        self.assertEqual(len(editor.audio_timeline.syllables), 3)

        # Select a syllable via timeline callback
        editor._on_timeline_syllable_clicked("L2:S0")
        self.assertEqual(editor.selected_syllable_id, "L2:S0")
        self.assertTrue(editor.docked_toolbar.visible)

        # Check mode tabs switching
        self.assertEqual(editor.toolbar_mode, "dur")
        editor.toolbar_mode = "seam"
        editor._refresh_ui()
        self.assertEqual(editor.toolbar_mode, "seam")

        editor.toolbar_mode = "shift"
        editor._refresh_ui()
        self.assertEqual(editor.toolbar_mode, "shift")

    def test_audio_timeline_collapse_expand_cycle(self):
        from ui.components.audio_timeline import AudioTimelineWidget
        tl = AudioTimelineWidget()

        # Initial state (expanded)
        tl.collapsed = False
        tl._refresh_timeline()
        self.assertTrue(tl.top_controls_row2.visible)

        # Toggle collapse
        tl._toggle_collapse()
        self.assertTrue(tl.collapsed)
        self.assertFalse(tl.top_controls_row2.visible)
        self.assertFalse(tl.timeline_image.visible)

        # Toggle back to expanded
        tl._toggle_collapse()
        self.assertFalse(tl.collapsed)
        self.assertTrue(tl.top_controls_row2.visible)

    def test_editor_multi_select_and_merge(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = EditorView()
        editor.document = doc
        editor._refresh_ui()

        # Multi-select first two syllables: "L2:S0", "L2:S1"
        editor.selected_syllable_ids = ["L2:S0", "L2:S1"]
        editor._refresh_ui()
        self.assertEqual(len(editor.selected_syllable_ids), 2)
        self.assertTrue(editor.docked_toolbar.visible)

        # Merge selected syllables
        res = merge_syllables(editor.document, editor.selected_syllable_ids)
        self.assertTrue(res.selected_ids)
        new_syls = list(editor.document.karaoke_syllables())
        # Was 3, now 2 syllables
        self.assertEqual(len(new_syls), 2)
        # Combined duration: 50cs + 50cs = 100cs
        self.assertEqual(new_syls[0].duration_cs, 100)
        self.assertEqual(new_syls[0].visible_text, "Hello")

    def test_editor_multi_select_burst(self):
        doc = AssDocument.from_text(self.ass_text)
        editor = EditorView()
        editor.document = doc
        editor._refresh_ui()

        # Multi-select all 3 syllables
        all_ids = [s.id for s in doc.karaoke_syllables()]
        colour_burst(editor.document, all_ids)
        for s in editor.document.karaoke_syllables():
            self.assertTrue(s.burst_marked)

        uncolour_burst(editor.document, all_ids)
        for s in editor.document.karaoke_syllables():
            self.assertFalse(s.burst_marked)

    def test_editor_dialogs_open_and_close(self):
        import flet as ft

        class MockPage:
            def __init__(self):
                self.opened_dialogs = []
                self.closed_dialogs = []
                self.services = []
                self.overlay = []

            def show_dialog(self, dlg):
                self.opened_dialogs.append(dlg)

            def pop_dialog(self):
                if self.opened_dialogs:
                    dlg = self.opened_dialogs.pop()
                    self.closed_dialogs.append(dlg)
                    return dlg
                return None

            def update(self):
                pass

        doc = AssDocument.from_text(self.ass_text)
        editor = EditorView()
        editor.document = doc
        mock_p = MockPage()
        editor.set_page(mock_p)
        editor._refresh_ui()

        s0 = list(doc.karaoke_syllables())[0]

        # Test Text Dialog
        editor._open_text_dialog(s0)
        self.assertEqual(len(mock_p.opened_dialogs), 1)
        editor._close_dialog()
        self.assertEqual(len(mock_p.closed_dialogs), 1)

        # Test Timing Dialog
        editor._open_timing_dialog(s0)
        self.assertEqual(len(mock_p.opened_dialogs), 1)
        editor._close_dialog()
        self.assertEqual(len(mock_p.closed_dialogs), 2)


if __name__ == "__main__":
    unittest.main()
