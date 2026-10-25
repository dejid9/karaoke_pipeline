from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from karaoke_core.alignment import AlignmentConversionSettings, convert_textgrid_to_ass
from karaoke_core.ass import AssDocument
from karaoke_core.language import detect_language_profile, profile_for_language
from karaoke_core.syllables import convert_ass_to_syllables, split_text_syllables
from karaoke_core.syllables import restore_document_text
from tests.test_alignment import TEXTGRID


class LanguageProfileTests(unittest.TestCase):
    def test_script_detection_and_mfa_pair(self):
        self.assertEqual(detect_language_profile("Это русский текст").code, "ru")
        self.assertEqual(detect_language_profile("これは日本語です").code, "ja")
        persian = detect_language_profile("این یک متن فارسی برای آزمایش است")
        self.assertEqual(persian.code, "fa")
        self.assertEqual(persian.acoustic_model, "")
        self.assertEqual(persian.dictionary_model, "")
        self.assertEqual(detect_language_profile("Ez egy magyar szöveg, nem német, és még hosszú is.").code, "hu")
        english = profile_for_language("english")
        self.assertEqual(english.acoustic_model, "english_mfa")
        self.assertEqual(english.dictionary_model, "english_us_mfa")
        portuguese = profile_for_language("portuguese")
        self.assertEqual(portuguese.code, "pt")
        self.assertEqual(portuguese.acoustic_model, "portuguese_mfa")
        self.assertEqual(portuguese.dictionary_model, "portuguese_mfa")
        self.assertEqual(
            detect_language_profile("Você não sabe que uma canção está comigo para sempre.").code,
            "pt",
        )

    def test_long_english_text_is_not_misread_from_one_foreign_stopword(self):
        sample = (
            "You don't even know that I'm gonna be the best. "
            "This is what it looks like when you rap with the rhythm. "
            "Everything is better when you have the words and the flow. Bu."
        )
        self.assertEqual(detect_language_profile(sample).code, "en")

    def test_syllable_split_preserves_exact_text(self):
        pieces = split_text_syllables("(hello!),", "en")
        self.assertEqual("".join(pieces), "(hello!),")
        self.assertGreaterEqual(len(pieces), 2)

    def test_closing_quote_before_comma_stays_with_previous_syllable(self):
        source = """[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\\kf10}при{\\kf10}вет{\\kf10}он\n"""
        document = AssDocument.from_text(source)
        restore_document_text(document, '\"привет\", он')
        self.assertEqual(
            [item.visible_text for item in document.karaoke_syllables()],
            ['\"при', 'вет\", ', 'он'],
        )


class FinalAlignmentPipelineTests(unittest.TestCase):
    def test_single_title_spans_complete_textgrid_including_edge_silence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            grid = root / "edges.TextGrid"
            text = root / "lyrics.txt"
            output = root / "lyrics.ass"
            edge_grid = TEXTGRID.replace("xmax = 1.23", "xmax = 2.00")
            edge_grid = edge_grid.replace(
                'intervals [1]:\n            xmin = 0\n            xmax = 0.47\n            text = "hello"',
                'intervals [1]:\n            xmin = 0.20\n            xmax = 0.47\n            text = "hello"',
                1,
            )
            edge_grid = edge_grid.replace(
                'intervals [3]:\n            xmin = 0.61\n            xmax = 2.00\n            text = "world"',
                'intervals [3]:\n            xmin = 0.61\n            xmax = 1.80\n            text = "world"',
                1,
            )
            grid.write_text(edge_grid, encoding="utf-8")
            text.write_text("Hello world", encoding="utf-8")
            convert_textgrid_to_ass(
                grid,
                output,
                transcript_path=text,
                settings=AlignmentConversionSettings(
                    max_words_per_line=1,
                    use_phone_boundaries=False,
                    syllabify=True,
                    flatten_dialogues=True,
                    restore_transcript_text=True,
                ),
            )
            document = AssDocument.load(output)
            events = [event for event in document.events() if event.kind == "Dialogue"]
            self.assertEqual(len(events), 1)
            self.assertAlmostEqual(events[0].start, 0.0)
            self.assertAlmostEqual(events[0].end, 2.0)
            self.assertEqual(sum(item.duration_cs for item in document.karaoke_syllables()), 200)

    def test_textgrid_to_syllables_flatten_and_exact_text_restore(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            grid = root / "sample.TextGrid"
            text = root / "lyrics.txt"
            output = root / "lyrics.ass"
            grid.write_text(TEXTGRID, encoding="utf-8")
            text.write_text("Hello,\nworld!", encoding="utf-8")
            report = convert_textgrid_to_ass(
                grid,
                output,
                transcript_path=text,
                settings=AlignmentConversionSettings(
                    max_words_per_line=1,
                    syllabify=True,
                    language="en",
                    flatten_dialogues=True,
                    restore_transcript_text=True,
                ),
            )
            self.assertTrue(report.syllabified)
            self.assertTrue(report.text_restored)
            self.assertEqual(report.lines, 1)
            self.assertEqual(report.language, "en")
            self.assertAlmostEqual(report.text_match_ratio or 0.0, 1.0)

            document = AssDocument.load(output)
            self.assertEqual(len([event for event in document.events() if event.kind == "Dialogue"]), 1)
            self.assertIn(
                "Style: Default,Heading Pro Variable,72,&H00FFFFFF,&H80FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,2,0,5,30,30,50,1",
                document.dumps(),
            )
            self.assertIn("WrapStyle: 0", document.dumps())
            self.assertNotIn(r"\c&Hff", document.dumps())
            self.assertEqual("".join(s.visible_text for s in document.karaoke_syllables()), "Hello,\nworld!")
            self.assertNotIn(r"\org", document.dumps())
            self.assertNotIn(r"\fr", document.dumps())
            self.assertEqual(sum(s.duration_cs for s in document.karaoke_syllables()), 123)

    def test_standalone_ass_syllabifier_keeps_duration(self):
        source_text = """[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,40,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\nDialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,{\\kf10}h{\\kf10}e{\\kf10}l{\\kf10}l{\\kf10}o\n"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.ass"
            output = root / "syllables.ass"
            source.write_text(source_text, encoding="utf-8")
            report = convert_ass_to_syllables(source, output, "en")
            document = AssDocument.load(output)
            self.assertEqual(report.input_units, 5)
            self.assertEqual("".join(s.visible_text for s in document.karaoke_syllables()), "hello")
            self.assertEqual(sum(s.duration_cs for s in document.karaoke_syllables()), 50)
            self.assertLess(report.output_units, report.input_units)

    def test_exact_text_pipeline_refuses_to_run_without_original_txt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            grid = root / "sample.TextGrid"
            grid.write_text(TEXTGRID, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "исходный TXT"):
                convert_textgrid_to_ass(
                    grid,
                    root / "lyrics.ass",
                    settings=AlignmentConversionSettings(
                        syllabify=True,
                        flatten_dialogues=True,
                        restore_transcript_text=True,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
