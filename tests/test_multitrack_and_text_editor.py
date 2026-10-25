import unittest
from pathlib import Path

from karaoke_core.ass import AssDocument
from karaoke_core.editor import (
    adjust_id_references_after_track0_delete,
    adjust_id_references_after_track0_insert,
)
from karaoke_gui.session import build_sps_transfer


SAMPLE_MULTITRACK_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\kf100}One {\\kf100}Two {\\kf100}Three
Dialogue: 0,0:00:01.50,0:00:03.50,Default,,0,0,0,track:1,{\\kf100\\id0:2}BackTwo {\\kf100\\id0:3}BackThree
"""


class TestMultitrackAndReferences(unittest.TestCase):
    def test_id_references_shift_on_track0_delete(self):
        doc = AssDocument.from_text(SAMPLE_MULTITRACK_ASS)
        # S1=One, S2=Two, S3=Three. Delete ID 2 (Two)
        adjust_id_references_after_track0_delete(doc, 2)
        events = [e for e in doc.events() if str(getattr(e, "effect", "")).startswith("track:1")]
        self.assertEqual(len(events), 1)
        # S2 reference was deleted from the track:1 line, and S3 reference shifted to id0:2
        self.assertNotIn(r"\id0:3", events[0].text)
        self.assertIn(r"\id0:2", events[0].text)

    def test_id_references_shift_on_track0_insert(self):
        doc = AssDocument.from_text(SAMPLE_MULTITRACK_ASS)
        # Insert before ID 2 -> previous ID 2 becomes ID 3, ID 3 becomes ID 4
        adjust_id_references_after_track0_insert(doc, 2)
        events = [e for e in doc.events() if str(getattr(e, "effect", "")).startswith("track:1")]
        self.assertEqual(len(events), 1)
        self.assertIn(r"\id0:3", events[0].text)
        self.assertIn(r"\id0:4", events[0].text)

    def test_sps_transfer_filters_to_track0_and_cleans_tags(self):
        doc = AssDocument.from_text(SAMPLE_MULTITRACK_ASS)
        # Add remap tag to track 0
        doc.events()[0].text = r"{\kf100}One {\kf100\remap}Two {\kf100}Three"
        doc.events()[0].commit()

        syllables = doc.karaoke_syllables()
        # Should have 3 syllables on track 0, 2 on track 1
        track0 = [s for s in syllables if getattr(s, "track", 0) == 0]
        track1 = [s for s in syllables if getattr(s, "track", 0) == 1]
        self.assertEqual(len(track0), 3)
        self.assertEqual(len(track1), 2)

        # Mock items with .source and .id
        class MockItem:
            def __init__(self, s):
                self.id = s.id
                self.source = s

        mock_items = [MockItem(s) for s in syllables]
        result = build_sps_transfer(mock_items)

        # SPS timeline must only contain track 0 syllables (3 total)
        self.assertEqual(len(result.timeline.syllables), 3)
        # SPS timeline text must have \remap stripped
        texts = [s.text.strip() for s in result.timeline.syllables]
        self.assertEqual(texts, ["One", "Two", "Three"])

    def test_session_insert_track_syllable(self):
        from karaoke_gui.session import KaraokeSession
        session = KaraokeSession()
        session.document = AssDocument.from_text(SAMPLE_MULTITRACK_ASS)
        session._rebuild_karaoke_after_edit()

        # Insert on track 2 linked to track 0 seq_id 1
        res = session.edit_insert_track_syllable(
            track=2, start_time=0.5, duration_cs=60, text="Intro", ref_track0_seq=1, tag_type="kf"
        )
        self.assertEqual(res.action, "insert-track")
        self.assertEqual(res.focus_time, 0.5)

        # Check document has the new event with track:2 and \id0:1
        evs = [e for e in session.document.events() if getattr(e, "effect", "") == "track:2"]
        self.assertEqual(len(evs), 1)
        self.assertIn(r"\kf60\id0:1", evs[0].text)
        self.assertIn("Intro", evs[0].text)

        # Rebuilt syllables should include track 2
        track2_syls = [s for s in session.karaoke_timeline.syllables if getattr(s, "track", 0) == 2]
        self.assertEqual(len(track2_syls), 1)
        self.assertEqual(track2_syls[0].start, 0.5)
        self.assertEqual(track2_syls[0].source.duration_cs, 60)

    def test_delete_sole_syllable_on_extra_track(self):
        from karaoke_core.editor import delete_syllable
        doc = AssDocument.from_text("""[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\\kf100}One {\\kf100}Two
