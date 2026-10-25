from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from karaoke_core.ass import AssDocument, KaraokeTagType
from karaoke_core.editor import (
    colour_burst,
    delete_syllable,
    insert_after,
    merge_syllables,
    redistribute_boundary,
    set_syllable_contents,
    set_syllable_romanization,
    set_syllable_visible_texts,
    set_tag_type,
    split_syllable,
    uncolour_burst,
)
from karaoke_gui.session import KaraokeSession


HEADER = """[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""


def doc_for(text: str, *, start="0:00:01.00", end="0:00:05.00") -> AssDocument:
    return AssDocument.from_text(HEADER + f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")


class KaraokeEditorCoreTests(unittest.TestCase):
    def test_colour_burst_writes_legacy_open_and_reset_tags(self):
        doc = doc_for(r"{\kf10}a{\kf10}b{\kf10}c{\kf10}d")
        result = colour_burst(doc, ["L4:S1", "L4:S2"])
        self.assertIn(r"{\kf10\c&Hff}b{\kf10}c{\kf10\c}d", doc.dumps())
        self.assertEqual(
            [item.burst_marked for item in doc.karaoke_syllables()],
            [False, True, True, False],
        )
        self.assertEqual(result.selected_ids, ("L4:S1", "L4:S2"))

    def test_colour_burst_at_event_end_appends_reset_after_last_syllable(self):
        doc = doc_for(r"{\kf10}a{\kf10}b{\kf10}c")
        colour_burst(doc, ["L4:S1", "L4:S2"])
        self.assertIn(r"{\kf10\c&Hff}b{\kf10}c{\c}", doc.dumps())
        self.assertEqual(
            [item.burst_marked for item in doc.karaoke_syllables()],
            [False, True, True],
        )

    def test_colour_burst_accepts_omitted_timing_gap_from_sps_selection(self):
        doc = doc_for(r"{\kf10}a{\k5}{\kf10}b{\kf10}c")
        colour_burst(doc, ["L4:S0", "L4:S2"])
        self.assertIn(r"{\kf10\c&Hff}a{\k5}{\kf10}b{\kf10\c}c", doc.dumps())
        self.assertEqual(
            [item.burst_marked for item in doc.karaoke_syllables()],
            [True, True, True, False],
        )

    def test_burst_colour_can_be_removed_or_split_without_touching_timing(self):
        doc = doc_for(r"{\kf10}a{\kf10\c&Hff}b{\kf10}c{\kf10}d{\kf10\c}e")
        before = [item.duration_cs for item in doc.karaoke_syllables()]
        uncolour_burst(doc, ["L4:S2"])
        syllables = doc.karaoke_syllables()
        self.assertEqual([item.duration_cs for item in syllables], before)
        self.assertEqual(
            [item.burst_marked for item in syllables],
            [False, True, False, True, False],
        )

    def test_manual_romanization_is_hidden_metadata_and_edits_with_text(self):
        doc = doc_for(r"{\kf10}ろ{\kf10}ま")
        set_syllable_romanization(doc, "L4:S0", "ro")
        set_syllable_contents(
            doc,
            text_values={"L4:S1": "字"},
            romanization_values={"L4:S1": "ma"},
        )
        syllables = doc.karaoke_syllables()
        self.assertEqual([item.visible_text for item in syllables], ["ろ", "字"])
        self.assertEqual([item.romanization for item in syllables], ["ro", "ma"])
        self.assertIn(r"\_kr", doc.dumps())
        self.assertNotIn("roろ", doc.dumps())

    def test_merge_combines_manual_romanization(self):
        doc = doc_for(r"{\kf10}ろ{\kf10}ま")
        set_syllable_romanization(doc, "L4:S0", "ro")
        set_syllable_romanization(doc, "L4:S1", "ma")
        merge_syllables(doc, ["L4:S0", "L4:S1"])
        syllables = doc.karaoke_syllables()
        self.assertEqual(len(syllables), 1)
        self.assertEqual(syllables[0].romanization, "roma")

    def test_insert_splits_odd_duration_without_moving_text(self):
        doc = doc_for(r"{\kf5\c&HFF}abc{\kf7}de")
        result = insert_after(doc, "L4:S0", new_type=KaraokeTagType.K)
        syllables = doc.karaoke_syllables()
        self.assertEqual([s.duration_cs for s in syllables], [2, 3, 7])
        self.assertEqual([s.visible_text for s in syllables], ["abc", "", "de"])
        self.assertEqual(syllables[1].tag_type, KaraokeTagType.K)
        self.assertIn(r"\c&HFF", doc.dumps())
        self.assertEqual(result.selected_ids, ("L4:S1",))

    def test_split_halves_text_and_preserves_inline_override(self):
        doc = doc_for(r"{\kf5\org(-2000000,0)}a{\bord2}bcd{\kf4}z")
        split_syllable(doc, "L4:S0", new_type=KaraokeTagType.KF)
        syllables = doc.karaoke_syllables()
        self.assertEqual([s.duration_cs for s in syllables], [2, 3, 4])
        self.assertEqual(syllables[0].visible_text, "ab")
        self.assertEqual(syllables[1].visible_text, "cd")
        self.assertIn(r"\org(-2000000,0)", doc.dumps())
        self.assertIn(r"\bord2", doc.dumps())
        self.assertEqual(sum(s.duration_cs for s in syllables), 9)

    def test_timeline_split_replaces_original_text_instead_of_duplicating_it(self):
        from karaoke_core.editor import split_syllable_at_time
        doc = doc_for(r"{\kf100}gonna ", start="0:00:00.00", end="0:00:01.00")
        split_syllable_at_time(doc, "L4:S0", 0.50)
        syllables = doc.karaoke_syllables()
        self.assertEqual([s.visible_text for s in syllables], ["gon", "na "])
        self.assertNotEqual(syllables[0].visible_text, "gonna ")

    def test_merge_keeps_non_karaoke_commands_from_removed_tag_blocks(self):
        doc = doc_for(r"{\kf4}ab{\kf5\c&HFF}cd{\ko6\fr0.01}ef")
        merge_syllables(doc, ["L4:S0", "L4:S1", "L4:S2"])
        syllables = doc.karaoke_syllables()
        self.assertEqual(len(syllables), 1)
        self.assertEqual(syllables[0].duration_cs, 15)
        self.assertEqual(syllables[0].visible_text, "abcdef")
        dumped = doc.dumps()
        self.assertIn(r"\c&HFF", dumped)
        self.assertIn(r"\fr0.01", dumped)
        self.assertEqual(dumped.count(r"\kf") + dumped.count(r"\ko"), 1)

    def test_delete_transfers_duration_to_next_and_preserves_colour(self):
        doc = doc_for(r"{\kf4\c&HFF}DELETE{\kf7}keep{\kf3\c}tail")
        delete_syllable(doc, "L4:S0")
        syllables = doc.karaoke_syllables()
        self.assertEqual([s.duration_cs for s in syllables], [11, 3])
        self.assertEqual([s.visible_text for s in syllables], ["keep", "tail"])
        self.assertNotIn("DELETE", doc.dumps())
        self.assertIn(r"\c&HFF", doc.dumps())
        self.assertEqual(sum(s.duration_cs for s in syllables), 14)

    def test_delete_last_transfers_duration_to_previous(self):
        doc = doc_for(r"{\k4}a{\k7}b")
        result = delete_syllable(doc, "L4:S1")
        syllables = doc.karaoke_syllables()
        self.assertEqual(len(syllables), 1)
        self.assertEqual(syllables[0].duration_cs, 11)
        self.assertEqual(syllables[0].visible_text, "a")
        self.assertEqual(result.selected_ids, ("L4:S0",))

    def test_boundary_redistribution_snaps_to_centiseconds_and_keeps_sum(self):
        doc = doc_for(r"{\kf10}a{\kf10}b")
        redistribute_boundary(doc, "L4:S0", "L4:S1", 1.134)
        syllables = doc.karaoke_syllables()
        self.assertEqual([s.duration_cs for s in syllables], [13, 7])
        self.assertAlmostEqual(syllables[0].end, 1.13, places=6)
        self.assertAlmostEqual(syllables[1].end, 1.20, places=6)

    def test_type_change_preserves_unknown_tags(self):
        doc = doc_for(r"{\k8\org(-2000000,0)\fr0.001}abc")
        set_tag_type(doc, ["L4:S0"], KaraokeTagType.KF)
        dumped = doc.dumps()
        self.assertIn(r"\kf8", dumped)
        self.assertIn(r"\org(-2000000,0)", dumped)
        self.assertIn(r"\fr0.001", dumped)


class KaraokeSessionEditTests(unittest.TestCase):
    def test_romanization_is_undoable(self):
        with tempfile.TemporaryDirectory() as td:
            ass = Path(td) / "song.ass"
            ass.write_text(
                HEADER + r"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\kf10}ろ" + "\n",
                encoding="utf-8",
            )
            session = KaraokeSession()
            session.open_subtitles(ass)
            session.edit_romanization("L4:S0", "ro")
            self.assertEqual(session.document.karaoke_syllables()[0].romanization, "ro")
            self.assertTrue(session.undo())
            self.assertEqual(session.document.karaoke_syllables()[0].romanization, "")

    def test_burst_colour_is_undoable_and_keeps_measurement_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            ass = Path(td) / "song.ass"
            ass.write_text(
                HEADER + r"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\kf5}a{\kf5}b{\kf5}c" + "\n",
                encoding="utf-8",
            )
            session = KaraokeSession()
            session.open_subtitles(ass)
            sidecar = session.measurement_sidecar_path()
            assert sidecar is not None
            sidecar.write_text(json.dumps({"version": 1, "measurements": []}), encoding="utf-8")
            session.edit_burst_colour(["L4:S1", "L4:S2"])
            self.assertTrue(sidecar.exists())
            self.assertEqual(
                [item.burst_marked for item in session.document.karaoke_syllables()],
                [False, True, True],
            )
            self.assertTrue(session.undo())
            self.assertNotIn(r"\c&Hff", session.document.dumps())

    def test_undo_redo_save_backup_and_stale_measurement_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ass = root / "song.ass"
            original = (HEADER + r"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\kf5}ab{\kf7}cd" + "\n")
            ass.write_text(original, encoding="utf-8")
            session = KaraokeSession()
            session.open_subtitles(ass)

            # Simulate an Update-003 sidecar. Structural/timing edits must stop
            # it from being silently applied to shifted IDs later.
            sidecar = session.measurement_sidecar_path()
            assert sidecar is not None
            sidecar.write_text(json.dumps({"version": 1, "measurements": []}), encoding="utf-8")

            session.edit_split("L4:S0", new_type=KaraokeTagType.KF)
            self.assertTrue(session.dirty)
            self.assertFalse(sidecar.exists())
            self.assertIsNotNone(session.last_measurement_archive)
            self.assertTrue(session.last_measurement_archive.exists())
            changed = session.document.dumps()
            self.assertNotEqual(changed, original)

            self.assertTrue(session.undo())
            self.assertEqual(session.document.dumps().replace("\r\n", "\n"), original.replace("\r\n", "\n"))
            self.assertTrue(session.redo())
            self.assertEqual(session.document.dumps().replace("\r\n", "\n"), changed.replace("\r\n", "\n"))

            saved = session.save_subtitles()
            self.assertEqual(saved, ass.resolve())
            self.assertFalse(session.dirty)
            backup = ass.with_name(ass.name + ".bak")
            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_text(encoding="utf-8").replace("\r\n", "\n"), original.replace("\r\n", "\n"))
            self.assertEqual(ass.read_text(encoding="utf-8").replace("\r\n", "\n"), changed.replace("\r\n", "\n"))

    def test_type_only_edit_does_not_stale_measurements(self):
        with tempfile.TemporaryDirectory() as td:
            ass = Path(td) / "song.ass"
            ass.write_text(HEADER + r"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\k5}ab" + "\n", encoding="utf-8")
            session = KaraokeSession()
            session.open_subtitles(ass)
            sidecar = session.measurement_sidecar_path()
            assert sidecar is not None
            sidecar.write_text(json.dumps({"version": 1, "measurements": []}), encoding="utf-8")
            session.edit_tag_type(["L4:S0"], KaraokeTagType.KF)
            self.assertTrue(sidecar.exists())
            self.assertIsNone(session.last_measurement_archive)

class KaraokeTextEditorCoreTests(unittest.TestCase):
    def test_text_edit_preserves_timing_and_explicit_inline_tags(self):
        from karaoke_core.editor import set_syllable_text
        doc = doc_for(r"{\kf5}a{\bord2}bc{\kf7}de")
        before = [(s.start, s.end, s.duration_cs) for s in doc.karaoke_syllables()]
        set_syllable_text(doc, "L4:S0", r"x{\bord2}yz")
        syllables = doc.karaoke_syllables()
        self.assertEqual([(s.start, s.end, s.duration_cs) for s in syllables], before)
        self.assertEqual(syllables[0].visible_text, "xyz")
        self.assertIn(r"\bord2", doc.dumps())

    def test_text_edit_rejects_embedded_karaoke_command(self):
        from karaoke_core.editor import KaraokeEditError, set_syllable_text
        doc = doc_for(r"{\kf5}abc{\kf7}de")
        with self.assertRaises(KaraokeEditError):
            set_syllable_text(doc, "L4:S0", r"ab{\kf2}c")

    def test_unspoken_markup_is_one_syllable_and_rejects_unbalanced_brackets(self):
        from karaoke_core.editor import KaraokeEditError, set_syllable_text
        doc = doc_for(r"{\kf20}puta a")
        set_syllable_text(doc, "L4:S0", "pu[ta a]")
        syllables = doc.karaoke_syllables()
        self.assertEqual(len(syllables), 1)
        self.assertEqual(syllables[0].visible_text, "pu[ta a]")
        with self.assertRaises(KaraokeEditError):
            set_syllable_text(doc, "L4:S0", "pu[ta a")

    def test_whole_text_edit_preserves_timing_ids_and_inline_overrides(self):
        doc = doc_for(r"{\kf10}ab{\bord2}{\kf20\c&Hff}cd{\c}")
        before = [
            (item.id, item.start, item.end, item.duration_cs)
            for item in doc.karaoke_syllables()
        ]
        set_syllable_visible_texts(
            doc,
            {"L4:S0": "a\nnew", "L4:S1": "c[not said]d"},
        )
        syllables = doc.karaoke_syllables()
        self.assertEqual(
            [(item.id, item.start, item.end, item.duration_cs) for item in syllables],
            before,
        )
        self.assertEqual([item.visible_text for item in syllables], ["a\nnew", "c[not said]d"])
        self.assertIn(r"\bord2", doc.dumps())
        self.assertIn(r"{\c}", doc.dumps())

    def test_split_at_cursor_uses_draft_and_keeps_odd_duration_exact(self):
        from karaoke_core.editor import split_syllable_at_raw_offset
        doc = doc_for(r"{\kf5}abcd{\kf7}z")
        result = split_syllable_at_raw_offset(
            doc, "L4:S0", 2, raw_text=r"xyUV", new_type=KaraokeTagType.KO
        )
        syllables = doc.karaoke_syllables()
        self.assertEqual([s.duration_cs for s in syllables], [2, 3, 7])
        self.assertEqual([s.visible_text for s in syllables], ["xy", "UV", "z"])
        self.assertEqual(syllables[1].tag_type, KaraokeTagType.KO)
        self.assertEqual(result.selected_ids, ("L4:S0", "L4:S1"))

    def test_split_at_cursor_rejects_cursor_inside_override_tag(self):
        from karaoke_core.editor import KaraokeEditError, split_syllable_at_raw_offset
        doc = doc_for(r"{\kf6}a{\bord2}bc{\kf4}z")
        raw = doc.karaoke_syllables()[0].raw_text
        inside = raw.index("bord") + 2
        with self.assertRaises(KaraokeEditError):
            split_syllable_at_raw_offset(doc, "L4:S0", inside)


class KaraokeTextSessionTests(unittest.TestCase):
    def test_text_only_edit_keeps_measurement_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            ass = Path(td) / "song.ass"
            ass.write_text(HEADER + r"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\kf5}ab{\kf5}cd" + "\n", encoding="utf-8")
            session = KaraokeSession()
            session.open_subtitles(ass)
            sidecar = session.measurement_sidecar_path()
            assert sidecar is not None
            sidecar.write_text(json.dumps({"version": 1, "measurements": []}), encoding="utf-8")
            session.edit_text("L4:S0", "hello")
            self.assertTrue(sidecar.exists())
            self.assertIsNone(session.last_measurement_archive)
            self.assertEqual(session.document.karaoke_syllables()[0].visible_text, "hello")


class KaraokeDraftLifecycleTests(unittest.TestCase):
    def test_stale_pre_split_editor_text_is_not_saved_for_shortened_left_id(self):
        from types import SimpleNamespace
        from karaoke_gui.app import KaraokeApp

        class Editor:
            @staticmethod
            def cget(_name):
                return "normal"

        fake = SimpleNamespace(
            _karaoke_text_bound_id="L4:S0",
            _karaoke_text_bound_raw="gonna ",
            _loading_karaoke_text=False,
            _karaoke_text_drafts={},
            karaoke_text_editor=Editor(),
            _source_for_karaoke_id=lambda _sid: SimpleNamespace(raw_text="gon"),
            _text_editor_value=lambda: "gonna ",
            _refresh_labels=lambda: None,
        )
        KaraokeApp._remember_current_karaoke_draft(fake)
        self.assertNotIn("L4:S0", fake._karaoke_text_drafts)


if __name__ == "__main__":
    unittest.main()
