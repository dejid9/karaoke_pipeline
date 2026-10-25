from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
import json
import math
import os
import subprocess
import tempfile
import zlib
from typing import Callable, Optional

from .media import media_tool_subprocess_env


ProgressCallback = Callable[[Optional[float], str], None]
LogCallback = Callable[[str], None]


def _emit_progress(callback: Optional[ProgressCallback], value: Optional[float], stage: str) -> None:
    if callback is not None:
        callback(value, stage)


def _emit_log(callback: Optional[LogCallback], message: str) -> None:
    if callback is not None:
        callback(message)


_CACHE_MAGIC = b"SPG1\n"
_QUANT_DB_MIN = -120.0
_QUANT_DB_MAX = 0.0


@dataclass(slots=True, frozen=True)
class SpectrogramAnalysisSettings:
    sample_rate: int = 22050
    fft_size: int = 1024
    overlap: float = 0.75
    window: str = "hann"

    @property
    def hop_size(self) -> int:
        return max(1, int(round(self.fft_size * (1.0 - self.overlap))))

    def validate(self) -> None:
        if self.sample_rate < 4000:
            raise ValueError("sample_rate must be at least 4000 Hz")
        if self.fft_size < 64 or self.fft_size > 16384 or self.fft_size & (self.fft_size - 1):
            raise ValueError("fft_size must be a power of two from 64 to 16384")
        if not (0.0 <= self.overlap < 0.98):
            raise ValueError("overlap must be in [0, 0.98)")
        if self.window not in {"hann", "hamming", "blackman", "rect"}:
            raise ValueError(f"unsupported window: {self.window}")


@dataclass(slots=True, frozen=True)
class SpectrogramViewSettings:
    min_frequency: float = 80.0
    max_frequency: float = 7000.0
    db_floor: float = -72.0
    db_ceiling: float = -8.0
    frequency_scale: str = "linear"

    def validate(self, nyquist: Optional[float] = None) -> None:
        if self.min_frequency < 0:
            raise ValueError("min_frequency cannot be negative")
        if self.max_frequency <= self.min_frequency:
            raise ValueError("max_frequency must be above min_frequency")
        if nyquist is not None and self.min_frequency >= nyquist:
            raise ValueError("min_frequency is above Nyquist")
        if self.db_ceiling <= self.db_floor:
            raise ValueError("db_ceiling must be above db_floor")
        if self.frequency_scale not in {"linear", "log"}:
            raise ValueError("frequency_scale must be linear or log")


VOICE_PRESETS = {
    "Низкий голос": (50.0, 5000.0),
    "Средний голос": (80.0, 7000.0),
    "Высокий голос": (120.0, 10000.0),
    "Полный диапазон": (20.0, 11000.0),
}

# The faster the expected articulation, the shorter the analysis window. 75%
# overlap keeps boundary motion smooth without exploding cache size.
SPEED_PRESETS = {
    "Медленно (≤6 SPS)": 2048,
    "Средне (6–12 SPS)": 1024,
    "Быстро (12–20 SPS)": 512,
    "Очень быстро (>20 SPS)": 256,
}


_COLOUR_STOPS = (
    (0.00, (8, 10, 18)),
    (0.20, (25, 38, 78)),
    (0.43, (73, 48, 126)),
    (0.68, (178, 78, 82)),
    (0.86, (235, 155, 72)),
    (1.00, (255, 238, 184)),
)


def _colour_lut(np):
    """Small fixed lookup table used by viewport rendering.

    Building the full RGB image through six boolean masks on every wheel event
    was surprisingly expensive. A 256-entry LUT keeps the colour mapping
    deterministic while moving almost all work into NumPy indexing.
    """
    positions = np.asarray([p for p, _ in _COLOUR_STOPS], dtype=np.float32)
    colours = np.asarray([c for _, c in _COLOUR_STOPS], dtype=np.float32)
    x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    lut = np.empty((256, 3), dtype=np.uint8)
    for channel in range(3):
        lut[:, channel] = np.rint(np.interp(x, positions, colours[:, channel])).astype(np.uint8)
    return lut


def fft_size_for_expected_sps(sps: float) -> int:
    sps = max(0.0, float(sps))
    if sps <= 6:
        return 2048
    if sps <= 12:
        return 1024
    if sps <= 20:
        return 512
    return 256


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on user environment
        raise RuntimeError("Для спектрограммы требуется NumPy (pip install numpy)") from exc
    return np


