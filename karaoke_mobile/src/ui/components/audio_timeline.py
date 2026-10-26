"""Audio Timeline Component with Waveform, Spectrogram, and Syllable Boundaries."""

from __future__ import annotations

import array
import base64
import io
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Callable, Optional
import wave

import flet as ft

from core.media import WaveformData, load_waveform, _read_pcm_peaks_python
from core.spectrogram import SpectrogramData, SpectrogramViewSettings, load_spectrogram
from ui.display_settings import get_display_settings
from ui.theme import ThemePalette, get_current_palette


def rgb_to_bmp(rgb_bytes: bytes, width: int, height: int) -> bytes:
    """Pack raw RGB bytes (width * height * 3) into a standard 24-bit uncompressed BMP."""
    row_bytes = width * 3
    padding = (4 - (row_bytes % 4)) % 4
    stride = row_bytes + padding
    image_size = stride * height
    file_size = 54 + image_size

    header = struct.pack(
        "<2sIHHI IiiHHIIiiII",
        b"BM",
        file_size,
        0, 0,
        54,
        40,
        width,
        -height,  # top-down row order
        1,
        24,
        0,
        image_size,
        2835, 2835,
        0, 0,
    )

    rows = []
    pad_bytes = b"\x00" * padding
    for y in range(height):
        row = rgb_bytes[y * row_bytes : (y + 1) * row_bytes]
        bgr = bytearray(row)
        for i in range(0, len(bgr), 3):
            bgr[i], bgr[i + 2] = bgr[i + 2], bgr[i]
        rows.append(bytes(bgr) + pad_bytes)

    return header + b"".join(rows)


