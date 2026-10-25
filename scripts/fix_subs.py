from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.syllables import flatten_ass_dialogues


def main() -> int:
    parser = argparse.ArgumentParser(description="Flatten karaoke Dialogue events without losing inter-event pauses")
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "work" / "output.ass")
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "work" / "output_flat.ass")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"ASS file not found: {args.input}")
    count = flatten_ass_dialogues(args.input, args.output)
    print(f"Created: {args.output}")
    print(f"Merged Dialogue events: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

