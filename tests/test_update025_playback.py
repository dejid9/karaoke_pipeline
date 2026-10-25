from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import wave

import karaoke_core.media as media
from karaoke_gui.theme import load_ui_preferences, save_ui_preferences


def test_playback_padding_defaults_and_clamping() -> None:
    player = media.MediaPlayer()
    assert player.lead_silence_seconds == 0.700
    assert player.tail_silence_seconds == 0.250
    player.set_padding(lead_seconds=9, tail_seconds=-1)
    assert player.lead_silence_seconds == 2.0
    assert player.tail_silence_seconds == 0.0


def test_playback_padding_is_persisted(tmp_path: Path) -> None:
    prefs = tmp_path / "ui.json"
    save_ui_preferences(
        "Тёмно-синяя · ночная",
        False,
        prefs,
        playback_warmup_ms=950,
        playback_tail_ms=300,
    )
    loaded = load_ui_preferences(prefs)
    assert loaded["playback_warmup_ms"] == 950
    assert loaded["playback_tail_ms"] == 300


def test_windows_native_wav_uses_instance_padding(monkeypatch, tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"x")
    ffplay = tmp_path / "ffplay.exe"
    ffplay.write_bytes(b"x")
    source = tmp_path / "song.mp3"
    source.write_bytes(b"x")
    calls = []

    def fake_run(cmd, **kwargs):
        with wave.open(str(Path(cmd[-1])), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(48000)
            out.writeframes((b"\x01\x00\x01\x00") * 3840)  # 80 ms
        return SimpleNamespace(returncode=0, stderr="")

    fake_winsound = SimpleNamespace(
        SND_FILENAME=1,
        SND_ASYNC=2,
        SND_NODEFAULT=4,
        PlaySound=lambda filename, flags: calls.append((filename, flags)),
    )
    monkeypatch.setattr(media.subprocess, "run", fake_run)
    monkeypatch.setattr(media.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)

    player = media.MediaPlayer(lead_silence_seconds=0.9, tail_silence_seconds=0.3)
    player.play(source, 0.4, 0.48, ffplay=ffplay, ffmpeg=ffmpeg)
    wav_path = Path(calls[0][0])
    with wave.open(str(wav_path), "rb") as src:
        duration = src.getnframes() / src.getframerate()
    assert abs(duration - 1.28) < 1 / 48000 + 1e-6
    player.stop()
