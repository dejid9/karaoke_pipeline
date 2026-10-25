import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from karaoke_core.project import load_project
from karaoke_core.sps import TimelineSyllable
from karaoke_gui.app import KaraokeApp
from karaoke_gui.session import KaraokeSession
from karaoke_gui.timeline import DualTimeline, Viewport, heat_colour


DENSE_ASS = """[Script Info]\nTitle: gui-test\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\kf8}a{\\kf8}b{\\kf8}c{\\kf8\\c&HFF}d{\\kf8}e{\\c\\kf8}f{\\kf8}g{\\kf8}h{\\kf8}i{\\kf8}j{\\kf8}k{\\kf8}l{\\kf8}m{\\kf8}n{\\kf8}o{\\kf8}p\n"""


class SessionTests(unittest.TestCase):
    def test_open_and_transfer_does_not_mutate_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.ass"
            p.write_text(DENSE_ASS, encoding="utf-8")
            before = p.read_bytes()
            session = KaraokeSession()
            session.open_subtitles(p)
            result = session.transfer_to_sps(min_peak_sps=5)
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(len(result.timeline.syllables), 16)
            self.assertTrue(result.candidates)
            self.assertIsNot(result.timeline, session.karaoke_timeline)

    def test_selected_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.ass"
            p.write_text(DENSE_ASS, encoding="utf-8")
            session = KaraokeSession()
            session.open_subtitles(p)
            ids = [s.id for s in session.syllables[2:8]]
            result = session.transfer_to_sps(syllable_ids=ids, min_peak_sps=2)
            self.assertEqual(result.scope, "selection")
            self.assertEqual([s.id for s in result.timeline.syllables], ids)

    def test_project_attachment_uses_relative_path_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            ass = root / "subtitles" / "song.ass"
            ass.parent.mkdir()
            ass.write_text(DENSE_ASS, encoding="utf-8")
            session = KaraokeSession()
            session.new_project(root)
            session.open_subtitles(ass)
            self.assertEqual(session.project.subtitles, "subtitles/song.ass")

    def test_save_as_project_keeps_open_media_subtitles_and_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ass = base / "song.ass"
            media = base / "song.wav"
            ass.write_text(DENSE_ASS, encoding="utf-8")
            media.write_bytes(b"RIFF-test")

            session = KaraokeSession()
            session.open_subtitles(ass)
            session.set_media(media)
            result = session.transfer_to_sps(min_peak_sps=2)
            first = result.timeline.syllables[0]
            session.set_measurement(first.id, first.end, first.start)

            project_root = base / "saved-project"
            session.attach_project(project_root)
            config = load_project(project_root)
            self.assertEqual(config.media, str(media.resolve()))
            self.assertEqual(config.subtitles, str(ass.resolve()))
            self.assertTrue((project_root / "cache" / "sps_measurements.json").is_file())

            reopened = KaraokeSession()
            reopened.open_project(project_root)
            restored = reopened.transfer_to_sps(min_peak_sps=2)
            restored_first = restored.timeline.syllables[0]
            self.assertAlmostEqual(restored_first.effective_start, first.end)
            self.assertAlmostEqual(restored_first.effective_end, first.start)


class TimelineMathTests(unittest.TestCase):
    def test_sps_selection_playback_uses_formal_end_when_markers_are_reversed(self):
        item = TimelineSyllable("L0:S0", 1.0, 1.2, "go").with_measurement(1.18, 1.04)
        calls = []
        fake_app = SimpleNamespace(
            _selected_sps_items=lambda: [item],
            _play_interval=lambda start, end, **kwargs: calls.append((start, end, kwargs["label"])),
            _set_status=lambda _text: None,
        )
        KaraokeApp.play_sps_selection(fake_app)
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(calls[0][0], 1.0)
        self.assertAlmostEqual(calls[0][1], 1.04)
        self.assertIn("формального End", calls[0][2])

    def test_sps_marker_playback_uses_same_reversed_boundary_rule(self):
        item = TimelineSyllable("L0:S0", 1.0, 1.2, "go").with_measurement(1.18, 1.04)
        calls = []
        fake_app = SimpleNamespace(
            _marker_bounds=lambda _context: (item.effective_start, item.effective_end),
            _marker_items=lambda _context: [item],
            _begin_transport=lambda start, end, **kwargs: calls.append((start, end, kwargs)),
            _set_status=lambda _text: None,
        )
        KaraokeApp.play_between_markers(fake_app, "sps")
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(calls[0][0], 1.0)
        self.assertAlmostEqual(calls[0][1], 1.04)

    def test_play_to_formal_end_rewinds_only_for_reversed_sps_markers(self):
        item = TimelineSyllable("L0:S0", 1.0, 1.2, "go").with_measurement(1.18, 1.04)
        calls = []
        fake_app = SimpleNamespace(
            playhead_time=1.18,
            _marker_bounds=lambda _context: (item.effective_start, item.effective_end),
            _marker_items=lambda _context: [item],
            _begin_transport=lambda start, end, **kwargs: calls.append((start, end, kwargs)),
            _set_status=lambda _text: None,
        )
        KaraokeApp.play_to_stop_marker(fake_app, "sps")
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(calls[0][0], 1.0)
        self.assertAlmostEqual(calls[0][1], 1.04)

    def test_viewport_zoom_and_clamp(self):
        vp = Viewport()
        vp.set_total(10, 110, reset=True)
        vp.zoom(0.5, 60)
        self.assertAlmostEqual(vp.span, 50)
        self.assertAlmostEqual(vp.view_start, 35)
        vp.pan(-1000)
        self.assertEqual(vp.view_start, 10)
        self.assertAlmostEqual(vp.view_end, 60)

    def test_precision_wheel_steps_support_mouse_and_touchpad_deltas(self):
        self.assertAlmostEqual(DualTimeline._wheel_steps(120), 1.0)
        self.assertAlmostEqual(DualTimeline._wheel_steps(-120), -1.0)
        self.assertAlmostEqual(DualTimeline._wheel_steps(30), 0.25)
        self.assertAlmostEqual(DualTimeline._wheel_steps(-1), -1.0)

    def test_heat_colour_is_stable_and_distinct(self):
        self.assertRegex(heat_colour(0), r"^#[0-9a-f]{6}$")
        self.assertRegex(heat_colour(1), r"^#[0-9a-f]{6}$")
        self.assertNotEqual(heat_colour(0), heat_colour(1))
        self.assertEqual(heat_colour(-10), heat_colour(0))
        self.assertEqual(heat_colour(10), heat_colour(1))


if __name__ == "__main__":
    unittest.main()
