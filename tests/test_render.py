from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest

from karaoke_core.ass import AssDocument
from karaoke_core.render import (
    AssTextStyle,
    BurstCounterLayout,
    BurstCounterSettings,
    CropRect,
    DirectVideoSettings,
    RenderLayoutSettings,
    RenderOutputSettings,
    RenderRangeError,
    RenderRangeSettings,
    VerticalFollowPlan,
    VerticalFollowSettings,
    _vertical_crop_y_expression,
    alpha_bbox,
    apply_text_case,
    ass_playres,
    ass_text_styles,
    build_burst_counter_document,
    build_burst_counter_plan,
    build_burst_style_preview_document,
    build_direct_video_command,
    build_render_command,
    build_vertical_follow_plan,
    dialogue_line_count,
    layout_event_text,
    karaoke_text_style,
    make_even_crop,
    materialize_romanization_overlays,
    measure_render_layout,
    padded_crop,
    prepare_render_document,
    prepare_range_document,
    resolve_render_range,
    render_karaoke_video,
    render_burst_counter_video,
    replace_ass_text_style,
    scale_ass_text_style,
    render_karaoke_on_source,
    render_rgba_frame,
    slice_burst_counter_plan,
    vertical_viewport_crop,
    interpolate_cube_surface,
    shift_hue,
    calculate_hue_offset_degrees,
    generate_surface_dynamic_tags,
    generate_burst_pulse_tags,
    burst_syllable_style,
    apply_render_burst_styling,
    ass_to_rgb,
)


