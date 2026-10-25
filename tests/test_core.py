import json
import tempfile
import unittest
from pathlib import Path

from karaoke_core.ass import AssDocument, KaraokeTagType
from karaoke_core.audacity import legacy_label_windows, load_audacity_labels
from karaoke_core.project import create_project, load_project, save_project
from karaoke_core.sps import (
    MeasurementTimeline, detect_bursts, find_strict_windows, legacy_windows,
    manual_bursts, selection_audition_bounds,
)


SAMPLE = """[Script Info]\r\nTitle: test\r\n\r\n[Events]\r\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\nDialogue: 0,0:00:10.00,0:00:12.00,Default,,0,0,0,,{\\k10}a{\\K10}b{\\kf10\\c&Hff}c{\\c\\ko10}d{\\kf10\\c&HFFFFFF}e\\N{\\org(-2000000,0)\\fr0.000573000}x\r\n"""


class AssCoreTests(unittest.TestCase):
    def test_exact_roundtrip_when_unmodified(self):
        doc = AssDocument.from_text(SAMPLE)
        self.assertEqual(doc.dumps(), SAMPLE)

    def test_all_karaoke_types_and_colour_state(self):
        doc = AssDocument.from_text(SAMPLE)
        syl = doc.karaoke_syllables()
        self.assertEqual([s.tag_type for s in syl], [KaraokeTagType.K, KaraokeTagType.CAPITAL_K, KaraokeTagType.KF, KaraokeTagType.KO, KaraokeTagType.KF])
        self.assertEqual([s.duration_cs for s in syl], [10, 10, 10, 10, 10])
        # c is red; bare \c before d resets; white must not be misread as red.
        self.assertEqual([s.burst_marked for s in syl], [False, False, True, False, False])

    def test_unknown_override_tags_survive_edit(self):
        doc = AssDocument.from_text(SAMPLE)
        syl = doc.karaoke_syllables()[2]
        doc.set_karaoke_type(syl, KaraokeTagType.K)
        out = doc.dumps()
        self.assertIn(r"\org(-2000000,0)\fr0.000573000", out)
        self.assertIn(r"\k10\c&Hff", out)

    def test_bom_is_preserved_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bom.ass"
            p.write_bytes(b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))
            doc = AssDocument.load(p)
            doc.save()
            self.assertEqual(p.read_bytes(), b"\xef\xbb\xbf" + SAMPLE.encode("utf-8"))


class ProjectTests(unittest.TestCase):
    def test_project_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            create_project(root, "demo")
            for name in ("source", "alignment", "subtitles", "cache", "exports"):
                self.assertTrue((root / name).is_dir())
            self.assertEqual(load_project(root).name, "demo")

    def test_ui_state_roundtrips_in_project_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            config = create_project(root, "demo")
            config.metadata["ui_state"] = {
                "version": 1,
                "active_tab": 2,
                "render": {"include_audio": False, "resolution_scale": "3"},
                "sps": {"loaded": True, "scope_ids": ["L0:S0"]},
            }
            save_project(root, config)
            restored = load_project(root)
            self.assertEqual(restored.metadata["ui_state"], config.metadata["ui_state"])


class SPSTests(unittest.TestCase):
    def _timeline(self):
        ass = """[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf10}a{\\kf10}b{\\kf10}c{\\kf10}d{\\kf10}e{\\kf10}f{\\kf10}g{\\kf10}h{\\kf10}i{\\kf10}j{\\kf10}k{\\kf10}l\n"""
        return MeasurementTimeline.from_karaoke(AssDocument.from_text(ass).karaoke_syllables())

    def test_strict_one_second(self):
        tl = self._timeline()
        best = max(find_strict_windows(tl.syllables), key=lambda w: w.speed)
        self.assertAlmostEqual(best.duration, 1.0)
        self.assertGreaterEqual(best.count, 10)

    def test_measurements_can_have_gaps(self):
        tl = self._timeline()
        a, b = tl.syllables[0], tl.syllables[1]
        tl.set_measurement(a.id, a.start + 0.02, a.end - 0.02)
        tl.set_measurement(b.id, b.start + 0.03, b.end - 0.01)
        self.assertLess(tl.syllables[0].effective_end, tl.syllables[1].effective_start)
        self.assertEqual(len(tl.changed()), 2)

    def test_measurement_end_can_precede_start_with_legacy_semantics(self):
        items = self._timeline().syllables[1:]
        # The first measured syllable uses the archived leading-"-"
        # convention: semantic Start is at 0.20, End at 0.10.
        items[0] = items[0].with_measurement(0.20, 0.10)
        self.assertGreater(items[0].effective_start, items[0].effective_end)
        windows = legacy_windows(items, measured=True)
        matching = next(window for window in windows if window.syllable_ids == tuple(item.id for item in items))
        self.assertAlmostEqual(matching.start, 0.20)
        self.assertAlmostEqual(matching.end, 1.20)
        self.assertAlmostEqual(matching.speed, len(items) / 1.0)

    def test_audition_of_reversed_single_syllable_stops_at_formal_end(self):
        item = self._timeline().syllables[0].with_measurement(0.09, 0.02)
        start, end, used_fallback = selection_audition_bounds([item], measured=True)
        self.assertTrue(used_fallback)
        self.assertAlmostEqual(start, item.start)
        self.assertAlmostEqual(end, 0.02)
        self.assertNotAlmostEqual(end, item.effective_start)

    def test_audition_of_multi_selection_never_expands_to_reversed_last_start(self):
        first, last = self._timeline().syllables[:2]
        last = last.with_measurement(last.end - 0.01, last.start + 0.02)
        start, end, used_fallback = selection_audition_bounds([first, last], measured=True)
        self.assertFalse(used_fallback)
        self.assertAlmostEqual(start, first.effective_start)
        self.assertAlmostEqual(end, last.effective_end)
        self.assertLess(end, last.effective_start)

    def test_connected_burst_expansion(self):
        tl = self._timeline()
        bursts = detect_bursts(tl.syllables, min_peak_sps=5, max_candidates=2)
        self.assertTrue(bursts)
        for burst in bursts:
            indices = [int(sid.split(":S")[-1]) for sid in burst.syllable_ids]
            self.assertEqual(indices, list(range(min(indices), max(indices) + 1)))

    def test_manual_red_regions(self):
        ass = """[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\\kf10}a{\\kf10\\c&HFF}b{\\kf10}c{\\c\\kf10}d\n"""
        tl = MeasurementTimeline.from_karaoke(AssDocument.from_text(ass).karaoke_syllables())
        bursts = manual_bursts(tl.syllables)
        self.assertEqual(len(bursts), 1)
        self.assertEqual(len(bursts[0].syllable_ids), 2)


class AudacityCompatibilityTests(unittest.TestCase):
    def test_archived_label_convention(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "labels.txt"
            p.write_text("0.000\t0.100\ta\n0.100\t0.200\t-b\n0.200\t1.050\tc\n", encoding="utf-8")
            labels = load_audacity_labels(p)
            self.assertEqual((labels[1].start, labels[1].end, labels[1].text), (0.2, 0.1, "b"))
            windows = legacy_label_windows(labels)
            self.assertTrue(windows)


if __name__ == "__main__":
    unittest.main()
