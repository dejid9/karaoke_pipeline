from __future__ import annotations

import math
import shutil
import struct
import subprocess
import sys
import types
from pathlib import Path

import pytest

import karaoke_core.media as media


class _FakeRawOutputStream:
    latency = 0.02
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.started = False
    def start(self): self.started = True
    def stop(self): self.started = False
    def close(self): self.started = False


class _FakeSD(types.SimpleNamespace):
    def __init__(self):
        super().__init__(RawOutputStream=_FakeRawOutputStream)
    @staticmethod
    def query_hostapis():
        return []


def _pcm(path: Path, frames: int = 4800, sr: int = 48000) -> media.PlaybackPCMCache:
    with path.open("wb") as f:
        for i in range(frames):
            v = int(12000 * math.sin(2 * math.pi * 440 * i / sr))
            f.write(struct.pack("<hh", v, v))
    return media.load_playback_pcm_cache(path)


def test_portaudio_direct_callback_uses_cached_pcm(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "sounddevice", _FakeSD())
    cache = _pcm(tmp_path / "x.pcm")
    engine = media._PortAudioPCMEngine(cursor_delay_seconds=0)
    engine.set_cache(cache)
    engine.play(0.0, 0.05, speed=1.0, preserve_pitch=True, ffmpeg=Path("ffmpeg"))
    out = bytearray(engine.BLOCKSIZE * 4)
    engine._callback(out, engine.BLOCKSIZE, None, None)
    assert any(out)
    assert engine.position() >= 0
    engine.pause()
    out2 = bytearray(engine.BLOCKSIZE * 4)
    engine._callback(out2, engine.BLOCKSIZE, None, None)
    assert not any(out2)
    engine.close()


def test_non_pitch_preserving_speed_is_in_process(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "sounddevice", _FakeSD())
    cache = _pcm(tmp_path / "x.pcm", frames=10000)
    engine = media._PortAudioPCMEngine(cursor_delay_seconds=0)
    engine.set_cache(cache)
    engine.play(0.0, 0.10, speed=2.0, preserve_pitch=False, ffmpeg=Path("ffmpeg"))
    assert engine._mode == "direct"
    before = engine.source_frame
    out = bytearray(engine.BLOCKSIZE * 4)
    engine._callback(out, engine.BLOCKSIZE, None, None)
    assert engine.source_frame - before == pytest.approx(engine.BLOCKSIZE * 2.0)
    engine.close()


def test_playback_pcm_cache_roundtrip(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    source = tmp_path / "tone.wav"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=0.25", "-ar", "48000", "-ac", "2", str(source),
    ], check=True)
    cache, path, cached = media.load_or_extract_playback_pcm_cache(
        source, ffmpeg=ffmpeg, cache_root=tmp_path / "cache"
    )
    assert not cached
    assert cache.duration == pytest.approx(0.25, abs=0.01)
    cache2, path2, cached2 = media.load_or_extract_playback_pcm_cache(
        source, ffmpeg=ffmpeg, cache_root=tmp_path / "cache"
    )
    assert cached2 and path2 == path
    assert cache2.total_frames == cache.total_frames

def test_ui_preferences_support_pitch_toggle(tmp_path: Path):
    from karaoke_gui.theme import load_ui_preferences, save_ui_preferences
    path = tmp_path / "prefs.json"
    save_ui_preferences("Тёмно-синяя · ночная", False, path=path, playback_preserve_pitch=False)
    assert load_ui_preferences(path)["playback_preserve_pitch"] is False


def test_media_player_falls_back_when_portaudio_unavailable():
    player = media.MediaPlayer()
    if media._is_windows_audio_platform():
        ready = player.prepare_output()
        assert ready is True
        assert player._sink is not None or player._pa_engine is not None
        assert "waveOut" in player.backend_description or "PortAudio" in player.backend_description
    player.close()