@dataclass(slots=True, frozen=True)
class SpectrogramData:
    sample_rate: int
    fft_size: int
    hop_size: int
    window: str
    frame_count: int
    frequency_bins: int
    duration: float
    quantized_db: bytes  # time-major uint8, -120..0 dB relative to track peak
    _lod_cache: dict[int, object] = field(default_factory=dict, compare=False, repr=False)

    def _matrix_for_lod(self, np, factor: int):
        factor = max(1, int(factor))
        cached = self._lod_cache.get(factor)
        if cached is not None:
            return cached
        base = np.frombuffer(self.quantized_db, dtype=np.uint8).reshape(self.frame_count, self.frequency_bins)
        if factor == 1 or self.frame_count <= 1:
            matrix = base
        else:
            full = (self.frame_count // factor) * factor
            parts = []
            if full:
                parts.append(base[:full].reshape(-1, factor, self.frequency_bins).max(axis=1))
            if full < self.frame_count:
                parts.append(base[full:].max(axis=0, keepdims=True))
            matrix = np.concatenate(parts, axis=0) if len(parts) > 1 else parts[0]
        # Keep only a few useful levels. The cache is mutable by design even on
        # this frozen value object; it is derived display data and is never saved.
        self._lod_cache[factor] = matrix
        if len(self._lod_cache) > 4:
            for key in tuple(self._lod_cache):
                if key not in {1, factor} and len(self._lod_cache) > 4:
                    self._lod_cache.pop(key, None)
        return matrix

    @property
    def nyquist(self) -> float:
        return self.sample_rate / 2.0

    @property
    def seconds_per_frame(self) -> float:
        return self.hop_size / self.sample_rate

    @property
    def frequency_step(self) -> float:
        return self.sample_rate / self.fft_size

    def render_rgb(
        self,
        start: float,
        end: float,
        width: int,
        height: int,
        view: SpectrogramViewSettings,
    ) -> bytes:
        """Return a smoothly resampled RGB viewport.

        When zoomed out, time bins are max-pooled so short consonants and
        transients remain visible. When zoomed in, both the time and frequency
        axes are linearly interpolated instead of repeating whole FFT cells.
        The old nearest-neighbour path was the reason a magnified spectrogram
        looked visibly chopped into rectangular blocks.
        """
        np = _numpy()
        width, height = max(1, int(width)), max(1, int(height))
        view.validate(self.nyquist)
        if self.frame_count <= 0 or not self.quantized_db or end <= start:
            return bytes(width * height * 3)

        # Pick a power-of-two time LOD before slicing. Very high-overlap FFT
        # settings can otherwise force every pan event to scan tens of thousands
        # of full-resolution frames even though the screen is only ~1000 px wide.
        raw_visible_frames = max(1.0, (end - start) / self.seconds_per_frame)
        raw_per_pixel = raw_visible_frames / max(1, width)
        lod_factor = 1
        while lod_factor * 2 <= raw_per_pixel:
            lod_factor *= 2
        matrix = self._matrix_for_lod(np, lod_factor)
        seconds_per_lod = self.seconds_per_frame * lod_factor
        first = max(0, int(math.floor(start / seconds_per_lod)))
        last = min(matrix.shape[0], int(math.ceil(end / seconds_per_lod)) + 1)
        if last <= first:
            last = min(matrix.shape[0], first + 1)
        visible = matrix[first:last]

        # Time LOD. Compression is peak-preserving; magnification is smooth.
        n = visible.shape[0]
        if n > width:
            starts = np.linspace(0, n, width + 1, dtype=np.int64)[:-1]
            # n > width guarantees monotonically increasing starts. reduceat is
            # much faster than running one Python max() loop per screen column.
            time_resampled = np.maximum.reduceat(visible, starts, axis=0).astype(np.float32)
        elif n == 1:
            time_resampled = np.repeat(visible.astype(np.float32), width, axis=0)
        else:
            pos = np.linspace(0.0, n - 1.0, width, dtype=np.float32)
            left = np.floor(pos).astype(np.int64)
            right = np.minimum(left + 1, n - 1)
            alpha = (pos - left).astype(np.float32)[:, None]
            time_resampled = visible[left].astype(np.float32) * (1.0 - alpha) + visible[right].astype(np.float32) * alpha

        lo = max(0.0, view.min_frequency)
        hi = min(self.nyquist, view.max_frequency)
        if view.frequency_scale == "log":
            lo_for_log = max(lo, max(self.frequency_step, 1.0))
            frequencies = np.geomspace(lo_for_log, max(lo_for_log + 1e-6, hi), height).astype(np.float32)
        else:
            frequencies = np.linspace(lo, hi, height, dtype=np.float32)

        # Frequency interpolation removes horizontal FFT-bin stair steps when
        # the user zooms the display or chooses a narrow voice range.
        fpos = np.clip(frequencies / self.frequency_step, 0.0, self.frequency_bins - 1.0)
        flo = np.floor(fpos).astype(np.int64)
        fhi = np.minimum(flo + 1, self.frequency_bins - 1)
        falpha = (fpos - flo).astype(np.float32)[None, :]
        sampled = time_resampled[:, flo] * (1.0 - falpha) + time_resampled[:, fhi] * falpha

        # y=0 is high frequency.
        q = sampled.T[::-1]
        db = _QUANT_DB_MIN + q * ((_QUANT_DB_MAX - _QUANT_DB_MIN) / 255.0)
        norm = np.clip((db - view.db_floor) / (view.db_ceiling - view.db_floor), 0.0, 1.0)
        indices = np.rint(norm * 255.0).astype(np.uint8)
        rgb = _colour_lut(np)[indices]
        return rgb.tobytes()

    def render_ppm(self, start: float, end: float, width: int, height: int, view: SpectrogramViewSettings) -> bytes:
        width, height = max(1, int(width)), max(1, int(height))
        return f"P6\n{width} {height}\n255\n".encode("ascii") + self.render_rgb(start, end, width, height, view)


def spectrogram_cache_path(
    media: str | Path,
    cache_root: Optional[str | Path],
    settings: SpectrogramAnalysisSettings,
) -> Path:
    settings.validate()
    media = Path(media).resolve()
    stat = media.stat()
    token = (
        f"{media}|{stat.st_size}|{stat.st_mtime_ns}|{settings.sample_rate}|"
        f"{settings.fft_size}|{settings.hop_size}|{settings.window}"
    ).encode("utf-8", "surrogatepass")
    digest = sha1(token).hexdigest()[:20]
    root = Path(cache_root) if cache_root is not None else Path(tempfile.gettempdir()) / "karaoke_sps_spectrograms"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{media.stem}-{digest}.spg"


def save_spectrogram(path: str | Path, data: SpectrogramData) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "sample_rate": data.sample_rate,
        "fft_size": data.fft_size,
        "hop_size": data.hop_size,
        "window": data.window,
        "frame_count": data.frame_count,
        "frequency_bins": data.frequency_bins,
        "duration": data.duration,
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload = _CACHE_MAGIC + str(len(encoded)).encode("ascii") + b"\n" + encoded + zlib.compress(data.quantized_db, level=6)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
    return path


def load_spectrogram(path: str | Path) -> SpectrogramData:
    raw = Path(path).read_bytes()
    if not raw.startswith(_CACHE_MAGIC):
        raise ValueError("Unsupported spectrogram cache format")
    rest = raw[len(_CACHE_MAGIC):]
    length_line, rest = rest.split(b"\n", 1)
    header_len = int(length_line)
    header = json.loads(rest[:header_len].decode("utf-8"))
    pixels = zlib.decompress(rest[header_len:])
    expected = int(header["frame_count"]) * int(header["frequency_bins"])
    if len(pixels) != expected:
        raise ValueError("Spectrogram cache size mismatch")
    return SpectrogramData(
        sample_rate=int(header["sample_rate"]),
        fft_size=int(header["fft_size"]),
        hop_size=int(header["hop_size"]),
        window=str(header["window"]),
        frame_count=int(header["frame_count"]),
        frequency_bins=int(header["frequency_bins"]),
        duration=float(header["duration"]),
        quantized_db=pixels,
    )


def _window_values(np, name: str, size: int):
    if name == "hann":
        return np.hanning(size).astype(np.float32)
    if name == "hamming":
        return np.hamming(size).astype(np.float32)
    if name == "blackman":
        return np.blackman(size).astype(np.float32)
    if name == "rect":
        return np.ones(size, dtype=np.float32)
    raise ValueError(name)


def extract_spectrogram(
    media: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    settings: SpectrogramAnalysisSettings = SpectrogramAnalysisSettings(),
    cache_path: Optional[str | Path] = None,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> SpectrogramData:
    settings.validate()
    np = _numpy()
    media = Path(media).resolve()
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(media),
        "-vn", "-ac", "1", "-ar", str(settings.sample_rate), "-f", "f32le", "pipe:1",
    ]
    _emit_progress(progress, 5.0, "Подготовка FFmpeg")
    _emit_log(log, "> " + " ".join(f'"{x}"' if " " in x else x for x in cmd))
    _emit_progress(progress, 10.0, "Декодирование аудио")
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=media_tool_subprocess_env(ffmpeg))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or f"ffmpeg exited with code {proc.returncode}")
    _emit_progress(progress, 35.0, "Аудио декодировано")
    samples = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float32, copy=False)
    duration = len(samples) / settings.sample_rate if settings.sample_rate else 0.0
    n_fft = settings.fft_size
    hop = settings.hop_size
    if len(samples) < n_fft:
        samples = np.pad(samples, (0, n_fft - len(samples)))
    frame_count = 1 + max(0, (len(samples) - n_fft) // hop)
    freq_bins = n_fft // 2 + 1
    window = _window_values(np, settings.window, n_fft)

    # Two passes avoid holding a full floating-point spectrogram in RAM.
    batch = 2048
    global_peak = 1e-12
    _emit_progress(progress, 38.0, "FFT: поиск максимума")
    for first in range(0, frame_count, batch):
        count = min(batch, frame_count - first)
        _emit_progress(progress, 38.0 + 27.0 * (first / max(1, frame_count)), "FFT: анализ амплитуд")
        starts = (first + np.arange(count, dtype=np.int64)) * hop
        frames = np.stack([samples[s:s + n_fft] for s in starts])
        magnitudes = np.abs(np.fft.rfft(frames * window, axis=1))
        local = float(magnitudes.max(initial=0.0))
        if local > global_peak:
            global_peak = local

    quantized = bytearray(frame_count * freq_bins)
    scale = 255.0 / (_QUANT_DB_MAX - _QUANT_DB_MIN)
    _emit_progress(progress, 66.0, "FFT: квантование dB")
    for first in range(0, frame_count, batch):
        count = min(batch, frame_count - first)
        _emit_progress(progress, 66.0 + 28.0 * (first / max(1, frame_count)), "FFT: формирование спектрограммы")
        starts = (first + np.arange(count, dtype=np.int64)) * hop
        frames = np.stack([samples[s:s + n_fft] for s in starts])
        magnitudes = np.abs(np.fft.rfft(frames * window, axis=1))
        db = 20.0 * np.log10(np.maximum(magnitudes, global_peak * 1e-12) / global_peak)
        q = np.clip(np.rint((db - _QUANT_DB_MIN) * scale), 0, 255).astype(np.uint8)
        start_byte = first * freq_bins
        quantized[start_byte:start_byte + q.size] = q.tobytes()

    data = SpectrogramData(
        sample_rate=settings.sample_rate,
        fft_size=n_fft,
        hop_size=hop,
        window=settings.window,
        frame_count=frame_count,
        frequency_bins=freq_bins,
        duration=duration,
        quantized_db=bytes(quantized),
    )
    if cache_path is not None:
        _emit_progress(progress, 96.0, "Сохранение кэша")
        save_spectrogram(cache_path, data)
    _emit_progress(progress, 100.0, "Спектрограмма готова")
    return data


def load_or_extract_spectrogram(
    media: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    cache_root: Optional[str | Path] = None,
    settings: SpectrogramAnalysisSettings = SpectrogramAnalysisSettings(),
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> tuple[SpectrogramData, Path, bool]:
    cache = spectrogram_cache_path(media, cache_root, settings)
    if cache.exists():
        try:
            _emit_progress(progress, 10.0, "Чтение spectrogram-кэша")
            data = load_spectrogram(cache)
            _emit_progress(progress, 100.0, "Спектрограмма загружена из кэша")
            _emit_log(log, f"Spectrogram cache: {cache}")
            return data, cache, True
        except Exception as exc:
            _emit_log(log, f"Повреждённый spectrogram cache будет перестроен: {exc}")
            cache.unlink(missing_ok=True)
    data = extract_spectrogram(media, ffmpeg=ffmpeg, settings=settings, cache_path=cache, progress=progress, log=log)
    return data, cache, False
