from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import wave

import karaoke_core.media as media
from karaoke_core.media import WaveformData
from karaoke_core.sps import TimelineSyllable, SPSGraphPoint
from karaoke_gui.sps_graph import GraphSeries, SPSGraph
from karaoke_gui.theme import THEMES
from karaoke_gui.timeline import DualTimeline, Viewport


def test_ffplay_short_clip_is_prerendered_to_pcm_wav(monkeypatch, tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"x")
    ffplay = tmp_path / "ffplay.exe"
    ffplay.write_bytes(b"x")
    source = tmp_path / "song.mp3"
    source.write_bytes(b"x")
    captured = {}

    class DummyProc:
        def poll(self):
            return 0

    def fake_run(cmd, **kwargs):
        captured["extract_cmd"] = cmd
        captured["run_kwargs"] = kwargs
        with wave.open(str(Path(cmd[-1])), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(48000)
            out.writeframes(b"\0\0\0\0" * 3840)
        return SimpleNamespace(returncode=0, stderr="")

    def fake_popen(cmd, **kwargs):
        captured["play_cmd"] = cmd
        captured["popen_kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    monkeypatch.setattr(media.subprocess, "Popen", fake_popen)
    player = media.MediaPlayer()
    player.play(source, 12.0, 12.08, ffplay=ffplay, ffmpeg=ffmpeg)

    extract_cmd = captured["extract_cmd"]
    assert extract_cmd[0] == str(ffmpeg.resolve())
    assert "-ss" in extract_cmd and float(extract_cmd[extract_cmd.index("-ss") + 1]) == 12.0
    assert "-t" in extract_cmd and abs(float(extract_cmd[extract_cmd.index("-t") + 1]) - 0.08) < 1e-6
    assert "pcm_s16le" in extract_cmd
    assert "atrim" not in " ".join(extract_cmd)
    assert "adelay" not in " ".join(extract_cmd)

    play_cmd = captured["play_cmd"]
    assert play_cmd[0] == str(ffplay.resolve())
    assert "-ss" not in play_cmd
    assert "-t" not in play_cmd
    assert "-af" not in play_cmd
    assert Path(play_cmd[-1]).suffix.lower() == ".wav"

    player.stop()


def test_playback_clip_extract_error_is_reported(monkeypatch, tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"x")
    ffplay = tmp_path / "ffplay.exe"
    ffplay.write_bytes(b"x")
    source = tmp_path / "song.mp3"
    source.write_bytes(b"x")

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stderr="decoder failed")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    player = media.MediaPlayer()
    import pytest
    with pytest.raises(RuntimeError, match="decoder failed"):
        player.play(source, 1.0, 1.1, ffplay=ffplay, ffmpeg=ffmpeg)


def test_timeline_waveform_fill_has_ordered_envelope_and_no_scrollbar() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.geometry("800x420")
    try:
        timeline = DualTimeline(root)
        timeline.pack(fill="both", expand=True)
        timeline.set_data([TimelineSyllable("L0:S0", 0.0, 1.0, "a")], reset_view=True)
        timeline.set_waveform(
            WaveformData(
                sample_rate=100,
                samples_per_bin=10,
                peaks=tuple((-1000 - i * 10, 1200 + i * 20) for i in range(20)),
                total_samples=200,
            ),
            reset_view=True,
        )
        root.update_idletasks()
        timeline.redraw()
        assert not hasattr(timeline, "scroll")

        polygons = [item for item in timeline.detail.find_all() if timeline.detail.type(item) == "polygon"]
        large = [timeline.detail.coords(item) for item in polygons if len(timeline.detail.coords(item)) > 20]
        assert large, "waveform fill polygon not drawn"
        coords = max(large, key=len)
        points = list(zip(coords[0::2], coords[1::2]))
        half = len(points) // 2
        upper_x = [x for x, _ in points[:half]]
        lower_x = [x for x, _ in points[half:]]
        assert upper_x == sorted(upper_x)
        assert lower_x == sorted(lower_x, reverse=True)

        old_center = (timeline.viewport.view_start + timeline.viewport.view_end) / 2
        timeline.viewport.zoom(0.25, old_center)
        root.update_idletasks()
        timeline._overview_navigate(SimpleNamespace(x=700))
        new_center = (timeline.viewport.view_start + timeline.viewport.view_end) / 2
        assert new_center > old_center
    finally:
        root.destroy()


def test_sps_theme_change_reuses_series_points() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.geometry("600x300")
    try:
        viewport = Viewport(0.0, 10.0, 0.0, 10.0)
        graph = SPSGraph(root, viewport=viewport)
        graph.pack(fill="both", expand=True)
        pts = [SPSGraphPoint(float(i), float(i + 1), 1, float(i), float(i + 1), (f"L0:S{i}",), "x", "strict-contained", False) for i in range(5)]
        graph.set_series([GraphSeries("ASS", pts, "#000000")])
        point_ids_before = tuple(id(p) for p in graph.series[0].points)
        palette = THEMES["Фиолетовая · ночная"]
        graph.apply_theme(palette)
        root.update_idletasks()
        assert tuple(id(p) for p in graph.series[0].points) == point_ids_before
        assert graph.series[0].colour == palette.accent
    finally:
        root.destroy()


def test_windows_native_playback_uses_winsound_and_padded_pcm(monkeypatch, tmp_path: Path) -> None:
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
            # 80 ms of non-silent PCM.
            out.writeframes((b"\x01\x00\x01\x00") * 3840)
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

    player = media.MediaPlayer()
    player.play(source, 0.4, 0.48, ffplay=ffplay, ffmpeg=ffmpeg)
    assert calls and calls[0][0] is not None
    wav_path = Path(calls[0][0])
    with wave.open(str(wav_path), "rb") as src:
        duration = src.getnframes() / src.getframerate()
        assert src.getnchannels() == 2
        assert src.getframerate() == 48000
    expected = player.LEAD_SILENCE_SECONDS + 0.08 + player.TAIL_SILENCE_SECONDS
    assert abs(duration - expected) < 1 / 48000 + 1e-6
    player.stop()
    assert calls[-1][0] is None
