from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from karaoke_core.sps import TimelineSyllable, sps_graph_points
from karaoke_gui.app import KaraokeApp
from karaoke_gui.sps_graph import (
    GraphExportSettings, GraphSeries, SPSGraph, _format_graph_time,
    render_sps_graph_png,
)
from karaoke_gui.theme import get_theme
from karaoke_gui.timeline import Viewport


class SPSGraphPointTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            TimelineSyllable(id=f"s{i}", start=i * 0.1, end=(i + 1) * 0.1, text=str(i))
            for i in range(15)
        ]

    def test_strict_graph_is_timeline_anchored(self):
        points = sps_graph_points(self.items, metric="strict-contained", window=1.0)
        self.assertTrue(points)
        self.assertEqual(points[0].time, self.items[0].start)
        self.assertTrue(all(abs(p.duration - 1.0) < 1e-9 for p in points))
        self.assertGreaterEqual(max(p.speed for p in points), 10.0)

    def test_measured_graph_uses_independent_trimmed_boundaries(self):
        measured = list(self.items)
        measured[0] = measured[0].with_measurement(0.03, 0.08)
        measured[1] = measured[1].with_measurement(0.12, 0.18)
        ass = sps_graph_points(measured, metric="legacy", measured=False)
        exact = sps_graph_points(measured, metric="legacy", measured=True)
        self.assertTrue(ass and exact)
        self.assertFalse(ass[0].measured)
        self.assertTrue(exact[0].measured)
        self.assertAlmostEqual(exact[0].time, 0.03)
        # Perceptual trimming shortens the actual legacy span and therefore can
        # change its count/duration rate without touching karaoke timing.
        self.assertNotEqual((ass[0].window_start, ass[0].window_end), (exact[0].window_start, exact[0].window_end))

    def test_onset_metric_is_available(self):
        points = sps_graph_points(self.items, metric="strict-onset", window=1.0)
        self.assertTrue(points)
        self.assertTrue(all(p.metric == "strict-onset" for p in points))

    def test_invalid_metric_rejected(self):
        with self.assertRaises(ValueError):
            sps_graph_points(self.items, metric="mystery")

    def test_display_subset_caps_dense_graph_geometry(self):
        points = list(range(10000))
        subset = SPSGraph._display_subset(points, 400)
        self.assertLessEqual(len(subset), 1002)
        self.assertEqual(subset[0], 0)
        self.assertEqual(subset[-1], points[-1])

    def test_png_export_is_16_by_9_and_contains_graph(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        viewport = Viewport()
        viewport.set_total(0.0, 1.5, reset=True)
        points = sps_graph_points(self.items, metric="legacy", measured=False)
        with tempfile.TemporaryDirectory() as td:
            target = render_sps_graph_png(
                Path(td) / "graph.png",
                [GraphSeries("ASS", points, "#5d8fe8")],
                viewport=viewport,
                palette=get_theme(None),
                smoothing=3,
                width=640,
                height=360,
            )
            with Image.open(target) as image:
                self.assertEqual(image.size, (640, 360))
                self.assertEqual(image.format, "PNG")
                self.assertGreater(len(image.getcolors(maxcolors=1_000_000) or []), 5)

    def test_app_png_export_uses_gui_viewport_not_measurement_timeline(self):
        points = sps_graph_points(self.items, metric="legacy", measured=False)
        visible_viewport = Viewport()
        visible_viewport.set_total(0.0, 1.5, reset=True)
        captured = {}

        def fake_render(path, series, **kwargs):
            captured["viewport"] = kwargs["viewport"]
            return Path(path)

        fake_app = SimpleNamespace(
            session=SimpleNamespace(
                sps_timeline=SimpleNamespace(syllables=self.items),
                subtitle_path=None,
                project_root=None,
            ),
            sps_timeline=SimpleNamespace(viewport=visible_viewport),
            sps_graph=SimpleNamespace(set_series=lambda *_args, **_kwargs: None),
            sps_graph_smoothing_var=SimpleNamespace(get=lambda: "1"),
            sps_graph_source_var=SimpleNamespace(get=lambda: "ASS timing"),
            palette=get_theme(None),
            _sps_graph_export_settings=None,
            _build_sps_graph_series=lambda: [GraphSeries("ASS", points, "#5d8fe8")],
            _set_status=lambda _message: None,
        )
        with tempfile.TemporaryDirectory() as td, patch(
            "karaoke_gui.app.filedialog.asksaveasfilename",
            return_value=str(Path(td) / "graph.png"),
        ), patch(
            "karaoke_gui.app.ask_sps_graph_export_settings",
            return_value=GraphExportSettings(),
        ), patch("karaoke_gui.app.render_sps_graph_png", side_effect=fake_render):
            KaraokeApp.export_sps_graph_png(fake_app)

        self.assertIs(captured["viewport"], visible_viewport)

    def test_export_axis_settings_are_validated(self):
        settings = GraphExportSettings(
            y_step=0.5, x_step=2.0, time_format="seconds",
            x_axis_label="Seconds", y_axis_label="Syllables / second",
            show_peak=True,
        ).validate()
        self.assertEqual(settings.y_step, 0.5)
        self.assertEqual(settings.x_step, 2.0)
        self.assertEqual(_format_graph_time(12.345, settings.time_format), "12.35")
        self.assertIn("00:12", _format_graph_time(12.345, "clock"))
        with self.assertRaises(ValueError):
            GraphExportSettings(y_step=0).validate()
        with self.assertRaises(ValueError):
            GraphExportSettings(x_step=0).validate()
        with self.assertRaises(ValueError):
            GraphExportSettings(time_format="frames").validate()


if __name__ == "__main__":
    unittest.main()
