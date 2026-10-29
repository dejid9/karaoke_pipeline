"""Enhanced Audio Timeline Component with Touch Snap & Waveform/Spectrogram Rendering."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import flet as ft

from core.media import WaveformData
from core.spectrogram import SpectrogramData
from core.sps import TimelineSyllable
from ui.components.audio_timeline import (
    AudioTimelineWidget as BaseAudioTimelineWidget,
    load_waveform_from_wav_bytes,
    rgb_to_bmp,
)
from ui.theme import ThemePalette, get_current_palette


class AudioTimelineWidget(BaseAudioTimelineWidget):
    """Touch-optimized Audio Timeline with Waveform, Spectrogram, Syllables and Snap-to-Playhead."""

    def __init__(
        self,
        *,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[WaveformData], Optional[SpectrogramData]], None]] = None,
        on_syllable_clicked: Optional[Callable[[str], None]] = None,
        on_cursor_moved: Optional[Callable[[float], None]] = None,
        on_time_changed: Optional[Callable[[float], None]] = None,
        on_boundary_dragged: Optional[Callable[[str, str, float], None]] = None,
    ):
        super().__init__(
            on_audio_loaded=on_audio_loaded,
            on_syllable_clicked=on_syllable_clicked,
            on_time_changed=on_time_changed or on_cursor_moved,
        )
        self.on_boundary_dragged = on_boundary_dragged

        # Touch-friendly snap buttons embedded right next to play controls
        pal = get_current_palette()
        self.btn_snap_in = ft.IconButton(
            icon=ft.Icons.START,
            tooltip="Поставить метку [I] по курсору",
            icon_size=16,
            icon_color=pal.accent,
            on_click=lambda e: self.set_marker_in(),
        )
        self.btn_snap_out = ft.IconButton(
            icon=ft.Icons.OUTPUT,
            tooltip="Поставить метку [O] по курсору",
            icon_size=16,
            icon_color=pal.accent,
            on_click=lambda e: self.set_marker_out(),
        )

        # Append snap buttons to row 1 controls if present
        if hasattr(self, "top_controls_row1") and hasattr(self.top_controls_row1, "controls"):
            # Insert before loop marker indicator
            self.top_controls_row1.controls.insert(-1, self.btn_snap_in)
            self.top_controls_row1.controls.insert(-1, self.btn_snap_out)

    def set_marker_in(self):
        """Set In-marker [I] to current center playhead time."""
        self.playback_limit_start = self.center_time
        if self.playback_limit_end is not None and self.playback_limit_end <= self.playback_limit_start:
            self.playback_limit_end = self.playback_limit_start + 1.0
        self._update_loop_badge()
        self._refresh_timeline()

    def set_marker_out(self):
        """Set Out-marker [O] to current center playhead time."""
        self.playback_limit_end = self.center_time
        if self.playback_limit_start is not None and self.playback_limit_start >= self.playback_limit_end:
            self.playback_limit_start = max(0.0, self.playback_limit_end - 1.0)
        self._update_loop_badge()
        self._refresh_timeline()

    def apply_theme(self, pal: ThemePalette):
        super().apply_theme(pal)
        if hasattr(self, "btn_snap_in"):
            self.btn_snap_in.icon_color = pal.accent
        if hasattr(self, "btn_snap_out"):
            self.btn_snap_out.icon_color = pal.accent
