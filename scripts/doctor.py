from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaoke_core.doctor import run_health_checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка karaoke/SPS проекта, Conda, MFA и FFmpeg")
    parser.add_argument("project", nargs="?", help="Каталог проекта с project.json")
    args = parser.parse_args()
    report = run_health_checks(args.project)
    print(report.format_text())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
