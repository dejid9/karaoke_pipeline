from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from karaoke_core.alignment import (
    AlignmentConversionSettings,
    AlignmentError,
    MFACommandSettings,
    build_mfa_align_command,
    convert_textgrid_to_ass,
    load_textgrid,
)
from karaoke_core.ass import AssDocument
from karaoke_core.sps import MeasurementTimeline, find_strict_windows
from karaoke_core.syllables import SyllableConversionError


TEXTGRID = '''File type = "ooTextFile"\nObject class = "TextGrid"\n\nxmin = 0\nxmax = 1.23\ntiers? <exists>\nsize = 2\nitem []:\n    item [1]:\n        class = "IntervalTier"\n        name = "words"\n        xmin = 0\n        xmax = 1.23\n        intervals: size = 3\n        intervals [1]:\n            xmin = 0\n            xmax = 0.47\n            text = "hello"\n        intervals [2]:\n            xmin = 0.47\n            xmax = 0.61\n            text = ""\n        intervals [3]:\n            xmin = 0.61\n            xmax = 1.23\n            text = "world"\n    item [2]:\n        class = "IntervalTier"\n        name = "phones"\n        xmin = 0\n        xmax = 1.23\n        intervals: size = 9\n        intervals [1]:\n            xmin = 0\n            xmax = 0.10\n            text = "h"\n        intervals [2]:\n            xmin = 0.10\n            xmax = 0.21\n            text = "e"\n        intervals [3]:\n            xmin = 0.21\n            xmax = 0.33\n            text = "l"\n        intervals [4]:\n            xmin = 0.33\n            xmax = 0.47\n            text = "o"\n        intervals [5]:\n            xmin = 0.47\n            xmax = 0.61\n            text = "sp"\n        intervals [6]:\n            xmin = 0.61\n            xmax = 0.76\n            text = "w"\n        intervals [7]:\n            xmin = 0.76\n            xmax = 0.90\n            text = "er"\n        intervals [8]:\n            xmin = 0.90\n            xmax = 1.07\n            text = "l"\n        intervals [9]:\n            xmin = 1.07\n            xmax = 1.23\n            text = "d"\n'''


