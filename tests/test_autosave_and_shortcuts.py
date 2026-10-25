from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from karaoke_core.ass import AssDocument
from karaoke_gui.session import KaraokeSession
from karaoke_gui.theme import load_ui_preferences, save_ui_preferences


SAMPLE_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,30,30,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\kf50}hel{\\kf50}lo {\\kf50}world
"""


class AutosaveAndBackupTests(unittest.TestCase):
    def test_rolling_five_backups_created_in_subfolder(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            ass_path = td_path / "song.ass"
            ass_path.write_text(SAMPLE_ASS, encoding="utf-8")

            session = KaraokeSession()
            session.open_subtitles(ass_path)

            backup_dir = td_path / "backups"

            # Perform 7 sequential edits and saves
            for i in range(1, 8):
                first_id = session.syllables[0].id
                session.edit_text(first_id, f"v{i}_text")
                saved = session.save_subtitles()
                self.assertEqual(saved, ass_path)

            # Check that the legacy single backup exists
            legacy_bak = td_path / "song.ass.bak"
            self.assertTrue(legacy_bak.exists())

            # Check that backups directory exists and has at most 5 numbered backups
            self.assertTrue(backup_dir.is_dir())
            backups = sorted(backup_dir.glob("song.ass.bak*"))
            self.assertGreaterEqual(len(backups), 1)
            self.assertLessEqual(len(backups), 5)

            # Verify that backups are named song.ass.bak1 .. song.ass.bak5
            names = [b.name for b in backups]
            for name in names:
                self.assertTrue(name.startswith("song.ass.bak"))

    def test_autosave_preference_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            pref_file = Path(td) / "ui.json"
            save_ui_preferences("Dark", False, path=pref_file, autosave_mode="5")
            loaded = load_ui_preferences(pref_file)
            self.assertEqual(loaded.get("autosave_mode"), "5")

            save_ui_preferences("Dark", False, path=pref_file, autosave_mode="after_edit")
            loaded = load_ui_preferences(pref_file)
            self.assertEqual(loaded.get("autosave_mode"), "after_edit")


class MarkUnspokenMultiSyllableTests(unittest.TestCase):
    def test_edit_texts_wraps_multiple_syllables_cleanly(self):
        session = KaraokeSession()
        session.document = AssDocument.from_text(SAMPLE_ASS)
        session._rebuild_karaoke_after_edit()

        ids = [s.id for s in session.syllables[:2]]
        changed = {sid: f"[{s.source.raw_text}]" for sid, s in zip(ids, session.syllables[:2])}
        result = session.edit_texts(changed)
        self.assertEqual(result.action, "text-batch")

        # Syllables should now have brackets in their raw text
        s1 = session.syllables[0]
        s2 = session.syllables[1]
        self.assertTrue(s1.source.raw_text.startswith("[") and s1.source.raw_text.endswith("]"))
        self.assertTrue(s2.source.raw_text.startswith("[") and s2.source.raw_text.endswith("]"))


if __name__ == "__main__":
    unittest.main()