ASS = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.40,Default,,0,0,0,,{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four
'''


class RenderLayoutTests(unittest.TestCase):
    def test_counter_can_copy_complete_karaoke_ass_style(self):
        doc = AssDocument.from_text(ASS)
        parsed = ass_text_styles(doc)
        self.assertIn("default", parsed)
        style = karaoke_text_style(doc)
        self.assertEqual(style.font_name, "Arial")
        self.assertEqual(style.font_size, 28)
        self.assertEqual(style.secondary_colour, "&H000000FF")
        self.assertEqual(style.outline, 2)
        self.assertEqual(style.alignment, 5)

        plan = build_burst_counter_plan(doc, duration=1.0)
        layout = BurstCounterLayout(180, 34, 200, 54, 210, 64, 28, plan.max_text)
        counter = build_burst_counter_document(
            plan, layout, frame_width=640, frame_height=360,
            settings=BurstCounterSettings(text_style=style),
        )
        counter_style = ass_text_styles(counter)["counter"]
        self.assertEqual(counter_style, replace(style, name="Counter"))
        text_event = next(event for event in counter.events() if event.style == "Counter")
        self.assertNotIn(r"\bord0", text_event.text)
        self.assertNotIn(r"\shad0", text_event.text)
        self.assertNotIn(r"\1c", text_event.text)

        doubled = scale_ass_text_style(style, 2)
        self.assertEqual(doubled.font_size, 56)
        self.assertEqual(doubled.outline, 4)

    def test_style_preview_uses_counter_style_and_card(self):
        style = AssTextStyle(
            font_name="Arial", font_size=36, primary_colour="&H0000FFFF",
            bold=True, italic=True, outline=3, shadow=2,
        )
        preview = build_burst_style_preview_document(style)
        styles = ass_text_styles(preview)
        self.assertEqual(styles["counter"].primary_colour, "&H0000FFFF")
        self.assertTrue(styles["counter"].bold)
        self.assertTrue(styles["counter"].italic)
        self.assertIn("card", styles)

    def test_replace_ass_style_updates_karaoke_and_preserves_events(self):
        doc = AssDocument.from_text(ASS)
        before_event = doc.events()[0]._serialize()
        original = karaoke_text_style(doc)
        updated = replace(
            original,
            font_name="Verdana",
            font_size=44,
            primary_colour="&H0000FFFF",
            bold=True,
            outline=3,
        )
        replace_ass_text_style(doc, original.name, updated)
        parsed = karaoke_text_style(doc)
        self.assertEqual(parsed.font_name, "Verdana")
        self.assertEqual(parsed.font_size, 44)
        self.assertEqual(parsed.primary_colour, "&H0000FFFF")
        self.assertTrue(parsed.bold)
        self.assertEqual(parsed.outline, 3)
        self.assertEqual(doc.events()[0]._serialize(), before_event)

    def test_rtl_render_copy_enables_whole_text_layout_without_reordering_source(self):
        rtl = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf10}سلام {\kf10}دنیا",
        )
        doc = AssDocument.from_text(rtl)
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        self.assertEqual(karaoke_text_style(doc).encoding, 1)
        self.assertEqual(karaoke_text_style(prepared).encoding, -1)
        self.assertEqual(
            [item.visible_text for item in prepared.karaoke_syllables()],
            ["سلام ", "دنیا"],
        )

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_manual_romanization_is_positioned_above_rtl_syllables_by_libass(self):
        from karaoke_core.editor import set_syllable_romanization
        rtl = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf10}سلام {\kf10}دنیا",
        )
        doc = AssDocument.from_text(rtl)
        ids = [item.id for item in doc.karaoke_syllables()]
        set_syllable_romanization(doc, ids[0], "salaam")
        set_syllable_romanization(doc, ids[1], "donyaa")
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        count = materialize_romanization_overlays(
            prepared, ffmpeg=shutil.which("ffmpeg")
        )
        self.assertEqual(count, 2)
        overlays = [
            event for event in prepared.events()
            if event.name == "KaraokeRomanization"
        ]
        self.assertEqual(len(overlays), 2)
        positions = []
        for event in overlays:
            match = __import__("re").search(r"\\pos\((\d+),(\d+)\)", event.text)
            self.assertIsNotNone(match)
            positions.append((int(match.group(1)), int(match.group(2))))
            self.assertIn(r"\fs", event.text)
        # Logical Persian order is visual right-to-left when Encoding=-1 makes
        # libass shape/reorder the whole karaoke event across override tags.
        self.assertGreater(positions[0][0], positions[1][0])

    def test_playres_and_render_copy(self):
        doc = AssDocument.from_text(ASS)
        before = doc.dumps()
        settings = RenderLayoutSettings(max_words_per_line=2, line_spacing_px=20)
        render = prepare_render_document(doc, settings)
        self.assertEqual(ass_playres(render), (320, 180))
        self.assertEqual(doc.dumps(), before)
        text = render.events()[0].text
        self.assertIn(r"\N", text)
        self.assertIn(r"\org(-2000000,0)\frz", text)
        self.assertIn(r"\c&HFF", text)
        angle = float(text.split(r"\frz", 1)[1].split("}", 1)[0])
        self.assertAlmostEqual(angle, -0.0005729, delta=0.000002)

        # Negative line spacing should yield positive rotation angle (shifting lines up)
        neg_text = layout_event_text(r"one\Ntwo", RenderLayoutSettings(line_spacing_px=-20), playres_x=1920)
        neg_angle = float(neg_text.split(r"\frz", 1)[1].split("}", 1)[0])
        self.assertAlmostEqual(neg_angle, 0.0005729, delta=0.000002)

    def test_line_spacing_direct_proportionality(self):
        doc = AssDocument.from_text(ASS)
        m_neg10 = measure_render_layout(doc, RenderLayoutSettings(max_words_per_line=2, line_spacing_px=-10))
        m0 = measure_render_layout(doc, RenderLayoutSettings(max_words_per_line=2, line_spacing_px=0))
        m20 = measure_render_layout(doc, RenderLayoutSettings(max_words_per_line=2, line_spacing_px=20))
        m40 = measure_render_layout(doc, RenderLayoutSettings(max_words_per_line=2, line_spacing_px=40))
        self.assertLess(m_neg10.content_bbox.height, m0.content_bbox.height)
        self.assertGreater(m20.content_bbox.height, m0.content_bbox.height)
        self.assertGreater(m40.content_bbox.height, m20.content_bbox.height)

    def test_unspoken_markup_is_render_only_and_does_not_add_sps_units(self):
        source = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf40}pu[ta a]",
        ).replace("&H000000FF,&H00000000", "&H00A0A0A0,&H00000000")
        doc = AssDocument.from_text(source)
        before = doc.dumps()
        self.assertEqual(len(doc.karaoke_syllables()), 1)

        prepared = prepare_render_document(doc, RenderLayoutSettings(line_spacing_px=0))
        rendered = prepared.events()[0].text
        self.assertNotIn("[", rendered)
        self.assertNotIn("]", rendered)
        self.assertIn(r"{\1c&HA0A0A0&\2c&HA0A0A0&\1a&H00&\2a&H00&}ta a{\1c\2c\1a\2a}", rendered)
        self.assertEqual(len(prepared.karaoke_syllables()), 1)
        self.assertEqual(doc.dumps(), before)

    def test_unspoken_fragment_inside_burst_restores_red_after_fragment(self):
        source = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf40\c&Hff}pu[ta a]end{\c}",
        ).replace("&H000000FF,&H00000000", "&H00A0A0A0,&H00000000")
        doc = AssDocument.from_text(source)
        prepared = prepare_render_document(doc, RenderLayoutSettings(line_spacing_px=0))
        rendered = prepared.events()[0].text
        self.assertIn(r"ta a{\1c&Hff&\2c\1a\2a}end", rendered)
        self.assertEqual(len(doc.karaoke_syllables()), 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_libass_accepts_unspoken_colour_overrides_inside_burst(self):
        source = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf40\c&Hff}pu[ta a]end{\c}",
        ).replace("&H000000FF,&H00000000", "&H00FF0000,&H00000000")
        prepared = prepare_render_document(
            AssDocument.from_text(source), RenderLayoutSettings(line_spacing_px=0)
        )
        rgba, width, height = render_rgba_frame(
            prepared, ffmpeg=shutil.which("ffmpeg"), width=320, height=180,
            timestamp=0.39,
        )
        self.assertIsNotNone(alpha_bbox(rgba, width, height))
        pixels = zip(rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4])
        opaque = [(r, g, b) for r, g, b, a in pixels if a > 64]
        red_pixels = sum(r > b + 30 for r, _g, b in opaque)
        blue_pixels = sum(b > r + 30 for r, _g, b in opaque)
        self.assertGreater(red_pixels, 10)
        self.assertGreater(blue_pixels, 10)

    def test_unspoken_fragment_uses_secondary_style_colour_as_unhighlighted_text(self):
        source = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf40}hello [ignored] world",
        ).replace("&H00FFFFFF,&H000000FF", "&H2000FF00,&H800000FF")
        doc = AssDocument.from_text(source)
        prepared = prepare_render_document(doc, RenderLayoutSettings(line_spacing_px=0))
        rendered = prepared.events()[0].text
        self.assertIn(r"{\1c&H0000FF&\2c&H0000FF&\1a&H80&\2a&H80&}ignored{\1c\2c\1a\2a}", rendered)

    def test_character_wrap_uses_whole_words_and_can_remove_original_breaks(self):
        text = r"one two\Nthree four"
        kept = layout_event_text(
            text,
            RenderLayoutSettings(max_chars_per_line=9, line_spacing_px=0),
            playres_x=1920,
        )
        self.assertEqual(kept, r"one two\Nthree\Nfour")

        rebuilt = layout_event_text(
            text,
            RenderLayoutSettings(
                max_chars_per_line=9,
                remove_original_line_breaks=True,
                line_spacing_px=0,
            ),
            playres_x=1920,
        )
        self.assertEqual(rebuilt, r"one two\Nthree\Nfour")

        unwrapped = layout_event_text(
            text,
            RenderLayoutSettings(
                remove_original_line_breaks=True,
                line_spacing_px=0,
            ),
            playres_x=1920,
        )
        self.assertEqual(unwrapped, "one two three four")

    def test_existing_line_spacing_is_not_duplicated(self):
        text = r"one\N{\org(-2000000,0)\frz0.0005}two"
        out = layout_event_text(text, RenderLayoutSettings(line_spacing_px=20), playres_x=1920)
        self.assertEqual(out.count(r"\org("), 1)
        self.assertEqual(out.count(r"\frz"), 1)

    def test_alpha_bbox_and_even_crop(self):
        rgba = bytearray(10 * 8 * 4)
        for y in range(2, 6):
            for x in range(3, 8):
                rgba[(y * 10 + x) * 4 + 3] = 255
        bbox = alpha_bbox(bytes(rgba), 10, 8)
        self.assertEqual(bbox, CropRect(3, 2, 5, 4))
        even = make_even_crop(CropRect(3, 2, 5, 3), 10, 8)
        self.assertEqual(even.width % 2, 0)
        self.assertEqual(even.height % 2, 0)

    def test_render_command_profiles(self):
        cmd = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=CropRect(10, 10, 100, 50),
            duration=1.0, output="x.mov",
            output_settings=RenderOutputSettings(fps=30, profile="transparent_mov"),
        )
        joined = " ".join(cmd)
        self.assertIn("qtrle", joined)
        self.assertIn("alpha=1", joined)
        self.assertIn("s=640x360", joined)
        self.assertIn("crop=200:100:20:20", joined)
        self.assertIn("-map 0:v:0", joined)
        self.assertIn("-an", joined)

        mov_audio = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=CropRect(10, 10, 100, 50),
            duration=1.0, output="x.mov", audio_source="source.flac",
            output_settings=RenderOutputSettings(fps=30, profile="transparent_mov"),
        )
        mov_joined = " ".join(mov_audio)
        self.assertIn("-map 1:a:0", mov_joined)
        self.assertIn("-c:a pcm_s16le", mov_joined)
        self.assertNotIn("-an", mov_joined)

        mp4_audio = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=CropRect(10, 10, 100, 50),
            duration=1.0, output="x.mp4", audio_source="source.opus",
            output_settings=RenderOutputSettings(fps=30, profile="black_mp4"),
        )
        mp4_joined = " ".join(mp4_audio)
        self.assertIn("-c:a aac", mp4_joined)
        self.assertIn("-b:a 192k", mp4_joined)
        self.assertIn("crop=200:100:20:20", mp4_joined)

    def test_burst_counter_plan_counts_and_keeps_summary_to_video_end(self):
        doc = AssDocument.from_text(ASS)
        plan = build_burst_counter_plan(doc, duration=1.0)
        self.assertEqual(len(plan.regions), 1)
        self.assertEqual(plan.regions[0].count, 4)
        self.assertAlmostEqual(plan.regions[0].duration, 0.4)
        self.assertEqual(plan.regions[0].summary, "10.00 SPS // 4 in 0.40s")
        self.assertEqual(plan.cues[0].text, "1 // 0.00s")
        self.assertEqual(plan.cues[-1].text, "10.00 SPS // 4 in 0.40s")
        self.assertAlmostEqual(plan.cues[-1].start, 0.4)
        self.assertAlmostEqual(plan.cues[-1].end, 1.0)

    def test_burst_counter_summary_can_round_or_use_custom_text(self):
        doc = AssDocument.from_text(ASS)
        visible = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        overrides = {
            visible[0].id: (0.0, visible[0].end),
            visible[-1].id: (visible[-1].start, 1.01),
        }
        rounded = build_burst_counter_plan(
            doc,
            duration=1.5,
            timing_overrides=overrides,
            round_summary_seconds=True,
        )
        self.assertEqual(rounded.cues[-1].text, "4.00 SPS // 4 in 1s")

        custom = build_burst_counter_plan(
            doc,
            duration=1.5,
            timing_overrides=overrides,
            custom_summary="15.00 SPS // 15 in 1s",
        )
        self.assertEqual(custom.cues[-1].text, "15.00 SPS // 15 in 1s")

    def test_uncoloured_timing_gap_splits_burst_measurements(self):
        text = r"{\kf10\c&HFF}one{\kf10\c}{\kf10\c&HFF}two"
        doc = AssDocument.from_text(ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            text,
        ))
        plan = build_burst_counter_plan(doc, duration=1.0)
        self.assertEqual(len(plan.regions), 2)
        self.assertEqual([region.count for region in plan.regions], [1, 1])

    def test_burst_counter_prefers_exact_sps_measurement_boundaries(self):
        doc = AssDocument.from_text(ASS)
        visible = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        overrides = {
            visible[0].id: (0.02, visible[0].end),
            visible[-1].id: (visible[-1].start, 0.52),
        }
        plan = build_burst_counter_plan(
            doc, duration=1.0, timing_overrides=overrides
        )
        self.assertAlmostEqual(plan.regions[0].start, 0.02)
        self.assertAlmostEqual(plan.regions[0].end, 0.52)
        self.assertEqual(plan.regions[0].summary, "8.00 SPS // 4 in 0.50s")

        clipped = slice_burst_counter_plan(plan, 0.2, 0.7)
        self.assertAlmostEqual(clipped.duration, 0.5)
        self.assertTrue(clipped.cues)
        self.assertGreaterEqual(min(cue.start for cue in clipped.cues), 0.0)
        self.assertLessEqual(max(cue.end for cue in clipped.cues), 0.5)

    def test_burst_counter_ass_has_outlined_box_and_bottom_right_padding(self):
        plan = build_burst_counter_plan(AssDocument.from_text(ASS), duration=1.0)
        layout = BurstCounterLayout(180, 34, 200, 54, 210, 64, 42, plan.max_text)
        counter = build_burst_counter_document(
            plan,
            layout,
            frame_width=640,
            frame_height=360,
            settings=BurstCounterSettings(),
        )
        dumped = counter.dumps()
        self.assertIn("PlayResX: 640", dumped)
        self.assertIn("PlayResY: 360", dumped)
        self.assertIn(r"\pos(420,286)\p1\bord5", dumped)
        self.assertIn(r"\3c&HFFFFFF&", dumped)
        self.assertIn("10.00 SPS // 4 in 0.40s", dumped)

    def test_burst_counter_filter_is_after_dynamic_crop(self):
        cmd = build_render_command(
            ffmpeg="ffmpeg",
            ass_filename="render.ass",
            burst_ass_filename="burst-counter.ass",
            playres_x=320,
            playres_y=180,
            crop=CropRect(10, 10, 100, 50),
            duration=1.0,
            output="x.mov",
            output_settings=RenderOutputSettings(fps=30, profile="transparent_mov"),
        )
        vf = cmd[cmd.index("-vf") + 1]
        karaoke_index = vf.index("subtitles=render.ass")
        crop_index = vf.index("crop=")
        counter_index = vf.index("subtitles=burst-counter.ass")
        self.assertLess(karaoke_index, crop_index)
        self.assertLess(crop_index, counter_index)

    def test_vertical_follow_command_uses_line_timings_and_easing(self):
        line_text = r"\N".join(rf"{{\kf10}}line{index}" for index in range(6))
        doc = AssDocument.from_text(ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            line_text,
        ))
        self.assertEqual(dialogue_line_count(doc), 6)
        bbox = CropRect(40, 20, 240, 120)
        full_crop = CropRect(30, 10, 260, 140)
        viewport = vertical_viewport_crop(full_crop, bbox, 6, 2, 320, 180)
        self.assertLess(viewport.height, full_crop.height)
        plan = build_vertical_follow_plan(
            doc, bbox, full_crop, 320, 180, VerticalFollowSettings(2, 0.3)
        )
        self.assertGreater(len(plan.keyframes), 1)
        cmd = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=full_crop, duration=1.0, output="x.mp4",
            output_settings=RenderOutputSettings(fps=30, profile="black_mp4"),
            vertical_follow=plan,
        )
        joined = " ".join(cmd)
        self.assertIn("crop=520:", joined)
        self.assertIn(r"if(lt(t\,", joined)

    def test_continuous_follow_interpolates_for_complete_line_interval(self):
        line_text = r"\N".join(rf"{{\kf10}}line{index}" for index in range(6))
        doc = AssDocument.from_text(ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            line_text,
        ))
        bbox = CropRect(40, 20, 240, 120)
        full_crop = CropRect(30, 10, 260, 140)
        plan = build_vertical_follow_plan(
            doc, bbox, full_crop, 320, 180,
            VerticalFollowSettings(2, 0.3, continuous=True),
        )
        self.assertTrue(plan.continuous)
        cmd = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=full_crop, duration=1.0, output="x.mp4",
            output_settings=RenderOutputSettings(fps=30, profile="black_mp4"),
            vertical_follow=plan,
        )
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("((t-", vf)
        self.assertIn("*(1-0.5*", vf)

        # 0% - piecewise linear
        plan_0 = build_vertical_follow_plan(
            doc, bbox, full_crop, 320, 180,
            VerticalFollowSettings(2, 0.3, continuous=True, smooth_percent=0),
        )
        cmd_0 = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=full_crop, duration=1.0, output="x.mp4",
            output_settings=RenderOutputSettings(fps=30, profile="black_mp4"),
            vertical_follow=plan_0,
        )
        vf_0 = cmd_0[cmd_0.index("-vf") + 1]
        self.assertIn("*(t-", vf_0)
        self.assertNotIn("*(1-0.5*", vf_0)

        # 100% - pure global linear function
        plan_100 = build_vertical_follow_plan(
            doc, bbox, full_crop, 320, 180,
            VerticalFollowSettings(2, 0.3, continuous=True, smooth_percent=100),
        )
        cmd_100 = build_render_command(
            ffmpeg="ffmpeg", ass_filename="render.ass", playres_x=320, playres_y=180,
            crop=full_crop, duration=1.0, output="x.mp4",
            output_settings=RenderOutputSettings(fps=30, profile="black_mp4"),
            vertical_follow=plan_100,
        )
        vf_100 = cmd_100[cmd_100.index("-vf") + 1]
        self.assertIn("*(t-0)", vf_100)

    def test_direct_video_command_renders_at_double_source_resolution(self):
        cmd = build_direct_video_command(
            ffmpeg="ffmpeg",
            source_media="source.mp4",
            ass_filename="render.ass",
            output="out.mp4",
            settings=DirectVideoSettings(
                video_codec="libx264", crf=20, preset="fast", audio_mode="aac", audio_bitrate_kbps=160
            ),
        )
        joined = " ".join(cmd)
        self.assertIn("-map 0:v:0", joined)
        self.assertIn("-map 0:a?", joined)
        self.assertIn("subtitles=render.ass", joined)
        self.assertNotIn("crop=", joined)
        self.assertIn("scale=ceil(iw*2/2)*2:ceil(ih*2/2)*2:flags=lanczos", joined)
        self.assertNotIn(" -r ", f" {joined} ")
        self.assertIn("-c:v libx264", joined)
        self.assertIn("-crf 20", joined)
        self.assertIn("-c:a aac", joined)
        self.assertIn("-b:a 160k", joined)

    def test_direct_settings_audio_modes(self):
        copy_cmd = build_direct_video_command(
            ffmpeg="ffmpeg", source_media="x.mkv", ass_filename="render.ass", output="o.mkv",
            settings=DirectVideoSettings(audio_mode="copy"),
        )
        self.assertIn("copy", copy_cmd)
        none_cmd = build_direct_video_command(
            ffmpeg="ffmpeg", source_media="x.mkv", ass_filename="render.ass", output="o.mkv",
            settings=DirectVideoSettings(audio_mode="none"),
        )
        self.assertIn("-an", none_cmd)

    def test_render_range_keeps_only_selected_syllables_and_zero_bases_timeline(self):
        doc = AssDocument.from_text(ASS)
        visible = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        segment = resolve_render_range(
            doc, RenderRangeSettings(visible[1].id, visible[2].id, pre_roll=0.05, post_roll=0.07)
        )
        self.assertAlmostEqual(segment.render_start, 0.05)
        self.assertAlmostEqual(segment.duration, 0.32)
        ranged = prepare_range_document(doc, segment)
        dialogue = [e for e in ranged.events() if e.kind == "Dialogue"]
        self.assertEqual(len(dialogue), 1)
        self.assertNotIn("one", dialogue[0].text)
        self.assertNotIn("four", dialogue[0].text)
        self.assertIn("two", dialogue[0].text)
        self.assertIn("three", dialogue[0].text)
        # 50 ms pre-roll is represented as an invisible karaoke delay.
        self.assertIn(r"{\k5}", dialogue[0].text)
        self.assertEqual(dialogue[0].start_raw, "0:00:00.00")

    def test_render_range_reports_exact_maximum_padding(self):
        from karaoke_core.media import MediaTimeBounds
        doc = AssDocument.from_text(ASS)
        visible = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        request = RenderRangeSettings(visible[1].id, visible[2].id, pre_roll=0.11, post_roll=0.0)
        with self.assertRaises(RenderRangeError) as cm:
            resolve_render_range(
                doc, request, media_duration=0.6, audio_bounds=MediaTimeBounds(0.0, 0.55)
            )
        self.assertIn("0.100 с", str(cm.exception))
        request = RenderRangeSettings(visible[1].id, visible[2].id, pre_roll=0.1, post_roll=0.26)
        with self.assertRaises(RenderRangeError) as cm:
            resolve_render_range(
                doc, request, media_duration=0.6, audio_bounds=MediaTimeBounds(0.0, 0.55)
            )
        self.assertIn("0.250 с", str(cm.exception))

    def test_direct_range_command_trims_and_fades_audio(self):
        doc = AssDocument.from_text(ASS)
        visible = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
        segment = resolve_render_range(
            doc, RenderRangeSettings(visible[1].id, visible[2].id, pre_roll=0.05, post_roll=0.07),
            media_duration=0.6,
        )
        cmd = build_direct_video_command(
            ffmpeg="ffmpeg", source_media="source.mp4", ass_filename="render.ass", output="out.mp4",
            settings=DirectVideoSettings(audio_mode="copy", audio_bitrate_kbps=192),
            render_range=segment, has_audio=True,
        )
        joined = " ".join(cmd)
        self.assertIn("-ss 0.050000", joined)
        self.assertIn("-t 0.320000", joined)
        self.assertIn("afade=t=in:st=0:d=0.050000", joined)
        self.assertIn("afade=t=out:st=0.250000:d=0.070000", joined)
        self.assertIn("-c:a aac", joined)
        self.assertNotIn("-c:a copy", joined)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_tall_single_dialogue_expands_preview_before_cropping(self):
        lines = r"\N".join(f"line {index:02d}" for index in range(24))
        tall_ass = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf10}" + lines,
        )
        doc = AssDocument.from_text(tall_ass)
        before = doc.dumps()
        measurement = measure_render_layout(
            doc,
            RenderLayoutSettings(
                line_spacing_px=0, padding_left=4, padding_right=4,
                padding_top=4, padding_bottom=4,
            ),
            ffmpeg=shutil.which("ffmpeg"),
        )
        self.assertEqual(doc.dumps(), before)
        self.assertEqual((measurement.source_playres_x, measurement.source_playres_y), (320, 180))
        self.assertGreater(measurement.playres_y, 180)
        self.assertGreater(measurement.content_bbox.height, 180)
        self.assertGreater(measurement.content_bbox.y, 1)
        self.assertLess(measurement.content_bbox.bottom, measurement.playres_y - 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_real_libass_measurement_and_tiny_render(self):
        doc = AssDocument.from_text(ASS)
        measurement = measure_render_layout(
            doc, RenderLayoutSettings(max_words_per_line=2, line_spacing_px=8, padding_left=4, padding_right=4, padding_top=4, padding_bottom=4),
            ffmpeg=shutil.which("ffmpeg"),
        )
        self.assertGreater(measurement.content_bbox.width, 0)
        self.assertGreater(measurement.content_bbox.height, 0)
        self.assertLessEqual(measurement.crop.right, 320)
        self.assertLessEqual(measurement.crop.bottom, 180)
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source_audio = td / "source.flac"
            import subprocess
            subprocess.run(
                [
                    shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=0.4",
                    "-c:a", "flac", str(source_audio),
                ],
                check=True,
            )
            target = td / "karaoke.mov"
            render_karaoke_video(
                doc,
                RenderLayoutSettings(max_words_per_line=2, line_spacing_px=8, padding_left=4, padding_right=4, padding_top=4, padding_bottom=4),
                target,
                crop=measurement.crop,
                render_canvas=(measurement.playres_x, measurement.playres_y),
                ffmpeg=shutil.which("ffmpeg"),
                output_settings=RenderOutputSettings(fps=5, profile="transparent_mov"),
                audio_source=source_audio,
                burst_counter_settings=BurstCounterSettings(
                    text_style=AssTextStyle(font_size=20)
                ),
            )
            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size, 100)
            probe = subprocess.run(
                [shutil.which("ffmpeg"), "-hide_banner", "-i", str(target), "-f", "null", "-"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn(f"{measurement.crop.width * 2}x{measurement.crop.height * 2}", probe.stderr)
            self.assertIn("Audio: pcm_s16le", probe.stderr)

            mp4_target = td / "karaoke.mp4"
            mp4_layout = RenderLayoutSettings(max_words_per_line=2, line_spacing_px=8)
            mp4_measurement = measure_render_layout(doc, mp4_layout, ffmpeg=shutil.which("ffmpeg"))
            render_karaoke_video(
                doc,
                mp4_layout,
                mp4_target,
                crop=mp4_measurement.crop,
                render_canvas=(mp4_measurement.playres_x, mp4_measurement.playres_y),
                ffmpeg=shutil.which("ffmpeg"),
                output_settings=RenderOutputSettings(fps=5, profile="black_mp4"),
                audio_source=source_audio,
            )
            mp4_probe = subprocess.run(
                [shutil.which("ffmpeg"), "-hide_banner", "-i", str(mp4_target), "-f", "null", "-"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(mp4_probe.returncode, 0, mp4_probe.stderr)
            self.assertIn(f"{mp4_measurement.crop.width * 2}x{mp4_measurement.crop.height * 2}", mp4_probe.stderr)
            self.assertIn("Audio: aac", mp4_probe.stderr)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
    def test_real_separate_burst_counter_has_card_dimensions(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        doc = AssDocument.from_text(ASS)
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "counter.mp4"
            render_burst_counter_video(
                doc,
                target,
                ffmpeg=ffmpeg,
                output_settings=RenderOutputSettings(
                    fps=5, profile="black_mp4", resolution_scale=3
                ),
                settings=BurstCounterSettings(text_style=AssTextStyle(font_size=20)),
                duration=1.0,
                active_interval_only=True,
            )
            self.assertTrue(target.exists())
            size = __import__("subprocess").run(
                [
                    ffprobe, "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                    str(target),
                ],
                stdout=__import__("subprocess").PIPE,
                stderr=__import__("subprocess").PIPE,
                text=True,
                check=True,
            ).stdout.strip()
            width, height = map(int, size.split("x"))
            self.assertEqual(width % 2, 0)
            self.assertEqual(height % 2, 0)
            self.assertLess(width, 1000)
            self.assertLess(height, 300)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
    def test_real_ranged_direct_burn_trims_and_keeps_audio(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        from karaoke_core.media import probe_audio_bounds, probe_media_duration
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "source.mp4"
            make = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=navy:s=320x180:r=30:d=0.8",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=0.8",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
            ]
            import subprocess
            subprocess.run(make, check=True)
            doc = AssDocument.from_text(ASS)
            visible = [s for s in doc.karaoke_syllables() if s.visible_text.strip()]
            segment = resolve_render_range(
                doc, RenderRangeSettings(visible[1].id, visible[2].id, 0.05, 0.07),
                media_duration=probe_media_duration(source, ffmpeg),
                audio_bounds=probe_audio_bounds(source, ffmpeg),
            )
            out = td / "ranged.mp4"
            render_karaoke_on_source(
                doc, RenderLayoutSettings(line_spacing_px=8), source, out, ffmpeg=ffmpeg,
                settings=DirectVideoSettings(video_codec="libx264", crf=30, preset="ultrafast", audio_mode="copy"),
                render_range=segment,
            )
            duration = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(out)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            )
            self.assertAlmostEqual(float(duration.stdout.strip()), segment.duration, delta=0.05)
            probe = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(out), "-f", "null", "-"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            self.assertIn("Audio:", probe.stderr)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_real_direct_burn_doubles_source_dimensions_and_keeps_audio(self):
        ffmpeg = shutil.which("ffmpeg")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "source.mp4"
            make = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=navy:s=320x180:r=12:d=0.6",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=0.6",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
            ]
            import subprocess
            subprocess.run(make, check=True)
            out = td / "burned.mp4"
            doc = AssDocument.from_text(ASS)
            before = doc.dumps()
            render_karaoke_on_source(
                doc, RenderLayoutSettings(max_words_per_line=2, line_spacing_px=8),
                source, out, ffmpeg=ffmpeg,
                settings=DirectVideoSettings(video_codec="libx264", crf=30, preset="ultrafast", audio_mode="copy"),
            )
            self.assertEqual(doc.dumps(), before)
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 500)
            probe = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(out), "-f", "null", "-"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn("640x360", probe.stderr)
            self.assertIn("Audio:", probe.stderr)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_romanization_for_unspoken_syllable_is_rendered_with_secondary_style_colour(self):
        from karaoke_core.editor import set_syllable_romanization
        # Two syllables, second is unspoken in [...] with secondary colour in style
        custom_ass = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf10}first {\kf15}[second]",
        ).replace("&H00FFFFFF,&H000000FF", "&H00FFFFFF,&H4000AAFF")
        doc = AssDocument.from_text(custom_ass)
        syllables = doc.karaoke_syllables()
        set_syllable_romanization(doc, syllables[0].id, "ichi")
        set_syllable_romanization(doc, syllables[1].id, "[ni]")
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        count = materialize_romanization_overlays(prepared, ffmpeg=shutil.which("ffmpeg"))
        self.assertEqual(count, 2)
        overlays = [e for e in prepared.events() if e.name == "KaraokeRomanization"]
        self.assertEqual(len(overlays), 2)
        # First overlay has normal colour and delay 0
        self.assertIn("ichi", overlays[0].text)
        self.assertIn(r"{\kf10}", overlays[0].text)
        # Second overlay is unspoken: brackets stripped, secondary colour &H00AAFF, delay \k10, duration \kf15
        self.assertIn("ni", overlays[1].text)
        self.assertNotIn("[", overlays[1].text)
        self.assertNotIn("]", overlays[1].text)
        self.assertIn(r"\1c&H00AAFF&", overlays[1].text)
        self.assertIn(r"\2c&H00AAFF&", overlays[1].text)
        self.assertIn(r"\1a&H40&", overlays[1].text)
        self.assertIn(r"{\k10}", overlays[1].text)
        self.assertIn(r"{\kf15}", overlays[1].text)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_romanization_settings_size_and_offset_y(self):
        from karaoke_core.editor import set_syllable_romanization
        doc = AssDocument.from_text(ASS)
        syllables = doc.karaoke_syllables()
        set_syllable_romanization(doc, syllables[0].id, "one_rom")
        prepared_default = prepare_render_document(doc, RenderLayoutSettings())
        materialize_romanization_overlays(
            prepared_default,
            ffmpeg=shutil.which("ffmpeg"),
            layout=RenderLayoutSettings(romanization_size_percent=55.0, romanization_offset_y=0),
        )
        overlay_def = [e for e in prepared_default.events() if e.name == "KaraokeRomanization"][0]

        prepared_custom = prepare_render_document(doc, RenderLayoutSettings())
        materialize_romanization_overlays(
            prepared_custom,
            ffmpeg=shutil.which("ffmpeg"),
            layout=RenderLayoutSettings(romanization_size_percent=80.0, romanization_offset_y=-10),
        )
        overlay_cust = [e for e in prepared_custom.events() if e.name == "KaraokeRomanization"][0]

        # Font sizes: default style font_size is 28, 55% = 15.4, 80% = 22.4
        self.assertIn(r"\fs15.400", overlay_def.text)
        self.assertIn(r"\fs22.400", overlay_cust.text)
        # Pos Y should be shifted by -10
        import re
        y_def = int(re.search(r"\\pos\(\d+,(\d+)\)", overlay_def.text).group(1))
        y_cust = int(re.search(r"\\pos\(\d+,(\d+)\)", overlay_cust.text).group(1))
        self.assertEqual(y_cust, y_def - 10)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_romanization_alignment_with_in_syllable_linebreak(self):
        from karaoke_core.editor import set_syllable_romanization
        linebroken_ass = ASS.replace(
            r"{\kf10\c&HFF}one {\kf10}two {\kf10}three {\kf10}four",
            r"{\kf20}first\Nsecond {\kf20}third",
        )
        doc = AssDocument.from_text(linebroken_ass)
        syllables = doc.karaoke_syllables()
        set_syllable_romanization(doc, syllables[0].id, "break_rom")
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        count = materialize_romanization_overlays(prepared, ffmpeg=shutil.which("ffmpeg"))
        self.assertEqual(count, 1)
        overlay = [e for e in prepared.events() if e.name == "KaraokeRomanization"][0]
        self.assertIn("break_rom", overlay.text)
        # Overlay should be positioned with positive coords
        import re
        match = re.search(r"\\pos\((\d+),(\d+)\)", overlay.text)
        self.assertIsNotNone(match)
        x, y = int(match.group(1)), int(match.group(2))
        self.assertGreater(x, 0)
        self.assertGreater(y, 0)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_romanization_disabled_toggle(self):
        from karaoke_core.editor import set_syllable_romanization
        doc = AssDocument.from_text(ASS)
        syllables = doc.karaoke_syllables()
        set_syllable_romanization(doc, syllables[0].id, "one_rom")
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        count = materialize_romanization_overlays(
            prepared,
            ffmpeg=shutil.which("ffmpeg"),
            layout=RenderLayoutSettings(enable_romanization=False),
        )
        self.assertEqual(count, 0)
        overlays = [e for e in prepared.events() if e.name == "KaraokeRomanization"]
        self.assertEqual(len(overlays), 0)

    def test_ffmpeg_progress_cancellation(self):
        import sys, threading
        from karaoke_core.render import _run_ffmpeg_progress
        evt = threading.Event()
        threading.Timer(0.1, evt.set).start()
        with self.assertRaises(RuntimeError) as cm:
            _run_ffmpeg_progress(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                cancel_event=evt,
            )
    def test_render_normalizes_bottom_alignment_to_middle_centered(self):
        doc = AssDocument.from_text(
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\an2\kf50}BottomLine" + "\n"
        )
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        styles = ass_text_styles(prepared)
        self.assertEqual(styles["default"].alignment, 5)
        self.assertIn(r"\an5", prepared.events()[0].text)
        self.assertNotIn(r"\an2", prepared.events()[0].text)

    def test_padded_crop_centers_content_symmetrically(self):
        # When content is near bottom edge, padded_crop centers it symmetrically within canvas bounds
        bbox = CropRect(100, 1000, 200, 50)
        crop = padded_crop(bbox, 1920, 1080, RenderLayoutSettings(padding_top=24, padding_bottom=24, padding_left=20, padding_right=20))
        # Desired height: 50 + 48 = 98. Center: 1025. y0 = 1025 - 49 = 976.
        self.assertEqual(crop.height, 98)
        self.assertEqual(bbox.y - crop.y, crop.bottom - bbox.bottom)
        self.assertEqual(bbox.y - crop.y, 24)

    def test_vertical_crop_y_expression_large_keyframe_count_ffmpeg_eval(self):
        # 100 keyframes should not exceed FFmpeg eval nesting/stack depth limit
        keyframes = tuple((float(i), i * 30) for i in range(100))
        for continuous in (True, False):
            plan = VerticalFollowPlan(
                crop=CropRect(0, 0, 100, 100),
                keyframes=keyframes,
                easing_seconds=0.5,
                continuous=continuous,
                smooth_percent=50.0,
            )
            expr = _vertical_crop_y_expression(
                plan,
                source_height=3000,
                scaled_height=3000,
                output_height=400,
            )
            self.assertIsInstance(expr, str)
            self.assertIn("if(lt(t", expr)

            # Test actual evaluation with FFmpeg nullsrc
            import subprocess
            cmd = [
                "ffmpeg", "-v", "error", "-f", "lavfi",
                "-i", "nullsrc=s=100x100:d=1",
                "-vf", f"crop=w=10:h=10:x=0:y={expr}",
                "-f", "null", "-",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"FFmpeg eval failed for continuous={continuous}: {res.stderr}")

    def test_interpolate_cube_surface_contrasting_colors_avoids_gray(self):
        red_ass = "&H0000FF&"    # RGB: 255, 0, 0
        cyan_ass = "&HFFFF00&"   # RGB: 0, 255, 255
        mid_ass = interpolate_cube_surface(red_ass, cyan_ass, 0.5)
        r, g, b = ass_to_rgb(mid_ass)
        # Verify that it didn't pass through gray (128, 128, 128)
        self.assertFalse(abs(r - g) < 20 and abs(g - b) < 20 and abs(r - 128) < 30, f"Interpolation desaturated to gray: RGB=({r},{g},{b})")
        # Ensure vibrant saturated color (at least one component near 255 or 0)
        self.assertTrue(max(r, g, b) >= 200, f"Too dark: RGB=({r},{g},{b})")
        self.assertTrue(min(r, g, b) <= 60, f"Too desaturated: RGB=({r},{g},{b})")

        # Red to Green passes through Yellow
        green_ass = "&H00FF00&"  # RGB: 0, 255, 0
        yellow_ass = interpolate_cube_surface(red_ass, green_ass, 0.5)
        yr, yg, yb = ass_to_rgb(yellow_ass)
        self.assertGreater(yr, 200)
        self.assertGreater(yg, 200)
        self.assertLess(yb, 50)

    def test_shift_hue_and_calculate_hue_offset(self):
        red_ass = "&H0000FF&"
        orange_ass = shift_hue(red_ass, 30.0)
        r, g, b = ass_to_rgb(orange_ass)
        self.assertGreater(r, 200)
        self.assertTrue(100 <= g <= 160)
        self.assertLess(b, 20)

        offset = calculate_hue_offset_degrees(red_ass, orange_ass)
        self.assertAlmostEqual(offset, 30.0, delta=1.5)

    def test_generate_surface_dynamic_tags_splits_wide_angles(self):
        red_ass = "&H0000FF&"
        orange_ass = "&H0080FF&"
        tags_small = generate_surface_dynamic_tags(red_ass, orange_ass, 0, 100)
        # <= 60 deg -> single \t tag
        self.assertEqual(tags_small.count(r"\t("), 1)

        cyan_ass = "&HFFFF00&"
        tags_large = generate_surface_dynamic_tags(red_ass, cyan_ass, 0, 100)
        # 180 deg -> multiple intermediate \t steps along cube surface
        self.assertGreater(tags_large.count(r"\t("), 1)

    def test_apply_render_burst_styling_alternate_gradient_dynamic(self):
        source = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\kf10\c&HFF}one {\kf10}two {\kf10}three{\c} {\kf10}four
'''
        doc = AssDocument.from_text(source)
        doc_raw_before = doc.dumps()

        # 1. Alternate mode: 1st=Red, 2nd=Orange, 3rd=Red
        alt_settings = RenderLayoutSettings(
            burst_color_mode="alternate",
            burst_base_color="&H0000FF&",
            burst_alt_color="&H0080FF&",
        )
        rendered_alt = prepare_render_document(doc, alt_settings)
        text_alt = rendered_alt.events()[0].text
        self.assertIn(r"\1c&H0000FF&", text_alt)
        self.assertIn(r"\1c&H0080FF&", text_alt)
        self.assertEqual(doc.dumps(), doc_raw_before)

        # 2. Gradient mode: 1st=Red, 3rd=Orange, 2nd=Interpolated intermediate
        grad_settings = RenderLayoutSettings(
            burst_color_mode="gradient",
            burst_base_color="&H0000FF&",
            burst_alt_color="&H0080FF&",
        )
        rendered_grad = prepare_render_document(doc, grad_settings)
        text_grad = rendered_grad.events()[0].text
        self.assertIn(r"\1c&H0000FF&", text_grad)
        self.assertIn(r"\1c&H0080FF&", text_grad)
        self.assertEqual(doc.dumps(), doc_raw_before)

        # 3. Dynamic mode: contains dynamic \t morphing tags
        dyn_settings = RenderLayoutSettings(
            burst_color_mode="dynamic",
            burst_base_color="&H0000FF&",
            burst_alt_color="&H0080FF&",
        )
        rendered_dyn = prepare_render_document(doc, dyn_settings)
        text_dyn = rendered_dyn.events()[0].text
        self.assertIn(r"\t(", text_dyn)
        self.assertIn(r"\1c", text_dyn)
        # All burst syllables must animate in sync until event_end_ms (1000ms)
        self.assertIn(r"\t(990,1000,", text_dyn)
        self.assertIn(r"\t(970,1000,", text_dyn)
        self.assertIn(r"\t(980,1000,", text_dyn)
        self.assertEqual(doc.dumps(), doc_raw_before)

    def test_build_burst_style_preview_document_burst_coloring(self):
        style = AssTextStyle(name="Default", font_name="Arial", font_size=32)
        preview_doc = build_burst_style_preview_document(
            style,
            width=900,
            height=220,
            burst_color_mode="alternate",
            burst_base_color="&H0000FF&",
            burst_alt_color="&H0080FF&",
            burst_hue_offset=30.0,
        )
        all_text = " ".join(e.text for e in preview_doc.events())
        self.assertIn(r"\1c&H0000FF&", all_text)
        self.assertIn(r"\1c&H0080FF&", all_text)

    def test_generate_burst_pulse_tags_frequency_and_phase(self):
        red = "&H0000FF&"
        orange = "&H0080FF&"
        init_tag, anim_tags = generate_burst_pulse_tags(red, orange, start_ms=0, end_ms=1000, hz=2.0, phase_offset_ms=0)
        self.assertEqual(init_tag, r"\1c&H0000FF&")
        self.assertIn(r"\t(", anim_tags)
        # Period at 2 Hz is 500ms; at t=250ms it should reach orange, and at t=500ms back to red.
        # Across 1000ms we should see multiple \t transitions.
        self.assertGreaterEqual(anim_tags.count(r"\t("), 4)

        # Continuity check with phase_offset: if syllable starts at t=250ms with phase 0, it starts from orange
        init_250, _ = generate_burst_pulse_tags(red, orange, start_ms=250, end_ms=500, hz=2.0, phase_offset_ms=0)
        self.assertEqual(init_250, r"\1c&H0080FF&")

    def test_burst_counter_document_font_offset_y(self):
        doc = AssDocument.from_text(ASS)
        plan = build_burst_counter_plan(doc, duration=1.0)
        layout = BurstCounterLayout(180, 34, 200, 54, 210, 64, 28, plan.max_text)

        counter_default = build_burst_counter_document(
            plan, layout, frame_width=640, frame_height=360,
            settings=BurstCounterSettings(font_offset_y=0),
        )
        counter_offset = build_burst_counter_document(
            plan, layout, frame_width=640, frame_height=360,
            settings=BurstCounterSettings(font_offset_y=25),
        )

        card_default = next(e for e in counter_default.events() if e.style == "Card")
        card_offset = next(e for e in counter_offset.events() if e.style == "Card")
        # Background card position and vector must remain identical
        self.assertEqual(card_default.text, card_offset.text)

        text_default = next(e for e in counter_default.events() if e.style == "Counter")
        text_offset = next(e for e in counter_offset.events() if e.style == "Counter")
        self.assertNotEqual(text_default.text, text_offset.text)
        # Verify text pos y is shifted by exactly 25
        import re
        m_def = re.search(r"\\pos\(([\d.]+),([\d.]+)\)", text_default.text)
        m_off = re.search(r"\\pos\(([\d.]+),([\d.]+)\)", text_offset.text)
        self.assertIsNotNone(m_def)
        self.assertIsNotNone(m_off)
        y_def = float(m_def.group(2))
        y_off = float(m_off.group(2))
        self.assertAlmostEqual(y_off - y_def, 25.0, places=1)

    def test_build_burst_style_preview_document_pulse_and_offset(self):
        style = AssTextStyle(name="Default", font_name="Arial", font_size=32)
        preview_offset = build_burst_style_preview_document(
            style,
            width=900,
            height=220,
            burst_color_mode="dynamic",
            burst_base_color="&H0000FF&",
            burst_alt_color="&H0080FF&",
            burst_pulse_hz=4.0,
            font_offset_y=-10,
        )
        counter_event = next(e for e in preview_offset.events() if e.style == "Counter")
        import re
        m = re.search(r"\\pos\(([\d.]+),([\d.]+)\)", counter_event.text)
        self.assertIsNotNone(m)
        expected_y = 12 + min(70, int(220 * 0.35)) / 2.0 - 10
        self.assertAlmostEqual(float(m.group(2)), expected_y, places=1)
        # Dynamic pulse tags in preview
        all_text = " ".join(e.text for e in preview_offset.events())
        self.assertIn(r"\t(", all_text)

    def test_vertical_viewport_crop_retains_manual_padding_and_bounds(self):
        content_bbox = CropRect(100, 200, 800, 400)
        base_crop = CropRect(76, 176, 848, 448)  # 48px vertical padding (24 top, 24 bottom)
        # Manual crop with +50px сверху/снизу added:
        manual_crop = CropRect(76, 126, 848, 548)  # 100px extra height!

        vp_from_base = vertical_viewport_crop(
            base_crop, content_bbox, line_count=4, visible_lines=2,
            canvas_width=1920, canvas_height=1080,
            base_crop=base_crop,
        )
        vp_from_manual = vertical_viewport_crop(
            manual_crop, content_bbox, line_count=4, visible_lines=2,
            canvas_width=1920, canvas_height=1080,
            base_crop=base_crop,
        )
        # Viewport height stays strictly based on line count (does not bloat from manual crop):
        self.assertEqual(vp_from_manual.height, vp_from_base.height)
        self.assertEqual(vp_from_manual.x, manual_crop.x)
        self.assertEqual(vp_from_manual.width, manual_crop.width)

        # When visible_lines >= line_count, compact base height is used:
        vp_all_from_manual = vertical_viewport_crop(
            manual_crop, content_bbox, line_count=4, visible_lines=4,
            canvas_width=1920, canvas_height=1080,
            base_crop=base_crop,
        )
        self.assertEqual(vp_all_from_manual.height, base_crop.height)
        self.assertEqual(vp_all_from_manual.width, manual_crop.width)

        # Follow plan motion uses full manual_crop bounds: camera reaches manual_crop.y at top
        # and manual_crop.bottom - viewport.height at bottom, while maintaining compact viewport height:
        source = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:04.00,Default,,0,0,0,,{\k10}line1\N{\k10}line2\N{\k10}line3\N{\k10}line4
'''
        doc = AssDocument.from_text(source)
        plan_manual = build_vertical_follow_plan(
            doc, content_bbox, manual_crop, canvas_width=1920, canvas_height=1080,
            settings=VerticalFollowSettings(visible_lines=2),
            base_crop=base_crop,
        )
        self.assertEqual(plan_manual.crop.height, vp_from_base.height)
        self.assertEqual(plan_manual.keyframes[0][1], manual_crop.y)
        self.assertEqual(plan_manual.keyframes[-1][1], manual_crop.bottom - plan_manual.crop.height)
        for _, y in plan_manual.keyframes:
            self.assertGreaterEqual(y, manual_crop.y)
            self.assertLessEqual(y, manual_crop.bottom - plan_manual.crop.height)

    def test_apply_text_case_modes(self):
        text = r"{\k20}при{\k20}вет, {\k20}МИР!\N{\k30}как {\k10}ДЕЛА? отлично. всё хорошо."
        self.assertEqual(apply_text_case(text, "as_is"), text)
        self.assertEqual(
            apply_text_case(text, "upper"),
            r"{\k20}ПРИ{\k20}ВЕТ, {\k20}МИР!\N{\k30}КАК {\k10}ДЕЛА? ОТЛИЧНО. ВСЁ ХОРОШО.",
        )
        self.assertEqual(
            apply_text_case(text, "lower"),
            r"{\k20}при{\k20}вет, {\k20}мир!\N{\k30}как {\k10}дела? отлично. всё хорошо.",
        )
        self.assertEqual(
            apply_text_case(text, "sentence"),
            r"{\k20}При{\k20}вет, {\k20}мир!\N{\k30}Как {\k10}дела? Отлично. Всё хорошо.",
        )

    def test_prepare_render_document_with_text_casing(self):
        source = r'''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\k50}hello {\k50}WORLD \N{\k50}another {\k50}LINE
