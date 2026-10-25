from __future__ import annotations

import tkinter as tk

from karaoke_core.sps import MeasurementTimeline, TimelineSyllable
from karaoke_gui.app import KaraokeApp, PLAY_SYMBOL
from karaoke_gui.keybindings import DEFAULT_HOTKEYS


def _items(count: int = 18, step: float = 0.1):
    return [TimelineSyllable(f"L0:S{i}", i * step, (i + 1) * step, str(i)) for i in range(count)]


def _button_texts(widget):
    out = []
    for child in widget.winfo_children():
        try:
            if child.winfo_class() == "TButton":
                out.append(str(child.cget("text")))
        except tk.TclError:
            pass
        out.extend(_button_texts(child))
    return out


def test_main_tabs_have_no_numeric_prefixes():
    app = KaraokeApp()
    try:
        labels = [app.notebook.tab(tab, "text") for tab in app.notebook.tabs()]
        assert labels == ["Подготовка", "Караоке", "Точный SPS", "Рендер", "Логи"]
    finally:
        app.destroy()


def test_bounded_transport_buttons_exist_in_both_editing_tabs_and_use_u25b6():
    app = KaraokeApp()
    try:
        assert PLAY_SYMBOL == "\u25b6"
        assert ord(PLAY_SYMBOL) == 0x25B6
        expected = {"|←", f"|{PLAY_SYMBOL}", "→|", f"{PLAY_SYMBOL}|", f"|{PLAY_SYMBOL}|"}
        for tab in (app.karaoke_tab, app.sps_tab):
            texts = set(_button_texts(tab))
            assert expected <= texts
    finally:
        app.destroy()


def test_start_finish_markers_are_one_shared_pair_and_keep_fastest_legacy_summary():
    app = KaraokeApp()
    try:
        items = _items()
        app.session.karaoke_timeline = MeasurementTimeline(items)
        app.karaoke_timeline.set_data(items, reset_view=True)
        app.karaoke_timeline.select_ids((items[2].id,))
        app.set_playback_range_marker("karaoke", "in")
        assert app.playback_range_ids["karaoke"]["in"] == items[2].id
        assert app.karaoke_timeline.playback_limits[0] == items[2].start
        assert app.karaoke_timeline.playback_limits[1] is None

        app.karaoke_timeline.select_ids((items[14].id,))
        app.set_playback_range_marker("karaoke", "out")
        assert app.playback_range_ids["karaoke"]["out"] == items[14].id
        assert app.karaoke_timeline.playback_limits == (items[2].start, items[14].end)
        assert app.karaoke_timeline.playback_range == (items[2].start, items[14].end)
        assert "max" in app.playback_range_vars["karaoke"].get()
    finally:
        app.destroy()


def test_three_bounded_play_commands_use_start_current_and_finish_independently(monkeypatch):
    app = KaraokeApp()
    try:
        items = _items()
        app.session.karaoke_timeline = MeasurementTimeline(items)
        app.karaoke_timeline.set_data(items, reset_view=True)
        app.playback_range_ids["karaoke"] = {"in": items[2].id, "out": items[14].id}
        app._update_playback_range_label("karaoke")
        calls = []
        monkeypatch.setattr(app, "_start_transport", lambda start, end, label: calls.append((start, end, label)) or True)

        app.play_from_start_marker("karaoke")
        assert calls[-1][:2] == (items[2].start, None)

        app.playhead_time = 0.73
        app.play_to_end_marker("karaoke")
        assert calls[-1][:2] == (0.73, items[14].end)

        app.play_marked_range("karaoke")
        assert calls[-1][:2] == (items[2].start, items[14].end)
    finally:
        app.destroy()


def test_ordinary_space_ignores_markers_and_second_space_stops_and_restores(monkeypatch):
    app = KaraokeApp()
    try:
        items = _items()
        app.session.karaoke_timeline = MeasurementTimeline(items)
        app.karaoke_timeline.set_data(items, reset_view=True)
        app.playback_range_ids["karaoke"] = {"in": items[2].id, "out": items[14].id}
        app.playhead_time = 0.47

        calls = []
        monkeypatch.setattr(app, "_start_transport", lambda start, end, label: calls.append((start, end, label)) or True)
        app.toggle_continuous_playback("karaoke")
        assert calls[-1][:2] == (0.47, None)

        class FakePlayer:
            playing = True
            paused = False
            def position(self): return 1.25
            def stop(self): self.playing = False
            def close(self): pass

        app.player = FakePlayer()
        app._playback_origin = 0.47
        app._playback_was_active = True
        app.playback_return_to_start_var.set(True)
        app.toggle_continuous_playback("karaoke")  # Space while active = Stop, not Pause.
        assert abs(app.playhead_time - 0.47) < 1e-12
        assert app._playback_origin is None
        assert app._playback_was_active is False
    finally:
        app.destroy()


def test_special_bounded_play_hotkeys_are_configurable():
    assert DEFAULT_HOTKEYS["play_range"] == "Shift+Space"
    assert DEFAULT_HOTKEYS["play_from_start"] == "Ctrl+I"
    assert DEFAULT_HOTKEYS["play_to_stop"] == "Ctrl+O"
