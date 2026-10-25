from __future__ import annotations

import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from karaoke_core.ass import AssDocument
from karaoke_core.media import load_or_extract_waveform
from karaoke_core.render import CropRect, RenderLayoutSettings, RenderOutputSettings, render_karaoke_video
from karaoke_gui.task_center import TaskCenter


ASS = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.30,Default,,0,0,0,,{\kf10}one {\kf10}two {\kf10}three
'''


def make_wav(path: Path, duration=0.3, rate=8000):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        frames = bytearray()
        for i in range(int(duration * rate)):
            frames.extend(struct.pack("<h", int(10000 * math.sin(2 * math.pi * 330 * i / rate))))
        f.writeframes(bytes(frames))


class TaskCenterTests(unittest.TestCase):
    def test_task_lifecycle_and_logs(self):
        center = TaskCenter()
        task = center.start("FFmpeg", "Render", stage="Старт", progress=0)
        task.update(42.5, "Кодирование")
        task.log("frame 10")
        snap = center.task(task.id)
        self.assertEqual(snap.stage, "Кодирование")
        self.assertAlmostEqual(snap.progress, 42.5)
        task.done("Готово")
        self.assertEqual(center.task(task.id).status, "done")
        self.assertEqual(center.task(task.id).progress, 100.0)
        self.assertTrue(any(e.message == "frame 10" for e in center.all_logs()))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
    def test_waveform_reports_stages_and_percent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav = root / "tone.wav"
            make_wav(wav)
            seen = []
            logs = []
            load_or_extract_waveform(
                wav, ffmpeg=shutil.which("ffmpeg"), cache_root=root / "cache",
                progress=lambda value, stage: seen.append((value, stage)),
                log=logs.append,
            )
            self.assertTrue(seen)
            self.assertEqual(seen[-1][0], 100.0)
            self.assertTrue(any("Декод" in stage for _, stage in seen))
            self.assertTrue(any(line.startswith("> ") for line in logs))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
    def test_ffmpeg_render_reports_progress(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.mov"
            seen = []
            logs = []
            render_karaoke_video(
                AssDocument.from_text(ASS), RenderLayoutSettings(), target,
                crop=CropRect(0, 0, 320, 180),
                ffmpeg=shutil.which("ffmpeg"), output_settings=RenderOutputSettings(fps=5, profile="transparent_mov"),
                progress=lambda value, stage: seen.append((value, stage)), log=logs.append,
            )
            self.assertTrue(target.exists())
            self.assertTrue(any(value is not None and value > 1 for value, _ in seen))
            self.assertEqual(seen[-1][0], 100.0)
            self.assertTrue(any("-progress" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
