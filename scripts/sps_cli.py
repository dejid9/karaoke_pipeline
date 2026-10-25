from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.ass import AssDocument
from karaoke_core.audacity import legacy_label_windows, load_audacity_labels
from karaoke_core.sps import MeasurementTimeline, detect_bursts, legacy_windows
from karaoke_core.measurements import load_measurements


def _fmt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def main() -> int:
    p = argparse.ArgumentParser(description="ASS-aware SPS analyzer")
    p.add_argument("input", type=Path, help="ASS file, or Audacity labels with --labels")
    p.add_argument("--labels", action="store_true", help="treat input as archived Audacity tab-separated labels")
    p.add_argument("--mode", choices=["legacy", "bursts"], default="legacy", help="legacy = точный пользовательский 1–2 s метод; bursts = внутренний авто-поиск кандидатов")
    p.add_argument("--measurements", type=Path, help="optional measurement sidecar JSON")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--csv", type=Path)
    args = p.parse_args()

    if args.labels:
        if args.mode != "legacy":
            p.error("--labels currently reproduces the legacy Audacity metric; use --mode legacy")
        rows = legacy_label_windows(load_audacity_labels(args.input))
        rows = sorted(rows, key=lambda x: (-x.speed, x.start))[: args.top]
    else:
        doc = AssDocument.load(args.input)
        timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
        measured = False
        if args.measurements:
            load_measurements(args.measurements, timeline)
            measured = True

        if args.mode == "legacy":
            rows = legacy_windows(timeline.syllables, measured=measured)
            rows = sorted(rows, key=lambda x: (-x.speed, x.start))[: args.top]
        else:
            bursts = detect_bursts(timeline.syllables)
            for b in bursts:
                print(f"{_fmt(b.start)} - {_fmt(b.end)}  peak={b.peak_sps:.3f} mean={b.mean_sps:.3f} heat={b.heat:.3f}  {b.text}")
            return 0

    for r in rows:
        print(f"{r.speed:.4f}\t{r.count}//{r.duration:.4f}\t{_fmt(r.start)}-{_fmt(r.end)}\t{r.text}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["start", "end", "duration", "count", "sps", "mode", "text"])
            for r in rows:
                writer.writerow([f"{r.start:.6f}", f"{r.end:.6f}", f"{r.duration:.6f}", r.count, f"{r.speed:.6f}", r.mode, r.text])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
