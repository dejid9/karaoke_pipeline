import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from karaoke_core.spectrogram import (
    SpectrogramAnalysisSettings,
    SpectrogramData,
    SpectrogramViewSettings,
    fft_size_for_expected_sps,
    load_or_extract_spectrogram,
    load_spectrogram,
    spectrogram_cache_path,
)


def make_wav(path: Path, duration=0.45, rate=22050):
    count = int(duration * rate)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        frames = bytearray()
        for i in range(count):
            # Two speech-ish bands so the image is not degenerate.
            value = int(9000 * math.sin(2 * math.pi * 220 * i / rate) + 3500 * math.sin(2 * math.pi * 1800 * i / rate))
            value = max(-32768, min(32767, value))
            frames.extend(struct.pack("<h", value))
        f.writeframes(frames)


class SpectrogramTests(unittest.TestCase):
    def test_speed_to_fft_presets(self):
        self.assertEqual(fft_size_for_expected_sps(5), 2048)
        self.assertEqual(fft_size_for_expected_sps(10), 1024)
        self.assertEqual(fft_size_for_expected_sps(16), 512)
        self.assertEqual(fft_size_for_expected_sps(25), 256)


    def test_zoomed_render_interpolates_instead_of_repeating_fft_blocks(self):
        # Two radically different time frames should become a gradient when
        # magnified. Nearest-neighbour rendering produced only two chopped
        # vertical blocks here.
        frame0 = bytes([0] * 5)
        frame1 = bytes([255] * 5)
        data = SpectrogramData(8000, 8, 800, "hann", 2, 5, 0.2, frame0 + frame1)
        view = SpectrogramViewSettings(0, 3000, -120, 0, "linear")
        rgb = data.render_rgb(0.0, 0.1, 17, 1, view)
        pixels = [rgb[i:i + 3] for i in range(0, len(rgb), 3)]
        self.assertGreater(len(set(pixels)), 4)

    def test_wide_view_builds_and_reuses_time_lod(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not available")
        matrix = np.arange(4096 * 17, dtype=np.uint32).astype(np.uint8).reshape(4096, 17)
        data = SpectrogramData(22050, 32, 32, "hann", 4096, 17, 4096 * 32 / 22050, matrix.tobytes())
        view = SpectrogramViewSettings(0, 9000, -120, 0, "linear")
        data.render_rgb(0, data.duration, 64, 32, view)
        self.assertTrue(any(factor > 1 for factor in data._lod_cache))
        keys = set(data._lod_cache)
        data.render_rgb(0, data.duration, 64, 32, view)
        self.assertEqual(set(data._lod_cache), keys)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
    def test_extract_cache_and_render(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "voice.wav"
            make_wav(media)
            before = media.read_bytes()
            settings = SpectrogramAnalysisSettings(sample_rate=22050, fft_size=512, overlap=0.75, window="hann")
            data, cache, cached = load_or_extract_spectrogram(
                media, ffmpeg=shutil.which("ffmpeg"), cache_root=root / "cache", settings=settings
            )
            self.assertFalse(cached)
            self.assertTrue(cache.exists())
            self.assertGreater(data.frame_count, 10)
            self.assertEqual(data.frequency_bins, 257)
            self.assertAlmostEqual(data.duration, 0.45, places=2)
            self.assertEqual(len(data.quantized_db), data.frame_count * data.frequency_bins)
            self.assertGreater(max(data.quantized_db), 200)
            self.assertEqual(media.read_bytes(), before)

            view = SpectrogramViewSettings(80, 5000, -75, -6, "linear")
            rgb = data.render_rgb(0.0, 0.3, 120, 64, view)
            self.assertEqual(len(rgb), 120 * 64 * 3)
            self.assertNotEqual(len(set(rgb)), 1)

            second, cache2, cached2 = load_or_extract_spectrogram(
                media, ffmpeg=shutil.which("ffmpeg"), cache_root=root / "cache", settings=settings
            )
            self.assertTrue(cached2)
            self.assertEqual(cache2, cache)
            self.assertEqual(second.quantized_db, data.quantized_db)
            self.assertEqual(load_spectrogram(cache).quantized_db, data.quantized_db)

            # Analysis settings affect cache identity; display-only settings do not.
            other = SpectrogramAnalysisSettings(sample_rate=22050, fft_size=1024, overlap=0.75, window="hann")
            self.assertNotEqual(spectrogram_cache_path(media, root / "cache", settings), spectrogram_cache_path(media, root / "cache", other))
            self.assertEqual(spectrogram_cache_path(media, root / "cache", settings), cache)


if __name__ == "__main__":
    unittest.main()
