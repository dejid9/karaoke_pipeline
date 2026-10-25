from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import tkinter as tk
import unittest

from karaoke_gui.audio_export import slice_audio
from karaoke_gui.render_panel import RenderPanel, BURST_COLOR_MODES


class AudioExportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_slice_audio_creates_expected_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_wav = tmp_path / "source.wav"
            # Generate 2.0s sine wave test file
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=2.0",
                str(src_wav),
            ]
            subprocess.run(cmd, check=True)
            self.assertTrue(src_wav.is_file())

            # Slice 0.5s to 1.2s (duration 0.7s) to mp3
            out_mp3 = tmp_path / "clip.mp3"
            slice_audio(src_wav, out_mp3, 0.5, 1.2, ffmpeg="ffmpeg", format_choice="mp3")
            self.assertTrue(out_mp3.is_file())
            self.assertGreater(out_mp3.stat().st_size, 500)

            # Slice to wav
            out_wav = tmp_path / "clip.wav"
            slice_audio(src_wav, out_wav, 0.2, 0.8, ffmpeg="ffmpeg", format_choice="wav")
            self.assertTrue(out_wav.is_file())
            self.assertGreater(out_wav.stat().st_size, 1000)

    def test_render_panel_burst_color_project_state_roundtrip(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError:
            self.skipTest("Tk unavailable")

        try:
            class DummySession:
                document = None
                syllables = []
                sps_timeline = None
                media_path = None
                def resolved_ffmpeg(self):
                    return None

            panel = RenderPanel(
                root,
                session=DummySession(),
                prepare_source=lambda: True,
                set_status=lambda _msg: None,
            )

            # Test variables in _PROJECT_STATE_VARS
            for var_name in ("burst_color_mode_var", "burst_base_color_var", "burst_alt_color_var", "burst_hue_offset_var"):
                self.assertIn(var_name, RenderPanel._PROJECT_STATE_VARS)

            # Set custom burst coloring state
            panel.burst_color_mode_var.set("alternate")
            panel.burst_base_color_var.set("&H0000FF&")
            panel.burst_alt_color_var.set("&H0080FF&")
            panel.burst_hue_offset_var.set("45")
            panel._update_burst_color_summary()

            state = panel.project_state(Path("C:/test_root"))
            self.assertEqual(state["burst_color_mode"], "alternate")
            self.assertEqual(state["burst_base_color"], "&H0000FF&")
            self.assertEqual(state["burst_alt_color"], "&H0080FF&")
            self.assertEqual(state["burst_hue_offset"], "45")

            # Reset and apply
            panel.burst_color_mode_var.set("single")
            panel.burst_base_color_var.set("&HFFFFFF&")
            panel.burst_alt_color_var.set("&H000000&")
            panel.burst_hue_offset_var.set("0")

            panel.apply_project_state(state, Path("C:/test_root"))
            self.assertEqual(panel.burst_color_mode_var.get(), "alternate")
            self.assertEqual(panel.burst_color_mode_display_var.get(), BURST_COLOR_MODES["alternate"])
            self.assertEqual(panel.burst_base_color_var.get(), "&H0000FF&")
            self.assertEqual(panel.burst_alt_color_var.get(), "&H0080FF&")
            self.assertEqual(panel.burst_hue_offset_var.get(), "45")
            self.assertIn("&H0000FF&", panel.burst_color_summary_var.get())
            self.assertIn("&H0080FF&", panel.burst_color_summary_var.get())

        finally:
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