Dialogue: 0,0:00:01.50,0:00:02.50,Default,,0,0,0,track:1,{\\kf100\\id0:2}Solo
""")
        syls = doc.karaoke_syllables()
        solo = next(s for s in syls if s.track == 1)
        # Deleting the only syllable in track 1 event should delete the event line
        res = delete_syllable(doc, solo.id)
        self.assertEqual(res.action, "delete")
        events = list(doc.events())
        self.assertEqual(len(events), 1)
        self.assertNotIn("track:1", [e.effect for e in events])

    def test_edit_add_track_creates_full_span_and_can_split(self):
        from karaoke_gui.session import KaraokeSession
        session = KaraokeSession()
        session.document = AssDocument.from_text(SAMPLE_MULTITRACK_ASS)
        session._rebuild_karaoke_after_edit()

        # Add track 2 spanning 10 seconds
        res = session.edit_add_track(track_id=2, duration_seconds=10.0, tag_type="kf")
        self.assertEqual(res.action, "add-track")

        # Find syllable on track 2
        track2_syls = [s for s in session.karaoke_timeline.syllables if getattr(s, "track", 0) == 2]
        self.assertEqual(len(track2_syls), 1)
        self.assertEqual(track2_syls[0].start, 0.0)
        self.assertEqual(track2_syls[0].end, 10.0)
        self.assertEqual(track2_syls[0].source.duration_cs, 1000)

        # Now split this syllable at 3.5s
        split_res = session.edit_split_at_time(track2_syls[0].id, 3.5)
        self.assertEqual(split_res.action, "split-time")
        track2_syls_after = [s for s in session.karaoke_timeline.syllables if getattr(s, "track", 0) == 2]
        self.assertEqual(len(track2_syls_after), 2)
        self.assertEqual(track2_syls_after[0].start, 0.0)
        self.assertEqual(track2_syls_after[0].end, 3.5)
        self.assertEqual(track2_syls_after[1].start, 3.5)
        self.assertEqual(track2_syls_after[1].end, 10.0)

        # Redistribute boundary between them to 4.0s
        boundary_res = session.edit_boundary(track2_syls_after[0].id, track2_syls_after[1].id, 4.0)
        self.assertEqual(boundary_res.action, "boundary")
        track2_syls_final = [s for s in session.karaoke_timeline.syllables if getattr(s, "track", 0) == 2]
        self.assertEqual(track2_syls_final[0].end, 4.0)
        self.assertEqual(track2_syls_final[1].start, 4.0)

    def test_vertical_follow_tracks_track0_only(self):
        from karaoke_core.render import build_vertical_follow_plan, dialogue_line_count, VerticalFollowSettings, CropRect
        # Document with 3 lines on Track 0, and a dialogue on Track 1 with 10 lines
        text = """[Script Info]
