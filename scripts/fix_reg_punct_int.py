from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.syllables import restore_ass_text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore exact case, punctuation and line breaks from TXT; render line spacing is not applied"
    )
    parser.add_argument("ass", nargs="?", type=Path, default=ROOT / "work" / "output_syllables.ass")
    parser.add_argument("text", nargs="?", type=Path, default=ROOT / "work" / "audio.txt")
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "work" / "output_syllables_fixed.ass")
    parser.add_argument("--minimum-ratio", type=float, default=0.9)
    args = parser.parse_args()
    if not args.ass.is_file():
        parser.error(f"ASS file not found: {args.ass}")
    if not args.text.is_file():
        parser.error(f"text file not found: {args.text}")
    report = restore_ass_text(args.ass, args.text, args.output, minimum_ratio=args.minimum_ratio)
    print(f"Created: {args.output}")
    print(f"Karaoke units={report.karaoke_units}; normalized chars={report.normalized_characters}; match={report.match_ratio:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

