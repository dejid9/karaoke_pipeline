from __future__ import annotations

import io
import time
from pathlib import Path
from types import SimpleNamespace

import karaoke_core.media as media
from karaoke_gui.theme import load_ui_preferences, save_ui_preferences


def test_atempo_chain_preserves_pitch_across_range() -> None:
    assert media._atempo_chain(1.0) == ""
    assert media._atempo_chain(0.5) == "atempo=0.500000"
    assert media._atempo_chain(0.25) == "atempo=0.500000,atempo=0.500000"
    assert media._atempo_chain(2.0) == "atempo=2.000000"
    assert media._atempo_chain(4.0) == "atempo=2.000000,atempo=2.000000"


def test_stream_command_selection_duration_tracks_speed(tmp_path: Path) -> None:
    player = media.MediaPlayer(cursor_delay_seconds=0.08)
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"x")
    song = tmp_path / "song.mp3"
    song.write_bytes(b"x")
    cmd = player._ffmpeg_stream_cmd(song, 10.0, 11.0, ffmpeg, 2.0)
    joined = " ".join(cmd)
    assert "atempo=2.000000" in joined
    assert "-t" in cmd
    assert abs(float(cmd[cmd.index("-t") + 1]) - 0.5) < 1e-6
    assert cmd[-2:] == ["s16le", "pipe:1"]


def test_playback_preferences_speed_and_cursor_delay_roundtrip(tmp_path: Path) -> None:
    prefs = tmp_path / "ui.json"
    save_ui_preferences(
        "Тёмно-синяя · ночная", False, prefs,
        playback_speed=0.75,
        playback_cursor_delay_ms=140,
    )
    loaded = load_ui_preferences(prefs)
    assert loaded["playback_speed"] == 0.75
    assert loaded["playback_cursor_delay_ms"] == 140


def test_persistent_stream_path_avoids_legacy_wav(monkeypatch, tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"; ffmpeg.write_bytes(b"x")
    source = tmp_path / "song.mp3"; source.write_bytes(b"x")
    captured = {}

    class Sink:
        chunk_bytes = 16
        def reset(self): pass
        def write(self, data, stop_event=None): captured.setdefault("chunks", []).append(bytes(data)); return True
        def drain(self, stop_event=None): captured["drained"] = True
        def pause(self): captured["paused"] = True
        def resume(self): captured["resumed"] = True
        def close(self): pass

    class Proc:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            self.stdout = io.BytesIO(b"\x01\x00" * 64)
            self._returncode = None
        def poll(self): return self._returncode
        def terminate(self): self._returncode = 0
        def wait(self, timeout=None): self._returncode = 0; return 0
        def kill(self): self._returncode = -9

    player = media.MediaPlayer(cursor_delay_seconds=0.0)
    sink = Sink()
    monkeypatch.setattr(player, "prepare_output", lambda: True)
    player._sink = sink
    monkeypatch.setattr(media.subprocess, "Popen", Proc)
    player.play(source, 1.0, 1.2, ffmpeg=ffmpeg, ffplay=None, speed=1.25)
    deadline = time.time() + 1.0
    while player.playing and time.time() < deadline:
        time.sleep(0.01)
    assert captured.get("chunks")
    assert "atempo=1.250000" in " ".join(captured["cmd"])
    assert player.position() >= 1.19
    player.close()

def test_timeline_playhead_and_seek_callback() -> None:
    import tkinter as tk
    from karaoke_gui.timeline import DualTimeline
    from karaoke_core.sps import TimelineSyllable

    root = tk.Tk(); root.geometry("640x320")
    seen = []
    try:
        timeline = DualTimeline(root, on_seek=lambda t: seen.append(t))
        timeline.pack(fill="both", expand=True)
        timeline.set_data([TimelineSyllable("L0:S0", 0.0, 2.0, "a")], reset_view=True)
        root.update()
        timeline.set_playhead(1.0)
        root.update()
        assert timeline.detail.find_withtag("playhead")
        event = SimpleNamespace(x=max(1, timeline.detail.winfo_width() // 2))
        timeline._detail_press(event)
        assert seen and 0.8 <= seen[-1] <= 1.2
    finally:
        root.destroy()
