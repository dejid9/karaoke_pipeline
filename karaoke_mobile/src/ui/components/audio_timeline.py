"""Audio Timeline Component with Waveform, Spectrogram, and Syllable Boundaries."""

from __future__ import annotations

import array
import asyncio
import base64
import io
import math
import os
from pathlib import Path
import re
import struct
import tempfile
from typing import Callable, Optional, Sequence
import wave

import flet as ft

try:
    import flet_audio as fta
except Exception:
    fta = None

from core.media import WaveformData, load_waveform, _read_pcm_peaks_python
from core.spectrogram import SpectrogramData, SpectrogramViewSettings, load_spectrogram
from core.sps import TimelineSyllable
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


def _get_dummy_silent_wav_path() -> str:
    """Provide a valid 44-byte silent WAV file so flet_audio.Audio initializes without error in Flutter."""
    tmp_path = os.path.join(tempfile.gettempdir(), "karaoke_silence_init.wav")
    if not os.path.exists(tmp_path):
        wav_hdr = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        try:
            with open(tmp_path, "wb") as f:
                f.write(wav_hdr)
        except Exception:
            pass
    return tmp_path


class AudioTimelineWidget(ft.Container):
    """Mobile Audio Timeline with Waveform, Spectrogram, and Perceptual Boundaries."""

    def __init__(
        self,
        *,
        on_audio_loaded: Optional[Callable[[str, bytes, Optional[WaveformData], Optional[SpectrogramData]], None]] = None,
        on_time_changed: Optional[Callable[[float], None]] = None,
        on_syllable_clicked: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.on_audio_loaded = on_audio_loaded
        self.on_time_changed = on_time_changed
        self.on_syllable_clicked = on_syllable_clicked

        self.syllables: list[TimelineSyllable] = []
        self.active_syllable_id: Optional[str] = None
        self._page: Optional[ft.Page] = None

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

        # Native Audio Player initialized with dummy silent wav
        self.temp_audio_path: Optional[str] = None
        self.is_playing: bool = False
        self._playback_token: int = 0
        self.audio_player: Optional[ft.Service] = None
        if fta is not None:
            try:
                init_src = _get_dummy_silent_wav_path()
                self.audio_player = fta.Audio(
                    src=init_src,
                    autoplay=False,
                    volume=1.0,
                    on_position_change=self._on_player_position_change,
                    on_state_change=self._on_player_state_change,
                )
            except Exception as ex:
                print(f"Error initializing flet_audio: {ex}")
                self.audio_player = None

        self._build_ui()

    def get_services(self) -> list[ft.Service]:
        svcs: list[ft.Service] = [self.audio_picker]
        if self.audio_player is not None:
            svcs.append(self.audio_player)
        return svcs

    def _safe_update(self):
        try:
            self.update()
        except Exception:
            pass

    def _get_page(self) -> Optional[ft.Page]:
        if getattr(self, "_page", None):
            return self._page
        try:
            if self.page:
                return self.page
        except Exception:
            pass
        return getattr(self, "_Control__page", None)

    def _ensure_audio_service(self):
        """Ensure audio_player service is properly attached to the page."""
        p = self._get_page()
        if p and self.audio_player is not None:
            if hasattr(p, "services") and self.audio_player not in p.services:
                p.services.append(self.audio_player)
                try:
                    p.update()
                except Exception:
                    pass

    def _update_player_src(self, path: str):
        """Update audio source on audio_player and push update to client."""
        self.temp_audio_path = path
        if self.audio_player is not None:
            self.audio_player.src = path
            try:
                self.audio_player.update()
            except Exception:
                pass

    def apply_theme(self, pal: ThemePalette):
        self._build_ui()
        self._refresh_timeline()
        p = self._get_page()
        if p:
            try:
                p.update()
            except Exception:
                self._safe_update()
        else:
            self._safe_update()

    def _toggle_collapse(self, e=None):
        self.collapsed = not self.collapsed
        ds = get_display_settings()
        ds.timeline_collapsed = self.collapsed
        ds.save()
        if hasattr(self, "toggle_collapse_btn"):
            self.toggle_collapse_btn.icon = ft.Icons.KEYBOARD_ARROW_DOWN if self.collapsed else ft.Icons.KEYBOARD_ARROW_UP
            self.toggle_collapse_btn.tooltip = "Развернуть" if self.collapsed else "Свернуть"
        if hasattr(self, "top_controls_row2"):
            self.top_controls_row2.visible = not self.collapsed
        self._refresh_timeline()
        p = self._get_page()
        if p:
            try:
                p.update()
            except Exception:
                self._safe_update()
        else:
            self._safe_update()

    def toggle_play(self, e=None):
        """Play/pause continuous playback from center_time playhead with smooth tracking."""
        if not self.audio_player or not self.temp_audio_path:
            return
        p = self._get_page()
        if not p:
            return

        async def _run():
            self._playback_token += 1
            if self.is_playing:
                self.is_playing = False
                self._update_play_icon()
                try:
                    await self.audio_player.pause()
                except Exception as ex:
                    print(f"Pause error: {ex}")
            else:
                self.is_playing = True
                self._update_play_icon()
                self._ensure_audio_service()
                token = self._playback_token
                try:
                    pos_ms = max(0, int(self.center_time * 1000))
                    if hasattr(self.audio_player, "play"):
                        await self.audio_player.play(pos_ms)
                    else:
                        await self.audio_player.seek(pos_ms)
                        await self.audio_player.resume()
                except Exception as ex:
                    print(f"Play error: {ex}")
                    self.is_playing = False
                    self._update_play_icon()
                    return

                # Smooth tracking loop
                start_time = self.center_time
                loop = asyncio.get_event_loop()
                t0 = loop.time()
                while self.is_playing and self._playback_token == token:
                    await asyncio.sleep(0.05)
                    elapsed = loop.time() - t0
                    cur = start_time + elapsed
                    if self.audio_duration and cur >= self.audio_duration:
                        self.center_time = self.audio_duration
                        self.is_playing = False
                        self._update_play_icon()
                        try:
                            await self.audio_player.pause()
                        except Exception:
                            pass
                        self._refresh_timeline()
                        self._safe_update()
                        break
                    self.center_time = round(cur, 3)
                    self._refresh_timeline()
                    self._safe_update()
                    if self.on_time_changed:
                        self.on_time_changed(self.center_time)

        p.run_task(_run)

    def stop_audio(self, e=None):
        """Stop audio playback and reset playhead."""
        if not self.audio_player:
            return
        p = self._get_page()
        if not p:
            return

        async def _run():
            self._playback_token += 1
            self.is_playing = False
            self._update_play_icon()
            try:
                await self.audio_player.pause()
                await self.audio_player.seek(0)
            except Exception:
                pass
            self.center_time = 0.0
            self._refresh_timeline()
            self._safe_update()
            if self.on_time_changed:
                self.on_time_changed(self.center_time)

        p.run_task(_run)

    def play_range(self, start_sec: float, end_sec: float):
        """Play a specific slice of audio (e.g. syllable or measurement) and auto-pause with visual cursor."""
        if not self.audio_player or not self.temp_audio_path:
            return
        p = self._get_page()
        if not p:
            return

        async def _run():
            self._playback_token += 1
            token = self._playback_token
            self.is_playing = True
            self._update_play_icon()
            self._ensure_audio_service()
            try:
                pos_ms = max(0, int(start_sec * 1000))
                if hasattr(self.audio_player, "play"):
                    await self.audio_player.play(pos_ms)
                else:
                    await self.audio_player.seek(pos_ms)
                    await self.audio_player.resume()

                dur = max(0.05, end_sec - start_sec)
                loop = asyncio.get_event_loop()
                t0 = loop.time()
                while loop.time() - t0 < dur and self.is_playing and self._playback_token == token:
                    elapsed = loop.time() - t0
                    self.center_time = round(start_sec + elapsed, 3)
                    self._refresh_timeline()
                    self._safe_update()
                    if self.on_time_changed:
                        self.on_time_changed(self.center_time)
                    await asyncio.sleep(0.04)

                if self._playback_token == token:
                    try:
                        await self.audio_player.pause()
                    except Exception:
                        pass
            except Exception as ex:
                print(f"Play range error: {ex}")
            finally:
                if self._playback_token == token:
                    self.is_playing = False
                    self._update_play_icon()
                    self.center_time = round(end_sec, 3)
                    self._refresh_timeline()
                    self._safe_update()
                    if self.on_time_changed:
                        self.on_time_changed(self.center_time)

        p.run_task(_run)

    def _update_play_icon(self):
        try:
            if hasattr(self, "play_pause_btn"):
                self.play_pause_btn.icon = ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW
                self.play_pause_btn.tooltip = "Пауза" if self.is_playing else "Воспроизвести с курсора"
                self._safe_update()
        except Exception:
            pass

    def _on_player_position_change(self, e):
        if not self.is_playing:
            return
        pos_val = getattr(e, "position", None)
        if pos_val is None and isinstance(getattr(e, "data", None), dict):
            pos_val = e.data.get("position")
        if pos_val is not None:
            if hasattr(pos_val, "total_seconds"):
                sec = pos_val.total_seconds()
            elif isinstance(pos_val, (int, float)):
                sec = pos_val / 1000.0 if pos_val > 100 else float(pos_val)
            else:
                try:
                    sec = float(pos_val) / 1000.0
                except Exception:
                    sec = None
            if sec is not None:
                self.center_time = round(sec, 3)
                self._refresh_timeline()
                self._safe_update()
                if self.on_time_changed:
                    self.on_time_changed(self.center_time)

    def _on_player_state_change(self, e):
        state = getattr(e, "data", None) or getattr(e, "state", None)
        if state in ("completed", "stopped", "paused"):
            if self.is_playing:
                self.is_playing = False
                self._update_play_icon()

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

        # Play / Pause & Stop Buttons
        self.play_pause_btn = ft.IconButton(
            icon=ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW,
            icon_size=ds.icon_size(18),
            tooltip="Воспроизвести / пауза",
            icon_color=pal.accent,
            on_click=self.toggle_play,
        )
        self.stop_btn = ft.IconButton(
            icon=ft.Icons.STOP,
            icon_size=ds.icon_size(18),
            tooltip="Остановить",
            icon_color=pal.fg,
            on_click=self.stop_audio,
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
                        self.play_pause_btn,
                        self.stop_btn,
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
        self.top_controls_row1 = top_controls_row1

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
        self.top_controls_row2 = top_controls_row2

        # Timeline Image Visualizer wrapped in GestureDetector for tap & pan scrubbing
        self.timeline_image = ft.Image(
            src="",
            fit="fill",
            height=self.render_height,
            border_radius=6,
            visible=False,
            expand=True,
        )

        self.timeline_gesture = ft.GestureDetector(
            content=self.timeline_image,
            on_tap_down=self._on_timeline_tap,
            on_pan_update=self._on_timeline_pan,
        )

        # Interactive Syllables Strip (chips below spectrogram)
        self.syllable_strip = ft.Row(
            [],
            spacing=3,
            wrap=True,
            visible=False,
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
                    self.timeline_gesture,
                    self.syllable_strip,
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

        if audio_bytes:
            self._cache_audio_file(name, audio_bytes)

        self._build_ui()
        self._refresh_timeline()
        self._safe_update()

    def _cache_audio_file(self, name: str, data: bytes):
        try:
            clean = re.sub(r"[^a-zA-Z0-9_\.-]", "_", name)
            if not Path(clean).suffix:
                clean += ".wav"
            tmp_dir = tempfile.gettempdir()
            self.temp_audio_path = os.path.join(tmp_dir, f"karaoke_audio_{clean}")
            with open(self.temp_audio_path, "wb") as fp:
                fp.write(data)
            self._update_player_src(self.temp_audio_path)
            self._ensure_audio_service()
        except Exception as ex:
            print(f"Error caching audio for player: {ex}")

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

    def set_syllables(
        self,
        syllables: Sequence[TimelineSyllable],
        active_id: Optional[str] = None,
    ):
        """Pass all syllables in document/timeline to display boundaries on spectrogram and waveform."""
        self.syllables = list(syllables)
        self.active_syllable_id = active_id
        if active_id:
            syl = next((s for s in self.syllables if s.id == active_id), None)
            if syl:
                self.active_start = syl.start
                self.active_end = syl.end
                self.measured_start = getattr(syl, "measured_start", None)
                self.measured_end = getattr(syl, "measured_end", None)
        self._refresh_timeline()
        self._safe_update()

    def focus_syllable(
        self,
        start: float,
        end: float,
        meas_start: Optional[float] = None,
        meas_end: Optional[float] = None,
        syllable_id: Optional[str] = None,
    ):
        self.active_start = start
        self.active_end = end
        self.measured_start = meas_start
        self.measured_end = meas_end
        if syllable_id:
            self.active_syllable_id = syllable_id
        elif self.syllables:
            match = next((s for s in self.syllables if abs(s.start - start) < 0.001 and abs(s.end - end) < 0.001), None)
            if match:
                self.active_syllable_id = match.id

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
        syllable_id: Optional[str] = None,
    ):
        self.active_start = start
        self.active_end = end
        self.measured_start = meas_start
        self.measured_end = meas_end
        self.active_syllable_id = syllable_id
        self._refresh_timeline()
        self._safe_update()

    def _on_timeline_tap(self, e: ft.TapEvent):
        width = self.render_width
        if width <= 0:
            return
        local_x = getattr(e, "local_x", None)
        if local_x is None and hasattr(e, "local_position") and e.local_position:
            local_x = e.local_position.x
        if local_x is None:
            return

        half_span = self.zoom_span / 2.0
        v_start = max(0.0, self.center_time - half_span)
        click_ratio = max(0.0, min(1.0, float(local_x) / width))
        t = round(v_start + click_ratio * self.zoom_span, 3)
        max_dur = max(self.audio_duration, (self.active_end or 0.0) + 10.0, 10.0)
        self.center_time = max(0.0, min(max_dur, t))

        # Check if tap landed on any syllable
        hit_syl = None
        for s in self.syllables:
            if s.start <= t <= s.end:
                hit_syl = s
                break

        if hit_syl:
            self.active_syllable_id = hit_syl.id
            self.active_start = hit_syl.start
            self.active_end = hit_syl.end
            self.measured_start = getattr(hit_syl, "measured_start", None)
            self.measured_end = getattr(hit_syl, "measured_end", None)
            if self.on_syllable_clicked:
                self.on_syllable_clicked(hit_syl.id)

        self._refresh_timeline()
        self._safe_update()
        if self.on_time_changed:
            self.on_time_changed(self.center_time)

    def _on_timeline_pan(self, e: ft.DragUpdateEvent):
        width = self.render_width
        if width <= 0:
            return
        dx = getattr(e, "delta_x", None)
        if dx is None and hasattr(e, "local_delta") and e.local_delta:
            dx = e.local_delta.x
        elif dx is None and hasattr(e, "primary_delta") and e.primary_delta is not None:
            dx = e.primary_delta
        if dx is None or dx == 0:
            return

        delta_sec = - (float(dx) / width) * self.zoom_span
        max_dur = max(self.audio_duration, (self.active_end or 0.0) + 10.0, 10.0)
        self.center_time = max(0.0, min(max_dur, self.center_time + delta_sec))
        self._refresh_timeline()
        self._safe_update()
        if self.on_time_changed:
            self.on_time_changed(self.center_time)

    def _handle_syllable_chip_click(self, sid: str):
        self.active_syllable_id = sid
        syl = next((s for s in self.syllables if s.id == sid), None)
        if syl:
            self.active_start = syl.start
            self.active_end = syl.end
            self.measured_start = getattr(syl, "measured_start", None)
            self.measured_end = getattr(syl, "measured_end", None)
            self.center_time = (syl.start + syl.end) / 2.0
        self._refresh_timeline()
        self._safe_update()
        if self.on_syllable_clicked:
            self.on_syllable_clicked(sid)
        if self.on_time_changed:
            self.on_time_changed(self.center_time)

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

        if path and os.path.exists(path):
            self._update_player_src(path)
            self._ensure_audio_service()
        elif data:
            self._cache_audio_file(name, data)

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
        ds = get_display_settings()
        has_media = self.waveform is not None or self.spectrogram is not None

        if hasattr(self, "top_controls_row2"):
            self.top_controls_row2.visible = not self.collapsed

        if self.collapsed:
            if hasattr(self, "timeline_gesture"):
                self.timeline_gesture.visible = False
            self.timeline_image.visible = False
            self.time_labels_row.visible = False
            self.syllable_strip.visible = False
            self.empty_banner.visible = False
            return

        if not has_media:
            if hasattr(self, "timeline_gesture"):
                self.timeline_gesture.visible = False
            self.timeline_image.visible = False
            self.time_labels_row.visible = False
            self.syllable_strip.visible = False
            self.empty_banner.visible = True
            return

        if hasattr(self, "timeline_gesture"):
            self.timeline_gesture.visible = True
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

        # Populate Syllables Strip with visible syllables
        self.syllable_strip.controls.clear()
        if self.syllables:
            visible_syls = [s for s in self.syllables if s.end >= v_start and s.start <= v_end]
            if visible_syls:
                self.syllable_strip.visible = True
                for s in visible_syls:
                    is_active = (s.id == self.active_syllable_id)
                    dur_ms = int(round(s.effective_duration * 1000)) if hasattr(s, "effective_duration") else int(round((s.end - s.start) * 1000))
                    txt = s.text.strip().replace("\n", " ") if hasattr(s, "text") and s.text else "•"
                    if len(txt) > 8:
                        txt = txt[:7] + "…"

                    label = f"{txt} ({dur_ms}ms)"
                    if getattr(s, "burst_marked", False):
                        label = f"🔥 {label}"

                    chip_bg = pal.accent if is_active else (pal.raised if getattr(s, "measurement_changed", False) else pal.panel)
                    chip_fg = pal.accent_fg if is_active else pal.fg
                    chip_border = ft.Border.all(
                        1.5 if is_active else 1,
                        pal.accent if is_active else (pal.accent_alt if getattr(s, "measurement_changed", False) else pal.border)
                    )

                    btn = ft.Container(
                        content=ft.Text(label, size=ds.font_size(9.5), weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL, color=chip_fg),
                        bgcolor=chip_bg,
                        border=chip_border,
                        border_radius=5,
                        padding=ds.button_padding(4, 2),
                        on_click=lambda e, sid=s.id: self._handle_syllable_chip_click(sid),
                    )
                    self.syllable_strip.controls.append(btn)
            else:
                self.syllable_strip.visible = False
        else:
            self.syllable_strip.visible = False

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
        border_rgb = hex_to_rgb(pal.border, (80, 80, 100))
        raised_rgb = hex_to_rgb(pal.raised, (40, 40, 55))
        accent_rgb = hex_to_rgb(pal.accent, (0, 229, 255))
        accent_alt_rgb = hex_to_rgb(pal.accent_alt if pal.accent_alt else pal.accent, (255, 179, 0))
        danger_rgb = hex_to_rgb(pal.danger, (255, 75, 75))
        ass_line_rgb = (0, 229, 255)  # Cyan
        meas_line_rgb = (255, 179, 0)  # Amber / Warning
        cursor_rgb = (255, 235, 59)    # Playhead cursor
        syl_line_rgb = (
            min(255, int(bg_rgb[0] * 0.4 + 90)),
            min(255, int(bg_rgb[1] * 0.4 + 100)),
            min(255, int(bg_rgb[2] * 0.4 + 130)),
        )
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

        top_lane_h = 10
        top_lane_colors: list[Optional[tuple[int, int, int]]] = [None] * width
        is_syl_boundary = bytearray(width)
        is_act_boundary = bytearray(width)
        is_meas_boundary = bytearray(width)
        is_active_body = bytearray(width)

        # Mark all visible syllables on the timeline
        for s in self.syllables:
            if s.end < v_start or s.start > v_end:
                continue
            xs0 = time_to_x(s.start)
            xs1 = time_to_x(s.end)
            if xs0 is None or xs1 is None:
                continue

            if 0 <= xs0 < width:
                is_syl_boundary[xs0] = 1
            if 0 <= xs1 < width:
                is_syl_boundary[xs1] = 1

            x_min = max(0, min(width - 1, min(xs0, xs1)))
            x_max = max(0, min(width - 1, max(xs0, xs1)))

            is_act = (s.id == self.active_syllable_id) or (
                self.active_start is not None and abs(s.start - self.active_start) < 0.001
            )
            is_burst = getattr(s, "burst_marked", False)
            is_meas_ch = getattr(s, "measurement_changed", False)

            if is_act:
                syl_col = accent_rgb
                for x in range(x_min, x_max + 1):
                    is_active_body[x] = 1
            elif is_burst:
                syl_col = danger_rgb
            elif is_meas_ch:
                syl_col = accent_alt_rgb
            else:
                syl_col = raised_rgb

            for x in range(x_min, x_max + 1):
                top_lane_colors[x] = syl_col

            if getattr(s, "measured_start", None) is not None:
                xm = time_to_x(s.measured_start)
                if xm is not None and 0 <= xm < width:
                    is_meas_boundary[xm] = 1
            if getattr(s, "measured_end", None) is not None:
                xm = time_to_x(s.measured_end)
                if xm is not None and 0 <= xm < width:
                    is_meas_boundary[xm] = 1

        x_act_s = time_to_x(self.active_start)
        x_act_e = time_to_x(self.active_end)
        x_meas_s = time_to_x(self.measured_start)
        x_meas_e = time_to_x(self.measured_end)

        # Fallback if no syllables list was set but active_start/end exist
        if not self.syllables and x_act_s is not None and x_act_e is not None:
            x_min = max(0, min(width - 1, min(x_act_s, x_act_e)))
            x_max = max(0, min(width - 1, max(x_act_s, x_act_e)))
            for x in range(x_min, x_max + 1):
                is_active_body[x] = 1
                top_lane_colors[x] = accent_rgb

        for x_val in (x_act_s, x_act_e):
            if x_val is not None:
                for off in (-1, 0, 1):
                    nx = x_val + off
                    if 0 <= nx < width:
                        is_act_boundary[nx] = 1

        for x_val in (x_meas_s, x_meas_e):
            if x_val is not None:
                for off in (-1, 0, 1):
                    nx = x_val + off
                    if 0 <= nx < width:
                        is_meas_boundary[nx] = 1

        center_x = time_to_x(self.center_time)

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

                # Top Syllable Status Lane
                if y < top_lane_h:
                    if y == top_lane_h - 1:
                        px_r, px_g, px_b = border_rgb
                    elif is_syl_boundary[x]:
                        px_r, px_g, px_b = border_rgb
                    else:
                        lane_col = top_lane_colors[x]
                        if lane_col is not None:
                            px_r, px_g, px_b = lane_col
                        elif spec_rgb_bytes is not None:
                            px_r = spec_rgb_bytes[idx]
                            px_g = spec_rgb_bytes[idx + 1]
                            px_b = spec_rgb_bytes[idx + 2]
                        else:
                            px_r, px_g, px_b = bg_rgb
                else:
                    # Waveform or Spectrogram body
                    if spec_rgb_bytes is not None:
                        px_r = spec_rgb_bytes[idx]
                        px_g = spec_rgb_bytes[idx + 1]
                        px_b = spec_rgb_bytes[idx + 2]
                    else:
                        px_r, px_g, px_b = tint_rgb if is_active_body[x] else bg_rgb

                    # Center baseline
                    if y == center_y:
                        px_r = int((px_r + center_rgb[0]) / 2)
                        px_g = int((px_g + center_rgb[1]) / 2)
                        px_b = int((px_b + center_rgb[2]) / 2)

                    # Waveform amplitude overlay
                    if use_waveform:
                        yt, yb = col_bounds[x]
                        if self.audio_mode == "both":
                            if abs(y - yt) <= 1 or abs(y - yb) <= 1:
                                px_r, px_g, px_b = wave_rgb
                        else:
                            if yt <= y <= yb:
                                px_r, px_g, px_b = wave_rgb

                # Syllable boundaries (active cyan > measured amber > general syllable line)
                if is_act_boundary[x]:
                    px_r, px_g, px_b = ass_line_rgb
                elif is_meas_boundary[x]:
                    px_r, px_g, px_b = meas_line_rgb
                elif is_syl_boundary[x]:
                    px_r = int(px_r * 0.35 + syl_line_rgb[0] * 0.65)
                    px_g = int(px_g * 0.35 + syl_line_rgb[1] * 0.65)
                    px_b = int(px_b * 0.35 + syl_line_rgb[2] * 0.65)

                # Center cursor playhead (dashed line)
                if center_x is not None and x == center_x and y >= top_lane_h:
                    if (y // 3) % 2 == 0:
                        px_r, px_g, px_b = cursor_rgb

                out_rgb[idx] = px_r
                out_rgb[idx + 1] = px_g
                out_rgb[idx + 2] = px_b

        bmp_data = rgb_to_bmp(bytes(out_rgb), width, height)
        return base64.b64encode(bmp_data).decode("ascii")
