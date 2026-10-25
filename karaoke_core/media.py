from __future__ import annotations

from array import array
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
import os
import json
import math
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
import zlib
from typing import BinaryIO, Callable, Iterable, Optional

try:
    import numpy as _np
except Exception:  # NumPy is optional for the waveform fast path.
    _np = None



ProgressCallback = Callable[[Optional[float], str], None]
LogCallback = Callable[[str], None]


def _background_process_creation_flags() -> int:
    """Keep cache/analysis FFmpeg jobs from making the GUI unresponsive."""
    if os.name != "nt":
        return 0
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    flags |= int(getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    return flags


def normalize_playback_speed(value: float) -> float:
    """Clamp playback speed and snap the near-1x dead zone to exactly 1.0.

    0.97x..1.03x (inclusive) is intentionally treated as 1.00x. This avoids
    accidental tiny tempo/pitch changes around the centre position of the UI
    slider and keeps the direct PortAudio path active.
    """
    try:
        speed = float(value)
    except (TypeError, ValueError):
        speed = 1.0
    speed = max(0.25, min(4.0, speed))
    if 0.97 - 1e-12 <= speed <= 1.03 + 1e-12:
        return 1.0
    return speed


def _is_windows_audio_platform() -> bool:
    return sys.platform.startswith("win")


def _windows_default_audio_endpoint_id() -> Optional[str]:
    """Return the current Windows Core Audio default render endpoint id.

    PortAudio binds a stream to the endpoint selected when the stream is
    opened.  Windows can change the default endpoint later (Bluetooth/headset,
    HDMI, USB DAC, etc.) without invalidating the Python object.  Querying
    IMMDeviceEnumerator lets the persistent player notice that switch and
    reopen only when it is actually necessary.  No third-party COM package is
    required.
    """
    if not _is_windows_audio_platform():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def guid(text: str) -> GUID:
            import uuid
            value = uuid.UUID(text)
            raw = value.bytes_le
            return GUID(
                int.from_bytes(raw[0:4], "little"),
                int.from_bytes(raw[4:6], "little"),
                int.from_bytes(raw[6:8], "little"),
                (ctypes.c_ubyte * 8).from_buffer_copy(raw[8:16]),
            )

        ole32 = ctypes.OleDLL("ole32")
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

        hr_init = int(ole32.CoInitializeEx(None, 0x2))  # COINIT_APARTMENTTHREADED
        should_uninit = hr_init in (0, 1)
        enumerator = ctypes.c_void_p()
        device = ctypes.c_void_p()
        endpoint_text = ctypes.c_void_p()
        try:
            clsid = guid("bcde0395-e52f-467c-8e3d-c4579291692e")
            iid = guid("a95664d2-9614-4f35-a746-de8db63617e6")
            hr = int(ole32.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(enumerator)))
            if hr < 0 or not enumerator.value:
                return None

            def method(ptr: ctypes.c_void_p, index: int, restype, *argtypes):
                vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
                return prototype(vtable[index])

            # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia).
            get_default = method(enumerator, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
            hr = int(get_default(enumerator, 0, 1, ctypes.byref(device)))
            if (hr < 0 or not device.value):
                # Some drivers only expose a console-role default.
                hr = int(get_default(enumerator, 0, 0, ctypes.byref(device)))
            if hr < 0 or not device.value:
                return None

            get_id = method(device, 5, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))
            hr = int(get_id(device, ctypes.byref(endpoint_text)))
            if hr < 0 or not endpoint_text.value:
                return None
            return ctypes.wstring_at(endpoint_text.value)
        finally:
            if endpoint_text.value:
                try: ole32.CoTaskMemFree(endpoint_text)
                except Exception: pass
            for ptr in (device, enumerator):
                if ptr.value:
                    try:
                        release = method(ptr, 2, wintypes.ULONG)
                        release(ptr)
                    except Exception:
                        pass
            if should_uninit:
                try: ole32.CoUninitialize()
                except Exception: pass
    except Exception:
        return None


def _refresh_sounddevice_catalog(sd) -> None:
    """Refresh PortAudio's device snapshot after a Windows default-device change."""
    terminate = getattr(sd, "_terminate", None)
    initialize = getattr(sd, "_initialize", None)
    if callable(terminate) and callable(initialize):
        terminate()
        initialize()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def media_tool_subprocess_env(executable: str | Path) -> dict[str, str]:
    """Return an environment safe for FFmpeg/ffprobe/ffplay on Windows.

    When the GUI itself is launched from a Conda environment, Conda prepends
    ``<env>\\Library\\bin`` and related directories to PATH.  A standalone
    FFmpeg distribution can then accidentally load GTK/gettext/etc. DLLs from
    that unrelated Conda environment, causing Windows loader errors before
    FFmpeg even starts.

    If the media executable lives *outside* the active CONDA_PREFIX, strip only
    that Conda prefix's PATH entries and prepend the executable directory.  If
    FFmpeg itself is inside the active Conda environment, leave PATH untouched.
    Non-Windows platforms are returned unchanged.
    """
    env = os.environ.copy()
    if not sys.platform.startswith("win"):
        return env
    try:
        exe = Path(executable).expanduser().resolve()
    except Exception:
        return env
    conda_raw = env.get("CONDA_PREFIX")
    if not conda_raw:
        return env
    try:
        conda_prefix = Path(conda_raw).expanduser().resolve()
    except Exception:
        return env
    if _is_relative_to(exe, conda_prefix):
        return env

    raw_path = env.get("PATH", "")
    kept: list[str] = []
    for entry in raw_path.split(os.pathsep):
        if not entry:
            continue
        try:
            resolved = Path(entry.strip('"')).expanduser().resolve()
            if _is_relative_to(resolved, conda_prefix):
                continue
        except Exception:
            pass
        kept.append(entry)
    exe_dir = str(exe.parent)
    kept = [item for item in kept if item.strip('"').lower() != exe_dir.lower()]
    env["PATH"] = os.pathsep.join([exe_dir, *kept])
    return env


def _emit_progress(callback: Optional[ProgressCallback], value: Optional[float], stage: str) -> None:
    if callback is not None:
        callback(value, stage)


def _emit_log(callback: Optional[LogCallback], message: str) -> None:
    if callback is not None:
        callback(message)

_MAGIC = b"WFM1"
_HEADER = struct.Struct("<4sIIIQ")  # magic, sample_rate, samples_per_bin, peak_count, total_samples


@dataclass(slots=True, frozen=True)
class WaveformData:
    sample_rate: int
    samples_per_bin: int
    peaks: tuple[tuple[int, int], ...]
    total_samples: int

    @property
    def seconds_per_bin(self) -> float:
        return self.samples_per_bin / self.sample_rate

    @property
    def duration(self) -> float:
        return self.total_samples / self.sample_rate if self.sample_rate else 0.0

    def columns(self, start: float, end: float, width: int) -> list[tuple[int, int]]:
        """Downsample min/max peaks to roughly one pair per output pixel."""
        width = max(1, int(width))
        if not self.peaks or end <= start:
            return [(0, 0)] * width
        first = max(0, int(start / self.seconds_per_bin))
        last = min(len(self.peaks), int(end / self.seconds_per_bin) + 2)
        visible = self.peaks[first:last]
        if not visible:
            return [(0, 0)] * width
        result: list[tuple[int, int]] = []
        n = len(visible)
        for x in range(width):
            a = (x * n) // width
            b = ((x + 1) * n) // width
            if b <= a:
                b = min(n, a + 1)
            chunk = visible[a:b]
            if not chunk:
                result.append((0, 0))
            else:
                result.append((min(p[0] for p in chunk), max(p[1] for p in chunk)))
        return result


def resolve_ffprobe(ffmpeg: Optional[str | Path] = None) -> Optional[Path]:
    # ffprobe must come from the same distribution as the selected FFmpeg.
    # Do not fall back to PATH/Conda.
    if not ffmpeg:
        return None
    value = Path(ffmpeg)
    candidates = [value.with_name("ffprobe.exe"), value.with_name("ffprobe")]
    for item in candidates:
        if item.is_file():
            return item.resolve()
    return None


def probe_media_duration(media: str | Path, ffmpeg: Optional[str | Path] = None) -> Optional[float]:
    ffprobe = resolve_ffprobe(ffmpeg)
    if ffprobe is None:
        return None
    try:
        proc = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(Path(media).resolve())],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", timeout=15, check=False,
            env=media_tool_subprocess_env(ffprobe),
        )
        if proc.returncode == 0:
            value = float((proc.stdout or "").strip())
            return value if value > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return None