'''
        doc = AssDocument.from_text(source)
        # Upper
        p_upper = prepare_render_document(doc, RenderLayoutSettings(text_case="upper"))
        self.assertIn("HELLO", p_upper.events()[0].text)
        self.assertIn(r"\N", p_upper.events()[0].text)
        self.assertIn("ANOTHER", p_upper.events()[0].text)
        self.assertIn("LINE", p_upper.events()[0].text)

        # Sentence
        p_sent = prepare_render_document(doc, RenderLayoutSettings(text_case="sentence"))
        self.assertIn("Hello", p_sent.events()[0].text)
        self.assertIn("world", p_sent.events()[0].text)
        self.assertIn("Another", p_sent.events()[0].text)
        self.assertIn("line", p_sent.events()[0].text)

    def test_materialize_romanization_with_casing(self):
        from karaoke_core.editor import set_syllable_romanization
        source = r'''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\k50}s1{\k50}s2\N{\k50}s3{\k50}s4
'''
        doc = AssDocument.from_text(source)
        sylls = doc.karaoke_syllables()
        set_syllable_romanization(doc, sylls[0].id, "watashi")
        set_syllable_romanization(doc, sylls[1].id, "wa")
        set_syllable_romanization(doc, sylls[2].id, "anata")
        set_syllable_romanization(doc, sylls[3].id, "desu")
        prepared = prepare_render_document(doc, RenderLayoutSettings())
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            count = materialize_romanization_overlays(
                prepared, ffmpeg=ffmpeg,
                layout=RenderLayoutSettings(romanization_case="sentence"),
            )
            self.assertGreater(count, 0)
            rom_events = [e for e in prepared.events() if e.name == "KaraokeRomanization"]
            texts = [e.text for e in rom_events]
            # First line syllables: Watashi, wa
            self.assertTrue(any("Watashi" in t for t in texts))
            self.assertTrue(any("wa" in t for t in texts))
            # Second line syllables: Anata, desu
            self.assertTrue(any("Anata" in t for t in texts))
            self.assertTrue(any("desu" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
