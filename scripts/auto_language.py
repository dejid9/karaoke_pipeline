from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.language import detect_language, detect_language_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect a supported lyrics language and print MFA defaults")
    parser.add_argument("text", nargs="?", type=Path, default=ROOT / "work" / "audio.txt")
    args = parser.parse_args()
    if not args.text.is_file():
        parser.error(f"text file not found: {args.text}")
    profile = detect_language_profile(args.text.read_text(encoding="utf-8-sig"))
    print(profile.name)
    print(f"code={profile.code}")
    print(f"acoustic={profile.acoustic_model}")
    print(f"dictionary={profile.dictionary_model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

