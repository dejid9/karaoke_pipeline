from __future__ import annotations

import tkinter as tk
from pathlib import Path

from karaoke_core.media import normalize_playback_speed
from karaoke_core.sps import MeasurementTimeline, TimelineSyllable
from karaoke_gui.app import KaraokeApp
from karaoke_gui.keybindings import DEFAULT_HOTKEYS
from karaoke_gui.theme import load_ui_preferences, save_ui_preferences
from karaoke_gui.timeline import DualTimeline


def _items(count: int = 18, step: float = 0.1):
    return [
        TimelineSyllable(f"L0:S{i}", i * step, (i + 1) * step, str(i))
        for i in range(count)
    ]


def test_speed_dead_zone_snaps_97_to_103_percent_to_one():
    assert normalize_playback_speed(0.97) == 1.0
    assert normalize_playback_speed(0.999) == 1.0
    assert normalize_playback_speed(1.03) == 1.0
    assert abs(normalize_playback_speed(0.969) - 0.969) < 1e-12
    assert abs(normalize_playback_speed(1.031) - 1.031) < 1e-12


def test_saved_speed_is_normalized(tmp_path: Path):
    prefs = tmp_path / "ui.json"
    save_ui_preferences("Тёмно-синяя · ночная", False, prefs, playback_speed=1.02)
    assert load_ui_preferences(prefs)["playback_speed"] == 1.0


def test_new_playback_limit_hotkeys_are_configurable_defaults():
    # Update 033 merges the former In/Out markers with the transport markers.
    assert DEFAULT_HOTKEYS["set_play_start"] == "I"
    assert DEFAULT_HOTKEYS["play_from_start"] == "Ctrl+I"
    assert DEFAULT_HOTKEYS["set_play_stop"] == "O"
    assert DEFAULT_HOTKEYS["play_to_stop"] == "Ctrl+O"
    assert "clear_play_limits" in DEFAULT_HOTKEYS


def test_timeline_draws_independent_play_start_and_stop():
    root = tk.Tk(); root.geometry("640x320")
    try:
        timeline = DualTimeline(root)
        timeline.pack(fill="both", expand=True)
        timeline.set_data(_items(), reset_view=True)
        root.update_idletasks()
        timeline.set_playback_limits(0.3, None)
        timeline.redraw(); root.update_idletasks()
        assert timeline.playback_limits == (0.3, None)
        assert timeline.overview.find_withtag("playback-limits")
        assert timeline.detail.find_withtag("playback-limits")
        timeline.set_playback_limits(None, 1.2)
        timeline.redraw(); root.update_idletasks()
        assert timeline.playback_limits == (None, 1.2)
        assert timeline.overview.find_withtag("playback-limits")
    finally:
        root.destroy()


def test_start_stop_markers_are_independent_and_normal_play_ignores_selection():
    app = KaraokeApp()
    try:
        items = _items()
        app.session.karaoke_timeline = MeasurementTimeline(items)
        app.karaoke_timeline.set_data(items, reset_view=True)

        # Without a Start marker, ordinary Play begins exactly at the playhead,
        # even if another syllable is selected.
        app.playhead_time = 0.47
        app.karaoke_timeline.select_ids((items[10].id,))
        assert app._continuous_bounds("karaoke") == (0.47, None)

        app.karaoke_timeline.select_ids((items[2].id,))
        app.set_playback_limit_marker("karaoke", "start")
        app.karaoke_timeline.select_ids((items[14].id,))
        app.set_playback_limit_marker("karaoke", "stop")
        # Update 033: ordinary Space ignores markers; the dedicated |▶ / ▶| /
        # |▶| buttons consume them instead.
        start, stop = app._continuous_bounds("karaoke")
        assert abs(start - 0.47) < 1e-12
        assert stop is None
        marker_start, marker_stop = app._marker_bounds("karaoke")
        assert abs(marker_start - items[2].start) < 1e-12
        assert abs(marker_stop - items[14].end) < 1e-12
        assert "max" in app.playback_limit_vars["karaoke"].get()

        app.clear_playback_limit("karaoke", "start")
        start, stop = app._continuous_bounds("karaoke")
        assert abs(start - 0.47) < 1e-12
        assert stop is None
        assert app.playback_limit_ids["karaoke"]["stop"] == items[14].id
    finally:
        app.destroy()


def test_return_to_start_uses_user_transport_origin_on_manual_and_natural_stop():
    app = KaraokeApp()
    try:
        class FakePlayer:
            playing = True
            paused = False
            def position(self): return 1.35
            def stop(self): self.playing = False; self.paused = False
            def close(self): pass

        try:
            app.player.close()
        except Exception:
            pass
        app.player = FakePlayer()
        app.playback_return_to_start_var.set(True)
        app._playback_origin = 0.42
        app._playback_was_active = True
        app.stop_playback()
        assert abs(app.playhead_time - 0.42) < 1e-12
        assert app._playback_origin is None
        assert app._playback_was_active is False

        # Natural completion goes through the same finalizer.
        app._playback_origin = 0.61
        app._playback_was_active = True
        app.player.playing = False
        app._poll_playback_cursor()
        assert abs(app.playhead_time - 0.61) < 1e-12
        assert app._playback_origin is None
    finally:
        if getattr(app, "_playback_poll_job", None):
            try: app.after_cancel(app._playback_poll_job)
            except Exception: pass
        app.destroy()