@dataclass(slots=True, frozen=True)
class MediaTimeBounds:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def probe_audio_bounds(media: str | Path, ffmpeg: Optional[str | Path] = None) -> Optional[MediaTimeBounds]:
    """Return the first audio stream's usable timeline bounds.

    Stream duration is preferred; container duration is used only as a fallback
    because some codecs/containers expose ``N/A`` for the stream duration.
    This is intentionally sourced from the same ffprobe distribution as the
    selected portable/custom FFmpeg.
    """
    ffprobe = resolve_ffprobe(ffmpeg)
    if ffprobe is None:
        return None
    try:
        proc = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=start_time,duration:format=duration",
                "-of", "json", str(Path(media).resolve()),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace", timeout=15, check=False,
            env=media_tool_subprocess_env(ffprobe),
        )
        if proc.returncode != 0:
            return None
        payload = json.loads(proc.stdout or "{}")
        streams = payload.get("streams") or []
        if not streams:
            return None
        stream = streams[0] or {}
        fmt = payload.get("format") or {}

        def number(value, default=None):
            try:
                parsed = float(value)
                return parsed if math.isfinite(parsed) else default
            except (TypeError, ValueError):
                return default

        start = number(stream.get("start_time"), 0.0) or 0.0
        duration = number(stream.get("duration"))
        if duration is None or duration <= 0:
            format_duration = number(fmt.get("duration"))
            if format_duration is None or format_duration <= 0:
                return None
            # Container duration is normally relative to timeline zero. If an
            # audio stream starts later, the fallback usable end is the end of
            # the container rather than start+container_duration.
            end = format_duration
        else:
            end = start + duration
        if end <= start:
            return None
        return MediaTimeBounds(float(start), float(end))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None


def resolve_ffplay(ffmpeg: Optional[str | Path] = None) -> Optional[Path]:
    # ffplay must come from the same selected distribution; no PATH fallback.
    if not ffmpeg:
        return None
    ffmpeg = Path(ffmpeg)
    candidates = [ffmpeg.with_name("ffplay.exe"), ffmpeg.with_name("ffplay")]
    for item in candidates:
        if item.is_file():
            return item.resolve()
    return None


def waveform_cache_path(media: str | Path, cache_root: Optional[str | Path] = None, *, bins_per_second: int = 100) -> Path:
    media = Path(media).resolve()
    stat = media.stat()
    token = f"{media}|{stat.st_size}|{stat.st_mtime_ns}|{bins_per_second}".encode("utf-8", "surrogatepass")
    digest = sha1(token).hexdigest()[:20]
    if cache_root is None:
        root = Path(tempfile.gettempdir()) / "karaoke_sps_waveforms"
    else:
        root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{media.stem}-{digest}.wfm"


def save_waveform(path: str | Path, waveform: WaveformData) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    values = array("h")
    for lo, hi in waveform.peaks:
        values.append(int(lo))
        values.append(int(hi))
    if sys.byteorder != "little":
        values.byteswap()
    body = zlib.compress(values.tobytes(), level=6)
    payload = _HEADER.pack(
        _MAGIC,
        waveform.sample_rate,
        waveform.samples_per_bin,
        len(waveform.peaks),
        waveform.total_samples,
    ) + body
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, target)
    return target


def load_waveform(path: str | Path) -> WaveformData:
    data = Path(path).read_bytes()
    if len(data) < _HEADER.size:
        raise ValueError("Waveform cache is truncated")
    magic, sample_rate, samples_per_bin, count, total_samples = _HEADER.unpack_from(data)
    if magic != _MAGIC:
        raise ValueError("Unsupported waveform cache format")
    raw = zlib.decompress(data[_HEADER.size:])
    values = array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != count * 2:
        raise ValueError("Waveform cache peak count mismatch")
    peaks = tuple((values[i], values[i + 1]) for i in range(0, len(values), 2))
    return WaveformData(sample_rate, samples_per_bin, peaks, total_samples)


def _read_pcm_peaks_python(stream: BinaryIO, samples_per_bin: int, on_samples: Optional[Callable[[int], None]] = None) -> tuple[list[tuple[int, int]], int]:
    """Pure-Python fallback for environments where NumPy is unavailable."""
    peaks: list[tuple[int, int]] = []
    pending = bytearray()
    current_min = 32767
    current_max = -32768
    in_bin = 0
    total_samples = 0

    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        pending.extend(chunk)
        usable = len(pending) - (len(pending) % 2)
        if not usable:
            continue
        values = array("h")
        values.frombytes(pending[:usable])
        del pending[:usable]
        if sys.byteorder != "little":
            values.byteswap()
        for sample in values:
            current_min = min(current_min, sample)
            current_max = max(current_max, sample)
            in_bin += 1
            total_samples += 1
            if in_bin >= samples_per_bin:
                peaks.append((current_min, current_max))
                current_min, current_max, in_bin = 32767, -32768, 0
        if on_samples is not None:
            on_samples(total_samples)

    if in_bin:
        peaks.append((current_min if current_min != 32767 else 0, current_max if current_max != -32768 else 0))
    return peaks, total_samples


def _read_pcm_peaks_numpy(stream: BinaryIO, samples_per_bin: int, on_samples: Optional[Callable[[int], None]] = None) -> tuple[list[tuple[int, int]], int]:
    """Vectorized peak extraction; typically tens of times faster than per-sample Python."""
    assert _np is not None
    peaks: list[tuple[int, int]] = []
    byte_tail = b""
    sample_tail = _np.empty(0, dtype=_np.dtype("<i2"))
    total_samples = 0

    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        if byte_tail:
            chunk = byte_tail + chunk
            byte_tail = b""
        usable = len(chunk) - (len(chunk) % 2)
        if usable != len(chunk):
            byte_tail = chunk[usable:]
        if not usable:
            continue

        values = _np.frombuffer(memoryview(chunk)[:usable], dtype="<i2")
        total_samples += int(values.size)
        if sample_tail.size:
            values = _np.concatenate((sample_tail, values))

        full = (int(values.size) // samples_per_bin) * samples_per_bin
        if full:
            blocks = values[:full].reshape(-1, samples_per_bin)
            lows = blocks.min(axis=1)
            highs = blocks.max(axis=1)
            peaks.extend(zip(lows.astype(_np.int16).tolist(), highs.astype(_np.int16).tolist()))
        sample_tail = values[full:].copy()
        if on_samples is not None:
            on_samples(total_samples)

    if sample_tail.size:
        peaks.append((int(sample_tail.min()), int(sample_tail.max())))
    return peaks, total_samples


def extract_waveform(
    media: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    bins_per_second: int = 100,
    sample_rate: int = 8000,
    cache_path: Optional[str | Path] = None,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> WaveformData:
    """Decode media once and create a compact min/max peak envelope.

    The original media is never modified. At 100 bins/s each waveform column is
    based on a 10 ms audio interval. NumPy is used when available so long media
    is processed in vectorized blocks instead of looping over every PCM sample
    in Python. A pure-Python fallback is kept for minimal installations.
    """
    media = Path(media).resolve()
    if bins_per_second <= 0 or sample_rate <= 0:
        raise ValueError("bins_per_second and sample_rate must be positive")
    samples_per_bin = max(1, round(sample_rate / bins_per_second))
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(media), "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1",
    ]
    duration_hint = probe_media_duration(media, ffmpeg)
    _emit_progress(progress, 5.0, "Подготовка FFmpeg")
    _emit_log(log, "> " + " ".join(f'"{x}"' if " " in x else x for x in cmd))
    _emit_progress(progress, 10.0, "Декодирование аудио")
    last_report = [-1.0]
    def on_samples(total: int) -> None:
        if duration_hint and duration_hint > 0:
            pct = 10.0 + min(80.0, (total / (duration_hint * sample_rate)) * 80.0)
            if pct - last_report[0] >= 0.5:
                last_report[0] = pct
                _emit_progress(progress, pct, "Декодирование / построение пиков")

    # Do not pipe stderr: a damaged input can emit enough diagnostics to fill a
    # pipe while we are still consuming stdout, which would stall FFmpeg.
    stderr_file = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        stdin=subprocess.DEVNULL,
        env=media_tool_subprocess_env(ffmpeg),
        creationflags=_background_process_creation_flags(),
    )
    assert proc.stdout is not None
    try:
        if _np is not None:
            peaks, total_samples = _read_pcm_peaks_numpy(proc.stdout, samples_per_bin, on_samples)
        else:
            peaks, total_samples = _read_pcm_peaks_python(proc.stdout, samples_per_bin, on_samples)
        proc.stdout.close()
        rc = proc.wait()
        stderr_file.seek(0)
        stderr = stderr_file.read().decode("utf-8", "replace")
        if rc != 0:
            raise RuntimeError(stderr.strip() or f"ffmpeg exited with code {rc}")
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        stderr_file.close()

    _emit_progress(progress, 92.0, "Формирование waveform")
    waveform = WaveformData(sample_rate, samples_per_bin, tuple(peaks), total_samples)
    if cache_path:
        _emit_progress(progress, 96.0, "Сохранение кэша")
        save_waveform(cache_path, waveform)
    _emit_progress(progress, 100.0, "Waveform готов")
    return waveform