class TextGridTests(unittest.TestCase):
    def test_parse_mfa_long_textgrid(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a.TextGrid"
            path.write_text(TEXTGRID, encoding="utf-8")
            grid = load_textgrid(path)
            self.assertEqual(grid.tier_names, ("words", "phones"))
            self.assertEqual(len(grid.tier("words").intervals), 3)
            self.assertAlmostEqual(grid.xmax, 1.23)

    def test_conversion_preserves_total_centiseconds_and_real_gap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tg = root / "a.TextGrid"
            out = root / "a.ass"
            transcript = root / "a.txt"
            tg.write_text(TEXTGRID, encoding="utf-8")
            transcript.write_text("Hello, world!", encoding="utf-8")
            report = convert_textgrid_to_ass(
                tg, out, transcript_path=transcript,
                settings=AlignmentConversionSettings(max_words_per_line=8, max_gap_seconds=0.7),
            )
            self.assertTrue(report.phone_tier_used)
            self.assertTrue(report.transcript_tokens_used)
            self.assertEqual(report.words, 2)
            self.assertEqual(report.lines, 1)
            self.assertEqual(report.timing_gaps, 1)

            doc = AssDocument.load(out)
            event = doc.events()[0]
            syllables = doc.karaoke_syllables()
            self.assertEqual(sum(s.duration_cs for s in syllables), 123)
            self.assertAlmostEqual(event.end - event.start, 1.23, places=2)
            gaps = [s for s in syllables if not s.visible_text.strip()]
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0].duration_cs, 14)
            visible = "".join(s.visible_text for s in syllables)
            self.assertIn("Hello,", visible)
            self.assertIn("world!", visible)

            # Timing-only gap remains on the karaoke timeline but must not be an
            # extra syllable in SPS calculations.
            timeline = MeasurementTimeline.from_karaoke(syllables)
            windows = find_strict_windows(timeline.syllables, window=2.0, mode="contained")
            best = max(windows, key=lambda w: w.count)
            self.assertEqual(best.count, report.visible_syllables)
            self.assertNotIn(gaps[0].id, best.syllable_ids)

    def test_missing_word_tier_is_explicit_error(self):
        broken = TEXTGRID.replace('name = "words"', 'name = "utterances"')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tg = root / "a.TextGrid"
            tg.write_text(broken, encoding="utf-8")
            with self.assertRaises(AlignmentError):
                convert_textgrid_to_ass(tg, root / "a.ass")

    def test_conversion_without_restore_transcript_succeeds_without_txt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tg = root / "a.TextGrid"
            out = root / "a.ass"
            tg.write_text(TEXTGRID, encoding="utf-8")
            report = convert_textgrid_to_ass(
                tg, out, transcript_path=None,
                settings=AlignmentConversionSettings(
                    max_words_per_line=8, max_gap_seconds=0.7,
                    restore_transcript_text=False,
                ),
            )
            self.assertFalse(report.text_restored)
            self.assertFalse(report.transcript_tokens_used)
            self.assertEqual(report.words, 2)
            self.assertEqual(report.lines, 1)

            doc = AssDocument.load(out)
            visible = "".join(s.visible_text for s in doc.karaoke_syllables())
            self.assertIn("hello", visible)
            self.assertIn("world", visible)

    def test_conversion_with_differing_script_succeeds_when_restore_is_false(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tg = root / "a.TextGrid"
            out = root / "a.ass"
            transcript = root / "burmese.txt"
            tg.write_text(TEXTGRID, encoding="utf-8")
            transcript.write_text("ဒီလိုက်းတွေ မတာအိုင်းနေတ်လေ", encoding="utf-8")
            report = convert_textgrid_to_ass(
                tg, out, transcript_path=transcript,
                settings=AlignmentConversionSettings(
                    max_words_per_line=8, max_gap_seconds=0.7,
                    restore_transcript_text=False,
                ),
            )
            self.assertFalse(report.text_restored)
            self.assertFalse(report.transcript_tokens_used)
            doc = AssDocument.load(out)
            visible = "".join(s.visible_text for s in doc.karaoke_syllables())
            self.assertIn("hello", visible)

    def test_conversion_with_differing_script_raises_when_restore_is_true(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tg = root / "a.TextGrid"
            out = root / "a.ass"
            transcript = root / "burmese.txt"
            tg.write_text(TEXTGRID, encoding="utf-8")
            transcript.write_text("ဒီလိုက်းတွေ မတာအိုင်းနေတ်လေ", encoding="utf-8")
            with self.assertRaises(SyllableConversionError) as ctx:
                convert_textgrid_to_ass(
                    tg, out, transcript_path=transcript,
                    settings=AlignmentConversionSettings(
                        max_words_per_line=8, max_gap_seconds=0.7,
                        restore_transcript_text=True,
                    ),
                )
            self.assertIn("слишком сильно отличается", str(ctx.exception))


class MFACommandTests(unittest.TestCase):
    def test_hf_command_is_explicit_and_uses_long_textgrid(self):
        cmd = build_mfa_align_command(
            "corpus", "aligned",
            MFACommandSettings(model="japanese_mfa", mode="hf", use_g2p=True, num_jobs=4),
        )
        self.assertEqual(cmd[:4], ["mfa", "align_hf", "corpus", "japanese_mfa"])
        self.assertIn("--use_g2p", cmd)
        self.assertIn("long_textgrid", cmd)
        self.assertEqual(cmd[cmd.index("--beam") + 1], "10")
        self.assertEqual(cmd[cmd.index("--retry_beam") + 1], "40")

    def test_legacy_never_falls_back_to_english_dictionary(self):
        with self.assertRaises(AlignmentError):
            build_mfa_align_command("corpus", "aligned", MFACommandSettings(model="japanese_mfa", mode="legacy"))

    def test_mfa_workspace_composite_dict_replacement(self):
        from dataclasses import replace
        from karaoke_core.mfa import MFAWorkspace
        ws = MFAWorkspace(Path("root"), Path("corpus"), Path("output"), Path("audio"), Path("transcript"), "audio")
        self.assertIsNone(ws.composite_dict_path)
        comp = Path("composite.dict")
        ws2 = replace(ws, composite_dict_path=comp)
        self.assertEqual(ws2.composite_dict_path, comp)


if __name__ == "__main__":
    unittest.main()

