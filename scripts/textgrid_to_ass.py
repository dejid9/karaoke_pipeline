from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow running the script from the project tree without installing a package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.alignment import AlignmentConversionSettings, convert_textgrid_to_ass
from karaoke_core.ass import KaraokeTagType


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an MFA/Praat TextGrid to timing-exact karaoke ASS")
    parser.add_argument("textgrid", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--word-tier", default="words")
    parser.add_argument("--phone-tier", default="phones")
    parser.add_argument("--tag", choices=("k", "kf", "ko", "K"), default="kf")
    parser.add_argument("--max-words", type=int, default=8)
    parser.add_argument("--max-gap", type=float, default=0.65)
    parser.add_argument("--max-line", type=float, default=8.0)
    parser.add_argument("--playres", default="1920x1080")
    parser.add_argument("--no-phone-boundaries", action="store_true")
    parser.add_argument("--language", default="auto", help="auto, en, ru, de, pl, tr, hu or ja")
    parser.add_argument("--syllables", dest="syllables", action="store_true", help="aggregate timing into language syllables (default)")
    parser.add_argument("--no-syllables", dest="syllables", action="store_false", help="keep TextGrid timing units")
    parser.add_argument("--flatten", dest="flatten", action="store_true", help="create one title for the complete TextGrid (default)")
    parser.add_argument("--no-flatten", dest="flatten", action="store_false", help="keep separate Dialogue events")
    parser.add_argument("--restore-text", dest="restore_text", action="store_true", help="restore exact TXT text")
    parser.add_argument("--no-restore-text", dest="restore_text", action="store_false", help="do not restore exact TXT text")
    parser.set_defaults(syllables=True, flatten=True, restore_text=True)
    args = parser.parse_args()
    restore_text = args.restore_text
    if restore_text and args.transcript is None:
        parser.error("--restore-text requires --transcript")
    try:
        rx, ry = (int(v) for v in args.playres.lower().split("x", 1))
    except Exception:
        parser.error("--playres must look like 1920x1080")
    report = convert_textgrid_to_ass(
        args.textgrid,
        args.output,
        transcript_path=args.transcript,
        settings=AlignmentConversionSettings(
            word_tier=args.word_tier,
            phone_tier=args.phone_tier,
            karaoke_tag=KaraokeTagType(args.tag),
            max_words_per_line=args.max_words,
            max_gap_seconds=args.max_gap,
            max_line_seconds=args.max_line,
            play_res_x=rx,
            play_res_y=ry,
            use_phone_boundaries=not args.no_phone_boundaries,
            syllabify=args.syllables,
            language=args.language,
            flatten_dialogues=args.flatten,
            restore_transcript_text=restore_text,
        ),
    )
    print(f"Created: {report.output_path}")
    print(f"Words={report.words}; lines={report.lines}; syllables={report.visible_syllables}; gaps={report.timing_gaps}")
    print(f"Phone tier used: {report.phone_tier_used}; transcript used: {report.transcript_tokens_used}")
    print(f"Language: {report.language}; syllabified: {report.syllabified}; exact text restored: {report.text_restored}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