def load_or_extract_waveform(
    media: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    cache_root: Optional[str | Path] = None,
    bins_per_second: int = 100,
    sample_rate: int = 8000,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> tuple[WaveformData, Path, bool]:
    cache = waveform_cache_path(media, cache_root, bins_per_second=bins_per_second)
    if cache.exists():
        try:
            _emit_progress(progress, 10.0, "Чтение waveform-кэша")
            data = load_waveform(cache)
            _emit_progress(progress, 100.0, "Waveform загружен из кэша")
            _emit_log(log, f"Waveform cache: {cache}")
            return data, cache, True
        except Exception as exc:
            _emit_log(log, f"Повреждённый waveform cache будет перестроен: {exc}")
            cache.unlink(missing_ok=True)
    waveform = extract_waveform(
        media,
        ffmpeg=ffmpeg,
        bins_per_second=bins_per_second,
        sample_rate=sample_rate,
        cache_path=cache,
        progress=progress,
        log=log,
    )
    return waveform, cache, False



@dataclass(slots=True, frozen=True)
class PlaybackPCMCache:
    path: Path
    sample_rate: int
    channels: int
    sample_width: int
    total_frames: int

    @property
    def duration(self) -> float:
        return self.total_frames / float(self.sample_rate or 1)


def playback_pcm_cache_path(
    media: str | Path, cache_root: Optional[str | Path] = None, *, sample_rate: int = 48000, channels: int = 2
) -> Path:
    media = Path(media).resolve()
    stat = media.stat()
    token = f"{media}|{stat.st_size}|{stat.st_mtime_ns}|pcm|{sample_rate}|{channels}".encode("utf-8", "surrogatepass")
    digest = sha1(token).hexdigest()[:20]
    if cache_root is None:
        root = Path(tempfile.gettempdir()) / "karaoke_sps_playback"
    else:
        root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{media.stem}-{digest}.s16le"


def load_playback_pcm_cache(path: str | Path, *, sample_rate: int = 48000, channels: int = 2) -> PlaybackPCMCache:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    frame_bytes = channels * 2
    size = path.stat().st_size
    if size <= 0 or size % frame_bytes:
        raise ValueError("Playback PCM cache has an invalid size")
    return PlaybackPCMCache(path.resolve(), sample_rate, channels, 2, size // frame_bytes)


def extract_playback_pcm_cache(
    media: str | Path, *, ffmpeg: str | Path, cache_path: str | Path,
    sample_rate: int = 48000, channels: int = 2, progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> PlaybackPCMCache:
    """Decode the first audio stream once to seekable raw PCM for low-latency transport.

    Playback never asks FFmpeg to seek/decode on a Space press when this cache is ready.
    The cache is atomic and keyed by source path/mtime/size.
    """
    media = Path(media).resolve(); target = Path(cache_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    duration = probe_media_duration(media, ffmpeg)
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(media), "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        "-f", "s16le", str(tmp), "-progress", "pipe:1", "-nostats",
    ]
    _emit_log(log, "> " + " ".join(f'"{x}"' if " " in x else x for x in cmd))
    _emit_progress(progress, 2.0, "Подготовка PCM-кэша")
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=media_tool_subprocess_env(ffmpeg),
        creationflags=_background_process_creation_flags(),
    )
    stderr_lines: list[str] = []
    def read_err():
        if proc.stderr is None: return
        for line in proc.stderr:
            line=line.rstrip()
            if line:
                stderr_lines.append(line); _emit_log(log, line)
    err_thread=threading.Thread(target=read_err, daemon=True); err_thread.start()
    try:
        if proc.stdout is not None:
            for raw in proc.stdout:
                line=raw.strip()
                if not line or "=" not in line: continue
                key, value=line.split("=",1)
                if key in {"out_time_us", "out_time_ms"} and duration and duration > 0:
                    try:
                        number=float(value)
                        # FFmpeg out_time_us is microseconds; older builds sometimes report out_time_ms in microseconds too.
                        seconds=number/1_000_000.0
                        pct=5.0 + min(90.0, max(0.0, seconds/duration*90.0))
                        _emit_progress(progress, pct, "Декодирование PCM для плеера")
                    except ValueError:
                        pass
        rc=proc.wait(); err_thread.join(timeout=0.5)
        if rc != 0:
            tmp.unlink(missing_ok=True)
            detail="\n".join(stderr_lines[-20:]).strip()
            raise RuntimeError(detail or f"ffmpeg exited with code {rc}")
        if not tmp.is_file() or tmp.stat().st_size <= channels*2:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("FFmpeg создал пустой PCM-кэш")
        os.replace(tmp, target)
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()
        tmp.unlink(missing_ok=True)
    _emit_progress(progress, 100.0, "PCM-кэш готов")
    return load_playback_pcm_cache(target, sample_rate=sample_rate, channels=channels)


def load_or_extract_playback_pcm_cache(
    media: str | Path, *, ffmpeg: str | Path, cache_root: Optional[str | Path] = None,
    sample_rate: int = 48000, channels: int = 2, progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> tuple[PlaybackPCMCache, Path, bool]:
    cache_path = playback_pcm_cache_path(media, cache_root, sample_rate=sample_rate, channels=channels)
    if cache_path.exists():
        try:
            data=load_playback_pcm_cache(cache_path, sample_rate=sample_rate, channels=channels)
            _emit_progress(progress, 100.0, "PCM-кэш загружен")
            _emit_log(log, f"Playback PCM cache: {cache_path}")
            return data, cache_path, True
        except Exception as exc:
            _emit_log(log, f"Повреждённый playback cache будет перестроен: {exc}")
            cache_path.unlink(missing_ok=True)
    data=extract_playback_pcm_cache(
        media, ffmpeg=ffmpeg, cache_path=cache_path, sample_rate=sample_rate, channels=channels,
        progress=progress, log=log,
    )
    return data, cache_path, False


class _WindowsWaveOutSink:
    """Small persistent WinMM waveOut sink for low-latency PCM playback.

    The device stays open for the lifetime of :class:`MediaPlayer`, so repeated
    50--150 ms karaoke auditions do not pay Windows/SDL device startup cost.
    """

    SAMPLE_RATE = 48000
    CHANNELS = 2
    SAMPLE_WIDTH = 2
    BUFFER_MS = 50
    BUFFER_COUNT = 4

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("waveOut backend is Windows-only")
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.winmm = ctypes.WinDLL("winmm")
        self._closed = False
        self._paused = False

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [
                ("wFormatTag", wintypes.WORD),
                ("nChannels", wintypes.WORD),
                ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD),
                ("nBlockAlign", wintypes.WORD),
                ("wBitsPerSample", wintypes.WORD),
                ("cbSize", wintypes.WORD),
            ]

        class WAVEHDR(ctypes.Structure):
            _fields_ = [
                ("lpData", ctypes.c_void_p),
                ("dwBufferLength", wintypes.DWORD),
                ("dwBytesRecorded", wintypes.DWORD),
                ("dwUser", ctypes.c_size_t),
                ("dwFlags", wintypes.DWORD),
                ("dwLoops", wintypes.DWORD),
                ("lpNext", ctypes.c_void_p),
                ("reserved", ctypes.c_size_t),
            ]

        self.WAVEHDR = WAVEHDR
        # Explicit prototypes matter on 64-bit Windows because waveOutOpen uses
        # UINT_PTR/DWORD_PTR arguments rather than plain 32-bit ints.
        self.winmm.waveOutOpen.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t, ctypes.POINTER(WAVEFORMATEX),
            ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD,
        ]
        self.winmm.waveOutOpen.restype = wintypes.UINT
        self.winmm.waveOutPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        self.winmm.waveOutPrepareHeader.restype = wintypes.UINT
        self.winmm.waveOutWrite.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        self.winmm.waveOutWrite.restype = wintypes.UINT
        self.winmm.waveOutPause.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutPause.restype = wintypes.UINT
        self.winmm.waveOutRestart.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutRestart.restype = wintypes.UINT
        self.winmm.waveOutReset.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutReset.restype = wintypes.UINT
        self.winmm.waveOutUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        self.winmm.waveOutUnprepareHeader.restype = wintypes.UINT
        self.winmm.waveOutClose.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutClose.restype = wintypes.UINT
        self.WHDR_DONE = 0x00000001
        self.WHDR_PREPARED = 0x00000002
        self.handle = ctypes.c_void_p()
        block_align = self.CHANNELS * self.SAMPLE_WIDTH
        fmt = WAVEFORMATEX(
            1, self.CHANNELS, self.SAMPLE_RATE,
            self.SAMPLE_RATE * block_align, block_align,
            self.SAMPLE_WIDTH * 8, 0,
        )
        result = self.winmm.waveOutOpen(
            ctypes.byref(self.handle), ctypes.c_size_t(0xFFFFFFFF), ctypes.byref(fmt),
            0, 0, 0,
        )
        if result != 0:
            raise RuntimeError(f"waveOutOpen failed: {result}")

        self.chunk_bytes = int(self.SAMPLE_RATE * self.BUFFER_MS / 1000) * block_align
        self._buffers: list[tuple[object, object, bool]] = []
        try:
            for _ in range(self.BUFFER_COUNT):
                raw = ctypes.create_string_buffer(self.chunk_bytes)
                hdr = WAVEHDR()
                hdr.lpData = ctypes.cast(raw, ctypes.c_void_p)
                hdr.dwBufferLength = self.chunk_bytes
                result = self.winmm.waveOutPrepareHeader(
                    self.handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR)
                )
                if result != 0:
                    raise RuntimeError(f"waveOutPrepareHeader failed: {result}")
                self._buffers.append((raw, hdr, False))
        except Exception:
            self.close()
            raise
        self._next = 0

    def _wait_available(self, index: int, stop_event: threading.Event | None = None) -> bool:
        raw, hdr, submitted = self._buffers[index]
        if not submitted:
            return True
        while not (hdr.dwFlags & self.WHDR_DONE):
            if stop_event is not None and stop_event.is_set():
                return False
            time.sleep(0.002)
        self._buffers[index] = (raw, hdr, False)
        return True

    def write(self, data: bytes, stop_event: threading.Event | None = None) -> bool:
        if self._closed or not data:
            return False
        idx = self._next
        if not self._wait_available(idx, stop_event):
            return False
        raw, hdr, _ = self._buffers[idx]
        n = min(len(data), self.chunk_bytes)
        self.ctypes.memmove(raw, data, n)
        hdr.dwBufferLength = n
        result = self.winmm.waveOutWrite(
            self.handle, self.ctypes.byref(hdr), self.ctypes.sizeof(self.WAVEHDR)
        )
        if result != 0:
            raise RuntimeError(f"waveOutWrite failed: {result}")
        self._buffers[idx] = (raw, hdr, True)
        self._next = (idx + 1) % len(self._buffers)
        return True

    def pause(self) -> None:
        if not self._closed:
            self.winmm.waveOutPause(self.handle)
            self._paused = True

    def resume(self) -> None:
        if not self._closed:
            self.winmm.waveOutRestart(self.handle)
            self._paused = False

    def reset(self) -> None:
        if self._closed:
            return
        self.winmm.waveOutReset(self.handle)
        for i, (raw, hdr, _submitted) in enumerate(self._buffers):
            self._buffers[i] = (raw, hdr, False)
        self._next = 0
        self._paused = False

    def drain(self, stop_event: threading.Event | None = None) -> None:
        for i in range(len(self._buffers)):
            if not self._wait_available(i, stop_event):
                return

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True
        try:
            self.winmm.waveOutReset(self.handle)
        except Exception:
            pass
        for raw, hdr, _submitted in getattr(self, "_buffers", []):
            try:
                self.winmm.waveOutUnprepareHeader(
                    self.handle, self.ctypes.byref(hdr), self.ctypes.sizeof(self.WAVEHDR)
                )
            except Exception:
                pass
        try:
            self.winmm.waveOutClose(self.handle)
        except Exception:
            pass
        self._buffers = []


