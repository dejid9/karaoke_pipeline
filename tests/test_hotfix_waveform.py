from __future__ import annotations

from array import array
from io import BytesIO
from pathlib import Path
import sys
import unittest

import karaoke_core.media as media


class WaveformFastPathTests(unittest.TestCase):
    def test_numpy_fast_path_matches_python_fallback(self):
        if media._np is None:
            self.skipTest("NumPy is not installed")
        samples = array("h", [
            -32768, -12000, -1, 0, 1, 12000, 32767, 500,
            -500, 3000, -3000, 25000, -25000, 42, -42, 777,
        ] * 257 + [1234, -2345, 32000])
        if sys.byteorder != "little":
            samples.byteswap()
        raw = samples.tobytes()
        py_peaks, py_total = media._read_pcm_peaks_python(BytesIO(raw), 37)
        np_peaks, np_total = media._read_pcm_peaks_numpy(BytesIO(raw), 37)
        self.assertEqual(np_total, py_total)
        self.assertEqual(np_peaks, py_peaks)

    def test_async_error_callbacks_bind_exception_eagerly(self):
        root = Path(__file__).resolve().parents[1] / "karaoke_gui"
        sources = "\n".join((root / name).read_text(encoding="utf-8") for name in ("app.py", "render_panel.py"))
        unsafe = (
            "lambda: self._waveform_failed(generation, exc)",
            "lambda: self._spectrogram_failed(generation, exc)",
            "lambda: self._transfer_failed(generation, exc)",
            "lambda: self._measure_failed(generation, exc)",
            "lambda: self._render_failed(generation, exc)",
        )
        for pattern in unsafe:
            self.assertNotIn(pattern, sources)
        self.assertIn("lambda exc=exc: self._waveform_failed(generation, exc)", sources)


if __name__ == "__main__":
    unittest.main()