def load_waveform_from_wav_bytes(data: bytes, bins_per_second: int = 100) -> WaveformData:
    """Pure Python 16-bit / 8-bit PCM WAV peak envelope extractor with zero external binaries."""
    with wave.open(io.BytesIO(data), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    samples_per_bin = max(1, round(rate / bins_per_second))

    if sampwidth == 2:
        samples = array.array("h")
        samples.frombytes(raw)
        if channels > 1:
            samples = samples[::channels]
        peaks = []
        for i in range(0, len(samples), samples_per_bin):
            chunk = samples[i : i + samples_per_bin]
            if chunk:
                peaks.append((min(chunk), max(chunk)))
        total_samples = len(samples)
    elif sampwidth == 1:
        # 8-bit unsigned PCM: 0..255 -> -32768..32767
        samples_list = [int((b - 128) * 256) for b in raw[::channels]]
        peaks = []
        for i in range(0, len(samples_list), samples_per_bin):
            chunk = samples_list[i : i + samples_per_bin]
            if chunk:
                peaks.append((min(chunk), max(chunk)))
        total_samples = len(samples_list)
    else:
        # Fallback to standard python peak reader
        stream = io.BytesIO(raw)
        peaks, total_samples = _read_pcm_peaks_python(stream, samples_per_bin)

    return WaveformData(rate, samples_per_bin, tuple(peaks), total_samples)


def hex_to_rgb(hex_str: str, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    try:
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        elif len(h) == 8:
            return int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
    except Exception:
        pass
    return default


class AudioTimelineWidget(ft.Container):
    """Mobile Audio Timeline with Waveform, Spectrogram, and Perceptual Boundaries."""

    def __init__(
        self,
        *,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[WaveformData], Optional[SpectrogramData]], None]] = None,
        on_time_changed: Optional[Callable[[float], None]] = None,
    ):
        super().__init__()
        self.on_audio_loaded = on_audio_loaded
        self.on_time_changed = on_time_changed

        self.waveform: Optional[WaveformData] = None
        self.spectrogram: Optional[SpectrogramData] = None
        self.spectrogram_view = SpectrogramViewSettings()
        self.audio_mode: str = "waveform"  # "waveform", "spectrogram", "both"
        self.audio_name: str = ""
        self.audio_duration: float = 0.0

        self.center_time: float = 0.0
        self.zoom_span: float = 6.0  # seconds visible
        self.active_start: Optional[float] = None
        self.active_end: Optional[float] = None
        self.measured_start: Optional[float] = None
        self.measured_end: Optional[float] = None

        self.collapsed: bool = get_display_settings().timeline_collapsed
        self.render_width: int = 320
        self.render_height: int = get_display_settings().timeline_height(80)

        # Native Audio FilePicker
        self.audio_picker = ft.FilePicker()
        self.audio_picker.on_result = self._on_audio_picked

        self._build_ui()

    def get_services(self) -> list[ft.Service]:
        return [self.audio_picker]

    def _safe_update(self):
        try:
            self.update()
        except Exception:
            pass

    def apply_theme(self, pal: ThemePalette):
        self._build_ui()
        self._refresh_timeline()
        self._safe_update()

    def _toggle_collapse(self, e=None):
        self.collapsed = not self.collapsed
        ds = get_display_settings()
        ds.timeline_collapsed = self.collapsed
        ds.save()
        self._build_ui()
        self._refresh_timeline()
        self._safe_update()

    def _build_ui(self):
        pal = get_current_palette()
        ds = get_display_settings()
        self.render_height = ds.timeline_height(80)

        # Top Bar: Audio Title, Time Span, Mode Switcher, Zoom & Pan
        self.audio_name_text = ft.Text(
            self.audio_name if self.audio_name else "Аудио не загружено",
            size=ds.font_size(11),
            weight=ft.FontWeight.BOLD,
            color=pal.fg if self.waveform or self.spectrogram else pal.muted,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        self.time_span_text = ft.Text("00:00.0 - 00:06.0", size=ds.font_size(9.5), color=pal.muted)

        # Mode Buttons
        def make_mode_btn(label: str, mode_val: str):
            is_active = self.audio_mode == mode_val
            return ft.FilledButton(
                label,
                style=ft.ButtonStyle(
                    bgcolor=pal.accent if is_active else pal.raised,
                    color=pal.accent_fg if is_active else pal.muted,
                    padding=ds.button_padding(5, 2),
                    shape=ft.RoundedRectangleBorder(radius=6),
                ),
                on_click=lambda e: self.set_audio_mode(mode_val),
            )

        self.mode_wave_btn = make_mode_btn("Вейв", "waveform")
        self.mode_spec_btn = make_mode_btn("Спектр", "spectrogram")
        self.mode_both_btn = make_mode_btn("Оба", "both")

        # Collapse / Expand button
        self.toggle_collapse_btn = ft.IconButton(
            icon=ft.Icons.KEYBOARD_ARROW_DOWN if self.collapsed else ft.Icons.KEYBOARD_ARROW_UP,
            icon_size=ds.icon_size(18),
            tooltip="Свернуть / развернуть таймлайн",
            icon_color=pal.accent,
            on_click=self._toggle_collapse,
        )

        # Zoom Buttons
        self.zoom_out_btn = ft.IconButton(
            icon=ft.Icons.ZOOM_OUT,
            icon_size=ds.icon_size(17),
            tooltip="Отдалить (увеличить диапазон)",
            icon_color=pal.fg,
            on_click=lambda e: self._change_zoom(1.5),
        )
        self.zoom_in_btn = ft.IconButton(
            icon=ft.Icons.ZOOM_IN,
            icon_size=ds.icon_size(17),
            tooltip="Приблизить (детальнее)",
            icon_color=pal.fg,
            on_click=lambda e: self._change_zoom(0.67),
        )

        # Pan Buttons
        self.pan_left_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            icon_size=ds.icon_size(17),
            tooltip="Сдвинуть влево (-1с)",
            icon_color=pal.fg,
            on_click=lambda e: self._pan(-1.0),
        )
        self.pan_right_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            icon_size=ds.icon_size(17),
            tooltip="Сдвинуть вправо (+1с)",
            icon_color=pal.fg,
            on_click=lambda e: self._pan(1.0),
        )

        # Audio Open Button
        self.open_audio_btn = ft.IconButton(
            icon=ft.Icons.AUDIO_FILE,
            icon_size=ds.icon_size(17),
            tooltip="Загрузить аудио (.wav, .mp3, .wfm, .spg)",
            icon_color=pal.accent,
            action=ft.PickFiles(
                self.audio_picker,
                allowed_extensions=["wav", "mp3", "ogg", "flac", "wfm", "spg"],
                with_data=True,
            ),
        )

        top_controls_row1 = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.MUSIC_NOTE, size=ds.icon_size(15), color=pal.accent),
                        self.audio_name_text,
                    ],
                    spacing=3,
                    expand=True,
                ),
                ft.Row(
                    [
                        self.toggle_collapse_btn,
                        self.open_audio_btn,
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        top_controls_row2 = ft.Row(
            [
                ft.Row([self.mode_wave_btn, self.mode_spec_btn, self.mode_both_btn], spacing=3),
                self.time_span_text,
                ft.Row(
                    [
                        self.pan_left_btn,
                        self.pan_right_btn,
                        self.zoom_out_btn,
                        self.zoom_in_btn,
                    ],
                    spacing=0,
                    tight=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            visible=not self.collapsed,
        )

        # Timeline Image Visualizer
        self.timeline_image = ft.Image(
            src="",
            fit="fill",
            height=self.render_height,
            border_radius=6,
            visible=False,
            expand=True,
        )

        # Time Labels Row under Image
        self.time_labels_row = ft.Row(
            [],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            visible=False,
        )

        # Empty State Banner
        self.empty_banner = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.GRAPHIC_EQ, size=20, color=pal.muted),
                            ft.Text("Вейвформа / спектрограмма", size=ds.font_size(11), weight=ft.FontWeight.BOLD, color=pal.muted),
                        ],
                        spacing=4,
                    ),
                    ft.FilledButton(
                        "🎵 Открыть",
                        style=ft.ButtonStyle(
                            bgcolor=pal.raised,
                            color=pal.fg,
                            padding=ds.button_padding(6, 3),
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                        action=ft.PickFiles(
                            self.audio_picker,
                            allowed_extensions=["wav", "mp3", "ogg", "flac", "wfm", "spg"],
                            with_data=True,
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            bgcolor=pal.panel,
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=8,
            border=ft.Border.all(1, pal.border),
            visible=not self.collapsed,
        )

        self.content = ft.Container(
            content=ft.Column(
                [
                    top_controls_row1,
                    top_controls_row2,
                    self.timeline_image,
                    self.time_labels_row,
                    self.empty_banner,
                ],
                spacing=3,
            ),
            bgcolor=pal.raised,
            padding=8,
            border_radius=10,
            border=ft.Border.all(1, pal.border),
        )

    def set_audio_mode(self, mode: str):
        if mode in {"waveform", "spectrogram", "both"}:
            self.audio_mode = mode
            self._build_ui()
            self._refresh_timeline()
            self._safe_update()

    def set_audio(
        self,
        name: str,
        audio_bytes: Optional[bytes] = None,
        waveform: Optional[WaveformData] = None,
        spectrogram: Optional[SpectrogramData] = None,
    ):
        self.audio_name = name
        self.waveform = waveform
        self.spectrogram = spectrogram

        if waveform is not None:
            self.audio_duration = waveform.duration
        elif spectrogram is not None:
            self.audio_duration = spectrogram.duration
        elif audio_bytes:
            self._decode_and_set_audio(name, audio_bytes)

        self._build_ui()
        self._refresh_timeline()
        self._safe_update()

    def _decode_and_set_audio(self, name: str, data: bytes):
        """Decode audio bytes to WaveformData and optionally SpectrogramData."""
        ext = Path(name).suffix.lower()
        try:
            if ext == ".wfm" or data.startswith(b"WFM1"):
                # Waveform cache format
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wfm")
                try:
                    tmp.write(data)
                    tmp.close()
                    self.waveform = load_waveform(tmp.name)
                    self.audio_duration = self.waveform.duration
                finally:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
            elif ext == ".spg" or data.startswith(b"SPG1"):
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".spg")
                try:
                    tmp.write(data)
                    tmp.close()
                    self.spectrogram = load_spectrogram(tmp.name)
                    self.audio_duration = self.spectrogram.duration
                finally:
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
            elif ext == ".wav" or data.startswith(b"RIFF"):
                self.waveform = load_waveform_from_wav_bytes(data)
                self.audio_duration = self.waveform.duration
            else:
                # Try generic WAV or if ffmpeg available
                try:
                    self.waveform = load_waveform_from_wav_bytes(data)
                    self.audio_duration = self.waveform.duration
                except Exception:
                    pass
        except Exception as ex:
            print(f"Error decoding audio {name}: {ex}")

    def focus_syllable(
        self,
        start: float,
        end: float,
        meas_start: Optional[float] = None,
        meas_end: Optional[float] = None,
    ):
        self.active_start = start
        self.active_end = end
        self.measured_start = meas_start
        self.measured_end = meas_end

        # Center timeline viewport on syllable
        mid = (start + end) / 2.0
        self.center_time = mid
        self._refresh_timeline()
        self._safe_update()

    def set_active_bounds(
        self,
        start: Optional[float],
        end: Optional[float],
        meas_start: Optional[float] = None,
        meas_end: Optional[float] = None,
    ):
        self.active_start = start
        self.active_end = end
        self.measured_start = meas_start
        self.measured_end = meas_end
        self._refresh_timeline()
        self._safe_update()

    def _change_zoom(self, factor: float):
        self.zoom_span = max(0.5, min(120.0, self.zoom_span * factor))
        self._refresh_timeline()
        self._safe_update()

    def _pan(self, delta_sec: float):
        max_dur = max(self.audio_duration, (self.active_end or 0.0) + 10.0, 10.0)
        self.center_time = max(0.0, min(max_dur, self.center_time + delta_sec))
        self._refresh_timeline()
        self._safe_update()
        if self.on_time_changed:
            self.on_time_changed(self.center_time)

    def _on_audio_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        picked = e.files[0]
        data = getattr(picked, "bytes", None)
        path = getattr(picked, "path", None)
        name = picked.name or "audio"

        if data is None and path and os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()

        if data:
            self._decode_and_set_audio(name, data)
            self.audio_name = name
            self._build_ui()
            self._refresh_timeline()
            self._safe_update()
            if self.on_audio_loaded:
                self.on_audio_loaded(name, data, self.waveform, self.spectrogram)

    def _refresh_timeline(self):
        pal = get_current_palette()
        has_media = self.waveform is not None or self.spectrogram is not None

        if self.collapsed:
            self.timeline_image.visible = False
            self.time_labels_row.visible = False
            self.empty_banner.visible = False
            return

        if not has_media:
            self.timeline_image.visible = False
            self.time_labels_row.visible = False
            self.empty_banner.visible = True
            return

        self.timeline_image.visible = True
        self.time_labels_row.visible = True
        self.empty_banner.visible = False

        half_span = self.zoom_span / 2.0
        v_start = max(0.0, self.center_time - half_span)
        v_end = v_start + self.zoom_span

        def fmt_time(t: float) -> str:
            m = int(t // 60)
            s = t % 60
            return f"{m:02d}:{s:04.1f}"

        self.time_span_text.value = f"{fmt_time(v_start)} - {fmt_time(v_end)} (±{self.zoom_span:.1f}s)"

        # Generate Time Ticks
        self.time_labels_row.controls.clear()
        ticks = 5
        step = (v_end - v_start) / (ticks - 1)
        for i in range(ticks):
            t_val = v_start + i * step
            self.time_labels_row.controls.append(
                ft.Text(fmt_time(t_val), size=9, color=pal.muted)
            )

        # Render BMP Viewport
        try:
            b64_bmp = self._render_viewport_bmp(v_start, v_end, pal)
            self.timeline_image.src = f"data:image/bmp;base64,{b64_bmp}"
        except Exception as ex:
            print(f"Error rendering timeline BMP: {ex}")

    def _render_viewport_bmp(self, v_start: float, v_end: float, pal: ThemePalette) -> str:
        width = self.render_width
        try:
            p = getattr(self, "_Control__page", None)
            if p is None:
                p = self.page
            if p and getattr(p, "width", None):
                width = max(240, min(1200, int(p.width - 32)))
                self.render_width = width
        except Exception:
            pass
        height = self.render_height

        bg_rgb = hex_to_rgb(pal.canvas, (22, 22, 30))
        center_rgb = hex_to_rgb(pal.border, (50, 50, 70))
        wave_rgb = hex_to_rgb(pal.accent_alt if pal.accent_alt else pal.accent, (0, 230, 118))
        ass_line_rgb = (0, 229, 255)  # Cyan
        meas_line_rgb = (255, 179, 0)  # Amber / Warning
        tint_rgb = (
            min(255, int(bg_rgb[0] * 0.7 + wave_rgb[0] * 0.3)),
            min(255, int(bg_rgb[1] * 0.7 + wave_rgb[1] * 0.3)),
            min(255, int(bg_rgb[2] * 0.7 + wave_rgb[2] * 0.3)),
        )

        span = max(1e-9, v_end - v_start)

        def time_to_x(t: Optional[float]) -> Optional[int]:
            if t is None:
                return None
            return int(round((t - v_start) / span * (width - 1)))

        x_act_s = time_to_x(self.active_start)
        x_act_e = time_to_x(self.active_end)
        x_meas_s = time_to_x(self.measured_start)
        x_meas_e = time_to_x(self.measured_end)

        use_spectrogram = (self.audio_mode in {"spectrogram", "both"} and self.spectrogram is not None)
        use_waveform = (self.audio_mode in {"waveform", "both"} and self.waveform is not None)

        spec_rgb_bytes: Optional[bytes] = None
        if use_spectrogram and self.spectrogram is not None:
            try:
                spec_rgb_bytes = self.spectrogram.render_rgb(v_start, v_end, width, height, self.spectrogram_view)
            except Exception:
                spec_rgb_bytes = None

        col_bounds: list[tuple[int, int]] = []
        center_y = height // 2
        half_h = max(1.0, center_y - 2)
        scale = half_h / 32768.0

        if use_waveform and self.waveform is not None:
            columns = self.waveform.columns(v_start, v_end, width)
            for x in range(min(width, len(columns))):
                lo, hi = columns[x]
                yt = max(0, min(height - 1, int(center_y - hi * scale)))
                yb = max(0, min(height - 1, int(center_y - lo * scale)))
                if yt > yb:
                    yt, yb = yb, yt
                col_bounds.append((yt, yb))

        while len(col_bounds) < width:
            col_bounds.append((center_y, center_y))

        # Compose 24-bit raw RGB buffer
        out_rgb = bytearray(width * height * 3)
        row_stride = width * 3

        for y in range(height):
            for x in range(width):
                idx = y * row_stride + x * 3

                # Base Background (Spectrogram or Solid Canvas)
                if spec_rgb_bytes is not None:
                    sp_r = spec_rgb_bytes[idx]
                    sp_g = spec_rgb_bytes[idx + 1]
                    sp_b = spec_rgb_bytes[idx + 2]
                    px_r, px_g, px_b = sp_r, sp_g, sp_b
                else:
                    is_tinted = (
                        x_act_s is not None
                        and x_act_e is not None
                        and min(x_act_s, x_act_e) <= x <= max(x_act_s, x_act_e)
                    )
                    px_r, px_g, px_b = tint_rgb if is_tinted else bg_rgb

                # Center baseline
                if y == center_y:
                    px_r = int((px_r + center_rgb[0]) / 2)
                    px_g = int((px_g + center_rgb[1]) / 2)
                    px_b = int((px_b + center_rgb[2]) / 2)

                # Waveform amplitude overlay
                if use_waveform:
                    yt, yb = col_bounds[x]
                    if self.audio_mode == "both":
                        # In "both" mode, draw top and bottom contour lines
                        if abs(y - yt) <= 1 or abs(y - yb) <= 1:
                            px_r, px_g, px_b = wave_rgb
                    else:
                        # In "waveform" mode, draw filled amplitude body
                        if yt <= y <= yb:
                            px_r, px_g, px_b = wave_rgb

                # Syllable boundaries (2px line for high touch visibility)
                if x_act_s is not None and abs(x - x_act_s) <= 1:
                    px_r, px_g, px_b = ass_line_rgb
                elif x_act_e is not None and abs(x - x_act_e) <= 1:
                    px_r, px_g, px_b = ass_line_rgb
                elif x_meas_s is not None and abs(x - x_meas_s) <= 1:
                    px_r, px_g, px_b = meas_line_rgb
                elif x_meas_e is not None and abs(x - x_meas_e) <= 1:
                    px_r, px_g, px_b = meas_line_rgb

                out_rgb[idx] = px_r
                out_rgb[idx + 1] = px_g
                out_rgb[idx + 2] = px_b

        bmp_data = rgb_to_bmp(bytes(out_rgb), width, height)
        return base64.b64encode(bmp_data).decode("ascii")