def _atempo_chain(speed: float) -> str:
    """Build an FFmpeg atempo chain for 0.25x..4x while preserving pitch."""
    speed = normalize_playback_speed(speed)
    factors: list[float] = []
    while speed < 0.5 - 1e-9:
        factors.append(0.5)
        speed /= 0.5
    while speed > 2.0 + 1e-9:
        factors.append(2.0)
        speed /= 2.0
    if abs(speed - 1.0) > 1e-9 or not factors:
        factors.append(speed)
    return ",".join(f"atempo={value:.6f}" for value in factors if abs(value - 1.0) > 1e-9)


class _PortAudioPCMEngine:
    """Persistent low-latency PortAudio transport over a seekable PCM cache.

    The output stream is opened once and kept alive. At 1x playback, or when
    pitch preservation is disabled, the callback reads directly from a memory
    mapped PCM cache. Pitch-preserving non-1x playback uses FFmpeg *only* as an
    atempo processor over that already-decoded cache; the audio device itself
    remains open, so there is no per-syllable device startup penalty.
    """
    SAMPLE_RATE = 48000
    CHANNELS = 2
    SAMPLE_WIDTH = 2
    BLOCKSIZE = 480  # 10 ms
    PREBUFFER_FRAMES = 1920  # 40 ms for atempo mode
    MAX_PROCESSED_BYTES = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * 2  # ~2 s

    def __init__(
        self,
        *,
        cursor_offset_seconds: float = 0.0,
        cursor_delay_seconds: float | None = None,
        follow_default_device: bool = True,
        monitor_default_device: bool = True,
    ) -> None:
        if _np is None:
            raise RuntimeError("Для низколатентного плеера требуется NumPy")
        try:
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError("Для низколатентного плеера требуется пакет sounddevice") from exc
        self.sd = sd
        self.lock = threading.RLock()
        self.cache: Optional[PlaybackPCMCache] = None
        self._samples = None
        self.state = "stopped"
        self.start_frame = 0.0
        self.end_frame: Optional[int] = None
        self.source_frame = 0.0
        self.speed = 1.0
        self.preserve_pitch = True
        # Update 029: the playhead follows submitted PCM immediately.  Do not
        # subtract PortAudio's nominal device latency: on some Windows/WASAPI
        # stacks it overestimates the perceptual delay by ~100 ms.  A small
        # signed visual offset remains available for manual fine tuning.
        if cursor_delay_seconds is not None and abs(float(cursor_offset_seconds)) < 1e-12:
            cursor_offset_seconds = 0.0  # legacy delay is intentionally not migrated
        self.cursor_offset_seconds = max(-0.25, min(0.25, float(cursor_offset_seconds)))
        self._drain_deadline: Optional[float] = None
        self._processed = bytearray()
        self._processed_eof = False
        self._processor: Optional[subprocess.Popen] = None
        self._processor_thread: Optional[threading.Thread] = None
        self._generation = 0
        self._mode = "direct"
        self._source_start_seconds = 0.0
        self._processed_output_frames = 0
        self._started_audio = False
        self._latency_seconds = 0.0
        self._backend_description = "PortAudio"
        self._selected_device_index: Optional[int] = None
        self.follow_default_device = bool(follow_default_device)
        self._system_default_endpoint_id = _windows_default_audio_endpoint_id()
        self._active_ffmpeg: Optional[Path] = None
        self._closed = False
        self._device_rebind_lock = threading.Lock()
        self._device_monitor_stop = threading.Event()
        self._device_monitor_thread: Optional[threading.Thread] = None
        self.stream = self._open_stream()
        if _is_windows_audio_platform() and monitor_default_device:
            self._device_monitor_thread = threading.Thread(
                target=self._device_monitor_loop, name="audio-device-monitor", daemon=True
            )
            self._device_monitor_thread.start()

    @property
    def backend_description(self) -> str:
        return self._backend_description

    def _open_stream(self):
        sd = self.sd
        kwargs = dict(
            samplerate=self.SAMPLE_RATE, blocksize=self.BLOCKSIZE, channels=self.CHANNELS,
            dtype="int16", latency="low", callback=self._callback,
        )
        # Prefer the *current* default WASAPI endpoint on Windows.  When the
        # system default changes, refresh_default_output_device() closes this
        # stream, refreshes PortAudio's device snapshot and opens a new one.
        selected: Optional[int] = None
        if _is_windows_audio_platform():
            try:
                hostapis = sd.query_hostapis()
                for api in hostapis:
                    if "wasapi" not in str(api.get("name", "")).lower():
                        continue
                    dev = int(api.get("default_output_device", -1))
                    if dev >= 0:
                        selected = dev
                        kwargs["device"] = dev
                        self._backend_description = "PortAudio / WASAPI"
                        break
            except Exception:
                pass
        try:
            stream = sd.RawOutputStream(**kwargs)
        except Exception:
            kwargs.pop("device", None)
            selected = None
            self._backend_description = "PortAudio / default"
            stream = sd.RawOutputStream(**kwargs)
        stream.start()
        self._selected_device_index = selected
        try:
            device_index = selected if selected is not None else getattr(stream, "device", None)
            if device_index is not None:
                info = sd.query_devices(device_index)
                name = str(info.get("name", "")).strip() if isinstance(info, dict) else ""
                if name:
                    self._backend_description += f" · {name}"
        except Exception:
            pass
        try:
            latency = stream.latency
            if isinstance(latency, (tuple, list)):
                latency = latency[-1]
            self._latency_seconds = max(0.0, float(latency or 0.0))
        except Exception:
            self._latency_seconds = 0.0
        return stream

    def set_cache(self, cache: PlaybackPCMCache) -> None:
        if cache.sample_rate != self.SAMPLE_RATE or cache.channels != self.CHANNELS or cache.sample_width != 2:
            raise ValueError("Playback PCM cache format does not match PortAudio engine")
        with self.lock:
            self.stop()
            self.cache = cache
            self._samples = _np.memmap(cache.path, dtype="<i2", mode="r", shape=(cache.total_frames, cache.channels))

    def clear_cache(self) -> None:
        with self.lock:
            self.stop()
            self.cache = None
            self._samples = None

    @property
    def playing(self) -> bool:
        with self.lock:
            self._finish_drain_if_needed()
            return self.state in {"playing", "draining"}

    @property
    def paused(self) -> bool:
        with self.lock:
            return self.state == "paused"

    def _finish_drain_if_needed(self) -> None:
        if self.state == "draining" and self._drain_deadline is not None and time.monotonic() >= self._drain_deadline:
            self.state = "stopped"
            if self.end_frame is not None:
                self.source_frame = float(self.end_frame)
            self._drain_deadline = None

    def position(self) -> float:
        with self.lock:
            self._finish_drain_if_needed()
            if self.cache is None:
                return 0.0
            # source_frame is the media frame most recently submitted to the
            # persistent PortAudio stream.  Following it directly makes the
            # playhead react on the first callback instead of intentionally
            # waiting for stream.latency + an extra UI delay.
            visual = self.source_frame + self.cursor_offset_seconds * self.SAMPLE_RATE * max(0.25, self.speed)
            visual = max(self.start_frame, visual)
            if self.end_frame is not None:
                visual = min(visual, float(self.end_frame))
            return visual / self.SAMPLE_RATE

    def set_cursor_offset(self, seconds: float) -> None:
        with self.lock:
            self.cursor_offset_seconds = max(-0.25, min(0.25, float(seconds)))

    def set_cursor_delay(self, seconds: float) -> None:
        # Backward-compatible API name.  Legacy positive delay semantics are
        # deliberately retired; callers should use set_cursor_offset().
        self.set_cursor_offset(seconds)

    def _stop_processor(self) -> None:
        proc = self._processor
        self._processor = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate(); proc.wait(timeout=0.25)
            except Exception:
                try: proc.kill()
                except Exception: pass
        self._processed.clear(); self._processed_eof = False
        self._processor_thread = None

    def stop(self) -> None:
        with self.lock:
            self._generation += 1
            self.state = "stopped"
            self._drain_deadline = None
            self._started_audio = False
            self._stop_processor()

    def pause(self) -> None:
        with self.lock:
            if self.state == "playing":
                self.state = "paused"

    def resume(self) -> None:
        with self.lock:
            if self.state == "paused":
                self.state = "playing"

    def set_follow_default_device(self, enabled: bool) -> None:
        enabled = bool(enabled)
        was_enabled = self.follow_default_device
        self.follow_default_device = enabled
        if enabled and not was_enabled and _is_windows_audio_platform():
            # Re-enabling the setting should immediately move to the current
            # system endpoint. Re-applying unchanged settings must not reopen
            # the device and introduce a new playback click/delay.
            try:
                self.refresh_default_output_device(force=True)
            except Exception:
                pass

    def _device_monitor_loop(self) -> None:
        # Poll Core Audio, not Tk.  The call is cheap and the actual PortAudio
        # stream is rebuilt only when the endpoint id changes.
        while not self._device_monitor_stop.wait(0.75):
            if self._closed or not self.follow_default_device:
                continue
            try:
                self.refresh_default_output_device(force=False)
            except Exception:
                # A transient unplug/replug should not kill the transport.
                pass

    def refresh_default_output_device(self, *, force: bool = False) -> bool:
        if not _is_windows_audio_platform():
            return False
        if not force and not self.follow_default_device:
            return False
        endpoint_id = _windows_default_audio_endpoint_id()
        if not force:
            if endpoint_id is None or endpoint_id == self._system_default_endpoint_id:
                return False
        self._rebind_output_stream(endpoint_id)
        return True

    def _rebind_output_stream(self, endpoint_id: Optional[str]) -> None:
        with self._device_rebind_lock:
            if self._closed:
                return
            with self.lock:
                was_state = self.state
                was_active = was_state in {"playing", "paused"}
                position = self.position() if was_active else (self.source_frame / self.SAMPLE_RATE)
                end = None if self.end_frame is None else self.end_frame / self.SAMPLE_RATE
                speed = self.speed
                preserve_pitch = self.preserve_pitch
                ffmpeg = self._active_ffmpeg
                self._generation += 1
                self.state = "stopped"
                self._drain_deadline = None
                self._started_audio = False
                self._stop_processor()
                old_stream = self.stream
                self.stream = None
            if old_stream is not None:
                try: old_stream.stop()
                except Exception: pass
                try: old_stream.close()
                except Exception: pass
            try:
                _refresh_sounddevice_catalog(self.sd)
            except Exception:
                pass
            new_stream = self._open_stream()
            with self.lock:
                self.stream = new_stream
                self._system_default_endpoint_id = endpoint_id or _windows_default_audio_endpoint_id()
            if was_active and self.cache is not None and ffmpeg is not None:
                # Resume at the media frame that had actually been submitted.
                self.play(position, end, speed=speed, preserve_pitch=preserve_pitch, ffmpeg=ffmpeg)
                if was_state == "paused":
                    self.pause()

    def close(self) -> None:
        self._closed = True
        self._device_monitor_stop.set()
        with self._device_rebind_lock:
            with self.lock:
                self.stop()
                stream = self.stream
                self.stream = None
            if stream is not None:
                try: stream.stop()
                except Exception: pass
                try: stream.close()
                except Exception: pass
        thread = self._device_monitor_thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=1.0)
        self._device_monitor_thread = None

    def _start_atempo_processor(self, ffmpeg: Path, start: float, end: Optional[float], speed: float, generation: int) -> None:
        cache = self.cache
        if cache is None:
            raise RuntimeError("PCM cache is not loaded")
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-ss", f"{start:.6f}", "-f", "s16le", "-ar", str(self.SAMPLE_RATE), "-ac", str(self.CHANNELS),
            "-i", str(cache.path),
        ]
        filters = []
        if end is not None:
            filters.append(f"atrim=duration={max(0.001, end-start):.9f}")
            filters.append("asetpts=PTS-STARTPTS")
        atempo = _atempo_chain(speed)
        if atempo:
            filters.append(atempo)
        if filters:
            cmd += ["-af", ",".join(filters)]
        cmd += ["-f", "s16le", "-ac", str(self.CHANNELS), "-ar", str(self.SAMPLE_RATE), "pipe:1"]
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, env=media_tool_subprocess_env(ffmpeg))
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(cmd, **kwargs)
        self._processor = proc

        def worker():
            try:
                stdout = proc.stdout
                if stdout is None: return
                while generation == self._generation:
                    # Keep only a small rolling buffer; a full song can be
                    # hundreds of MB of PCM and FFmpeg can otherwise outrun
                    # real-time playback very quickly.
                    while generation == self._generation:
                        with self.lock:
                            buffered = len(self._processed)
                        if buffered < self.MAX_PROCESSED_BYTES:
                            break
                        time.sleep(0.01)
                    chunk = stdout.read(64 * 1024)
                    if not chunk: break
                    with self.lock:
                        if generation != self._generation: break
                        self._processed.extend(chunk)
                with self.lock:
                    if generation == self._generation:
                        self._processed_eof = True
            finally:
                try:
                    if proc.poll() is None: proc.terminate()
                except Exception: pass
        thread=threading.Thread(target=worker, name="playback-atempo", daemon=True)
        self._processor_thread=thread; thread.start()

    def play(self, start: float, end: Optional[float], *, speed: float, preserve_pitch: bool, ffmpeg: Path) -> None:
        with self.lock:
            if self.cache is None or self._samples is None:
                raise RuntimeError("PCM-кэш для плеера ещё не готов")
            self.stop()
            self._generation += 1; generation=self._generation
            start=max(0.0, min(float(start), self.cache.duration))
            end_value=None if end is None else max(start, min(float(end), self.cache.duration))
            self.start_frame=start*self.SAMPLE_RATE
            self.source_frame=self.start_frame
            self.end_frame=None if end_value is None else int(round(end_value*self.SAMPLE_RATE))
            self._source_start_seconds=start
            self.speed=normalize_playback_speed(speed)
            self.preserve_pitch=bool(preserve_pitch)
            self._active_ffmpeg = Path(ffmpeg)
            self._processed_output_frames=0
            self._started_audio=False
            self._drain_deadline=None
            self._mode="processed" if self.preserve_pitch and abs(self.speed-1.0)>1e-6 else "direct"
            self.state="playing"
            if self._mode == "processed":
                self._start_atempo_processor(ffmpeg, start, end_value, self.speed, generation)

    def set_speed(self, speed: float, *, preserve_pitch: Optional[bool], ffmpeg: Path) -> None:
        with self.lock:
            speed=normalize_playback_speed(speed)
            preserve=self.preserve_pitch if preserve_pitch is None else bool(preserve_pitch)
            if abs(speed-self.speed)<1e-6 and preserve == self.preserve_pitch:
                return
            pos=self.position(); end=None if self.end_frame is None else self.end_frame/self.SAMPLE_RATE
            was_active=self.state in {"playing", "paused"}; was_paused=self.state == "paused"
        if was_active:
            self.play(pos, end, speed=speed, preserve_pitch=preserve, ffmpeg=ffmpeg)
            if was_paused: self.pause()
        else:
            with self.lock:
                self.speed=speed; self.preserve_pitch=preserve

    def _direct_block(self, frames: int) -> tuple[bytes, bool]:
        cache=self.cache; samples=self._samples
        if cache is None or samples is None:
            return b"\x00"*(frames*self.CHANNELS*self.SAMPLE_WIDTH), False
        end_frame=cache.total_frames if self.end_frame is None else min(cache.total_frames, self.end_frame)
        if self.source_frame >= end_frame:
            return b"\x00"*(frames*self.CHANNELS*self.SAMPLE_WIDTH), True
        speed=self.speed
        if abs(speed-1.0)<1e-9:
            start=int(self.source_frame); take=min(frames, max(0,end_frame-start))
            block=_np.asarray(samples[start:start+take], dtype="<i2").tobytes()
            self.source_frame += take
            done=take < frames or self.source_frame >= end_frame
            if take < frames: block += b"\x00"*((frames-take)*self.CHANNELS*self.SAMPLE_WIDTH)
            return block, done
        positions=self.source_frame + _np.arange(frames, dtype=_np.float64)*speed
        valid=positions < end_frame
        count=int(valid.sum())
        out=_np.zeros((frames,self.CHANNELS), dtype=_np.int16)
        if count:
            pos=positions[:count]; i0=_np.floor(pos).astype(_np.int64); i1=_np.minimum(i0+1,end_frame-1); frac=(pos-i0)[:,None]
            a=_np.asarray(samples[i0],dtype=_np.float32); b=_np.asarray(samples[i1],dtype=_np.float32)
            out[:count]=_np.clip(a+(b-a)*frac,-32768,32767).astype(_np.int16)
            self.source_frame += count*speed
        return out.tobytes(), count < frames or self.source_frame >= end_frame

    def _processed_block(self, frames: int) -> tuple[bytes, bool]:
        need=frames*self.CHANNELS*self.SAMPLE_WIDTH
        # Do not start the audible stream until a small chunk has been produced.
        # While waiting, output silence and leave the media position untouched.
        if not self._started_audio:
            if len(self._processed) < min(need, self.PREBUFFER_FRAMES*self.CHANNELS*self.SAMPLE_WIDTH) and not self._processed_eof:
                return b"\x00"*need, False
            self._started_audio=True
        available=min(need,len(self._processed)); available -= available%(self.CHANNELS*self.SAMPLE_WIDTH)
        block=bytes(self._processed[:available]); del self._processed[:available]
        produced_frames=available//(self.CHANNELS*self.SAMPLE_WIDTH)
        if produced_frames:
            self._processed_output_frames += produced_frames
            self.source_frame=self.start_frame + self._processed_output_frames*self.speed
        if available < need: block += b"\x00"*(need-available)
        done=self._processed_eof and not self._processed
        return block, done

    def _callback(self, outdata, frames, time_info, status) -> None:
        zero=b"\x00"*(frames*self.CHANNELS*self.SAMPLE_WIDTH)
        try:
            with self.lock:
                self._finish_drain_if_needed()
                if self.state in {"stopped", "paused", "draining"}:
                    outdata[:] = zero; return
                if self._mode == "processed": block, done=self._processed_block(frames)
                else: block, done=self._direct_block(frames)
                outdata[:] = block
                if done and self.state == "playing":
                    latency=max(0.01, self._latency_seconds)
                    self.state="draining"; self._drain_deadline=time.monotonic()+latency
        except Exception:
            try: outdata[:] = zero
            except Exception: pass
            with self.lock:
                self.state="stopped"



