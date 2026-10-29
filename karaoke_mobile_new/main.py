"""
Karaoke Mobile New — Unified Mobile Workbench
Built completely from scratch with zero legacy dependencies.
"""
from __future__ import annotations

import sys
from pathlib import Path
import flet as ft

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Core imports (pure Python, ready to use)
from core.ass import AssDocument, KaraokeSyllable, format_ass_time
from core.editor import (
    split_syllable, split_syllable_at_time, merge_syllables,
    insert_after, delete_syllable, set_tag_type, colour_burst,
    uncolour_burst, set_syllable_text, set_syllable_romanization,
)
from core.media import WaveformData, load_waveform
from core.spectrogram import SpectrogramData, load_spectrogram
from core.sps import MeasurementTimeline


def main(page: ft.Page):
    page.title = "Karaoke Mobile New"
    page.bgcolor = "#000000"
    page.padding = 0

    # Agent: Implement the unified mobile workbench here from scratch!
    page.add(
        ft.SafeArea(
            ft.Container(
                ft.Text("Karaoke Mobile New — готово к созданию интерфейса с нуля!", color="#ffffff", size=18),
                alignment=ft.Alignment.CENTER,
                expand=True,
            ),
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
