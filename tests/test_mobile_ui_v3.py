"""Unit tests for ui_v3 (Completely rewritten Workbench Touch UI)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

mobile_src = Path(__file__).resolve().parent.parent / "karaoke_mobile" / "src"
if str(mobile_src) not in sys.path:
    sys.path.insert(0, str(mobile_src))

from core.ass import AssDocument
from ui_v3.workbench import Workbench
from ui_v3.editor_view import EditorView


class TestUIv3Workbench(unittest.TestCase):
    def setUp(self):
        self.ass_text = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\k50}Hel{\\k50}lo{\\k100} World\n"
        )
        self.doc = AssDocument.from_text(self.ass_text)

    def test_workbench_initialization_and_load(self):
        wb = Workbench()
        self.assertIsNone(wb.document)
        self.assertEqual(len(wb.syllables), 0)

        wb.load_ass_text(self.ass_text)
        self.assertIsNotNone(wb.document)
        self.assertEqual(len(wb.syllables), 3)
        self.assertEqual(len(wb.overview.controls), 3)
        self.assertEqual(len(wb.detail.controls), 3)

    def test_workbench_selection_and_inspector(self):
        wb = Workbench()
        wb.load_ass_text(self.ass_text)

        # Select first syllable
        first_syl = wb.syllables[0]
        wb._select(first_syl.id)
        self.assertEqual(wb.selected_id, first_syl.id)
        self.assertEqual(wb.selected.visible_text, "Hel")

        # Test switching modes
        wb._switch("actions")
        self.assertEqual(wb.mode, "actions")
        self.assertGreater(len(wb.inspector.controls), 0)

        wb._switch("lines")
        self.assertEqual(wb.mode, "lines")
        self.assertGreater(len(wb.inspector.controls), 0)

        wb._switch("syllable")
        self.assertEqual(wb.mode, "syllable")
        self.assertGreater(len(wb.inspector.controls), 0)

    def test_workbench_undo_redo(self):
        from core.editor import set_syllable_text
        wb = Workbench()
        wb.load_ass_text(self.ass_text)
        wb._select(wb.syllables[0].id)

        # Mutate text
        wb._mutate(lambda: set_syllable_text(wb.document, wb.selected.id, "Modified"))
        self.assertEqual(wb.syllables[0].visible_text, "Modified")

        wb.undo()
        self.assertEqual(wb.syllables[0].visible_text, "Hel")

        wb.redo()
        self.assertEqual(wb.syllables[0].visible_text, "Modified")

    def test_editor_view_adapter(self):
        ev = EditorView()
        ev.load_ass_text(self.ass_text)
        self.assertEqual(len(ev.syllables), 3)

        ev.selected_syllable_id = ev.syllables[1].id
        self.assertEqual(ev.selected_syllable_id, ev.syllables[1].id)
        self.assertEqual(ev.selected.visible_text, "lo")

        # _refresh_ui compatibility call
        ev._refresh_ui()
        self.assertEqual(len(ev.overview.controls), 3)


if __name__ == "__main__":
    unittest.main()
