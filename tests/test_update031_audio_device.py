from __future__ import annotations

import math
import struct
import sys
import types
from pathlib import Path

import karaoke_core.media as media
from karaoke_gui.theme import load_ui_preferences, save_ui_preferences


class FakeStream:
    latency = 0.01
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.device = kwargs.get("device")
        self.started = False
        self.closed = False
        self.__class__.created.append(self)

    def start(self): self.started = True
    def stop(self): self.started = False
    def close(self): self.closed = True; self.started = False


class FakeSD(types.SimpleNamespace):
    def __init__(self):
        self.default_device = 1
        self.terminate_count = 0
        self.initialize_count = 0
        super().__init__(RawOutputStream=self._stream)

    def _stream(self, **kwargs):
        return FakeStream(**kwargs)

    def query_hostapis(self):
        return [{"name": "Windows WASAPI", "default_output_device": self.default_device}]

    def query_devices(self, index):
        return {"name": f"Device {index}", "max_output_channels": 2}

    def _terminate(self): self.terminate_count += 1
    def _initialize(self): self.initialize_count += 1


def make_pcm(path: Path, frames: int = 9600, sr: int = 48000):
    with path.open("wb") as f:
        for i in range(frames):
            value = int(10000 * math.sin(2 * math.pi * 440 * i / sr))
            f.write(struct.pack("<hh", value, value))
    return media.load_playback_pcm_cache(path)


def test_engine_rebinds_when_windows_default_endpoint_changes(monkeypatch, tmp_path: Path):
    fake = FakeSD()
    FakeStream.created.clear()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(media, "_is_windows_audio_platform", lambda: True)
    endpoint = {"id": "endpoint-A"}
    monkeypatch.setattr(media, "_windows_default_audio_endpoint_id", lambda: endpoint["id"])

    engine = media._PortAudioPCMEngine(monitor_default_device=False)
    cache = make_pcm(tmp_path / "audio.pcm")
    engine.set_cache(cache)
    engine.play(0.0, 0.15, speed=1.0, preserve_pitch=False, ffmpeg=Path("ffmpeg"))
    first = engine.stream
    assert first.device == 1
    assert "Device 1" in engine.backend_description

    out = bytearray(engine.BLOCKSIZE * 4)
    engine._callback(out, engine.BLOCKSIZE, None, None)
    before = engine.position()

    fake.default_device = 2
    endpoint["id"] = "endpoint-B"
    assert engine.refresh_default_output_device(force=False) is True
    assert first.closed is True
    assert engine.stream.device == 2
    assert "Device 2" in engine.backend_description
    assert fake.terminate_count == 1
    assert fake.initialize_count == 1
    assert engine.position() >= before
    assert engine.playing
    engine.close()


def test_no_rebind_when_endpoint_is_unchanged(monkeypatch):
    fake = FakeSD()
    FakeStream.created.clear()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(media, "_is_windows_audio_platform", lambda: True)
    monkeypatch.setattr(media, "_windows_default_audio_endpoint_id", lambda: "same")
    engine = media._PortAudioPCMEngine(monitor_default_device=False)
    first = engine.stream
    assert engine.refresh_default_output_device(force=False) is False
    assert engine.stream is first
    assert fake.terminate_count == 0
    engine.close()


def test_follow_default_device_preference_roundtrip(tmp_path: Path):
    path = tmp_path / "prefs.json"
    save_ui_preferences(
        "Тёмно-синяя · ночная", False, path=path,
        playback_follow_default_device=False,
    )
    assert load_ui_preferences(path)["playback_follow_default_device"] is False
