"""Export burst candidates from ASS to Audacity label format.

This replaces the old substring-based colour parser and disconnected expansion
algorithm.  Manual red marks are parsed by karaoke_core; automatic candidates use
connected left/right expansion from strict one-second SPS peaks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.ass import AssDocument
from karaoke_core.sps import MeasurementTimeline, detect_bursts, manual_bursts


def _safe_label(text: str) -> str:
    text = text.replace("\n", " ").replace("\t", " ").strip()
    return text or "_"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ass", nargs="?", type=Path, default=Path("work/output_flat.ass"))
    parser.add_argument("-o", "--output", type=Path, default=Path("output_bursts.txt"))
    parser.add_argument("--auto", action="store_true", help="export automatic burst candidates instead of manual red marks")
    parser.add_argument("--min-sps", type=float, default=6.0)
    args = parser.parse_args()

    doc = AssDocument.load(args.ass)
    timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())

    if args.auto:
        bursts = detect_bursts(timeline.syllables, min_peak_sps=args.min_sps)
    else:
        bursts = manual_bursts(timeline.syllables)

    lines: list[str] = []
    by_id = {s.id: s for s in timeline.syllables}
    for burst_no, burst in enumerate(bursts, 1):
        for sid in burst.syllable_ids:
            s = by_id[sid]
            lines.append(f"{s.start:.3f}\t{s.end:.3f}\t{_safe_label(s.text)}")

    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(bursts)} burst(s), {len(lines)} syllable label(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
