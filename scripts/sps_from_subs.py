"""Compatibility entry point for the old SPS script, now using karaoke_core."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.ass import AssDocument
from karaoke_core.sps import MeasurementTimeline, legacy_windows

INPUT_ASS = Path("work/output_syllables.ass")


def main() -> int:
    doc = AssDocument.load(INPUT_ASS)
    timeline = MeasurementTimeline.from_karaoke(doc.karaoke_syllables())
    groups = legacy_windows(timeline.syllables)
    if not groups:
        print("Подходящих групп не найдено")
        return 0
    best = max(groups, key=lambda g: g.speed)
    if abs(best.duration - 1.0) <= 0.01:
        print(f"{best.speed:.4f} (округлённо {best.count})\t\t{best.count}//{best.duration:.4f}\t\t{best.text}")
    else:
        print(f"{best.speed:.4f}\t\t{best.count}//{best.duration:.4f}\t\t{best.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
