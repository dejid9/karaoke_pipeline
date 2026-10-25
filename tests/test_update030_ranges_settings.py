from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path

from karaoke_core.sps import MeasurementTimeline, TimelineSyllable, fastest_legacy_window
from karaoke_gui.app import KaraokeApp
from karaoke_gui.keybindings import (
    DEFAULT_HOTKEYS,
    merged_hotkeys,
    normalize_shortcut,
    shortcut_to_tk,
    validate_hotkeys,
)
from karaoke_gui.theme import load_ui_preferences, save_ui_preferences
from karaoke_gui.timeline import DualTimeline


def _items(count: int = 16, step: float = 0.1):
    return [
        TimelineSyllable(f"L0:S{i}", i * step, (i + 1) * step, str(i))
        for i in range(count)
    ]


def test_fastest_user_window_is_legacy_1_to_2_seconds():
    items = _items()
    peak = fastest_legacy_window(items)
    assert peak is not None
    assert 1.0 <= peak.duration <= 2.0
    assert peak.mode == "legacy"
    assert peak.speed >= 9.9


def test_fastest_measured_window_uses_independent_trim_boundaries():
    items = _items()
    items[0] = items[0].with_measurement(0.04, 0.08)
    items[10] = items[10].with_measurement(1.00, 1.06)
    peak = fastest_legacy_window(items, measured=True)
    assert peak is not None
    assert peak.mode == "legacy-measured"
    assert 1.0 <= peak.duration <= 2.0


def test_hotkeys_normalize_convert_and_reject_duplicates():
    assert normalize_shortcut("control + shift + space") == "Ctrl+Shift+Space"
    assert shortcut_to_tk("Alt+Left") == "<Alt-Left>"
    assert shortcut_to_tk("Ctrl+Shift+K") == "<Control-Shift-K>"
    assert not any("Alt" in value for value in DEFAULT_HOTKEYS.values())
    values = dict(DEFAULT_HOTKEYS)
    values["play_selection"] = "F8"
    values["play_range"] = "F8"
    try:
        validate_hotkeys(values)
    except ValueError as exc:
        assert "Одинаковое сочетание" in str(exc)
    else:
        raise AssertionError("duplicate shortcut should be rejected")


def test_legacy_alt_defaults_are_migrated_but_custom_alt_is_kept():
    old = dict(DEFAULT_HOTKEYS)
    old.update({
        "previous_syllable": "Alt+Left",
        "next_syllable": "Alt+Right",
        "insert_syllable": "Ctrl+Alt+I",
        "split_syllable": "Ctrl+Alt+S",
        "merge_syllables": "Ctrl+Alt+M",
        "reset_measurement": "Ctrl+Alt+R",
    })
    migrated = merged_hotkeys(old)
    for action in old.keys() & {
        "previous_syllable", "next_syllable", "insert_syllable",
        "split_syllable", "merge_syllables", "reset_measurement",
    }:
        assert migrated[action] == DEFAULT_HOTKEYS[action]

    custom = dict(DEFAULT_HOTKEYS)
    custom["previous_syllable"] = "Alt+Up"
    assert merged_hotkeys(custom)["previous_syllable"] == "Alt+Up"


def test_settings_roundtrip_includes_transport_graph_and_hotkeys(tmp_path: Path):
    prefs = tmp_path / "ui.json"
    hotkeys = dict(DEFAULT_HOTKEYS)
    hotkeys["play_range"] = "F9"
    save_ui_preferences(
        "Тёмно-синяя · ночная", True, prefs,
        playback_return_to_start=False,
        sps_graph_source="Точное measurement",
        sps_graph_smoothing=7,
        spectrogram_mode="Both",
        spectrogram_analysis={"sample_rate": 22050, "fft_size": 512, "overlap": 0.75, "window": "hann"},
        spectrogram_view={"min_frequency": 80.0, "max_frequency": 8000.0, "db_floor": -90.0, "db_ceiling": -15.0, "frequency_scale": "log"},
        hotkeys=hotkeys,
    )
    loaded = load_ui_preferences(prefs)
    assert loaded["playback_return_to_start"] is False
    assert loaded["sps_graph_source"] == "Точное measurement"
    assert loaded["sps_graph_smoothing"] == 7
    assert loaded["spectrogram_mode"] == "Both"
    assert loaded["spectrogram_analysis"]["fft_size"] == 512
    assert loaded["spectrogram_view"]["frequency_scale"] == "log"
    assert loaded["hotkeys"]["play_range"] == "F9"


def test_timeline_draws_in_out_range():
    root = tk.Tk(); root.geometry("640x320")
    try:
        timeline = DualTimeline(root)
        timeline.pack(fill="both", expand=True)
        timeline.set_data(_items(), reset_view=True)
        root.update_idletasks()
        timeline.set_playback_range(0.2, 1.1)
        timeline.redraw()
        root.update_idletasks()
        assert timeline.playback_range == (0.2, 1.1)
        assert timeline.overview.find_withtag("playback-range")
        assert timeline.detail.find_withtag("playback-range")
        timeline.set_playback_range(None, None)
        timeline.redraw()
        root.update_idletasks()
        assert timeline.playback_range is None
    finally:
        root.destroy()


def test_app_range_is_contiguous_and_stop_returns_to_origin(monkeypatch):
    app = KaraokeApp()
    try:
        items = _items(14)
        app.session.karaoke_timeline = MeasurementTimeline(items)
        app.karaoke_timeline.set_data(items, reset_view=True)
        app.karaoke_timeline.select_ids((items[2].id, items[12].id))
        app.set_playback_range_from_selection("karaoke")
        chosen = app._range_items("karaoke")
        assert [s.id for s in chosen] == [s.id for s in items[2:13]]
        assert "max" in app.playback_range_vars["karaoke"].get()
        assert app.karaoke_timeline.playback_range == (items[2].start, items[12].end)

        class FakePlayer:
            playing = True
            paused = False
            def position(self): return 1.25
            def stop(self): self.playing = False; self.paused = False
            def close(self): pass

        try:
            app.player.close()
        except Exception:
            pass
        app.player = FakePlayer()
        app._playback_origin = 0.35
        app._playback_was_active = True
        app.playback_return_to_start_var.set(True)
        app.stop_playback()
        assert abs(app.playhead_time - 0.35) < 1e-9
        assert app._playback_origin is None
    finally:
        try:
            app.destroy()
        except tk.TclError:
            pass


def test_gui_exact_graph_metric_is_always_legacy():
    app = KaraokeApp()
    try:
        app.sps_graph_metric_var.set("Strict contained")
        assert app._graph_metric_key() == "legacy"
    finally:
        app.destroy()
