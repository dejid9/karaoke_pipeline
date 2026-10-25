import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from karaoke_core.media import load_or_extract_waveform, load_waveform
from karaoke_core.measurements import MeasurementRecord, replace_measurements
from karaoke_gui.session import KaraokeSession


DENSE_ASS = """[Script Info]\nTitle: measure-test\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\kf10}a{\\kf10}b{\\kf10}c{\\kf10}d{\\kf10}e{\\kf10}f{\\kf10}g{\\kf10}h{\\kf10}i{\\kf10}j\n"""


def make_wav(path: Path, duration=0.35, rate=8000):
    count = int(duration * rate)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        frames = bytearray()
        for i in range(count):
            value = int(12000 * math.sin(2 * math.pi * 440 * i / rate))
            frames.extend(struct.pack("<h", value))
        f.writeframes(bytes(frames))


class MeasurementPersistenceTests(unittest.TestCase):
    def test_measurement_changes_have_separate_undo_redo_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            ass = Path(tmp) / "song.ass"
            ass.write_text(DENSE_ASS, encoding="utf-8")
            session = KaraokeSession()
            session.open_subtitles(ass)
            result = session.transfer_to_sps()
            first = result.timeline.syllables[0]

            session.set_measurement(first.id, first.start + 0.01, first.end - 0.01)
            self.assertEqual(session.undo_measurement(), first.id)
            restored = next(s for s in session.sps_timeline.syllables if s.id == first.id)
            self.assertFalse(restored.measurement_changed)

            self.assertEqual(session.redo_measurement(), first.id)
            repeated = next(s for s in session.sps_timeline.syllables if s.id == first.id)
            self.assertTrue(repeated.measurement_changed)

    def test_loading_snapshot_replaces_measurements_missing_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ass = Path(tmp) / "song.ass"
            ass.write_text(DENSE_ASS, encoding="utf-8")
            session = KaraokeSession()
            session.open_subtitles(ass)
            result = session.transfer_to_sps(min_peak_sps=2)
            first, second = result.timeline.syllables[:2]
            result.timeline.set_measurement(first.id, first.end, first.start)
            records = {
                second.id: MeasurementRecord(second.id, second.start + 0.01, second.end - 0.01),
            }

            replace_measurements(records, result.timeline)
            lookup = {item.id: item for item in result.timeline.syllables}
            self.assertFalse(lookup[first.id].measurement_changed)
            self.assertTrue(lookup[second.id].measurement_changed)

    def test_reversed_measurement_roundtrips_through_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            ass = root / "subtitles" / "song.ass"
            ass.parent.mkdir()
            ass.write_text(DENSE_ASS, encoding="utf-8")
            session = KaraokeSession()
            session.new_project(root)
            session.open_subtitles(ass)
            result = session.transfer_to_sps(min_peak_sps=2)
            item = result.timeline.syllables[0]
            session.set_measurement(item.id, item.end, item.start)

            restored = session.transfer_to_sps(min_peak_sps=2)
            restored_item = next(s for s in restored.timeline.syllables if s.id == item.id)
            self.assertAlmostEqual(restored_item.effective_start, item.end)
            self.assertAlmostEqual(restored_item.effective_end, item.start)
            self.assertGreater(restored_item.effective_start, restored_item.effective_end)

    def test_partial_transfers_merge_and_reset_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            ass = root / "subtitles" / "song.ass"
            ass.parent.mkdir()
            ass.write_text(DENSE_ASS, encoding="utf-8")
            before = ass.read_bytes()

            session = KaraokeSession()
            session.new_project(root)
            session.open_subtitles(ass)
            all_result = session.transfer_to_sps(min_peak_sps=2)
            first = all_result.timeline.syllables[0]
            second = all_result.timeline.syllables[1]
            session.set_measurement(first.id, first.start + 0.01, first.end - 0.01)

            # A later partial transfer must not erase the first syllable's record.
            session.transfer_to_sps(syllable_ids=[second.id], min_peak_sps=2)
            current = session.sps_timeline.syllables[0]
            session.set_measurement(current.id, current.start + 0.02, current.end - 0.01)

            restored = session.transfer_to_sps(min_peak_sps=2)
            lookup = {s.id: s for s in restored.timeline.syllables}
            self.assertTrue(lookup[first.id].measurement_changed)
            self.assertTrue(lookup[second.id].measurement_changed)
            self.assertAlmostEqual(lookup[first.id].effective_start, first.start + 0.01)
            self.assertAlmostEqual(lookup[second.id].effective_start, second.start + 0.02)

            session.clear_measurement(first.id)
            restored2 = session.transfer_to_sps(min_peak_sps=2)
            lookup2 = {s.id: s for s in restored2.timeline.syllables}
            self.assertFalse(lookup2[first.id].measurement_changed)
            self.assertTrue(lookup2[second.id].measurement_changed)
            self.assertEqual(ass.read_bytes(), before)


class WaveformTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
    def test_waveform_extract_and_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            media = tmp / "tone.wav"
            make_wav(media)
            before = media.read_bytes()
            waveform, cache, cached = load_or_extract_waveform(media, ffmpeg=shutil.which("ffmpeg"), cache_root=tmp / "cache")
            self.assertFalse(cached)
            self.assertTrue(cache.exists())
            self.assertGreater(len(waveform.peaks), 20)
            self.assertAlmostEqual(waveform.duration, 0.35, places=2)
            self.assertTrue(any(lo < 0 < hi for lo, hi in waveform.peaks))
            self.assertEqual(media.read_bytes(), before)

            second, cache2, cached2 = load_or_extract_waveform(media, ffmpeg=shutil.which("ffmpeg"), cache_root=tmp / "cache")
            self.assertTrue(cached2)
            self.assertEqual(cache2, cache)
            self.assertEqual(second.peaks, waveform.peaks)
            self.assertEqual(load_waveform(cache).peaks, waveform.peaks)

    def test_waveform_columns_are_pixel_bounded(self):
        from karaoke_core.media import WaveformData
        data = WaveformData(100, 1, tuple((-i, i) for i in range(100)), 100)
        columns = data.columns(0.2, 0.8, 17)
        self.assertEqual(len(columns), 17)
        self.assertTrue(all(lo <= hi for lo, hi in columns))


if __name__ == "__main__":
    unittest.main()
