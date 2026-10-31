import unittest
from pathlib import Path
from karaoke_core.ass import AssDocument, romanization_override_command
from karaoke_core.render import (
    RenderRangeSettings,
    resolve_render_range,
    prepare_render_document,
    materialize_romanization_overlays,
    RenderLayoutSettings,
    render_burst_counter_video,
    CropRect,
)
import karaoke_core.render as render_mod


class TestFragmentRenderRemapAndCounter(unittest.TestCase):
    def test_fragment_render_preserves_remap_and_retimed_overlays(self):
        sample_ass = (
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\kf50}First {\kf50}Second" + "\n"
            r"Dialogue: 0,0:00:05.00,0:00:10.00,Default,,0,0,0,,{\kf100\remap}Hello {\kf100}World" + "\n"
            r"Dialogue: 0,0:00:06.00,0:00:08.00,Default,,0,0,0,track:1,{\kf100\id0:3}Hello" + "\n"
        )
        doc = AssDocument.from_text(sample_ass)
        settings = RenderLayoutSettings()
        syllables = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        # Select "Hello" and "World" (syllables 2 and 3)
        range_settings = RenderRangeSettings(
            start_syllable_id=syllables[2].id,
            end_syllable_id=syllables[3].id,
            pre_roll=0.5,
            post_roll=0.5,
        )
        resolved = resolve_render_range(doc, range_settings)
        # Content start is 5.0, pre_roll is 0.5 -> render_start is 4.5
        self.assertAlmostEqual(resolved.render_start, 4.5)

        frag_doc = prepare_render_document(doc, settings, render_range=resolved)
        retimed_evs = [e for e in frag_doc.events() if "retimed:3" in str(getattr(e, "effect", ""))]
        self.assertEqual(len(retimed_evs), 1)
        ev = retimed_evs[0]
        self.assertEqual(ev.kind, "Dialogue")
        # 6.00s in original document with render_start=4.50s should be at 1.50s in fragment
        self.assertEqual(ev.start_raw, "0:00:01.50")
        self.assertIn("Hello", ev.text)
        self.assertIn(r"\kf100", ev.text)

    def test_fragment_render_with_retimed_romanization(self):
        cmd_hello = romanization_override_command("hello")
        cmd_world = romanization_override_command("world")
        sample_ass = (
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\kf50}First {\kf50}Second" + "\n"
            rf"Dialogue: 0,0:00:05.00,0:00:10.00,Default,,0,0,0,,{{\kf100\remap{cmd_hello}}}Hello {{\kf100{cmd_world}}}World" + "\n"
            r"Dialogue: 0,0:00:06.00,0:00:08.00,Default,,0,0,0,track:1,{\kf100\id0:3}Hello" + "\n"
        )
        doc = AssDocument.from_text(sample_ass)
        settings = RenderLayoutSettings(enable_romanization=True)
        syllables = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        range_settings = RenderRangeSettings(
            start_syllable_id=syllables[2].id,
            end_syllable_id=syllables[3].id,
            pre_roll=0.5,
            post_roll=0.5,
        )
        resolved = resolve_render_range(doc, range_settings)

        orig_diag = render_mod._romanization_diagnostic_boxes
        try:
            render_mod._romanization_diagnostic_boxes = lambda d, **kwargs: {
                s.id: CropRect(100, 100, 50, 50) for s in d.karaoke_syllables()
            }
            frag_doc = prepare_render_document(doc, settings, render_range=resolved)
            materialize_romanization_overlays(frag_doc, ffmpeg="ffmpeg", layout=settings, render_range=resolved)

            retimed_romaji = [
                e for e in frag_doc.events()
                if "retimed_romaji:3" in str(getattr(e, "effect", ""))
            ]
            self.assertEqual(len(retimed_romaji), 1)
            self.assertEqual(retimed_romaji[0].start_raw, "0:00:01.50")
            self.assertIn("hello", retimed_romaji[0].text)
        finally:
            render_mod._romanization_diagnostic_boxes = orig_diag

    def test_burst_counter_video_fragment_and_audio(self):
        from unittest.mock import patch
        sample_ass = (
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\kf50}First {\kf50}Second" + "\n"
            r"Dialogue: 0,0:00:05.00,0:00:10.00,Default,,0,0,0,,{\c&H0000FF&}{\kf100}Hello {\kf100}World" + "\n"
        )
        doc = AssDocument.from_text(sample_ass)
        syllables = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        range_settings = RenderRangeSettings(
            start_syllable_id=syllables[2].id,
            end_syllable_id=syllables[3].id,
            pre_roll=0.5,
            post_roll=0.5,
        )
        resolved = resolve_render_range(doc, range_settings)

        # Mock build_render_command and _run_ffmpeg_progress to verify arguments passed
        with patch("karaoke_core.render.build_render_command") as mock_build, \
             patch("karaoke_core.render._run_ffmpeg_progress") as mock_run, \
             patch("karaoke_core.render.measure_burst_counter_layout") as mock_measure, \
             patch("karaoke_core.render.resolve_ffprobe", return_value=None), \
             patch("karaoke_core.render.probe_audio_bounds") as mock_bounds:
            
            mock_measure.return_value = render_mod.BurstCounterLayout(
                text_width=100,
                text_height=40,
                box_width=120,
                box_height=60,
                outer_width=130,
                outer_height=70,
                font_size=20.0,
                max_text="12.0 SPS",
            )
            mock_bounds.return_value = render_mod.MediaTimeBounds(0.0, 10.0)
            mock_build.return_value = ["ffmpeg", "-test"]

            out = render_burst_counter_video(
                doc,
                output="output.mp4",
                render_range=resolved,
                audio_source="test_audio.wav",
            )
            mock_build.assert_called_once()
            _, kwargs = mock_build.call_args
            self.assertEqual(kwargs["render_range"], resolved)
            self.assertEqual(kwargs["audio_source"], "test_audio.wav")
            self.assertTrue(kwargs["has_audio"])
            self.assertAlmostEqual(kwargs["duration"], resolved.duration)


if __name__ == "__main__":
    unittest.main()
