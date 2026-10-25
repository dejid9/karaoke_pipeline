"""Interactive SPS graph backed by karaoke_core.

This keeps the old PyQtGraph prototype, but removes its regex ASS parser.
The user-facing metric is intentionally fixed to the archived legacy 1–2 second
method so this helper matches the GUI/CLI exact SPS result.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PyQt5 import QtCore, QtWidgets
import pyqtgraph as pg

from karaoke_core.ass import AssDocument
from karaoke_core.sps import MeasurementTimeline, sps_graph_points

INPUT_ASS = Path("work/output_flat.ass")
GRAPH_MODE = "legacy"  # user-facing SPS is fixed to the archived 1–2 s method
SHOW_CURVE = True


def fmt_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def build_results():
    doc = AssDocument.load(INPUT_ASS)
    timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
    metric = "legacy"
    points = sps_graph_points(timeline.syllables, metric=metric)
    return [
        {
            "x": p.time,
            "start": p.window_start,
            "end": p.window_end,
            "diff": p.duration,
            "count": p.count,
            "speed": p.speed,
            "text": p.text,
        }
        for p in points
    ]


def main() -> int:
    results = build_results()
    if not results:
        print("Нет результатов")
        return 0

    app = QtWidgets.QApplication([])
    pg.setConfigOptions(antialias=True)

    window = QtWidgets.QWidget()
    window.setWindowTitle(f"SPS Timeline — {GRAPH_MODE}")
    window.resize(1700, 900)
    layout = QtWidgets.QVBoxLayout(window)

    checkbox = QtWidgets.QCheckBox("Smooth curve mode")
    layout.addWidget(checkbox)
    smooth_label = QtWidgets.QLabel("Smoothing: 1")
    layout.addWidget(smooth_label)
    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setMinimum(1)
    slider.setMaximum(50)
    slider.setValue(1)
    layout.addWidget(slider)

    plot = pg.PlotWidget()
    layout.addWidget(plot)
    plot.setLabel("left", "SPS")
    plot.setLabel("bottom", "Timeline")
    plot.showGrid(x=True, y=True)

    x = np.array([r["x"] for r in results], dtype=float)
    y = np.array([r["speed"] for r in results], dtype=float)
    scatter = pg.ScatterPlotItem(x=x, y=y, size=8, pen=pg.mkPen(255, 255, 255), brush=pg.mkBrush(255, 255, 255, 180))
    curve = pg.PlotCurveItem(pen=pg.mkPen(0, 255, 255, width=2))
    curve.hide()
    plot.addItem(scatter)
    plot.addItem(curve)

    tooltip = pg.TextItem(anchor=(0, 1))
    tooltip.setZValue(100)
    tooltip.hide()
    plot.addItem(tooltip)
    highlight = pg.ScatterPlotItem(size=18, pen=pg.mkPen(255, 255, 0, width=2), brush=pg.mkBrush(255, 255, 0, 120))
    plot.addItem(highlight)

    def update_mode():
        smooth = slider.value()
        smooth_label.setText(f"Smoothing: {smooth}")
        if checkbox.isChecked() and len(x) >= 2:
            scatter.hide()
            # np.interp requires increasing x; duplicated points are harmless for
            # display after sorting.
            order = np.argsort(x)
            xs0, ys0 = x[order], y[order]
            xs = np.linspace(xs0.min(), xs0.max(), min(4000, max(500, len(xs0) * 4)))
            ys = np.interp(xs, xs0, ys0)
            if smooth > 1:
                kernel = np.ones(smooth) / smooth
                ys = np.convolve(ys, kernel, mode="same")
            curve.setData(xs, ys)
            curve.show()
        else:
            curve.hide()
            scatter.show()

    vb = plot.getViewBox()

    def mouse_moved(pos):
        if not plot.sceneBoundingRect().contains(pos):
            tooltip.hide()
            highlight.clear()
            return
        point = vb.mapSceneToView(pos)
        # Normalize x/y distance to the current view so time scale does not dwarf
        # SPS scale during nearest-point selection.
        xr, yr = vb.viewRange()
        xscale = max(1e-9, xr[1] - xr[0])
        yscale = max(1e-9, yr[1] - yr[0])
        nearest = None
        nearest_dist = float("inf")
        for r in results:
            dx = (r["x"] - point.x()) / xscale
            dy = (r["speed"] - point.y()) / yscale
            dist = math.hypot(dx, dy)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = r
        if nearest is None or nearest_dist > 0.04:
            tooltip.hide()
            highlight.clear()
            return
        r = nearest
        tooltip.setHtml(
            f'<div style="background-color:black;color:white;padding:8px;">'
            f'<b>{fmt_time(r["start"])}</b><br>'
            f'SPS: {r["speed"]:.3f}<br>{r["count"]} syllables<br>'
            f'{r["diff"]:.3f} sec<br><br>{r["text"]}</div>'
        )
        tooltip.setPos(r["x"], r["speed"])
        tooltip.show()
        highlight.setData([r["x"]], [r["speed"]])

    checkbox.stateChanged.connect(update_mode)
    slider.valueChanged.connect(update_mode)
    plot.scene().sigMouseMoved.connect(mouse_moved)
    update_mode()
    plot.setLimits(xMin=float(x.min()), xMax=float(x.max()), yMin=0)

    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
