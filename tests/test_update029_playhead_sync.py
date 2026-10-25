from __future__ import annotations

import importlib.util
import json
import math
import struct
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


media = _load("_update029_media", ROOT / "karaoke_core" / "media.py")
theme = _load("_update029_theme", ROOT / "karaoke_gui" / "theme.py")


class FakeRawOutputStream:
    latency = 0.120  # Deliberately large to catch the old subtraction bug.

    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.started = False

    def start(self): self.started = True
    def stop(self): self.started = False
    def close(self): self.started = False


class FakeSD(types.SimpleNamespace):
    def __init__(self):
        super().__init__(RawOutputStream=FakeRawOutputStream)

    @staticmethod
    def query_hostapis():
        return []


def make_pcm(path: Path, frames: int = 4800, sr: int = 48000):
    with path.open("wb") as f:
        for i in range(frames):
            v = int(8000 * math.sin(2 * math.pi * 440 * i / sr))
            f.write(struct.pack("<hh", v, v))
    return media.load_playback_pcm_cache(path)


def test_playhead_no_longer_waits_for_reported_output_latency(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "sounddevice", FakeSD())
    engine = media._PortAudioPCMEngine(cursor_offset_seconds=0)
    engine.set_cache(make_pcm(tmp_path / "a.pcm"))
    engine.play(0.0, 0.08, speed=1.0, preserve_pitch=True, ffmpeg=Path("ffmpeg"))
    out = bytearray(engine.BLOCKSIZE * engine.CHANNELS * engine.SAMPLE_WIDTH)
    engine._callback(out, engine.BLOCKSIZE, None, None)
    # One 10 ms PortAudio block was submitted. The old implementation would
    # clamp back to 0 for ~120 ms (+ the old 80 ms UI delay).
    assert engine.position() == pytest.approx(0.010, abs=0.001)
    engine.close()


def test_signed_playhead_offset_is_only_fine_tuning(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "sounddevice", FakeSD())
    engine = media._PortAudioPCMEngine(cursor_offset_seconds=0.005)
    engine.set_cache(make_pcm(tmp_path / "a.pcm"))
    engine.play(0.0, 0.08, speed=1.0, preserve_pitch=True, ffmpeg=Path("ffmpeg"))
    out = bytearray(engine.BLOCKSIZE * engine.CHANNELS * engine.SAMPLE_WIDTH)
    engine._callback(out, engine.BLOCKSIZE, None, None)
    assert engine.position() == pytest.approx(0.015, abs=0.001)
    engine.set_cursor_offset(-0.005)
    assert engine.position() == pytest.approx(0.005, abs=0.001)
    engine.close()


def test_legacy_80ms_preference_migrates_to_zero(tmp_path: Path):
    prefs = tmp_path / "prefs.json"
    prefs.write_text(json.dumps({"playback_cursor_delay_ms": 80}), encoding="utf-8")
    loaded = theme.load_ui_preferences(prefs)
    assert loaded["playback_cursor_offset_ms"] == 0


def test_new_signed_offset_persists(tmp_path: Path):
    prefs = tmp_path / "prefs.json"
    theme.save_ui_preferences(
        "Тёмно-синяя · ночная", False, path=prefs, playback_cursor_offset_ms=-25
    )
    loaded = theme.load_ui_preferences(prefs)
    assert loaded["playback_cursor_offset_ms"] == -25
