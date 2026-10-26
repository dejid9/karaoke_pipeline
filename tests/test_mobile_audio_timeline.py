import array
import io
from pathlib import Path
import struct
import sys
import unittest
import wave

sys.path.insert(0, str(Path(__file__).parent.parent / "karaoke_mobile" / "src"))

from core.media import WaveformData
from core.spectrogram import SpectrogramData, SpectrogramViewSettings
from ui.components.audio_timeline import (
    AudioTimelineWidget,
    load_waveform_from_wav_bytes,
    rgb_to_bmp,
)


class TestMobileAudioTimeline(unittest.TestCase):
    def test_rgb_to_bmp_header_and_size(self):
        width, height = 10, 5
        dummy_rgb = bytes([128, 200, 255] * (width * height))
        bmp = rgb_to_bmp(dummy_rgb, width, height)

        self.assertTrue(bmp.startswith(b"BM"))
        self.assertEqual(len(bmp), 54 + (width * 3 + (4 - (width * 3 % 4)) % 4) * height)

        # Verify BITMAPINFOHEADER unpack
        magic, file_size, res1, res2, offset = struct.unpack_from("<2sIHHI", bmp, 0)
        self.assertEqual(magic, b"BM")
        self.assertEqual(file_size, len(bmp))
        self.assertEqual(offset, 54)

    def test_load_waveform_from_wav_bytes(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            # 0.5s audio (11025 samples)
            samples = array.array("h", [int(5000 * ((i % 50) / 25.0 - 1.0)) for i in range(11025)])
            wf.writeframes(samples.tobytes())

        wav_bytes = buf.getvalue()
        wfm = load_waveform_from_wav_bytes(wav_bytes, bins_per_second=100)

        self.assertIsInstance(wfm, WaveformData)
        self.assertAlmostEqual(wfm.duration, 0.5, places=2)
        self.assertEqual(len(wfm.peaks), 51)

        # Test downsampled columns
        cols = wfm.columns(0.0, 0.5, 360)
        self.assertEqual(len(cols), 360)

    def test_audio_timeline_widget_rendering(self):
        widget = AudioTimelineWidget()
        self.assertEqual(widget.audio_mode, "waveform")

        # Set synthetic waveform
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(array.array("h", [1500] * 8000).tobytes())

        wfm = load_waveform_from_wav_bytes(buf.getvalue(), bins_per_second=100)
        widget.set_audio("test_song.wav", buf.getvalue(), waveform=wfm)

        self.assertTrue(widget.timeline_image.visible)
        self.assertTrue(widget.timeline_image.src.startswith("data:image/bmp;base64,"))
        self.assertTrue(len(widget.timeline_image.src) > 100)

        # Focus syllable and check bounds
        widget.focus_syllable(start=0.2, end=0.6, meas_start=0.18, meas_end=0.62)
        self.assertEqual(widget.active_start, 0.2)
        self.assertEqual(widget.active_end, 0.6)
        self.assertEqual(widget.measured_start, 0.18)
        self.assertEqual(widget.measured_end, 0.62)

        # Mode switching
        widget.set_audio_mode("spectrogram")
        self.assertEqual(widget.audio_mode, "spectrogram")

        widget.set_audio_mode("both")
        self.assertEqual(widget.audio_mode, "both")

    def test_pure_python_spectrogram_render(self):
        spg = SpectrogramData(
            sample_rate=22050,
            fft_size=512,
            hop_size=128,
            window="hann",
            frame_count=20,
            frequency_bins=257,
            duration=1.0,
            quantized_db=bytes([i % 256 for i in range(20 * 257)]),
        )
        view = SpectrogramViewSettings()
        rgb = spg._render_rgb_python(0.0, 1.0, 100, 40, view)
        self.assertEqual(len(rgb), 100 * 40 * 3)


if __name__ == "__main__":
    unittest.main()
