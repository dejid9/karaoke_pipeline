from __future__ import annotations

import time
import tkinter as tk

from karaoke_gui.app import KaraokeApp
from karaoke_gui.timeline import DualTimeline, Viewport
from karaoke_gui.sps_graph import SPSGraph


def _pump(root: tk.Misc, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)


def test_app_pollers_do_not_multiply() -> None:
    app = KaraokeApp()
    try:
        _pump(app, 0.45)
        first = tuple(app.tk.call("after", "info"))
        _pump(app, 0.75)
        second = tuple(app.tk.call("after", "info"))
        # There are redraw/debounce callbacks as the app settles, but the
        # number must stay bounded. Update 027 grew a new perpetual playback
        # poller every 120 ms and would rapidly exceed this threshold.
        assert len(first) < 20
        assert len(second) < 20
        assert app._task_poll_job is not None
        assert app._playback_poll_job is not None
    finally:
        app.destroy()


def test_hidden_timeline_defers_redraw_until_mapped() -> None:
    root = tk.Tk()
    root.withdraw()
    viewport = Viewport(0.0, 10.0, 0.0, 5.0)
    timeline = DualTimeline(root)
    timeline.viewport = viewport
    timeline.pack(fill="both", expand=True)
    root.update_idletasks()
    calls = {"overview": 0, "detail": 0}
    orig_overview = timeline._draw_overview
    orig_detail = timeline._draw_detail

    def draw_overview():
        calls["overview"] += 1
        return orig_overview()

    def draw_detail():
        calls["detail"] += 1
        return orig_detail()

    timeline._draw_overview = draw_overview
    timeline._draw_detail = draw_detail
    timeline.redraw()
    assert calls == {"overview": 0, "detail": 0}
    assert timeline._needs_redraw_on_map

    root.deiconify()
    _pump(root, 0.12)
    assert calls["overview"] >= 1
    assert calls["detail"] >= 1
    root.destroy()


def test_hidden_sps_graph_defers_redraw() -> None:
    root = tk.Tk()
    root.withdraw()
    graph = SPSGraph(root, viewport=Viewport(0.0, 10.0, 0.0, 5.0))
    graph.pack(fill="both", expand=True)
    root.update_idletasks()
    graph.redraw()
    assert graph._needs_redraw_on_map
    root.deiconify()
    _pump(root, 0.12)
    assert not graph._needs_redraw_on_map
    root.destroy()
