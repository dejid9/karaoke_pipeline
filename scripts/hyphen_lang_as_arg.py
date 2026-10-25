from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.ass import AssDocument
from karaoke_core.language import detect_language_profile, profile_for_language
from karaoke_core.syllables import convert_ass_to_syllables


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert grapheme/phone karaoke ASS timing to syllable timing")
    parser.add_argument("language", nargs="?", default="auto", help="en, ru, de, pl, tr, hu, ja or Pyphen locale")
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "work" / "output.ass")
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "work" / "output_syllables.ass")
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--flatten", dest="flatten", action="store_true", help="merge Dialogue events into one title (default)")
    parser.add_argument("--no-flatten", dest="flatten", action="store_false", help="keep separate Dialogue events")
    parser.set_defaults(flatten=True)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"ASS file not found: {args.input}")
    if args.transcript is not None and not args.transcript.is_file():
        parser.error(f"transcript not found: {args.transcript}")

    if args.language.casefold() == "auto":
        if args.transcript is not None:
            sample = args.transcript.read_text(encoding="utf-8-sig")
        else:
            sample = " ".join(s.visible_text for s in AssDocument.load(args.input).karaoke_syllables())
        profile = detect_language_profile(sample)
    else:
        profile = profile_for_language(args.language)
    report = convert_ass_to_syllables(
        args.input,
        args.output,
        profile,
        transcript_path=args.transcript,
        flatten=args.flatten,
    )
    print(f"Created: {args.output}")
    print(f"Language={report.language}; units={report.input_units}->{report.output_units}; Dialogue={report.dialogue_lines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