PlayResX: 1920
PlayResY: 1080

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:10.00,Default,,0,0,0,,{\\kf100}Row1\\N{\\kf100}Row2\\N{\\kf100}Row3
Dialogue: 0,0:00:00.00,0:00:20.00,Default,,0,0,0,track:1,{\\kf50}T1\\N{\\kf50}T2\\N{\\kf50}T3\\N{\\kf50}T4\\N{\\kf50}T5\\N{\\kf50}T6
"""
        doc = AssDocument.from_text(text)
        # Line count must be 3 (from Track 0), not 6 from Track 1!
        self.assertEqual(dialogue_line_count(doc), 3)

        bbox = CropRect(100, 100, 400, 300)
        full_crop = CropRect(50, 50, 500, 400)
        settings = VerticalFollowSettings(visible_lines=1, easing_seconds=0.3)
        plan = build_vertical_follow_plan(doc, bbox, full_crop, 1920, 1080, settings)

        # Plan must have 4 keyframes: hold at 0.0 + the 3 lines of Track 0
        self.assertEqual(len(plan.keyframes), 4)
        # First keyframe timestamp is 0.0 hold
        self.assertEqual(plan.keyframes[0][0], 0.0)
        # Second keyframe corresponds to Row1 starting at 1.0s
        self.assertAlmostEqual(plan.keyframes[1][0], 1.0, places=2)
        # Third keyframe corresponds to Row2 starting at 2.0s
        self.assertAlmostEqual(plan.keyframes[2][0], 2.0, places=2)
        # Fourth keyframe corresponds to Row3 starting at 3.0s
        self.assertAlmostEqual(plan.keyframes[3][0], 3.0, places=2)

    def test_materialize_remap_no_invalid_group_reference(self):
        from karaoke_core.render import prepare_render_document, RenderLayoutSettings
        doc = AssDocument.from_text(
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\kf50\remap}Hello {\kf50}World" + "\n"
        )
        settings = RenderLayoutSettings()
        # Should not raise re.error: invalid group reference 1
        rendered = prepare_render_document(doc, settings)
        self.assertIn("1c", rendered.events()[0].text)

    def test_resolve_extra_track_references_and_strip_id_tags(self):
        from karaoke_core.render import resolve_extra_track_references_and_strip_id_tags, prepare_render_document, RenderLayoutSettings
        doc = AssDocument.from_text(
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\kf50\-romaji:he}Бе{\kf50\-romaji:gi}ги" + "\n"
            r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,track:1,{\kf50\id0:1}" + "\n"
            r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,track:1,{\kf50}{\id0:2}" + "\n"
            r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,track:1,{\kf50\id0:1}Кастом" + "\n"
        )
        resolve_extra_track_references_and_strip_id_tags(doc)
        evs = doc.events()
        # Track 0 untouched text and romaji
        self.assertIn("Бе", evs[0].text)
        self.assertIn("ги", evs[0].text)
        # Extra track 1 line 1: empty text referenced id 1 -> replaced with "Бе" and romaji "he", \id0:1 stripped
        self.assertIn("Бе", evs[1].text)
        self.assertNotIn(r"\id", evs[1].text)
        self.assertNotIn("{}", evs[1].text)
        # Extra track 1 line 2: empty text referenced id 2 -> replaced with "ги" and romaji "gi", \id0:2 stripped
        self.assertIn("ги", evs[2].text)
        self.assertNotIn(r"\id", evs[2].text)
        self.assertNotIn("{}", evs[2].text)
        # Extra track 1 line 3: explicit text preserved, \id0:1 stripped
        self.assertIn("Кастом", evs[3].text)
        self.assertNotIn(r"\id", evs[3].text)

    def test_prepare_geometry_document_strips_extra_tracks(self):
        from karaoke_core.render import prepare_geometry_document, RenderLayoutSettings
        doc = AssDocument.from_text(
            "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\kf50}MainTrack" + "\n"
            r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,track:1,{\kf50}ExtraTrack1" + "\n"
            r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,track:2,{\kf50}ExtraTrack2" + "\n"
        )
        geo_doc, _ = prepare_geometry_document(doc, RenderLayoutSettings())
        geo_events = geo_doc.events()
        # Geometry doc should only retain track 0 dialogue events
        self.assertEqual(len(geo_events), 1)
        self.assertIn("MainTrack", geo_events[0].text)

    def test_expand_extra_track_overlays_and_romanization(self):
        from karaoke_core.render import prepare_render_document, RenderLayoutSettings, materialize_romanization_overlays
        ass_text = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,60,&H00FFFFFF,&H80FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,2,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:10.00,Default,,0,0,0,,{\\kf100\\_kraGU}{\\remap}One {\\kf100\\_krdHdv}Two
Dialogue: 0,0:00:00.00,0:00:10.00,Default,,0,0,0,track:1,{\\kf200}{\\kf50}{\\id0:1}{\\wipe}{\\kf50}{\\kf80}{\\id0:1}{\\kf620}
"""
        doc = AssDocument.from_text(ass_text)
        rdoc = prepare_render_document(doc, RenderLayoutSettings())
        dialogues = [e for e in rdoc.events() if e.kind == "Dialogue"]
        comments = [e for e in rdoc.events() if e.kind == "Comment" and e.effect == "track:1"]
        self.assertEqual(len(comments), 1)

        # Base dialogue + 2 retimed overlays for ID 1
        self.assertEqual(len(dialogues), 3)

        ov1 = dialogues[1]
        self.assertEqual(ov1.start_raw, "0:00:02.00")
        self.assertEqual(ov1.end_raw, "0:00:02.50")
        self.assertIn(r"\2a&HFF&", ov1.text)
        self.assertIn(r"\kf50", ov1.text)
        self.assertIn("One", ov1.text)

        ov2 = dialogues[2]
        self.assertEqual(ov2.start_raw, "0:00:03.00")
        self.assertEqual(ov2.end_raw, "0:00:10.00")
        self.assertIn(r"\2a&HFF&", ov2.text)
        self.assertIn(r"\kf80", ov2.text)
        self.assertIn("One", ov2.text)

        cnt = materialize_romanization_overlays(rdoc, ffmpeg="ffmpeg")
        retimed_rom = [e for e in rdoc.events() if "retimed_romaji:1" in e.effect]
        self.assertEqual(len(retimed_rom), 2)
        self.assertEqual(retimed_rom[0].start_raw, "0:00:02.00")
        self.assertEqual(retimed_rom[0].end_raw, "0:00:02.50")
        self.assertIn(r"\kf50", retimed_rom[0].text)
        self.assertIn("he", retimed_rom[0].text)
        self.assertEqual(retimed_rom[1].start_raw, "0:00:03.00")
        self.assertEqual(retimed_rom[1].end_raw, "0:00:10.00")
        self.assertIn(r"\kf80", retimed_rom[1].text)
        self.assertIn("he", retimed_rom[1].text)

    def test_render_panel_state_and_settings(self):
        import tkinter as tk
        from karaoke_gui.render_panel import RenderPanel
        from karaoke_gui.session import KaraokeSession

        root = tk.Tk()
        root.withdraw()
        try:
            session = KaraokeSession()
            panel = RenderPanel(root, session=session, prepare_source=lambda: True, set_status=lambda s: None)
            panel.spacing_var.set("-15")
            panel.enable_romanization_var.set(False)
            settings = panel._layout_settings()
            self.assertEqual(settings.line_spacing_px, -15.0)
            self.assertFalse(settings.enable_romanization)

            state = panel.project_state(Path("."))
            self.assertEqual(state["spacing"], "-15")
            self.assertFalse(state["enable_romanization"])

            panel.spacing_var.set("20")
            panel.enable_romanization_var.set(True)
            panel.apply_project_state(state, Path("."))
            self.assertEqual(panel.spacing_var.get(), "-15")
            self.assertFalse(panel.enable_romanization_var.get())
        finally:
            root.destroy()

    def test_russian_layout_shortcuts_text_and_entry(self):
        import tkinter as tk
        from karaoke_gui.app import KaraokeApp

        app = KaraokeApp()
        app.withdraw()
        try:
            # 1. Test Text widget
            text_widget = app.karaoke_text_editor
            text_widget.config(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", "Строка текста")
            text_widget.focus_set()

            # Select All with Russian keysym Cyrillic_ef
            ev_select_all = tk.Event()
            ev_select_all.widget = text_widget
            ev_select_all.state = 4  # Ctrl
            ev_select_all.keycode = ord("A")
            ev_select_all.keysym = "cyrillic_ef"
            ev_select_all.char = "ф"
            res = app._handle_text_widget_shortcuts(ev_select_all)
            self.assertEqual(res, "break")
            self.assertTrue(bool(text_widget.tag_ranges("sel")))

            # Copy with Russian keysym Cyrillic_es
            ev_copy = tk.Event()
            ev_copy.widget = text_widget
            ev_copy.state = 4
            ev_copy.keycode = ord("C")
            ev_copy.keysym = "cyrillic_es"
            ev_copy.char = "\x03"
            res = app._handle_text_widget_shortcuts(ev_copy)
            self.assertEqual(res, "break")
            self.assertEqual(app.clipboard_get(), "Строка текста")

            # Cut with Russian keysym Cyrillic_che
            ev_cut = tk.Event()
            ev_cut.widget = text_widget
            ev_cut.state = 4
            ev_cut.keycode = ord("X")
            ev_cut.keysym = "cyrillic_che"
            ev_cut.char = "ч"
            res = app._handle_text_widget_shortcuts(ev_cut)
            self.assertEqual(res, "break")
            self.assertEqual(text_widget.get("1.0", "end-1c"), "")

            # Paste with Russian keysym Cyrillic_em
            ev_paste = tk.Event()
            ev_paste.widget = text_widget
            ev_paste.state = 4
            ev_paste.keycode = ord("V")
            ev_paste.keysym = "cyrillic_em"
            ev_paste.char = "м"
            res = app._handle_text_widget_shortcuts(ev_paste)
            self.assertEqual(res, "break")
            self.assertEqual(text_widget.get("1.0", "end-1c"), "Строка текста")

            # 2. Test Entry widget
            entry_widget = tk.Entry(app)
            entry_widget.insert(0, "Тестовое поле")
            ev_entry_sel = tk.Event()
            ev_entry_sel.widget = entry_widget
            ev_entry_sel.state = 4
            ev_entry_sel.keycode = ord("A")
            ev_entry_sel.keysym = "cyrillic_ef"
            ev_entry_sel.char = "ф"
            res = app._handle_text_widget_shortcuts(ev_entry_sel)
            self.assertEqual(res, "break")
            self.assertTrue(entry_widget.selection_present())
            self.assertEqual(entry_widget.selection_get(), "Тестовое поле")
        finally:
            app.destroy()

    def test_multitrack_reordering_and_split_active_track(self):
        from karaoke_gui.app import KaraokeApp
        app = KaraokeApp()
        app.withdraw()
        try:
            app.session.document = AssDocument.from_text(SAMPLE_MULTITRACK_ASS)
            app.session._rebuild_karaoke_after_edit()
            app.advanced_mode_var.set(True)
            app.karaoke_timeline.set_advanced_mode(True)
            app._refresh_from_session(reset_view=True)

            self.assertEqual(app.karaoke_timeline.tracks, [0, 1])

            # 1. Reorder tracks: move Track 0 down so Track 1 is above Track 0
            app._handle_move_track(0, 1)
            self.assertEqual(app.karaoke_timeline.tracks, [1, 0])
            self.assertEqual(app.karaoke_timeline.active_track, 0)

            # Move Track 1 down so Track 0 is above Track 1
            app._handle_move_track(1, 1)
            self.assertEqual(app.karaoke_timeline.tracks, [0, 1])
            self.assertEqual(app.karaoke_timeline.active_track, 1)

            # Move Track 1 up again so Track 1 is above Track 0
            app._handle_move_track(1, -1)
            self.assertEqual(app.karaoke_timeline.tracks, [1, 0])
            self.assertEqual(app.karaoke_timeline.active_track, 1)

            # 2. Test split selection at playhead = 2.2 (strictly inside both Track 0 'Two' and Track 1 'BackTwo')
            app._set_playhead(2.2)
            app.karaoke_timeline.selected_ids = set()

            # When active_track is 1 and no selection: candidate on Track 1 must be chosen
            app.karaoke_timeline.active_track = 1
            item = app._karaoke_item_for_playhead_split()
            self.assertIsNotNone(item)
            self.assertEqual(getattr(item.source, "track", 0), 1)
            self.assertIn("BackTwo", item.text)

            # When active_track is 0 and no selection: candidate on Track 0 must be chosen
            app.karaoke_timeline.active_track = 0
            item = app._karaoke_item_for_playhead_split()
            self.assertIsNotNone(item)
            self.assertEqual(getattr(item.source, "track", 0), 0)
            self.assertIn("Two", item.text)

            # 3. Test explicit selection overriding stale active_track
            syl_t1 = next(s for s in app.session.syllables if getattr(s.source, "track", 0) == 1 and "BackTwo" in s.text)
            syl_t0 = next(s for s in app.session.syllables if getattr(s.source, "track", 0) == 0 and "Two" in s.text)

            # Force active_track to 0, but select Track 1's syllable
            app.karaoke_timeline.active_track = 0
            app.karaoke_timeline.selected_ids = {syl_t1.id}
            item = app._karaoke_item_for_playhead_split()
            self.assertIsNotNone(item)
            self.assertEqual(item.id, syl_t1.id)
            self.assertEqual(app.karaoke_timeline.active_track, 1)

            # Force active_track to 1, but select Track 0's syllable
            app.karaoke_timeline.active_track = 1
            app.karaoke_timeline.selected_ids = {syl_t0.id}
            item = app._karaoke_item_for_playhead_split()
            self.assertIsNotNone(item)
            self.assertEqual(item.id, syl_t0.id)
            self.assertEqual(app.karaoke_timeline.active_track, 0)

            # 4. Test _karaoke_selection_changed updates active_track
            app.karaoke_timeline.active_track = 0
            app._karaoke_selection_changed({syl_t1.id})
            self.assertEqual(app.karaoke_timeline.active_track, 1)

            app._karaoke_selection_changed({syl_t0.id})
            self.assertEqual(app.karaoke_timeline.active_track, 0)
        finally:
            app.destroy()

    def test_alignment_panel_worker_scoping(self):
        import symtable
        panel_file = Path(__file__).resolve().parent.parent / "karaoke_gui" / "alignment_panel.py"
        table = symtable.symtable(panel_file.read_text(encoding="utf-8"), str(panel_file), "exec")

        def find_symbol_in_scope(t, func_name, symbol_name):
            if t.get_name() == func_name:
                for c in t.get_children():
                    if c.get_name() == "worker":
                        for s in c.get_symbols():
                            if s.get_name() == symbol_name:
                                return s
            for c in t.get_children():
                res = find_symbol_in_scope(c, func_name, symbol_name)
                if res is not None:
                    return res
            return None

        settings_sym = find_symbol_in_scope(table, "run_mfa", "settings")
        self.assertIsNotNone(settings_sym)
        self.assertFalse(settings_sym.is_local())
        self.assertTrue(settings_sym.is_free())

        active_sym = find_symbol_in_scope(table, "run_mfa", "active_settings")
        self.assertIsNotNone(active_sym)
        self.assertTrue(active_sym.is_local())
        self.assertTrue(active_sym.is_assigned())


if __name__ == "__main__":
    unittest.main()