class MediaPlayer:
    """Audacity-like transport with persistent Windows audio output.

    On Windows the player keeps one WinMM ``waveOut`` device open and streams
    PCM decoded by FFmpeg into it. Repeated syllable auditioning therefore does
    not reopen the audio device. The same engine also supports continuous play,
    pause/resume and pitch-preserving playback speed.

    If WinMM cannot be initialized, the older pre-rendered WAV + winsound/ffplay
    path remains available as a compatibility fallback.
    """

    DEFAULT_LEAD_SILENCE_SECONDS = 0.700
    DEFAULT_TAIL_SILENCE_SECONDS = 0.250
    LEAD_SILENCE_SECONDS = DEFAULT_LEAD_SILENCE_SECONDS
    TAIL_SILENCE_SECONDS = DEFAULT_TAIL_SILENCE_SECONDS
    DEFAULT_CURSOR_DELAY_SECONDS = 0.0  # legacy alias
    DEFAULT_CURSOR_OFFSET_SECONDS = 0.0

    def __init__(
        self,
        *,
        lead_silence_seconds: float | None = None,
        tail_silence_seconds: float | None = None,
        cursor_delay_seconds: float | None = None,
        cursor_offset_seconds: float | None = None,
        follow_default_device: bool = True,
    ) -> None:
        self.lead_silence_seconds = self._clamp_padding(
            self.DEFAULT_LEAD_SILENCE_SECONDS if lead_silence_seconds is None else lead_silence_seconds
        )
        self.tail_silence_seconds = self._clamp_padding(
            self.DEFAULT_TAIL_SILENCE_SECONDS if tail_silence_seconds is None else tail_silence_seconds
        )
        # Legacy cursor_delay_seconds is intentionally ignored on migration.
        # PortAudio playback no longer needs an artificial positive delay.
        requested_offset = self.DEFAULT_CURSOR_OFFSET_SECONDS if cursor_offset_seconds is None else float(cursor_offset_seconds)
        self.cursor_offset_seconds = max(-0.25, min(0.25, requested_offset))
        self.cursor_delay_seconds = 0.0  # compatibility attribute only
        self._proc: Optional[subprocess.Popen] = None
        self._temp_audio: Optional[Path] = None
        self._win_playing = False
        self._cleanup_timer: Optional[threading.Timer] = None
        self._generation = 0

        self._sink: Optional[_WindowsWaveOutSink] = None
        self._sink_failed = False
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop = threading.Event()
        self._stream_lock = threading.RLock()
        self._state = "stopped"  # stopped | playing | paused
        self._source_start = 0.0
        self._source_end: Optional[float] = None
        self._speed = 1.0
        self._clock_origin: Optional[float] = None
        self._pause_started: Optional[float] = None
        self._pause_accum = 0.0
        self._last_position = 0.0
        self._active_media: Optional[Path] = None
        self._active_ffmpeg: Optional[Path] = None
        self._active_ffplay: Optional[Path] = None
        self._pa_engine: Optional[_PortAudioPCMEngine] = None
        self._portaudio_error: Optional[str] = None
        self._prepare_output_lock = threading.RLock()
        self._closed = False
        self._pcm_cache: Optional[PlaybackPCMCache] = None
        self._pcm_media: Optional[Path] = None
        self._preserve_pitch = True
        self._follow_default_device = bool(follow_default_device)

    @staticmethod
    def _clamp_padding(value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        return max(0.0, min(2.0, value))

    def set_padding(self, *, lead_seconds: float | None = None, tail_seconds: float | None = None) -> None:
        if lead_seconds is not None:
            self.lead_silence_seconds = self._clamp_padding(lead_seconds)
        if tail_seconds is not None:
            self.tail_silence_seconds = self._clamp_padding(tail_seconds)

    def set_cursor_offset(self, seconds: float) -> None:
        self.cursor_offset_seconds = max(-0.25, min(0.25, float(seconds)))
        if self._pa_engine is not None:
            self._pa_engine.set_cursor_offset(self.cursor_offset_seconds)

    def set_cursor_delay(self, seconds: float) -> None:
        # Compatibility shim for code from Updates 025-028.
        self.set_cursor_offset(seconds)

    def set_preserve_pitch(self, enabled: bool) -> None:
        self._preserve_pitch = bool(enabled)

    @property
    def preserve_pitch(self) -> bool:
        return self._preserve_pitch

    @property
    def backend_description(self) -> str:
        if self._pa_engine is not None:
            return self._pa_engine.backend_description
        if self._portaudio_error:
            return f"Fallback ({self._portaudio_error})"
        return "Fallback"

    def set_pcm_cache(self, media: str | Path, cache: PlaybackPCMCache) -> None:
        self._pcm_media = Path(media).resolve()
        self._pcm_cache = cache
        if self.prepare_output() and self._pa_engine is not None:
            self._pa_engine.set_cache(cache)

    def clear_pcm_cache(self) -> None:
        self._pcm_media = None
        self._pcm_cache = None
        if self._pa_engine is not None:
            self._pa_engine.clear_cache()

    def prepare_output(self) -> bool:
        """Open one PortAudio stream ahead of the first user click.

        The previous raw waveOut backend is deliberately no longer selected by
        default: some Windows drivers block the Python/Tk thread around waveOut
        state changes. PortAudio uses an audio callback thread, matching the
        architecture used by editors such as Audacity much more closely.
        """
        with self._prepare_output_lock:
            if self._closed:
                return False
            if self._pa_engine is not None:
                return True
            try:
                engine = _PortAudioPCMEngine(
                    cursor_offset_seconds=self.cursor_offset_seconds,
                    follow_default_device=self._follow_default_device,
                )
                if self._closed:
                    engine.close()
                    return False
                if self._pcm_cache is not None:
                    engine.set_cache(self._pcm_cache)
                self._pa_engine = engine
                self._portaudio_error = None
                return True
            except Exception as exc:
                self._portaudio_error = str(exc)
                self._pa_engine = None
                return False

    @property
    def follow_default_device(self) -> bool:
        return self._follow_default_device

    def set_follow_default_device(self, enabled: bool) -> None:
        self._follow_default_device = bool(enabled)
        if self._pa_engine is not None:
            self._pa_engine.set_follow_default_device(self._follow_default_device)

    def refresh_output_device(self, *, force: bool = True) -> bool:
        """Re-open PortAudio on the current Windows default output endpoint."""
        if not self.prepare_output() or self._pa_engine is None:
            return False
        return self._pa_engine.refresh_default_output_device(force=force)

    @property
    def playing(self) -> bool:
        if self._pa_engine is not None and self._pcm_cache is not None:
            return self._pa_engine.playing
        if self._state == "playing":
            return True
        proc_playing = self._proc is not None and self._proc.poll() is None
        return self._win_playing or proc_playing

    @property
    def paused(self) -> bool:
        if self._pa_engine is not None and self._pcm_cache is not None:
            return self._pa_engine.paused
        return self._state == "paused"

    @property
    def speed(self) -> float:
        return self._speed

    def position(self) -> float:
        if self._pa_engine is not None and self._pcm_cache is not None:
            return self._pa_engine.position()
        with self._stream_lock:
            if self._state == "stopped" or self._clock_origin is None:
                return self._last_position
            now = self._pause_started if self._state == "paused" and self._pause_started is not None else time.monotonic()
            elapsed = max(0.0, now - self._clock_origin - self._pause_accum)
            pos = self._source_start + elapsed * self._speed
            if self._source_end is not None:
                pos = min(pos, self._source_end)
            self._last_position = max(self._source_start, pos)
            return self._last_position

    def _cancel_cleanup_timer(self) -> None:
        timer = self._cleanup_timer
        self._cleanup_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _cleanup_temp_audio(self) -> None:
        path = self._temp_audio
        self._temp_audio = None
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _pad_pcm_wav(path: Path, lead_seconds: float, tail_seconds: float) -> float:
        lead_seconds = max(0.0, float(lead_seconds))
        tail_seconds = max(0.0, float(tail_seconds))
        if lead_seconds <= 0 and tail_seconds <= 0:
            with wave.open(str(path), "rb") as src:
                return src.getnframes() / float(src.getframerate() or 1)
        with wave.open(str(path), "rb") as src:
            nchannels = src.getnchannels(); sampwidth = src.getsampwidth(); framerate = src.getframerate()
            comptype = src.getcomptype(); compname = src.getcompname(); frames = src.readframes(src.getnframes())
        lead_frames = int(round(lead_seconds * framerate)); tail_frames = int(round(tail_seconds * framerate))
        silence_frame = b"\x00" * (nchannels * sampwidth)
        padded = silence_frame * lead_frames + frames + silence_frame * tail_frames
        fd, raw_tmp = tempfile.mkstemp(prefix="karaoke-sps-pad-", suffix=".wav", dir=str(path.parent)); os.close(fd)
        tmp = Path(raw_tmp)
        try:
            with wave.open(str(tmp), "wb") as dst:
                dst.setnchannels(nchannels); dst.setsampwidth(sampwidth); dst.setframerate(framerate)
                dst.setcomptype(comptype, compname); dst.writeframes(padded)
            os.replace(tmp, path)
        finally:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
        return (lead_frames + len(frames) // max(1, nchannels * sampwidth) + tail_frames) / float(framerate or 1)

    def _finish_windows_playback(self, generation: int, path: Path) -> None:
        if generation != self._generation:
            return
        self._win_playing = False
        if self._temp_audio == path:
            self._cleanup_temp_audio()
        self._cleanup_timer = None

    def _stop_stream(self, *, keep_device: bool = True) -> None:
        self._generation += 1
        self._stream_stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate(); proc.wait(timeout=0.4)
            except Exception:
                try: proc.kill()
                except Exception: pass
        self._proc = None
        sink = self._sink
        if sink is not None:
            try: sink.reset()
            except Exception: pass
        thread = self._stream_thread
        self._stream_thread = None
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=0.35)
        self._stream_stop = threading.Event()
        if not keep_device and sink is not None:
            try: sink.close()
            except Exception: pass
            self._sink = None

    def stop(self) -> None:
        if self._pa_engine is not None:
            try: self._pa_engine.stop()
            except Exception: pass
        with self._stream_lock:
            if self._state in {"playing", "paused"}:
                self._last_position = self.position()
            self._state = "stopped"
            self._clock_origin = None
            self._pause_started = None
            self._pause_accum = 0.0
        self._stop_stream(keep_device=True)
        self._cancel_cleanup_timer()
        if self._win_playing and sys.platform.startswith("win"):
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:
                pass
        self._win_playing = False
        self._cleanup_temp_audio()

    def close(self) -> None:
        with self._prepare_output_lock:
            self._closed = True
            self.stop()
            if self._pa_engine is not None:
                try: self._pa_engine.close()
                except Exception: pass
                self._pa_engine = None
            self._stop_stream(keep_device=False)

    def pause(self) -> None:
        if self._pa_engine is not None and self._pcm_cache is not None:
            self._pa_engine.pause(); return
        with self._stream_lock:
            if self._state != "playing":
                return
            self._last_position = self.position()
            self._state = "paused"
            self._pause_started = time.monotonic()
        if self._sink is not None:
            try: self._sink.pause()
            except Exception: pass

    def resume(self) -> None:
        if self._pa_engine is not None and self._pcm_cache is not None:
            self._pa_engine.resume(); return
        with self._stream_lock:
            if self._state != "paused":
                return
            now = time.monotonic()
            if self._pause_started is not None:
                self._pause_accum += now - self._pause_started
            self._pause_started = None
            self._state = "playing"
        if self._sink is not None:
            try: self._sink.resume()
            except Exception: pass

    def toggle_pause(self) -> bool:
        if self._state == "paused":
            self.resume(); return False
        if self._state == "playing":
            self.pause(); return True
        return False

    def _ffmpeg_stream_cmd(
        self, media: Path, start: float, end: Optional[float], ffmpeg: Path, speed: float
    ) -> list[str]:
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-ss", f"{start:.6f}", "-i", str(media),
            "-map", "0:a:0", "-vn", "-sn", "-dn",
        ]
        filters = _atempo_chain(speed)
        if filters:
            cmd += ["-af", filters]
        if end is not None:
            # -t is output duration, so compensate for atempo.
            cmd += ["-t", f"{max(0.001, (end - start) / speed):.6f}"]
        cmd += ["-ac", "2", "-ar", "48000", "-f", "s16le", "pipe:1"]
        return cmd

    def _stream_worker(self, generation: int, proc: subprocess.Popen, sink: _WindowsWaveOutSink) -> None:
        first = True
        try:
            stdout = proc.stdout
            if stdout is None:
                return
            while generation == self._generation and not self._stream_stop.is_set():
                data = stdout.read(sink.chunk_bytes)
                if not data:
                    break
                if not sink.write(data, self._stream_stop):
                    break
                if first:
                    first = False
                    with self._stream_lock:
                        if generation == self._generation:
                            self._clock_origin = time.monotonic()
                            self._pause_accum = 0.0
                            self._pause_started = None
            if generation == self._generation and not self._stream_stop.is_set():
                sink.drain(self._stream_stop)
        except Exception:
            pass
        finally:
            if generation == self._generation:
                with self._stream_lock:
                    if self._source_end is not None:
                        self._last_position = self._source_end
                    else:
                        self._last_position = self.position()
                    self._state = "stopped"
                    self._clock_origin = None
                try:
                    if proc.poll() is None: proc.terminate()
                except Exception: pass

    def _start_stream(
        self,
        media: Path,
        start: float,
        end: Optional[float],
        *,
        ffmpeg: Path,
        ffplay: Optional[Path],
        speed: float,
    ) -> bool:
        if not self.prepare_output() or self._sink is None:
            return False
        self._stop_stream(keep_device=True)
        self._generation += 1
        generation = self._generation
        self._stream_stop.clear()
        try:
            self._sink.reset()
        except Exception:
            return False
        cmd = self._ffmpeg_stream_cmd(media, start, end, ffmpeg, speed)
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "bufsize": 0,
            "env": media_tool_subprocess_env(ffmpeg),
        }
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception:
            return False
        self._proc = proc
        with self._stream_lock:
            self._state = "playing"
            self._source_start = start
            self._source_end = end
            self._speed = speed
            self._last_position = start
            self._clock_origin = None  # starts only when first PCM reaches waveOut
            self._pause_started = None
            self._pause_accum = 0.0
            self._active_media = media
            self._active_ffmpeg = ffmpeg
            self._active_ffplay = ffplay
        thread = threading.Thread(target=self._stream_worker, args=(generation, proc, self._sink), daemon=True)
        self._stream_thread = thread
        thread.start()
        return True

    def _play_windows_native(self, temp_audio: Path, padded_duration: float) -> bool:
        if not sys.platform.startswith("win"):
            return False
        try:
            import winsound
            flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            winsound.PlaySound(str(temp_audio), flags)
        except Exception:
            return False
        self._win_playing = True
        generation = self._generation
        timer = threading.Timer(max(0.25, padded_duration + 0.75), self._finish_windows_playback, args=(generation, temp_audio))
        timer.daemon = True; self._cleanup_timer = timer; timer.start()
        return True

    def _legacy_play(
        self,
        media: Path,
        start: float,
        end: float,
        *,
        ffplay: Path,
        ffmpeg: Path,
    ) -> None:
        """Compatibility fallback used only when persistent waveOut is unavailable."""
        duration = end - start
        fd, raw_path = tempfile.mkstemp(prefix="karaoke-sps-play-", suffix=".wav"); os.close(fd)
        temp_audio = Path(raw_path); self._temp_audio = temp_audio
        extract_cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-ss", f"{start:.6f}", "-i", str(media), "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-t", f"{duration:.6f}", "-af", "asetpts=PTS-STARTPTS", "-ac", "2", "-ar", "48000",
            "-c:a", "pcm_s16le", str(temp_audio),
        ]
        run_kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE,
                      "text": True, "env": media_tool_subprocess_env(ffmpeg)}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(extract_cmd, **run_kwargs)
        if result.returncode != 0 or not temp_audio.is_file() or temp_audio.stat().st_size <= 44:
            detail = (result.stderr or "").strip(); self._cleanup_temp_audio()
            raise RuntimeError(f"FFmpeg не смог подготовить фрагмент для воспроизведения:\n{detail}" if detail else "FFmpeg не смог подготовить фрагмент для воспроизведения")
        padded_duration = self._pad_pcm_wav(temp_audio, self.lead_silence_seconds, self.tail_silence_seconds)
        if self._play_windows_native(temp_audio, padded_duration):
            return
        play_cmd = [str(ffplay), "-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit", "-vn", str(temp_audio)]
        popen_kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE,
                        "env": media_tool_subprocess_env(ffplay)}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self._proc = subprocess.Popen(play_cmd, **popen_kwargs)

    def play(
        self,
        media: str | Path,
        start: float,
        end: float,
        *,
        ffplay: str | Path | None = None,
        ffmpeg: str | Path | None = None,
        speed: float = 1.0,
    ) -> None:
        """Play only the requested selection using the persistent engine when possible."""
        self.stop()
        media_path = Path(media).resolve()
        if ffmpeg is None:
            if ffplay is None:
                raise FileNotFoundError("ffmpeg не указан")
            fp = Path(ffplay).resolve()
            ffmpeg_path = fp.with_name("ffmpeg.exe" if fp.suffix.lower() == ".exe" else "ffmpeg")
        else:
            ffmpeg_path = Path(ffmpeg).resolve()
        if not ffmpeg_path.is_file():
            raise FileNotFoundError(f"ffmpeg не найден: {ffmpeg_path}")
        ffplay_path = Path(ffplay).resolve() if ffplay is not None else None
        start = max(0.0, float(start)); end = max(start + 0.001, float(end)); speed = normalize_playback_speed(speed)
        if self._pcm_cache is not None and self._pcm_media == media_path and self.prepare_output() and self._pa_engine is not None:
            if self._follow_default_device:
                try: self._pa_engine.refresh_default_output_device(force=False)
                except Exception: pass
            self._active_media = media_path; self._active_ffmpeg = ffmpeg_path; self._active_ffplay = ffplay_path; self._speed = speed
            self._pa_engine.play(start, end, speed=speed, preserve_pitch=self._preserve_pitch, ffmpeg=ffmpeg_path)
            return
        if self._start_stream(media_path, start, end, ffmpeg=ffmpeg_path, ffplay=ffplay_path, speed=speed):
            return
        if ffplay_path is None or not ffplay_path.is_file():
            raise RuntimeError("Низколатентный Windows playback недоступен, а ffplay.exe для fallback не найден")
        self._legacy_play(media_path, start, end, ffplay=ffplay_path, ffmpeg=ffmpeg_path)

    def play_continuous(
        self,
        media: str | Path,
        start: float,
        *,
        ffmpeg: str | Path,
        ffplay: str | Path | None = None,
        speed: float = 1.0,
    ) -> None:
        """Play from ``start`` until EOF without stopping at syllable boundaries."""
        self.stop()
        media_path = Path(media).resolve(); ffmpeg_path = Path(ffmpeg).resolve()
        ffplay_path = Path(ffplay).resolve() if ffplay is not None else None
        start = max(0.0, float(start)); speed = normalize_playback_speed(speed)
        if self._pcm_cache is not None and self._pcm_media == media_path and self.prepare_output() and self._pa_engine is not None:
            if self._follow_default_device:
                try: self._pa_engine.refresh_default_output_device(force=False)
                except Exception: pass
            self._active_media = media_path; self._active_ffmpeg = ffmpeg_path; self._active_ffplay = ffplay_path; self._speed = speed
            self._pa_engine.play(start, None, speed=speed, preserve_pitch=self._preserve_pitch, ffmpeg=ffmpeg_path)
            return
        if self._start_stream(media_path, start, None, ffmpeg=ffmpeg_path, ffplay=ffplay_path, speed=speed):
            return
        if ffplay_path is None or not ffplay_path.is_file():
            raise RuntimeError("Низколатентный Windows playback недоступен, а ffplay.exe не найден")
        filters = _atempo_chain(speed)
        cmd = [str(ffplay_path), "-hide_banner", "-loglevel", "error", "-nodisp", "-autoexit", "-ss", f"{start:.6f}"]
        if filters: cmd += ["-af", filters]
        cmd += [str(media_path)]
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE,
                  "env": media_tool_subprocess_env(ffplay_path)}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self._proc = subprocess.Popen(cmd, **kwargs)
        with self._stream_lock:
            self._state = "playing"; self._source_start = start; self._source_end = None; self._speed = speed
            self._last_position = start; self._clock_origin = time.monotonic(); self._pause_accum = 0.0
            self._active_media = media_path; self._active_ffmpeg = ffmpeg_path; self._active_ffplay = ffplay_path

    def set_speed(self, speed: float) -> None:
        """Apply a new speed. Active playback restarts at the current media position."""
        speed = normalize_playback_speed(speed)
        if self._pa_engine is not None and self._pcm_cache is not None and self._active_ffmpeg is not None:
            self._pa_engine.set_speed(speed, preserve_pitch=self._preserve_pitch, ffmpeg=self._active_ffmpeg)
            self._speed = speed
            return
        if abs(speed - self._speed) < 1e-6:
            return
        state = self._state
        pos = self.position()
        end = self._source_end
        media = self._active_media; ffmpeg = self._active_ffmpeg; ffplay = self._active_ffplay
        self._speed = speed
        if state not in {"playing", "paused"} or media is None or ffmpeg is None:
            return
        if end is None:
            self.play_continuous(media, pos, ffmpeg=ffmpeg, ffplay=ffplay, speed=speed)
        else:
            self.play(media, pos, end, ffmpeg=ffmpeg, ffplay=ffplay, speed=speed)
        if state == "paused":
            self.pause()
