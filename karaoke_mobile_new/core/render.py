from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import colorsys
import math
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
from typing import Callable, Iterable, Mapping, Optional

from .ass import (
    AssDocument, AssEvent, KaraokeSyllable, _OVERRIDE_RE, format_ass_time, parse_ass_time,
    unspoken_spans,
)
from .media import (
    MediaTimeBounds,
    media_tool_subprocess_env,
    probe_audio_bounds,
    probe_media_duration,
    resolve_ffprobe,
)



ProgressCallback = Callable[[Optional[float], str], None]
LogCallback = Callable[[str], None]


def _display_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if any(ch.isspace() for ch in part) else part for part in command)


def _parse_hms(value: str) -> Optional[float]:
    try:
        hh, mm, ss = value.strip().split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except (ValueError, TypeError):
        return None


def _run_ffmpeg_progress(
    command: list[str],
    *,
    cwd: str | Path | None = None,
    duration: Optional[float] = None,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
    stage: str = "FFmpeg render",
    cancel_event: Optional[threading.Event] = None,
) -> None:
    # FFmpeg's machine-readable progress protocol gives us reliable progress
    # without parsing localized human status lines. It writes key=value pairs
    # to stderr here, mixed with errors only when something actually fails.
    cmd = list(command)
    insert_at = max(1, len(cmd) - 1)
    cmd[insert_at:insert_at] = ["-progress", "pipe:2", "-nostats"]
    if log:
        log("> " + _display_command(cmd))
    if progress:
        progress(1.0, stage + ": запуск")
    popen_kwargs = dict(
        cwd=str(cwd) if cwd is not None else None,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        env=media_tool_subprocess_env(cmd[0]),
    )
    if os.name == "nt":
        # A 2x render processes four times as many pixels.  FFmpeg otherwise
        # runs at normal priority and can starve Tk's paint/window-management
        # thread on Windows even though the render itself is already on a
        # worker thread.  Below-normal priority preserves encoding quality and
        # only yields CPU time while the user is interacting with the app.
        below_normal = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        if below_normal:
            popen_kwargs["creationflags"] = below_normal
    proc = subprocess.Popen(cmd, **popen_kwargs)
    assert proc.stderr is not None

    def _cancel_watcher():
        if cancel_event is None:
            return
        while proc.poll() is None:
            if cancel_event.wait(timeout=0.2):
                break
        if cancel_event.is_set() and proc.poll() is None:
            if log:
                log("Получен сигнал отмены. Отправляю 'q' в FFmpeg...")
            try:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.write("q\n")
                    proc.stdin.flush()
            except Exception:
                pass
            for _ in range(30):
                if proc.poll() is not None:
                    return
                time.sleep(0.1)
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    watcher = None
    if cancel_event is not None:
        watcher = threading.Thread(target=_cancel_watcher, daemon=True)
        watcher.start()

    errors: list[str] = []
    last_pct = -1.0
    for raw in proc.stderr:
        line = raw.strip()
        if not line:
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            if key == "out_time":
                current = _parse_hms(value)
                if duration and duration > 0 and current is not None:
                    pct = max(1.0, min(99.0, current / duration * 100.0))
                    if pct - last_pct >= 0.25:
                        last_pct = pct
                        if progress:
                            progress(pct, stage)
            elif key == "progress" and value == "end":
                if progress:
                    progress(100.0, stage + ": завершение")
            # frame/fps/speed are intentionally not copied to the permanent log
            # every update; that would generate thousands of nearly identical lines.
            continue
        errors.append(line)
        if log:
            log(line)
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except Exception:
        pass
    proc.stderr.close()
    rc = proc.wait()
    if watcher is not None:
        watcher.join(timeout=1.0)
    if cancel_event is not None and cancel_event.is_set():
        if log:
            log("Рендер остановлен пользователем (сигнал 'q').")
        raise RuntimeError("Рендер отменён пользователем")
    if rc != 0:
        detail = "\n".join(errors[-50:]).strip()
        raise RuntimeError(detail or f"ffmpeg exited with {rc}")
    if progress:
        progress(100.0, stage + ": готово")

_PLAYRES_X_RE = re.compile(r"^\s*PlayResX\s*:\s*(\d+)\s*$", re.IGNORECASE)
_PLAYRES_Y_RE = re.compile(r"^\s*PlayResY\s*:\s*(\d+)\s*$", re.IGNORECASE)
_DYNAMIC_GEOMETRY_RE = re.compile(r"\\(?:move|t)\s*\(", re.IGNORECASE)
_LINE_BREAK_RE = re.compile(r"\\[Nn]")
_EXISTING_LINE_SHIFT_RE = re.compile(
    r"^\{[^{}]*(?:\\org\s*\([^)]*\))[^{}]*\\fr(?:z)?[-+]?\d", re.IGNORECASE
)


@dataclass(slots=True, frozen=True)
class RenderLayoutSettings:
    max_words_per_line: int = 0
    max_chars_per_line: int = 0
    remove_original_line_breaks: bool = False
    line_spacing_px: float = 20.0
    use_far_origin_spacing: bool = True
    far_origin_x: float = -2_000_000.0
    padding_left: int = 24
    padding_right: int = 24
    padding_top: int = 24
    padding_bottom: int = 24
    even_dimensions: bool = True
    enable_romanization: bool = True
    romanization_size_percent: float = 55.0
    romanization_offset_y: int = 0
    text_case: str = "as_is"
    romanization_case: str = "as_is"
    burst_color_mode: str = "single"
    burst_base_color: str = "&H0000FF&"
    burst_alt_color: str = "&H0080FF&"
    burst_hue_offset: float = 30.0
    burst_pulse_hz: float = 2.0

    def validate(self) -> "RenderLayoutSettings":
        if self.max_words_per_line < 0:
            raise ValueError("max_words_per_line must be >= 0")
        if self.max_chars_per_line < 0:
            raise ValueError("max_chars_per_line must be >= 0")
        if not -500.0 <= self.line_spacing_px <= 500.0:
            raise ValueError("line_spacing_px must be between -500 and 500")
        if self.far_origin_x > -1000:
            raise ValueError("far_origin_x should be far outside the frame (for example -2000000)")
        for name in ("padding_left", "padding_right", "padding_top", "padding_bottom"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        if self.enable_romanization:
            if not 0.0 <= float(self.romanization_size_percent) <= 300.0:
                raise ValueError("romanization_size_percent must be between 0 and 300")
            if not -1000 <= int(self.romanization_offset_y) <= 1000:
                raise ValueError("romanization_offset_y must be between -1000 and 1000")
        valid_cases = {"as_is", "upper", "lower", "sentence"}
        if self.text_case not in valid_cases:
            raise ValueError(f"text_case must be one of {valid_cases}, got {self.text_case!r}")
        if self.romanization_case not in valid_cases:
            raise ValueError(f"romanization_case must be one of {valid_cases}, got {self.romanization_case!r}")
        if self.burst_color_mode not in {"single", "alternate", "gradient", "dynamic"}:
            raise ValueError(f"burst_color_mode must be one of 'single', 'alternate', 'gradient', 'dynamic', got {self.burst_color_mode!r}")
        if not -360.0 <= float(self.burst_hue_offset) <= 360.0:
            raise ValueError("burst_hue_offset must be between -360 and 360")
        if not 0.05 <= float(self.burst_pulse_hz) <= 50.0:
            raise ValueError("burst_pulse_hz must be between 0.05 and 50.0")
        return self


class CaseState:
    __slots__ = ("capitalize_next",)

    def __init__(self, capitalize_next: bool = True) -> None:
        self.capitalize_next = capitalize_next


def apply_text_case(text: str, mode: str, state: Optional[CaseState] = None) -> str:
    """Transform visible text casing while strictly preserving ASS override tags and escapes."""
    if not text or not mode or mode == "as_is":
        return text
    mode = mode.lower()
    if mode not in {"upper", "lower", "sentence"}:
        return text

    pattern = re.compile(r"(\{[^{}]*\}|\\[Nnh])")
    tokens = pattern.split(text)

    if mode == "upper":
        return "".join(
            t if (t.startswith("{") and t.endswith("}")) or t in (r"\N", r"\n", r"\h")
            else t.upper()
            for t in tokens
        )
    if mode == "lower":
        return "".join(
            t if (t.startswith("{") and t.endswith("}")) or t in (r"\N", r"\n", r"\h")
            else t.lower()
            for t in tokens
        )

    # sentence mode: capitalize start of sentence and after \N / \n
    if state is None:
        state = CaseState(capitalize_next=True)
    out: list[str] = []
    for t in tokens:
        if t.startswith("{") and t.endswith("}"):
            out.append(t)
        elif t in (r"\N", r"\n"):
            out.append(t)
            state.capitalize_next = True
        elif t == r"\h":
            out.append(t)
        else:
            t_chars: list[str] = []
            for i, ch in enumerate(t):
                if ch.isalpha():
                    if state.capitalize_next:
                        t_chars.append(ch.upper())
                        state.capitalize_next = False
                    else:
                        t_chars.append(ch.lower())
                else:
                    t_chars.append(ch)
                    if ch in (".", "!", "?", "…"):
                        if ch == "." and i > 0 and i + 1 < len(t) and t[i - 1].isdigit() and t[i + 1].isdigit():
                            continue
                        state.capitalize_next = True
            out.append("".join(t_chars))
    return "".join(out)


@dataclass(slots=True, frozen=True)
class CropRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def clamp(self, canvas_width: int, canvas_height: int) -> "CropRect":
        width = max(1, min(int(self.width), int(canvas_width)))
        height = max(1, min(int(self.height), int(canvas_height)))
        x = max(0, min(int(self.x), int(canvas_width) - width))
        y = max(0, min(int(self.y), int(canvas_height) - height))
        return CropRect(x, y, width, height)


@dataclass(slots=True, frozen=True)
class RenderMeasurement:
    playres_x: int
    playres_y: int
    content_bbox: CropRect
    crop: CropRect
    rgba: bytes
    dynamic_geometry: bool = False
    source_playres_x: int = 0
    source_playres_y: int = 0
    line_count: int = 1


@dataclass(slots=True, frozen=True)
class RenderOutputSettings:
    fps: float = 60.0
    profile: str = "transparent_mov"
    resolution_scale: float = 2.0

    def validate(self) -> "RenderOutputSettings":
        if self.fps <= 0 or self.fps > 240:
            raise ValueError("fps must be > 0 and <= 240")
        if self.profile not in {"transparent_mov", "black_mp4"}:
            raise ValueError(f"Unknown render profile: {self.profile}")
        if not 1.0 <= float(self.resolution_scale) <= 4.0:
            raise ValueError("resolution_scale must be between 1 and 4")
        return self


@dataclass(slots=True, frozen=True)
class VerticalFollowSettings:
    """Limit the output to a moving window of subtitle rows."""

    visible_lines: int = 0
    easing_seconds: float = 0.35
    continuous: bool = False
    smooth_percent: float = 50.0

    @property
    def enabled(self) -> bool:
        return self.visible_lines > 0

    def validate(self) -> "VerticalFollowSettings":
        if self.visible_lines < 0 or self.visible_lines > 100:
            raise ValueError("visible_lines must be between 0 and 100")
        if self.easing_seconds < 0 or self.easing_seconds > 10:
            raise ValueError("easing_seconds must be between 0 and 10")
        if self.smooth_percent < 0 or self.smooth_percent > 100:
            raise ValueError("smooth_percent must be between 0 and 100")
        return self


@dataclass(slots=True, frozen=True)
class VerticalFollowPlan:
    crop: CropRect
    keyframes: tuple[tuple[float, int], ...]
    easing_seconds: float
    continuous: bool = False
    smooth_percent: float = 50.0


@dataclass(slots=True, frozen=True)
class AssTextStyle:
    """The visual fields of one ASS v4+ style."""

    name: str = "Default"
    font_name: str = "Arial"
    font_size: float = 42.0
    primary_colour: str = "&H00FFFFFF"
    secondary_colour: str = "&H00FFFFFF"
    outline_colour: str = "&H00000000"
    back_colour: str = "&H00000000"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike_out: bool = False
    scale_x: float = 100.0
    scale_y: float = 100.0
    spacing: float = 0.0
    angle: float = 0.0
    border_style: int = 1
    outline: float = 0.0
    shadow: float = 0.0
    alignment: int = 5
    margin_l: int = 0
    margin_r: int = 0
    margin_v: int = 0
    encoding: int = 1

    def validate(self) -> "AssTextStyle":
        if not self.name.strip() or not self.font_name.strip():
            raise ValueError("ASS style name and font name cannot be empty")
        if any(ch in self.name + self.font_name for ch in ",\r\n"):
            raise ValueError("ASS style and font names cannot contain commas or line breaks")
        numeric = (
            float(self.font_size), float(self.scale_x), float(self.scale_y),
            float(self.spacing), float(self.angle), float(self.outline), float(self.shadow),
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("ASS style numeric fields must be finite")
        if not 1 <= float(self.font_size) <= 500:
            raise ValueError("ASS font size must be between 1 and 500")
        for label, colour in (
            ("primary", self.primary_colour),
            ("secondary", self.secondary_colour),
            ("outline", self.outline_colour),
            ("shadow", self.back_colour),
        ):
            if not re.fullmatch(r"&[Hh][0-9A-Fa-f]{1,8}&?", colour.strip()):
                raise ValueError(f"Invalid ASS {label} colour: {colour}")
        if not 1 <= float(self.scale_x) <= 1000 or not 1 <= float(self.scale_y) <= 1000:
            raise ValueError("ASS ScaleX/ScaleY must be between 1 and 1000")
        for label, value in (("outline", self.outline), ("shadow", self.shadow)):
            if not 0 <= float(value) <= 100:
                raise ValueError(f"ASS {label} must be between 0 and 100")
        if int(self.border_style) not in {1, 3}:
            raise ValueError("ASS BorderStyle must be 1 or 3")
        if not 1 <= int(self.alignment) <= 9:
            raise ValueError("ASS alignment must be between 1 and 9")
        if min(int(self.margin_l), int(self.margin_r), int(self.margin_v)) < 0:
            raise ValueError("ASS margins cannot be negative")
        return self

    def ass_line(self, *, name: str = "Counter", font_size: Optional[float] = None) -> str:
        self.validate()
        size = float(self.font_size if font_size is None else font_size)

        def number(value: float) -> str:
            return f"{float(value):.4f}".rstrip("0").rstrip(".") or "0"

        values = (
            name, self.font_name, number(size), self.primary_colour,
            self.secondary_colour, self.outline_colour, self.back_colour,
            "-1" if self.bold else "0", "-1" if self.italic else "0",
            "-1" if self.underline else "0", "-1" if self.strike_out else "0",
            number(self.scale_x), number(self.scale_y), number(self.spacing),
            number(self.angle), str(int(self.border_style)), number(self.outline),
            number(self.shadow), str(int(self.alignment)), str(int(self.margin_l)),
            str(int(self.margin_r)), str(int(self.margin_v)), str(int(self.encoding)),
        )
        return "Style: " + ",".join(values)

    def ass_values(self, *, name: Optional[str] = None) -> dict[str, str]:
        """Return values keyed like a v4+ ``Format`` declaration."""
        line = self.ass_line(name=name or self.name)
        values = line.split(":", 1)[1].lstrip().split(",")
        return dict(zip(_ASS_STYLE_FIELDS, values))


_ASS_STYLE_FIELDS = (
    "name", "fontname", "fontsize", "primarycolour", "secondarycolour",
    "outlinecolour", "backcolour", "bold", "italic", "underline",
    "strikeout", "scalex", "scaley", "spacing", "angle", "borderstyle",
    "outline", "shadow", "alignment", "marginl", "marginr", "marginv", "encoding",
)


def ass_text_styles(document: AssDocument) -> dict[str, AssTextStyle]:
    """Parse v4+ styles without normalising or mutating the source ASS."""
    in_styles = False
    fields = _ASS_STYLE_FIELDS
    result: dict[str, AssTextStyle] = {}
    for raw in document.lines:
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_styles = stripped.casefold() == "[v4+ styles]"
            continue
        if not in_styles:
            continue
        if stripped.casefold().startswith("format:"):
            parsed = tuple(value.strip().casefold() for value in stripped.split(":", 1)[1].split(","))
            if parsed:
                fields = parsed
            continue
        if not stripped.casefold().startswith("style:"):
            continue
        values = [value.strip() for value in stripped.split(":", 1)[1].split(",", len(fields) - 1)]
        if len(values) != len(fields):
            continue
        data = dict(zip(fields, values))
        try:
            style = AssTextStyle(
                name=data.get("name", "Default"),
                font_name=data.get("fontname", "Arial"),
                font_size=float(data.get("fontsize", 42)),
                primary_colour=data.get("primarycolour", "&H00FFFFFF"),
                secondary_colour=data.get("secondarycolour", "&H00FFFFFF"),
                outline_colour=data.get("outlinecolour", "&H00000000"),
                back_colour=data.get("backcolour", "&H00000000"),
                bold=int(data.get("bold", "0")) != 0,
                italic=int(data.get("italic", "0")) != 0,
                underline=int(data.get("underline", "0")) != 0,
                strike_out=int(data.get("strikeout", "0")) != 0,
                scale_x=float(data.get("scalex", 100)),
                scale_y=float(data.get("scaley", 100)),
                spacing=float(data.get("spacing", 0)),
                angle=float(data.get("angle", 0)),
                border_style=int(data.get("borderstyle", 1)),
                outline=float(data.get("outline", 0)),
                shadow=float(data.get("shadow", 0)),
                alignment=int(data.get("alignment", 5)),
                margin_l=int(data.get("marginl", 0)),
                margin_r=int(data.get("marginr", 0)),
                margin_v=int(data.get("marginv", 0)),
                encoding=int(data.get("encoding", 1)),
            ).validate()
        except (TypeError, ValueError):
            continue
        result[style.name.casefold()] = style
    return result


def karaoke_text_style(document: AssDocument) -> AssTextStyle:
    """Resolve the base style used by the first karaoke dialogue."""
    styles = ass_text_styles(document)
    events = [event for event in document.events() if event.kind == "Dialogue"]
    karaoke_lines = {item.event_line_index for item in document.karaoke_syllables()}
    preferred = next((event for event in events if event.line_index in karaoke_lines), None)
    if preferred is None and events:
        preferred = events[0]
    if preferred is not None:
        found = styles.get(preferred.style.casefold())
        if found is not None:
            return found
    if "default" in styles:
        return styles["default"]
    if styles:
        return next(iter(styles.values()))
    return AssTextStyle()


def replace_ass_text_style(
    document: AssDocument,
    style_name: str,
    style: AssTextStyle,
) -> AssTextStyle:
    """Replace one existing v4+ style while preserving its Format order."""
    style.validate()
    wanted = style_name.strip().casefold()
    if not wanted:
        raise ValueError("ASS style name cannot be empty")
    in_styles = False
    fields = _ASS_STYLE_FIELDS
    for index, raw in enumerate(document.lines):
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_styles = stripped.casefold() == "[v4+ styles]"
            continue
        if not in_styles:
            continue
        if stripped.casefold().startswith("format:"):
            parsed = tuple(value.strip().casefold() for value in stripped.split(":", 1)[1].split(","))
            if parsed:
                fields = parsed
            continue
        if not stripped.casefold().startswith("style:"):
            continue
        current = [value.strip() for value in stripped.split(":", 1)[1].split(",", len(fields) - 1)]
        if len(current) != len(fields):
            continue
        old_values = dict(zip(fields, current))
        if old_values.get("name", "").casefold() != wanted:
            continue
        replacement = replace(style, name=old_values.get("name", style_name)).validate()
        changed = replacement.ass_values(name=replacement.name)
        values = [changed.get(field, old_values.get(field, "")) for field in fields]
        prefix = raw[:len(raw) - len(raw.lstrip())]
        document.lines[index] = prefix + "Style: " + ",".join(values)
        return replacement
    raise ValueError(f"ASS style {style_name!r} was not found")


def scale_ass_text_style(style: AssTextStyle, scale: float) -> AssTextStyle:
    """Scale pixel-valued style fields for a final-resolution ASS layer."""
    scale = float(scale)
    if scale <= 0:
        raise ValueError("ASS style scale must be positive")
    return replace(
        style,
        font_size=style.font_size * scale,
        spacing=style.spacing * scale,
        outline=style.outline * scale,
        shadow=style.shadow * scale,
        margin_l=int(round(style.margin_l * scale)),
        margin_r=int(round(style.margin_r * scale)),
        margin_v=int(round(style.margin_v * scale)),
    )


@dataclass(slots=True, frozen=True)
class BurstCounterSettings:
    """Appearance and update cadence of the post-crop burst SPS overlay."""

    font_name: str = "Arial"
    font_size: int = 42
    text_padding: int = 10
    outline: int = 5
    frame_margin: int = 15
    tick_seconds: float = 0.01
    round_summary_seconds: bool = False
    custom_summary: str = ""
    text_style: Optional[AssTextStyle] = None
    font_offset_y: int = 0

    def validate(self) -> "BurstCounterSettings":
        if not self.font_name.strip():
            raise ValueError("Burst counter font name cannot be empty")
        if self.font_size < 10 or self.font_size > 300:
            raise ValueError("Burst counter font size must be between 10 and 300")
        if self.text_padding < 0 or self.text_padding > 200:
            raise ValueError("Burst counter padding must be between 0 and 200")
        if self.outline < 0 or self.outline > 50:
            raise ValueError("Burst counter outline must be between 0 and 50")
        if self.frame_margin < 0 or self.frame_margin > 500:
            raise ValueError("Burst counter frame margin must be between 0 and 500")
        if self.tick_seconds <= 0 or self.tick_seconds > 0.25:
            raise ValueError("Burst counter tick must be > 0 and <= 0.25 seconds")
        if "\n" in self.custom_summary or "\r" in self.custom_summary:
            raise ValueError("Burst counter custom summary must fit on one line")
        if len(self.custom_summary) > 300:
            raise ValueError("Burst counter custom summary is too long")
        if not -500 <= int(self.font_offset_y) <= 500:
            raise ValueError("Burst counter font_offset_y must be between -500 and 500")
        if self.text_style is not None:
            self.text_style.validate()
        return self

    def resolved_text_style(self) -> AssTextStyle:
        return self.text_style or AssTextStyle(
            font_name=self.font_name,
            font_size=float(self.font_size),
        )


@dataclass(slots=True, frozen=True)
class BurstCounterRegion:
    start: float
    end: float
    syllable_starts: tuple[float, ...]

    @property
    def count(self) -> int:
        return len(self.syllable_starts)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def sps(self) -> float:
        return self.count / self.duration if self.duration > 0 else 0.0

    @property
    def summary(self) -> str:
        return f"{self.sps:.2f} SPS // {self.count} in {self.duration:.2f}s"


@dataclass(slots=True, frozen=True)
class BurstCounterCue:
    start: float
    end: float
    text: str


@dataclass(slots=True, frozen=True)
class BurstCounterPlan:
    duration: float
    regions: tuple[BurstCounterRegion, ...]
    cues: tuple[BurstCounterCue, ...]

    @property
    def first_start(self) -> float:
        return self.regions[0].start if self.regions else self.duration

    @property
    def max_text(self) -> str:
        return max((cue.text for cue in self.cues), key=lambda value: (len(value), value), default="0 // 0.00s")


@dataclass(slots=True, frozen=True)
class BurstCounterLayout:
    text_width: int
    text_height: int
    box_width: int
    box_height: int
    outer_width: int
    outer_height: int
    font_size: float
    max_text: str


@dataclass(slots=True, frozen=True)
class RenderRangeSettings:
    """Select a contiguous karaoke syllable fragment plus media padding."""

    start_syllable_id: str
    end_syllable_id: str
    pre_roll: float = 0.0
    post_roll: float = 0.0

    def validate(self) -> "RenderRangeSettings":
        if not self.start_syllable_id or not self.end_syllable_id:
            raise ValueError("Нужно выбрать начальный и конечный karaoke-слог")
        if self.pre_roll < 0 or self.post_roll < 0:
            raise ValueError("Время до/после фрагмента не может быть отрицательным")
        return self


@dataclass(slots=True, frozen=True)
class ResolvedRenderRange:
    start_syllable_id: str
    end_syllable_id: str
    content_start: float
    content_end: float
    render_start: float
    render_end: float
    pre_roll: float
    post_roll: float
    max_pre_roll: float
    max_post_roll: Optional[float]

    @property
    def duration(self) -> float:
        return max(0.0, self.render_end - self.render_start)


class RenderRangeError(ValueError):
    pass


def _format_limit(value: float) -> str:
    return f"{max(0.0, value):.3f} с"


def resolve_render_range(
    document: AssDocument,
    settings: RenderRangeSettings,
    *,
    media_duration: Optional[float] = None,
    audio_bounds: Optional[MediaTimeBounds] = None,
) -> ResolvedRenderRange:
    """Resolve syllable IDs to absolute content/render bounds.

    ``media_duration``/``audio_bounds`` are optional for standalone overlays.
    For source-video rendering they make pre/post-roll validation strict and
    provide the exact maximum the GUI can report to the user.
    """
    settings.validate()
    syllables = [s for s in document.karaoke_syllables() if s.visible_text.strip()]
    by_id = {s.id: i for i, s in enumerate(syllables)}
    if settings.start_syllable_id not in by_id:
        raise RenderRangeError("Начальный слог больше не существует в открытом ASS")
    if settings.end_syllable_id not in by_id:
        raise RenderRangeError("Конечный слог больше не существует в открытом ASS")
    a, b = by_id[settings.start_syllable_id], by_id[settings.end_syllable_id]
    if a > b:
        raise RenderRangeError("Начальный слог должен находиться раньше конечного")
    first, last = syllables[a], syllables[b]
    content_start = float(first.start)
    content_end = float(last.end)
    if content_end <= content_start:
        raise RenderRangeError("У выбранного диапазона нет положительной длительности")

    lower_bound = 0.0
    upper_bound: Optional[float] = None
    if media_duration is not None and media_duration > 0:
        upper_bound = float(media_duration)
    if audio_bounds is not None:
        lower_bound = max(lower_bound, float(audio_bounds.start))
        upper_bound = float(audio_bounds.end) if upper_bound is None else min(upper_bound, float(audio_bounds.end))

    max_pre = max(0.0, content_start - lower_bound)
    max_post = None if upper_bound is None else max(0.0, upper_bound - content_end)

    eps = 0.0005
    if settings.pre_roll > max_pre + eps:
        raise RenderRangeError(
            f"Перед выбранным первым слогом недостаточно медиа/аудио. "
            f"Максимально возможное время до начала: {_format_limit(max_pre)}."
        )
    if max_post is not None and settings.post_roll > max_post + eps:
        raise RenderRangeError(
            f"После выбранного последнего слога недостаточно медиа/аудио. "
            f"Максимально возможное время после конца: {_format_limit(max_post)}."
        )
    if audio_bounds is not None and (content_start < audio_bounds.start - eps or content_end > audio_bounds.end + eps):
        raise RenderRangeError(
            "Выбранный диапазон karaoke выходит за границы первого аудиопотока; "
            f"аудио доступно примерно {audio_bounds.start:.3f}–{audio_bounds.end:.3f} с."
        )
    render_start = content_start - min(settings.pre_roll, max_pre)
    render_end = content_end + (settings.post_roll if max_post is None else min(settings.post_roll, max_post))
    return ResolvedRenderRange(
        settings.start_syllable_id, settings.end_syllable_id,
        content_start, content_end, render_start, render_end,
        float(settings.pre_roll), float(settings.post_roll), max_pre, max_post,
    )


_KARAOKE_COMMAND_ONLY_RE = re.compile(r"\\(?:kf|ko|K|k)\d+")
_OVERRIDE_BLOCK_ONLY_RE = re.compile(r"\{[^{}]*\}")


def _prefix_overrides_without_karaoke(text: str) -> str:
    """Keep state/position/colour tags from a discarded karaoke prefix."""
    out: list[str] = []
    for match in _OVERRIDE_BLOCK_ONLY_RE.finditer(text):
        block = _KARAOKE_COMMAND_ONLY_RE.sub("", match.group(0))
        if block.startswith("{") and block.endswith("}") and block[1:-1].strip():
            out.append(block)
    return "".join(out)


def prepare_range_document(document: AssDocument, segment: ResolvedRenderRange) -> AssDocument:
    """Build a render-only ASS containing only the selected syllable interval.

    Events outside the interval become Comments. For partially selected events,
    visible text before/after the requested syllables is omitted while override
    state is preserved. Every selected event is shifted to a zero-based output
    timeline with an invisible karaoke delay before its first selected syllable.
    """
    result = AssDocument.from_text(document.dumps())
    result.bom = document.bom
    all_syllables = [s for s in result.karaoke_syllables() if s.visible_text.strip()]
    by_id = {s.id: i for i, s in enumerate(all_syllables)}
    if segment.start_syllable_id not in by_id or segment.end_syllable_id not in by_id:
        raise RenderRangeError("Диапазон слогов устарел; выберите начало и конец заново")
    a, b = by_id[segment.start_syllable_id], by_id[segment.end_syllable_id]
    selected_ids = {s.id for s in all_syllables[a:b + 1]}
    syllables_by_event: dict[int, list[KaraokeSyllable]] = {}
    for syl in result.karaoke_syllables():
        syllables_by_event.setdefault(syl.event_line_index, []).append(syl)

    for event in result.events():
        if event.kind != "Dialogue":
            continue
        event_syllables = syllables_by_event.get(event.line_index, [])
        chosen = [s for s in event_syllables if s.id in selected_ids]
        if not chosen:
            event.kind = "Comment"
            event.commit()
            continue
        first, last = chosen[0], chosen[-1]
        prefix = _prefix_overrides_without_karaoke(event.text[:first.tag_block_start])
        selected_end = last.tag_block_end + len(last.raw_text)
        selected_raw = event.text[first.tag_block_start:selected_end]
        delay_cs = max(0, int(round((first.start - segment.render_start) * 100.0)))
        delay = rf"{{\k{delay_cs}}}" if delay_cs else ""
        event.text = prefix + delay + selected_raw
        event.start_raw = "0:00:00.00"
        event.end_raw = format_ass_time(max(0.01, last.end - segment.render_start))
        event.commit()
    return result


@dataclass(slots=True, frozen=True)
class DirectVideoSettings:
    """Encoding settings for burning karaoke into an existing video.

    Timestamps and frame cadence are inherited from the input video. By default
    the frame is upscaled 2x before libass draws the subtitles, so both the
    picture and subtitle raster are rendered at twice the source dimensions.
    Audio can stay bit-identical (``copy``), be converted to AAC for container
    compatibility, or be omitted.
    """

    video_codec: str = "libx264"
    crf: int = 18
    preset: str = "medium"
    audio_mode: str = "copy"
    audio_bitrate_kbps: int = 192
    pixel_format: str = "yuv420p"
    resolution_scale: float = 2.0

    def validate(self) -> "DirectVideoSettings":
        if self.video_codec not in {"libx264", "libx265"}:
            raise ValueError(f"Unsupported video codec: {self.video_codec}")
        if not 0 <= int(self.crf) <= 51:
            raise ValueError("CRF must be between 0 and 51")
        if self.preset not in {
            "ultrafast", "superfast", "veryfast", "faster", "fast",
            "medium", "slow", "slower", "veryslow",
        }:
            raise ValueError(f"Unsupported encoder preset: {self.preset}")
        if self.audio_mode not in {"copy", "aac", "none"}:
            raise ValueError(f"Unsupported audio mode: {self.audio_mode}")
        if not 32 <= int(self.audio_bitrate_kbps) <= 1024:
            raise ValueError("AAC bitrate must be between 32 and 1024 kbps")
        if self.pixel_format not in {"yuv420p", "yuv422p", "yuv444p"}:
            raise ValueError(f"Unsupported pixel format: {self.pixel_format}")
        if not 1.0 <= float(self.resolution_scale) <= 4.0:
            raise ValueError("resolution_scale must be between 1 and 4")
        return self


def ass_playres(document: AssDocument, fallback: tuple[int, int] = (1920, 1080)) -> tuple[int, int]:
    """Read PlayResX/Y without normalising or modifying the ASS source."""
    x = y = None
    in_script_info = False
    for line in document.lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_script_info = stripped.lower() == "[script info]"
            continue
        if not in_script_info:
            continue
        if x is None:
            m = _PLAYRES_X_RE.match(line)
            if m:
                x = int(m.group(1))
                continue
        if y is None:
            m = _PLAYRES_Y_RE.match(line)
            if m:
                y = int(m.group(1))
    fx, fy = fallback
    return (x or fx, y or fy)


def _set_ass_playres(document: AssDocument, width: int, height: int) -> None:
    """Set PlayRes on a render-only document without touching the source ASS."""
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        raise ValueError("PlayRes dimensions must be positive")
    in_script_info = False
    script_info_index: Optional[int] = None
    x_index: Optional[int] = None
    y_index: Optional[int] = None
    for index, line in enumerate(document.lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_script_info = stripped.lower() == "[script info]"
            if in_script_info:
                script_info_index = index
            continue
        if not in_script_info:
            continue
        if _PLAYRES_X_RE.match(line):
            x_index = index
        elif _PLAYRES_Y_RE.match(line):
            y_index = index
    if script_info_index is None:
        document.lines[0:0] = ["[Script Info]", f"PlayResX: {width}", f"PlayResY: {height}"]
        return
    if x_index is not None:
        document.lines[x_index] = f"PlayResX: {width}"
    if y_index is not None:
        document.lines[y_index] = f"PlayResY: {height}"
    missing: list[str] = []
    if x_index is None:
        missing.append(f"PlayResX: {width}")
    if y_index is None:
        missing.append(f"PlayResY: {height}")
    if missing:
        document.lines[script_info_index + 1:script_info_index + 1] = missing


def _event_at(document: AssDocument, line_index: int) -> Optional[AssEvent]:
    return next((event for event in document.events() if event.line_index == line_index), None)


def _visible_units(text: str) -> list[tuple[int, int, str]]:
    """Return raw spans for visible characters/ASS whitespace escapes.

    Override blocks are omitted.  ``\\N``/``\\n`` become newlines and ``\\h`` a
    space.  Keeping raw spans lets the wrapper insert line breaks without ever
    reconstructing override blocks or karaoke commands.
    """
    units: list[tuple[int, int, str]] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            end = text.find("}", i + 1)
            if end >= 0:
                i = end + 1
                continue
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in "Nnh":
            esc = text[i : i + 2]
            units.append((i, i + 2, "\n" if esc in (r"\N", r"\n") else " "))
            i += 2
            continue
        units.append((i, i + 1, text[i]))
        i += 1
    return units


def _line_shift_tag(line_number: int, playres_x: int, spacing_px: float, origin_x: float) -> str:
    """Create the user's distant-origin micro-rotation line-spacing trick.

    The old script used an approximately constant 0.00002865 degrees/pixel for
    an origin near x=-2,000,000.  Here the angle is derived from the actual ASS
    PlayRes centre, so the requested pixel displacement is much closer to exact.
    """
    if line_number <= 0 or spacing_px == 0:
        return ""
    anchor_x = playres_x / 2.0
    distance = anchor_x - origin_x
    if distance <= 0:
        raise ValueError("far origin must be to the left of the subtitle anchor")
    shift = line_number * spacing_px
    ratio = max(-0.999999, min(0.999999, shift / distance))
    angle = -math.degrees(math.asin(ratio))
    origin_text = str(int(origin_x)) if float(origin_x).is_integer() else f"{origin_x:.3f}".rstrip("0").rstrip(".")
    return rf"{{\org({origin_text},0)\frz{angle:.9f}}}"


def _remove_authored_line_breaks(text: str) -> str:
    replacements = [
        (start, end) for start, end, ch in _visible_units(text) if ch == "\n"
    ]
    for start, end in reversed(replacements):
        text = text[:start] + " " + text[end:]
    return text


def _word_wrap_break_positions(
    text: str, max_words_per_line: int, max_chars_per_line: int = 0,
) -> list[tuple[int, int]]:
    """Find whitespace runs that should become hard line breaks.

    Wrapping happens only between complete words. Character mode therefore
    keeps widths much more even without ever cutting a word or an ASS block.
    When both limits are enabled, whichever is reached first starts a new row.
    """
    if max_words_per_line <= 0 and max_chars_per_line <= 0:
        return []
    units = _visible_units(text)
    replacements: list[tuple[int, int]] = []
    words = 0
    line_chars = 0
    i = 0
    while i < len(units):
        _, _, ch = units[i]
        if ch == "\n":
            words = 0
            line_chars = 0
            i += 1
            continue
        whitespace: list[tuple[int, int, str]] = []
        while i < len(units) and units[i][2].isspace() and units[i][2] != "\n":
            whitespace.append(units[i])
            i += 1
        if i >= len(units) or units[i][2] == "\n":
            continue
        word_start = i
        while i < len(units) and not units[i][2].isspace():
            i += 1
        word_len = i - word_start
        separator_len = len(whitespace) if words else 0
        exceeds_words = bool(max_words_per_line > 0 and words >= max_words_per_line)
        exceeds_chars = bool(
            max_chars_per_line > 0
            and words > 0
            and line_chars + separator_len + word_len > max_chars_per_line
        )
        if whitespace and (exceeds_words or exceeds_chars):
            raw_start = whitespace[0][0]
            raw_end = whitespace[-1][1]
            # Never delete an override block embedded between spaces. Replacing
            # just the last visible space keeps the block byte-for-byte intact.
            if "{" in text[raw_start:raw_end] or "}" in text[raw_start:raw_end]:
                raw_start, raw_end, _ = whitespace[-1]
            replacements.append((raw_start, raw_end))
            words = 1
            line_chars = word_len
        else:
            words += 1
            line_chars += separator_len + word_len
    return replacements


def _inject_line_spacing(text: str, *, playres_x: int, spacing_px: float, origin_x: float) -> str:
    if spacing_px == 0:
        return text
    out: list[str] = []
    i = 0
    line_no = 0
    while i < len(text):
        if text.startswith(r"\N", i) or text.startswith(r"\n", i):
            out.append(text[i : i + 2])
            i += 2
            line_no += 1
            # Respect a line shift already authored by the user/old script.
            m = re.match(r"\{[^{}]*\}", text[i:])
            block = m.group(0) if m else ""
            if block and _EXISTING_LINE_SHIFT_RE.match(block):
                continue
            out.append(_line_shift_tag(line_no, playres_x, spacing_px, origin_x))
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def layout_event_text(text: str, settings: RenderLayoutSettings, *, playres_x: int) -> str:
    settings.validate()
    if settings.remove_original_line_breaks:
        text = _remove_authored_line_breaks(text)
    replacements = _word_wrap_break_positions(
        text, settings.max_words_per_line, settings.max_chars_per_line
    )
    if replacements:
        for start, end in reversed(replacements):
            text = text[:start] + r"\N" + text[end:]
    if getattr(settings, "text_case", "as_is") != "as_is":
        text = apply_text_case(text, settings.text_case)
    if settings.use_far_origin_spacing and settings.line_spacing_px != 0:
        text = _inject_line_spacing(
            text,
            playres_x=playres_x,
            spacing_px=settings.line_spacing_px,
            origin_x=settings.far_origin_x,
        )
    return text


def _enable_whole_text_layout_for_rtl(document: AssDocument) -> None:
    """Use libass whole-event bidi/shaping for styles containing RTL text.

    Karaoke override tags split an event into runs.  Traditional VSFilter
    layout places those runs left-to-right even when each run is Persian or
    Arabic.  libass' documented Encoding=-1 extension enables whole-text
    shaping, including bidi reordering across the karaoke tags.
    """
    rtl_styles: set[str] = set()
    for event in document.events():
        if event.kind != "Dialogue":
            continue
        visible = "".join(unit[2] for unit in _visible_units(event.text))
        if any(unicodedata.bidirectional(ch) in {"R", "AL", "AN"} for ch in visible):
            rtl_styles.add(event.style.casefold())
    if not rtl_styles:
        return
    for style in ass_text_styles(document).values():
        if style.name.casefold() in rtl_styles and style.encoding != -1:
            replace_ass_text_style(document, style.name, replace(style, encoding=-1))


def _ass_colour_and_alpha(value: str) -> tuple[str, str]:
    """Extract BGR and alpha hex strings from an ASS style colour (e.g. &HAABBGGRR)."""
    raw = str(value).strip().strip("&")
    if raw.startswith(("&H", "&h")):
        raw = raw[2:]
    elif raw.startswith(("H", "h")):
        raw = raw[1:]
    if len(raw) == 8:
        alpha = raw[:2]
        bgr = raw[2:]
    elif len(raw) == 6:
        alpha = "00"
        bgr = raw
    elif len(raw) < 6:
        alpha = "00"
        bgr = raw.zfill(6)
    else:
        raw = raw.zfill(8)
        alpha = raw[:2]
        bgr = raw[2:]
    return bgr.upper(), alpha.upper()


def _normalise_ass_colour(value: str) -> str:
    colour = str(value).strip()
    return colour if colour.endswith("&") else colour + "&"


def _is_track0_event(event: AssEvent) -> bool:
    effect = str(getattr(event, "effect", "") or "").strip()
    return not effect.startswith("track:") or effect == "track:0"


@dataclass(slots=True, frozen=True)
class RetimedReference:
    track: int
    ref_track0_seq: int
    start: float
    duration_cs: int
    tag_type: str
    has_wipe: bool
    custom_text: str = ""


def extract_retimed_references(document: AssDocument) -> list[RetimedReference]:
    """Scan all extra track dialogue events for \\id0:N references and wipe flags."""
    refs: list[RetimedReference] = []
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for s in document.karaoke_syllables(include_comments=False):
        by_event.setdefault(s.event_line_index, []).append(s)

    for event in document.events():
        if event.kind != "Dialogue":
            continue
        if _is_track0_event(event):
            continue
        effect = str(getattr(event, "effect", "") or "").strip()
        try:
            track_num = int(effect.split("track:", 1)[1])
        except (ValueError, IndexError):
            track_num = 1

        syls = by_event.get(event.line_index, [])
        for s in syls:
            tag_block = event.text[s.tag_block_start:s.tag_block_end]
            full_text = tag_block + s.raw_text
            m_id = re.search(r"\\id\d*:(\d+)", full_text)
            if not m_id:
                continue
            ref_seq = int(m_id.group(1))
            has_wipe = bool(re.search(r"\\wipe\b", full_text))
            refs.append(
                RetimedReference(
                    track=track_num,
                    ref_track0_seq=ref_seq,
                    start=s.start,
                    duration_cs=s.duration_cs,
                    tag_type=s.tag_type.value,
                    has_wipe=has_wipe,
                    custom_text=s.visible_text.strip(),
                )
            )
    return refs


def _is_pure_retimed_extra_track_event(event: AssEvent, syls: list[KaraokeSyllable]) -> bool:
    if _is_track0_event(event):
        return False
    has_any_ref = False
    for s in syls:
        tag_block = event.text[s.tag_block_start:s.tag_block_end]
        full_text = tag_block + s.raw_text
        if re.search(r"\\id\d*:\d+", full_text):
            has_any_ref = True
        elif s.visible_text.strip():
            return False
    return has_any_ref


_PRIMARY_COLOUR_COMMAND_RE = re.compile(
    r"\\(?:1?c)(?:&H[0-9A-Fa-f]+&?)?(?=\\|\}|$)", re.IGNORECASE
)


def normalize_ass_colour(val: str) -> str:
    s = str(val or "").strip()
    if s.startswith("#") and len(s) == 7:
        r = int(s[1:3], 16)
        g = int(s[3:5], 16)
        b = int(s[5:7], 16)
        return f"&H{b:02X}{g:02X}{r:02X}&"
    if s.startswith("#") and len(s) == 9:
        a = int(s[1:3], 16)
        r = int(s[3:5], 16)
        g = int(s[5:7], 16)
        b = int(s[7:9], 16)
        return f"&H{a:02X}{b:02X}{g:02X}{r:02X}&"
    raw = s.strip("&").lstrip("&H").lstrip("&h")
    try:
        num = int(raw, 16)
    except ValueError:
        return "&H0000FF&"
    if len(raw) > 6:
        a = (num >> 24) & 0xFF
        b = (num >> 16) & 0xFF
        g = (num >> 8) & 0xFF
        r = num & 0xFF
        return f"&H{a:02X}{b:02X}{g:02X}{r:02X}&"
    else:
        b = (num >> 16) & 0xFF
        g = (num >> 8) & 0xFF
        r = num & 0xFF
        return f"&H{b:02X}{g:02X}{r:02X}&"


def ass_to_rgb(ass_color: str) -> tuple[int, int, int]:
    normalized = normalize_ass_colour(ass_color)
    raw = normalized.strip("&").lstrip("&H").lstrip("&h")
    num = int(raw, 16)
    b = (num >> 16) & 0xFF
    g = (num >> 8) & 0xFF
    r = num & 0xFF
    return r, g, b


def rgb_to_ass(r: float, g: float, b: float) -> str:
    ir = max(0, min(255, int(round(r))))
    ig = max(0, min(255, int(round(g))))
    ib = max(0, min(255, int(round(b))))
    return f"&H{ib:02X}{ig:02X}{ir:02X}&"


def rgb_to_hex(r: float, g: float, b: float) -> str:
    ir = max(0, min(255, int(round(r))))
    ig = max(0, min(255, int(round(g))))
    ib = max(0, min(255, int(round(b))))
    return f"#{ir:02X}{ig:02X}{ib:02X}"


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.strip().lstrip("#")
    if len(s) == 6:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return ass_to_rgb(hex_str)


def shift_hue(ass_color: str, hue_offset_degrees: float) -> str:
    r, g, b = ass_to_rgb(ass_color)
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    h = (h + hue_offset_degrees / 360.0) % 1.0
    r_new, g_new, b_new = colorsys.hsv_to_rgb(h, s, v)
    return rgb_to_ass(r_new * 255.0, g_new * 255.0, b_new * 255.0)


def calculate_hue_offset_degrees(base_ass: str, target_ass: str) -> float:
    r1, g1, b1 = ass_to_rgb(base_ass)
    r2, g2, b2 = ass_to_rgb(target_ass)
    h1, _, _ = colorsys.rgb_to_hsv(r1 / 255.0, g1 / 255.0, b1 / 255.0)
    h2, _, _ = colorsys.rgb_to_hsv(r2 / 255.0, g2 / 255.0, b2 / 255.0)
    dh = (h2 - h1) % 1.0
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    return round(dh * 360.0, 1)


def interpolate_cube_surface(c1_ass: str, c2_ass: str, t: float) -> str:
    """Interpolate between two colours along the outer surface of the RGB color cube.

    By shortest arc in HSV, maintaining saturation and value, we traverse intermediate
    saturated cube faces (e.g. Red -> Yellow -> Green or Red -> Magenta -> Cyan)
    instead of cutting straight through the desaturated gray center.
    """
    t = max(0.0, min(1.0, float(t)))
    if t <= 0.0:
        return normalize_ass_colour(c1_ass)
    if t >= 1.0:
        return normalize_ass_colour(c2_ass)
    r1, g1, b1 = ass_to_rgb(c1_ass)
    r2, g2, b2 = ass_to_rgb(c2_ass)
    h1, s1, v1 = colorsys.rgb_to_hsv(r1 / 255.0, g1 / 255.0, b1 / 255.0)
    h2, s2, v2 = colorsys.rgb_to_hsv(r2 / 255.0, g2 / 255.0, b2 / 255.0)
    if s1 < 0.05 and s2 < 0.05:
        return rgb_to_ass(r1 + t * (r2 - r1), g1 + t * (g2 - g1), b1 + t * (b2 - b1))
    dh = (h2 - h1) % 1.0
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    elif dh == 0.5:
        dh = 0.5
    h = (h1 + t * dh) % 1.0
    s = s1 + t * (s2 - s1)
    if s1 > 0.4 and s2 > 0.4:
        s = max(s, min(s1, s2))
    v = v1 + t * (v2 - v1)
    if v1 > 0.4 and v2 > 0.4:
        v = max(v, min(v1, v2))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return rgb_to_ass(r * 255.0, g * 255.0, b * 255.0)


def generate_surface_dynamic_tags(c1_ass: str, c2_ass: str, start_ms: int, end_ms: int) -> str:
    """Generate libass \\t tags transitioning between colours along the cube surface."""
    if end_ms <= start_ms:
        return ""
    r1, g1, b1 = ass_to_rgb(c1_ass)
    r2, g2, b2 = ass_to_rgb(c2_ass)
    h1, s1, _ = colorsys.rgb_to_hsv(r1 / 255.0, g1 / 255.0, b1 / 255.0)
    h2, s2, _ = colorsys.rgb_to_hsv(r2 / 255.0, g2 / 255.0, b2 / 255.0)
    if s1 < 0.05 and s2 < 0.05:
        return rf"\t({start_ms},{end_ms},\1c{normalize_ass_colour(c2_ass)})"
    dh = (h2 - h1) % 1.0
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    deg = abs(dh * 360.0)
    if deg <= 60.0:
        return rf"\t({start_ms},{end_ms},\1c{normalize_ass_colour(c2_ass)})"
    steps = max(2, int(math.ceil(deg / 45.0)))
    tags: list[str] = []
    dur = end_ms - start_ms
    for step in range(1, steps + 1):
        t_prev = start_ms + int(round((step - 1) / steps * dur))
        t_curr = start_ms + int(round(step / steps * dur))
        c_step = interpolate_cube_surface(c1_ass, c2_ass, step / steps)
        tags.append(rf"\t({t_prev},{t_curr},\1c{c_step})")
    return "".join(tags)


def generate_burst_pulse_tags(
    c1_ass: str,
    c2_ass: str,
    start_ms: int,
    end_ms: int,
    hz: float = 2.0,
    *,
    phase_offset_ms: int = 0,
    step_ms: int = 30,
) -> tuple[str, str]:
    """Generate (initial_1c_tag, animation_t_tags) pulsing smoothly between c1 and c2 along the cube surface.

    start_ms and end_ms are in milliseconds relative to the event start.
    phase_offset_ms is the reference time (e.g. burst group start) for consistent rhythmic phase.
    """
    c1_norm = normalize_ass_colour(c1_ass)
    c2_norm = normalize_ass_colour(c2_ass)
    if end_ms <= start_ms:
        return (rf"\1c{c1_norm}", "")

    hz = max(0.05, min(50.0, float(hz)))
    r1, g1, b1 = ass_to_rgb(c1_norm)
    r2, g2, b2 = ass_to_rgb(c2_norm)
    h1, s1, v1 = colorsys.rgb_to_hsv(r1 / 255.0, g1 / 255.0, b1 / 255.0)
    h2, s2, v2 = colorsys.rgb_to_hsv(r2 / 255.0, g2 / 255.0, b2 / 255.0)

    dh = (h2 - h1) % 1.0
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0

    if c1_norm == c2_norm or (dh == 0.0 and s1 == s2 and v1 == v2):
        return (rf"\1c{c1_norm}", "")

    def color_at_t(t_abs: float) -> str:
        t_sec = (t_abs - phase_offset_ms) / 1000.0
        # Smooth sinusoidal factor: 0.0 at t=0, 1.0 at half_period, 0.0 at period
        factor = 0.5 * (1.0 - math.cos(2.0 * math.pi * hz * t_sec))
        h = (h1 + factor * dh) % 1.0
        s = s1 + factor * (s2 - s1)
        v = v1 + factor * (v2 - v1)
        if s1 > 0.4 and s2 > 0.4:
            s = max(s, min(s1, s2))
        if v1 > 0.4 and v2 > 0.4:
            v = max(v, min(v1, v2))
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return rgb_to_ass(r * 255.0, g * 255.0, b * 255.0)

    c_initial = color_at_t(float(start_ms))
    init_tag = rf"\1c{c_initial}"

    step_duration_ms = max(10.0, float(step_ms))
    tags: list[str] = []
    t_curr = float(start_ms)
    while t_curr < end_ms - 1e-3:
        t_next = min(float(end_ms), t_curr + step_duration_ms)
        c_next = color_at_t(t_next)
        tags.append(rf"\t({int(round(t_curr))},{int(round(t_next))},\1c{c_next})")
        t_curr = t_next

    return (init_tag, "".join(tags))


def burst_syllable_style(
    item: KaraokeSyllable,
    all_syllables: Iterable[KaraokeSyllable],
    settings: Optional[RenderLayoutSettings] = None,
) -> tuple[str, str]:
    """Return (c_start_ass, dynamic_tags) for a burst-marked syllable."""
    if settings is None:
        return ("&H0000FF&", "")
    mode = getattr(settings, "burst_color_mode", "single") or "single"
    base_color = normalize_ass_colour(getattr(settings, "burst_base_color", "&H0000FF&"))
    alt_color = normalize_ass_colour(getattr(settings, "burst_alt_color", "&H0080FF&"))

    event_syls = [s for s in all_syllables if s.event_line_index == item.event_line_index]
    if not event_syls:
        return (base_color, "")

    burst_groups: list[list[KaraokeSyllable]] = []
    cur_group: list[KaraokeSyllable] = []
    for s in event_syls:
        if s.burst_marked:
            cur_group.append(s)
        else:
            if cur_group:
                burst_groups.append(cur_group)
                cur_group = []
    if cur_group:
        burst_groups.append(cur_group)

    target_group: list[KaraokeSyllable] = []
    idx_in_group = 0
    for group in burst_groups:
        for idx, s in enumerate(group):
            if s.id == item.id:
                target_group = group
                idx_in_group = idx
                break
        if target_group:
            break

    if not target_group:
        return (base_color, "")

    k = len(target_group)
    dur_ms = max(1, item.duration_cs * 10)
    if mode == "alternate":
        color = base_color if (idx_in_group % 2 == 0) else alt_color
        return (color, "")
    elif mode == "gradient":
        t = (idx_in_group / (k - 1)) if k > 1 else 0.0
        color = interpolate_cube_surface(base_color, alt_color, t)
        return (color, "")
    elif mode == "dynamic":
        hz = getattr(settings, "burst_pulse_hz", 2.0)
        group_start = target_group[0].start
        group_end = target_group[-1].end
        event_start = getattr(item, "event_start", target_group[0].start)
        event_end = getattr(item, "event_end", None)
        if event_end is None and event_syls:
            event_end = max(s.end for s in event_syls)
        if event_end is None:
            event_end = group_end
        group_start_ms = max(0, int(round((group_start - event_start) * 1000.0)))
        group_end_ms = max(group_start_ms + 1, int(round((group_end - event_start) * 1000.0)))
        event_end_ms = max(group_end_ms, int(round((event_end - event_start) * 1000.0)))
        s_start_ms = max(0, int(round((item.start - event_start) * 1000.0)))
        init_tag, anim_tags = generate_burst_pulse_tags(
            base_color, alt_color,
            start_ms=s_start_ms,
            end_ms=event_end_ms,
            hz=hz,
            phase_offset_ms=group_start_ms,
        )
        return (init_tag.replace(r"\1c", ""), anim_tags)
    else:  # "single"
        return (base_color, "")


def apply_render_burst_styling(
    document: AssDocument,
    settings: RenderLayoutSettings,
) -> None:
    """Apply burst styling (alternate, gradient, dynamic, or custom single color).

    Replaces color override tags in burst syllables and injects clean resets
    after each burst sequence on the render copy of the document.
    """
    mode = getattr(settings, "burst_color_mode", "single") or "single"
    base_color = normalize_ass_colour(getattr(settings, "burst_base_color", "&H0000FF&"))
    alt_color = normalize_ass_colour(getattr(settings, "burst_alt_color", "&H0080FF&"))

    if mode == "single" and base_color == "&H0000FF&":
        return

    by_event: dict[int, list[KaraokeSyllable]] = {}
    for s in document.karaoke_syllables():
        by_event.setdefault(s.event_line_index, []).append(s)

    for event in document.events():
        if event.kind != "Dialogue":
            continue
        event_syls = by_event.get(event.line_index, [])
        if not event_syls or not any(s.burst_marked for s in event_syls):
            continue

        burst_groups: list[list[KaraokeSyllable]] = []
        cur_group: list[KaraokeSyllable] = []
        for s in event_syls:
            if s.burst_marked:
                cur_group.append(s)
            else:
                if cur_group:
                    burst_groups.append(cur_group)
                    cur_group = []
        if cur_group:
            burst_groups.append(cur_group)

        replacements: list[tuple[int, int, str]] = []
        for group in burst_groups:
            k = len(group)
            group_start_s = group[0].start
            group_end_s = group[-1].end
            group_start_ms = max(0, int(round((group_start_s - event.start) * 1000.0)))
            group_end_ms = max(group_start_ms + 1, int(round((group_end_s - event.start) * 1000.0)))
            event_end_ms = max(group_end_ms, int(round((event.end - event.start) * 1000.0)))
            hz = getattr(settings, "burst_pulse_hz", 2.0)
            for idx, s in enumerate(group):
                dur_ms = max(1, s.duration_cs * 10)
                if mode == "alternate":
                    color = base_color if (idx % 2 == 0) else alt_color
                    tag = rf"\1c{color}"
                elif mode == "gradient":
                    t = (idx / (k - 1)) if k > 1 else 0.0
                    color = interpolate_cube_surface(base_color, alt_color, t)
                    tag = rf"\1c{color}"
                elif mode == "dynamic":
                    s_start_ms = max(0, int(round((s.start - event.start) * 1000.0)))
                    init_tag, anim_tags = generate_burst_pulse_tags(
                        base_color, alt_color,
                        start_ms=s_start_ms,
                        end_ms=event_end_ms,
                        hz=hz,
                        phase_offset_ms=group_start_ms,
                    )
                    tag = init_tag + anim_tags
                else:  # "single"
                    color = base_color
                    tag = rf"\1c{color}"

                block = event.text[s.tag_block_start:s.tag_block_end]
                cleaned = _PRIMARY_COLOUR_COMMAND_RE.sub("", block)
                if cleaned.startswith("{") and cleaned.endswith("}"):
                    new_block = cleaned[:-1] + tag + "}"
                else:
                    new_block = "{" + tag + "}"
                new_block = re.sub(r"\\{2,}", r"\\", new_block)
                replacements.append((s.tag_block_start, s.tag_block_end, new_block))

            last_syl = group[-1]
            next_idx = last_syl.syllable_ordinal + 1
            if next_idx < len(event_syls):
                next_syl = event_syls[next_idx]
                if not next_syl.burst_marked:
                    n_block = event.text[next_syl.tag_block_start:next_syl.tag_block_end]
                    cleaned_n = _PRIMARY_COLOUR_COMMAND_RE.sub("", n_block)
                    if cleaned_n.startswith("{") and cleaned_n.endswith("}"):
                        new_n = cleaned_n[:-1] + r"\1c}"
                    else:
                        new_n = r"{\1c}"
                    new_n = re.sub(r"\\{2,}", r"\\", new_n)
                    replacements.append((next_syl.tag_block_start, next_syl.tag_block_end, new_n))
            else:
                end_pos = last_syl.tag_block_end + len(last_syl.raw_text)
                if not re.search(r"\{\s*\\(?:1?c)\s*\}", event.text[end_pos:]):
                    replacements.append((end_pos, end_pos, r"{\1c}"))

        if replacements:
            for start, end, replacement in sorted(replacements, key=lambda x: (x[0], x[1]), reverse=True):
                event.text = event.text[:start] + replacement + event.text[end:]
            event.commit()


def expand_extra_track_overlays(
    document: AssDocument,
    settings: RenderLayoutSettings,
    *,
    refs: Optional[list[RetimedReference]] = None,
) -> None:
    """Generate pixel-exact retimed syllable overlay Dialogue lines and wipe effects.

    Prevents duplicate text, positioning drift, or double opacity when an extra track
    re-times syllables from Track 0.
    """
    if refs is None:
        refs = getattr(document, "_extra_track_references", None) or extract_retimed_references(document)
    if not refs:
        resolve_extra_track_references_and_strip_id_tags(document)
        return

    setattr(document, "_extra_track_references", refs)

    track0_syllables = [s for s in document.karaoke_syllables() if getattr(s, "track", 0) == 0]
    track0_map = {i + 1: s for i, s in enumerate(track0_syllables)}

    by_event: dict[int, list[KaraokeSyllable]] = {}
    for s in document.karaoke_syllables(include_comments=False):
        by_event.setdefault(s.event_line_index, []).append(s)

    for event in document.events():
        if event.kind == "Dialogue" and not _is_track0_event(event):
            syls = by_event.get(event.line_index, [])
            if _is_pure_retimed_extra_track_event(event, syls):
                event.kind = "Comment"
                event.commit()
            else:
                event.text = re.sub(r"\\id\d*:\d+\b", "", event.text)
                event.text = re.sub(r"\\wipe\b", "", event.text)
                event.text = re.sub(r"\{\s*\}", "", event.text)
                event.commit()

    events_by_line = {e.line_index: e for e in document.events()}
    new_event_lines: list[str] = []

    for ref in refs:
        if ref.ref_track0_seq not in track0_map:
            continue
        ref_syl = track0_map[ref.ref_track0_seq]
        parent_event = events_by_line.get(ref_syl.event_line_index)
        if parent_event is None:
            continue

        overlay_start = ref.start
        overlay_end = (
            overlay_start + (ref.duration_cs / 100.0)
            if ref.has_wipe
            else parent_event.end
        )
        if overlay_end <= overlay_start:
            continue

        raw_prefix = parent_event.text[:ref_syl.tag_block_start]
        prefix = re.sub(r"\\(?:kf|ko|K|k)\d+", "", raw_prefix)
        prefix = re.sub(r"\\[_-][a-zA-Z0-9+=/:-]+", "", prefix)
        prefix = _strip_color_and_alpha_overrides(prefix)
        prefix = re.sub(r"\{\s*\}", "", prefix)

        raw_suffix = parent_event.text[ref_syl.tag_block_end + len(ref_syl.raw_text):]
        suffix = re.sub(r"\\(?:kf|ko|K|k)\d+", "", raw_suffix)
        suffix = re.sub(r"\\[_-][a-zA-Z0-9+=/:-]+", "", suffix)
        suffix = _strip_color_and_alpha_overrides(suffix)
        suffix = re.sub(r"\{\s*\}", "", suffix)

        render_text = ref.custom_text if ref.custom_text else _OVERRIDE_RE.sub("", ref_syl.raw_text)
        burst_tag = ""
        if ref_syl.burst_marked:
            syl_col, syl_dyn = burst_syllable_style(ref_syl, track0_syllables, settings)
            c = syl_col if syl_col.endswith("&") else (syl_col + "&")
            burst_tag = rf"\1c{c}" + syl_dyn
        active = (
            rf"{{\alpha&H00&\2a&HFF&\3a&HFF&\4a&HFF&{burst_tag}}}"
            rf"{{\{ref.tag_type}{ref.duration_cs}}}"
            rf"{render_text}"
            rf"{{\alpha&HFF&}}"
        )

        overlay_text = r"{\alpha&HFF&}" + prefix + active + suffix
        try:
            layer = str(int(parent_event.layer) + 1)
        except ValueError:
            layer = "1"

        wipe_marker = "wipe" if ref.has_wipe else "hold"
        effect = f"retimed:{ref.ref_track0_seq}:{ref.tag_type}:{ref.duration_cs}:{wipe_marker}"
        name = f"Retimed:{ref.ref_track0_seq}"

        line = "Dialogue: " + ",".join([
            layer,
            format_ass_time(overlay_start),
            format_ass_time(overlay_end),
            parent_event.style,
            name,
            parent_event.margin_l,
            parent_event.margin_r,
            parent_event.margin_v,
            effect,
            overlay_text,
        ])
        new_event_lines.append(line)

    _insert_event_lines(document, new_event_lines)


def resolve_extra_track_references_and_strip_id_tags(document: AssDocument) -> None:
    """Resolve \\id0:N references on extra tracks to Track 0 syllable text, and strip all \\id tags."""
    track0_syllables = [s for s in document.karaoke_syllables() if getattr(s, "track", 0) == 0]
    track0_map = {i + 1: s for i, s in enumerate(track0_syllables)}

    by_event: dict[int, list[KaraokeSyllable]] = {}
    for s in document.karaoke_syllables():
        by_event.setdefault(s.event_line_index, []).append(s)

    for event in document.events():
        if event.kind != "Dialogue":
            continue
        orig = event.text
        is_extra = not _is_track0_event(event)
        if is_extra:
            syls = by_event.get(event.line_index, [])
            for s in sorted(syls, key=lambda x: x.syllable_ordinal, reverse=True):
                tag_block = event.text[s.tag_block_start:s.tag_block_end]
                m = re.search(r"\\id\d*:(\d+)", s.raw_text) or re.search(r"\\id\d*:(\d+)", tag_block)
                if m and not s.visible_text.strip():
                    ref_seq = int(m.group(1))
                    if ref_seq in track0_map:
                        ref_syl = track0_map[ref_seq]
                        repl = ref_syl.raw_text
                        if ref_syl.romanization and not s.romanization:
                            repl = f"{{\\-romaji:{ref_syl.romanization}}}" + repl
                        start_pos = s.tag_block_end
                        end_pos = start_pos + len(s.raw_text)
                        event.text = event.text[:start_pos] + repl + event.text[end_pos:]

        cleaned = re.sub(r"\\id\d*:\d+\b", "", event.text)
        cleaned = re.sub(r"\\wipe\b", "", cleaned)
        cleaned = re.sub(r"\{\s*\}", "", cleaned)
        cleaned = re.sub(r"\{\s+", "{", cleaned)
        cleaned = re.sub(r"\s+\}", "}", cleaned)
        if cleaned != orig:
            event.text = cleaned
            event.commit()


def materialize_unspoken_fragments(
    document: AssDocument,
    settings: Optional[RenderLayoutSettings] = None,
) -> int:
    r"""Turn source ``[text]`` into render-only non-karaoke-colouring spans.

    Both primary and secondary colours, as well as alphas, are set to the style's
    secondary colour and alpha inside the span, so ignored fragments always
    render as unhighlighted (незакрашенный) text throughout the entire video.
    On exit the secondary colour/alpha are reset, and primary colour returns
    either to style default or to burst colour when the containing syllable is
    part of a manually marked burst. Source brackets and karaoke timing remain
    untouched because this function only receives the render copy.
    """
    styles = ass_text_styles(document)
    fallback = karaoke_text_style(document)
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in document.karaoke_syllables():
        by_event.setdefault(item.event_line_index, []).append(item)
    changed = 0
    for event in document.events():
        if event.kind != "Dialogue":
            continue
        style = styles.get(event.style.casefold(), fallback)
        bgr, alpha = _ass_colour_and_alpha(style.secondary_colour)
        opening = rf"{{\1c&H{bgr}&\2c&H{bgr}&\1a&H{alpha}&\2a&H{alpha}&}}"
        replacements: list[tuple[int, int, str]] = []
        for item in by_event.get(event.line_index, ()):
            spans = unspoken_spans(item.raw_text)
            tag_block = event.text[item.tag_block_start:item.tag_block_end]
            has_remap_tag = bool(re.search(r"\\remap\b", tag_block))
            has_remap_raw = bool(re.search(r"\\remap\b", item.raw_text))
            is_remap_track0 = (getattr(item, "track", 0) == 0 and (has_remap_tag or has_remap_raw))
            if not spans and not is_remap_track0:
                continue
            rendered = item.raw_text
            if item.burst_marked:
                mode = getattr(settings, "burst_color_mode", "single") if settings else "single"
                base_color = normalize_ass_colour(getattr(settings, "burst_base_color", "&H0000FF&")) if settings else "&H0000FF&"
                if mode != "single" or base_color != "&H0000FF&":
                    syl_col = burst_syllable_style(item, document.karaoke_syllables(), settings)[0] if settings else "&H0000FF&"
                    c = syl_col if syl_col.endswith("&") else (syl_col + "&")
                    closing = rf"{{\1c{c}\2c\1a\2a}}"
                else:
                    closing = r"{\1c&Hff&\2c\1a\2a}"
            else:
                closing = r"{\1c\2c\1a\2a}"
            for start, end in reversed(spans):
                rendered = (
                    rendered[:start] + opening + rendered[start + 1:end - 1]
                    + closing + rendered[end:]
                )
                changed += 1
            if is_remap_track0:
                if has_remap_raw:
                    rendered = re.sub(r"\{\\remap\}", lambda _: opening, rendered)
                    rendered = re.sub(r"\\remap\b", lambda _: opening, rendered)
                    rendered = rendered + closing
                elif has_remap_tag:
                    rendered = opening + rendered + closing
                changed += 1
            content_start = item.tag_block_end
            replacements.append((
                content_start,
                content_start + len(item.raw_text),
                rendered,
            ))
        if replacements:
            for start, end, replacement in sorted(replacements, reverse=True):
                event.text = event.text[:start] + replacement + event.text[end:]
            event.text = re.sub(r"\\remap\b", "", event.text)
            event.text = re.sub(r"\{\s*\}", "", event.text)
            event.commit()
    return changed


def prepare_render_document(
    document: AssDocument,
    settings: RenderLayoutSettings,
    *,
    render_range: Optional[ResolvedRenderRange] = None,
) -> AssDocument:
    """Create a render-only ASS copy; the editable source document is untouched."""
    settings.validate()
    render_doc = prepare_range_document(document, render_range) if render_range is not None else AssDocument.from_text(document.dumps())
    render_doc.bom = document.bom
    refs = extract_retimed_references(render_doc)
    setattr(render_doc, "_extra_track_references", refs)
    materialize_unspoken_fragments(render_doc, settings)
    for style in ass_text_styles(render_doc).values():
        if style.alignment in {1, 2, 3}:
            target_alignment = style.alignment + 3
            replace_ass_text_style(render_doc, style.name, replace(style, alignment=target_alignment))
    playres_x, _ = ass_playres(render_doc)
    for event in render_doc.events():
        if event.kind != "Dialogue":
            continue
        event.text = re.sub(r"\\an([123])\b", lambda m: rf"\an{int(m.group(1)) + 3}", event.text)
        event.text = layout_event_text(event.text, settings, playres_x=playres_x)
        event.commit()
    _enable_whole_text_layout_for_rtl(render_doc)
    apply_render_burst_styling(render_doc, settings)
    expand_extra_track_overlays(render_doc, settings, refs=refs)
    return render_doc


def prepare_geometry_document(
    document: AssDocument,
    settings: RenderLayoutSettings,
    *,
    render_range: Optional[ResolvedRenderRange] = None,
) -> tuple[AssDocument, bool]:
    """Make all dialogue lines visible at t=5s for a worst-case static layout frame."""
    has_track0 = any(ev.kind == "Dialogue" and _is_track0_event(ev) for ev in document.events())
    if has_track0:
        track0_doc = AssDocument.from_text(document.dumps())
        track0_doc.bom = document.bom
        events_to_remove = [ev.line_index for ev in track0_doc.events() if ev.kind == "Dialogue" and not _is_track0_event(ev)]
        for line_idx in sorted(events_to_remove, reverse=True):
            del track0_doc.lines[line_idx]
        base_doc = track0_doc
    else:
        base_doc = document

    render_doc = prepare_render_document(base_doc, settings, render_range=render_range)
    dynamic = False
    for event in render_doc.events():
        if event.kind != "Dialogue":
            continue
        if _DYNAMIC_GEOMETRY_RE.search(event.text):
            dynamic = True
        event.start_raw = "0:00:00.00"
        event.end_raw = "0:00:10.00"
        event.commit()
    return render_doc, dynamic


def _write_temp_ass(document: AssDocument, directory: str | Path, name: str = "render-layout.ass") -> Path:
    path = Path(directory) / name
    payload = document.dumps().encode("utf-8")
    if document.bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)
    return path


def render_rgba_frame(
    document: AssDocument,
    *,
    ffmpeg: str | Path = "ffmpeg",
    width: Optional[int] = None,
    height: Optional[int] = None,
    timestamp: float = 5.0,
) -> tuple[bytes, int, int]:
    playres_x, playres_y = ass_playres(document)
    width = int(width or playres_x)
    height = int(height or playres_y)
    if width <= 0 or height <= 0:
        raise ValueError("render dimensions must be positive")
    with tempfile.TemporaryDirectory(prefix="karaoke-render-frame-") as td:
        _write_temp_ass(document, td, "frame.ass")
        filter_graph = f"setpts=PTS+{float(timestamp):.6f}/TB,subtitles=frame.ass:alpha=1"
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=black@0.0:s={width}x{height}:r=100:d=0.04,format=rgba",
            "-vf", filter_graph,
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
        ]
        proc = subprocess.run(cmd, cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=media_tool_subprocess_env(ffmpeg))
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or f"ffmpeg exited with {proc.returncode}")
        expected = width * height * 4
        if len(proc.stdout) != expected:
            raise RuntimeError(f"Unexpected RGBA frame size: got {len(proc.stdout)}, expected {expected}")
        return proc.stdout, width, height


def _romanization_targets(document: AssDocument) -> list[KaraokeSyllable]:
    return [
        item for item in document.karaoke_syllables()
        if item.romanization.strip() and item.visible_text.strip()
    ]


def _ass_bgr_colour(red: int, green: int, blue: int) -> str:
    return f"&H00{blue:02X}{green:02X}{red:02X}&"


_COLOR_ALPHA_TAG_RE = re.compile(
    r"\\[1234]?c(?:&H[0-9A-Fa-f]+&?)?|\\[1234]?a(?:&H[0-9A-Fa-f]+&?)?|\\alpha(?:&H[0-9A-Fa-f]+&?)?",
    re.IGNORECASE,
)


def _strip_color_and_alpha_overrides(text: str) -> str:
    return _COLOR_ALPHA_TAG_RE.sub("", text)


def _romanization_diagnostic_boxes(
    document: AssDocument,
    *,
    ffmpeg: str | Path,
    batch_size: int = 32,
) -> dict[str, CropRect]:
    """Locate annotated base glyphs through libass itself.

    Each batch renders up to 32 targets in distinct hues while every
    other glyph remains layout-participating but transparent.  This avoids
    duplicating HarfBuzz/FriBidi layout logic and therefore also works for RTL
    scripts, ligatures, fallback fonts and authored line breaks.
    """
    targets = _romanization_targets(document)
    if not targets:
        return {}
    width, height = ass_playres(document)
    boxes: dict[str, CropRect] = {}
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in targets:
        by_event.setdefault(item.event_line_index, []).append(item)

    for event_line_index, event_targets in by_event.items():
        for offset in range(0, len(event_targets), max(1, int(batch_size))):
            batch = event_targets[offset:offset + max(1, int(batch_size))]
            diagnostic = AssDocument.from_text(document.dumps())
            diagnostic.bom = document.bom
            # Strip colour and alpha overrides so diagnostic hues are never overridden
            for ev in diagnostic.events():
                if ev.kind == "Dialogue":
                    ev.text = _strip_color_and_alpha_overrides(ev.text)
                    ev.commit()
            event = _event_at(diagnostic, event_line_index)
            if event is None:
                continue
            for other in diagnostic.events():
                if other.line_index != event_line_index and other.kind == "Dialogue":
                    other.kind = "Comment"
                    other.commit()
            event.start_raw = "0:00:00.00"
            event.end_raw = "0:00:10.00"
            event_items = [
                item for item in diagnostic.karaoke_syllables()
                if item.event_line_index == event_line_index
            ]
            batch_ids = {item.id for item in batch}
            hues: dict[str, float] = {}
            replacements: list[tuple[int, int, str]] = []
            count = len(batch)
            for index, target in enumerate(batch):
                hue = index / max(1, count)
                hues[target.id] = hue
            for item in event_items:
                if item.id not in batch_ids:
                    replacements.append((item.tag_block_end, item.tag_block_end, r"{\alpha&HFF&}"))
                    continue
                hue = hues[item.id]
                red_f, green_f, blue_f = colorsys.hsv_to_rgb(hue, 0.92, 1.0)
                colour = _ass_bgr_colour(
                    round(red_f * 255), round(green_f * 255), round(blue_f * 255)
                )
                show = (
                    r"{\alpha&H00&\1c" + colour + r"\2c" + colour
                    + r"\3a&HFF&\4a&HFF&\bord0\shad0}"
                )
                m_break = re.search(r"\\[Nn]", item.raw_text)
                if m_break:
                    if m_break.start() > 0:
                        meas_start = item.tag_block_end
                        meas_end = meas_start + m_break.start()
                        replacements.append((meas_start, meas_start, show))
                        replacements.append((meas_end, meas_end, r"{\alpha&HFF&}"))
                    else:
                        leading_end = m_break.end()
                        next_break = re.search(r"\\[Nn]", item.raw_text[leading_end:])
                        meas_start = item.tag_block_end + leading_end
                        meas_end = (meas_start + next_break.start()) if next_break else (item.tag_block_end + len(item.raw_text))
                        replacements.append((meas_start, meas_start, show))
                        replacements.append((meas_end, meas_end, r"{\alpha&HFF&}"))
                else:
                    content_start = item.tag_block_end
                    content_end = content_start + len(item.raw_text)
                    replacements.append((content_start, content_start, show))
                    replacements.append((content_end, content_end, r"{\alpha&HFF&}"))
            event.text = r"{\alpha&HFF&}" + _apply_text_replacements(event.text, replacements)
            event.commit()
            rgba, _, _ = render_rgba_frame(
                diagnostic, ffmpeg=ffmpeg, width=width, height=height, timestamp=0.1
            )
            bounds = {
                item.id: [width, height, -1, -1] for item in batch
            }
            for pixel in range(0, len(rgba), 4):
                red, green, blue, alpha = rgba[pixel:pixel + 4]
                if alpha < 96:
                    continue
                hue, saturation, _value = colorsys.rgb_to_hsv(
                    red / 255.0, green / 255.0, blue / 255.0
                )
                if saturation < 0.35:
                    continue
                target = min(
                    batch,
                    key=lambda item: min(
                        abs(hue - hues[item.id]), 1.0 - abs(hue - hues[item.id])
                    ),
                )
                x = (pixel // 4) % width
                y = (pixel // 4) // width
                box = bounds[target.id]
                box[0] = min(box[0], x)
                box[1] = min(box[1], y)
                box[2] = max(box[2], x)
                box[3] = max(box[3], y)
            for item in batch:
                left, top, right, bottom = bounds[item.id]
                if right >= left and bottom >= top:
                    boxes[item.id] = CropRect(
                        left, top, right - left + 1, bottom - top + 1
                    )
    return boxes


def _apply_text_replacements(
    source: str, replacements: Iterable[tuple[int, int, str]],
) -> str:
    result = source
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def _insert_event_lines(document: AssDocument, lines: list[str]) -> None:
    if not lines:
        return
    in_events = False
    insert_at = len(document.lines)
    for index, raw in enumerate(document.lines):
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_events:
                insert_at = index
                break
            in_events = stripped.casefold() == "[events]"
    document.lines[insert_at:insert_at] = lines


def _is_unspoken_syllable(item: KaraokeSyllable, style: AssTextStyle) -> bool:
    try:
        if unspoken_spans(item.raw_text):
            return True
    except ValueError:
        pass
    try:
        if unspoken_spans(item.romanization):
            return True
    except ValueError:
        pass
    if "[" in item.raw_text and "]" in item.raw_text:
        return True
    if "[" in item.romanization and "]" in item.romanization:
        return True
    bgr, _ = _ass_colour_and_alpha(style.secondary_colour)
    if bgr and f"&H{bgr}&".casefold() in item.raw_text.casefold():
        return True
    if "\\remap" in item.raw_text:
        return True
    return False


def materialize_romanization_overlays(
    document: AssDocument,
    *,
    ffmpeg: str | Path,
    size_ratio: Optional[float] = None,
    offset_y: Optional[int] = None,
    layout: Optional[RenderLayoutSettings] = None,
) -> int:
    """Add positioned render-only Dialogue lines for manual romanization."""
    if layout is not None and not layout.enable_romanization:
        return 0
    if layout is not None:
        if size_ratio is None:
            size_ratio = float(layout.romanization_size_percent) / 100.0
        if offset_y is None:
            offset_y = int(layout.romanization_offset_y)
    if size_ratio is None:
        size_ratio = 0.55
    if size_ratio <= 0:
        return 0
    if offset_y is None:
        offset_y = 0

    targets = _romanization_targets(document)
    if not targets:
        return 0
    boxes = _romanization_diagnostic_boxes(document, ffmpeg=ffmpeg)
    events = {event.line_index: event for event in document.events()}
    styles = ass_text_styles(document)
    fallback = karaoke_text_style(document)
    lines: list[str] = []

    track0_syllables = [s for s in document.karaoke_syllables() if getattr(s, "track", 0) == 0]
    track0_id_to_seq = {s.id: i + 1 for i, s in enumerate(track0_syllables)}
    refs_by_seq: dict[int, list[RetimedReference]] = {}
    if hasattr(document, "_extra_track_references"):
        for ref in getattr(document, "_extra_track_references"):
            refs_by_seq.setdefault(ref.ref_track0_seq, []).append(ref)
    else:
        for ev in document.events():
            eff = str(getattr(ev, "effect", "") or "")
            if eff.startswith("retimed:"):
                parts = eff.split(":")
                if len(parts) >= 5:
                    try:
                        seq_num = int(parts[1])
                        t_type = parts[2]
                        d_cs = int(parts[3])
                        wipe = parts[4] == "wipe"
                        refs_by_seq.setdefault(seq_num, []).append(
                            RetimedReference(
                                track=1,
                                ref_track0_seq=seq_num,
                                start=ev.start,
                                duration_cs=d_cs,
                                tag_type=t_type,
                                has_wipe=wipe,
                            )
                        )
                    except (ValueError, IndexError):
                        pass

    romaji_mode = getattr(layout, "romanization_case", "as_is") if layout else "as_is"
    cur_event_idx: Optional[int] = None
    romaji_state: Optional[CaseState] = None

    for item in targets:
        bbox = boxes.get(item.id)
        event = events.get(item.event_line_index)
        if bbox is None or event is None:
            continue
        if cur_event_idx != item.event_line_index:
            cur_event_idx = item.event_line_index
            romaji_state = CaseState(capitalize_next=True)
        clean_romaji = re.sub(r"[\[\]]", "", item.romanization).strip()
        if not clean_romaji:
            continue
        if romaji_mode and romaji_mode != "as_is":
            clean_romaji = apply_text_case(clean_romaji, romaji_mode, state=romaji_state)
            if r"\N" in item.raw_text or r"\n" in item.raw_text or "\n" in item.visible_text:
                if romaji_state is not None:
                    romaji_state.capitalize_next = True
        style = styles.get(event.style.casefold(), fallback)
        font_size = max(1.0, style.font_size * float(size_ratio))
        outline = max(0.0, style.outline * float(size_ratio))
        shadow = max(0.0, style.shadow * float(size_ratio))
        gap = max(2, int(round(style.font_size * 0.08)))
        x = int(round(bbox.x + bbox.width / 2))
        y = max(0, int(round(bbox.y - gap + offset_y)))

        is_unspoken = _is_unspoken_syllable(item, style)
        if is_unspoken:
            bgr, alpha = _ass_colour_and_alpha(style.secondary_colour)
            colour = rf"\1c&H{bgr}&\2c&H{bgr}&\1a&H{alpha}&\2a&H{alpha}&"
        elif item.burst_marked:
            syl_col, syl_dyn = burst_syllable_style(item, document.karaoke_syllables(), layout)
            c = syl_col if syl_col.endswith("&") else (syl_col + "&")
            colour = rf"\1c{c}" + syl_dyn
        else:
            colour = ""

        delay_cs = max(0, int(round((item.start - event.start) * 100.0)))
        delay_tag = rf"{{\k{delay_cs}}}" if delay_cs > 0 else ""
        karaoke_tag = rf"{{\{item.tag_type.value}{item.duration_cs}}}"

        tags = (
            rf"\an2\pos({x},{y})\fs{font_size:.3f}"
            rf"\bord{outline:.3f}\shad{shadow:.3f}{colour}"
        )
        try:
            layer = str(int(event.layer) + 1)
        except ValueError:
            layer = "1"
        lines.append(
            "Dialogue: " + ",".join([
                layer, event.start_raw, event.end_raw, event.style,
                "KaraokeRomanization", "0", "0", "0", "",
                "{" + tags + "}" + delay_tag + karaoke_tag + clean_romaji,
            ])
        )

        seq = track0_id_to_seq.get(item.id)
        if seq and seq in refs_by_seq:
            try:
                ov_layer = str(int(event.layer) + 2)
            except ValueError:
                ov_layer = "2"
            for ref in refs_by_seq[seq]:
                ov_start = ref.start
                ov_end = (
                    ov_start + (ref.duration_cs / 100.0)
                    if ref.has_wipe
                    else event.end
                )
                if ov_end <= ov_start:
                    continue
                ov_tags = (
                    rf"\an2\pos({x},{y})\fs{font_size:.3f}"
                    rf"\bord{outline:.3f}\shad{shadow:.3f}\2a&HFF&\3a&HFF&\4a&HFF&"
                )
                ov_karaoke = rf"{{\{ref.tag_type}{ref.duration_cs}}}"
                lines.append(
                    "Dialogue: " + ",".join([
                        ov_layer,
                        format_ass_time(ov_start),
                        format_ass_time(ov_end),
                        event.style,
                        "KaraokeRomanization", "0", "0", "0",
                        f"retimed_romaji:{seq}",
                        "{" + ov_tags + "}" + ov_karaoke + clean_romaji,
                    ])
                )
    _insert_event_lines(document, lines)
    return len(lines)


def alpha_bbox(rgba: bytes, width: int, height: int, *, threshold: int = 1) -> Optional[CropRect]:
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA byte count does not match dimensions")
    # Extract and scan the alpha plane with C-backed bytes operations.  The old
    # per-pixel Python loop held the GIL for millions of iterations on the tall
    # measurement canvas and made Tk window movement visibly stutter.
    threshold = max(0, min(256, int(threshold)))
    if threshold == 0:
        return CropRect(0, 0, width, height)
    alpha = rgba[3::4]
    if threshold > 1:
        table = bytes(0 if value < threshold else value for value in range(256))
        alpha = alpha.translate(table)
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y in range(height):
        row = alpha[y * width:(y + 1) * width]
        visible = row.strip(b"\0")
        if not visible:
            continue
        left = len(row) - len(row.lstrip(b"\0"))
        right = len(row.rstrip(b"\0")) - 1
        min_x = min(min_x, left)
        max_x = max(max_x, right)
        min_y = min(min_y, y)
        max_y = y
    if max_x < min_x or max_y < min_y:
        return None
    return CropRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def burst_counter_regions(
    document: AssDocument,
    timing_overrides: Optional[Mapping[str, tuple[float, float]]] = None,
) -> tuple[BurstCounterRegion, ...]:
    """Return contiguous visible syllable groups carrying the burst colour."""
    groups: list[list[KaraokeSyllable]] = []
    current: list[KaraokeSyllable] = []
    for syllable in document.karaoke_syllables():
        visible = bool(syllable.visible_text.strip())
        if syllable.burst_marked and visible:
            current.append(syllable)
        elif not syllable.burst_marked and current:
            # Even a timing-only karaoke tag can carry the colour reset between
            # two authored bursts; do not silently merge those measurements.
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    regions: list[BurstCounterRegion] = []
    for group in groups:
        def bounds(item: KaraokeSyllable) -> tuple[float, float]:
            if timing_overrides is not None and item.id in timing_overrides:
                start, end = timing_overrides[item.id]
                return float(start), float(end)
            return float(item.start), float(item.end)

        start = bounds(group[0])[0]
        end = bounds(group[-1])[1]
        if end <= start:
            continue
        regions.append(BurstCounterRegion(
            start,
            end,
            tuple(bounds(s)[0] for s in group),
        ))
    return tuple(regions)


def build_burst_counter_plan(
    document: AssDocument,
    *,
    duration: Optional[float] = None,
    tick_seconds: float = 0.01,
    timing_overrides: Optional[Mapping[str, tuple[float, float]]] = None,
    round_summary_seconds: bool = False,
    custom_summary: str = "",
) -> BurstCounterPlan:
    """Build stopwatch/count cues followed by a persistent SPS summary."""
    if tick_seconds <= 0:
        raise ValueError("Burst counter tick must be positive")
    regions = burst_counter_regions(document, timing_overrides)
    natural_duration = max_dialogue_end(document)
    duration = natural_duration if duration is None else float(duration)
    if regions:
        duration = max(duration, regions[-1].end)
    if duration <= 0:
        raise ValueError("No positive duration is available for the burst counter")
    step_cs = max(1, int(round(tick_seconds * 100.0)))
    cues: list[BurstCounterCue] = []
    for index, region in enumerate(regions):
        start_cs = max(0, int(round(region.start * 100.0)))
        end_cs = max(start_cs + 1, int(round(region.end * 100.0)))
        onset_cs = tuple(int(round(value * 100.0)) for value in region.syllable_starts)
        for current_cs in range(start_cs, end_cs, step_cs):
            cue_end_cs = min(end_cs, current_cs + step_cs)
            current = current_cs / 100.0
            cue_end = cue_end_cs / 100.0
            count = sum(1 for onset in onset_cs if onset <= current_cs)
            elapsed = max(0.0, current - region.start)
            cues.append(BurstCounterCue(current, cue_end, f"{count} // {elapsed:.2f}s"))
        summary_end = regions[index + 1].start if index + 1 < len(regions) else duration
        if summary_end > region.end + 1e-9:
            summary = custom_summary.strip()
            if not summary:
                if round_summary_seconds:
                    shown_seconds = max(1.0, float(math.floor(region.duration + 0.5)))
                    shown_sps = region.count / shown_seconds
                    summary = (
                        f"{shown_sps:.2f} SPS // {region.count} "
                        f"in {shown_seconds:g}s"
                    )
                else:
                    summary = region.summary
            cues.append(BurstCounterCue(region.end, summary_end, summary))
    return BurstCounterPlan(duration, regions, tuple(cues))


def slice_burst_counter_plan(
    plan: BurstCounterPlan,
    start: float,
    end: float,
) -> BurstCounterPlan:
    """Clip an absolute counter plan to a zero-based render interval."""
    start, end = float(start), float(end)
    if end <= start:
        raise ValueError("Burst counter slice must have a positive duration")
    cues = tuple(
        BurstCounterCue(
            max(cue.start, start) - start,
            min(cue.end, end) - start,
            cue.text,
        )
        for cue in plan.cues
        if cue.end > start and cue.start < end
    )
    shifted_regions = tuple(
        BurstCounterRegion(
            region.start - start,
            region.end - start,
            tuple(value - start for value in region.syllable_starts),
        )
        for region in plan.regions
    )
    return BurstCounterPlan(end - start, shifted_regions, cues)


def _burst_counter_probe_document(
    text: str,
    settings: BurstCounterSettings,
    font_size: float,
) -> AssDocument:
    escaped = text.replace("{", r"\{").replace("}", r"\}")
    style = settings.resolved_text_style()
    payload = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 8192\n"
        "PlayResY: 1024\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style.ass_line(name='Counter', font_size=font_size)}\n"
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Counter,,0,0,0,,{{\\an7\\pos(128,128)}}{escaped}\n"
    )
    return AssDocument.from_text(payload)


def measure_burst_counter_layout(
    plan: BurstCounterPlan,
    *,
    ffmpeg: str | Path = "ffmpeg",
    settings: BurstCounterSettings = BurstCounterSettings(),
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
) -> BurstCounterLayout:
    """Measure the longest information line with the same libass renderer."""
    settings.validate()
    if not plan.regions:
        raise ValueError("ASS does not contain a coloured burst")
    font_size = float(settings.resolved_text_style().font_size)
    for _attempt in range(4):
        probe = _burst_counter_probe_document(plan.max_text, settings, font_size)
        rgba, width, height = render_rgba_frame(
            probe, ffmpeg=ffmpeg, width=8192, height=1024, timestamp=0.5
        )
        bbox = alpha_bbox(rgba, width, height)
        if bbox is None:
            raise RuntimeError("libass rendered no burst counter text")
        box_width = bbox.width + settings.text_padding * 2
        box_height = bbox.height + settings.text_padding * 2
        outer_width = box_width + settings.outline * 2
        outer_height = box_height + settings.outline * 2
        fits_width = max_width is None or outer_width <= max_width
        fits_height = max_height is None or outer_height <= max_height
        if fits_width and fits_height:
            return BurstCounterLayout(
                bbox.width, bbox.height, box_width, box_height,
                outer_width, outer_height, font_size, plan.max_text,
            )
        ratios = [1.0]
        if max_width is not None:
            ratios.append(max_width / max(1, outer_width))
        if max_height is not None:
            ratios.append(max_height / max(1, outer_height))
        next_size = math.floor(font_size * min(ratios) * 0.97)
        if next_size < 10 or next_size >= font_size:
            break
        font_size = float(next_size)
    raise ValueError(
        "Burst SPS table does not fit the rendered frame even at the minimum readable font size"
    )


def build_burst_counter_document(
    plan: BurstCounterPlan,
    layout: BurstCounterLayout,
    *,
    frame_width: int,
    frame_height: int,
    settings: BurstCounterSettings = BurstCounterSettings(),
    window_start: float = 0.0,
    window_end: Optional[float] = None,
    bottom_right: bool = True,
) -> AssDocument:
    """Create the independent ASS layer rendered after the karaoke crop."""
    settings.validate()
    if not plan.regions:
        raise ValueError("ASS does not contain a coloured burst")
    frame_width, frame_height = int(frame_width), int(frame_height)
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("Burst counter frame dimensions must be positive")
    window_start = max(0.0, float(window_start))
    window_end = plan.duration if window_end is None else min(plan.duration, float(window_end))
    if window_end <= window_start:
        raise ValueError("Burst counter render window has no positive duration")
    visible_cues = [cue for cue in plan.cues if cue.end > window_start and cue.start < window_end]
    if not visible_cues:
        raise ValueError("The selected interval does not contain burst SPS information")

    if bottom_right:
        x = frame_width - settings.frame_margin - settings.outline - layout.box_width
        y = frame_height - settings.frame_margin - settings.outline - layout.box_height
    else:
        x = settings.outline
        y = settings.outline
    if x < settings.outline or y < settings.outline:
        raise ValueError("Burst SPS table does not fit inside the rendered frame")
    center_x = x + layout.box_width / 2.0
    center_y = y + layout.box_height / 2.0 + settings.font_offset_y
    box_start = max(window_start, visible_cues[0].start) - window_start
    box_end = window_end - window_start
    vector = f"m 0 0 l {layout.box_width} 0 l {layout.box_width} {layout.box_height} l 0 {layout.box_height}"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {frame_width}\n"
        f"PlayResY: {frame_height}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{settings.resolved_text_style().ass_line(name='Counter', font_size=layout.font_size)}\n"
        "Style: Card,Arial,10,&H00000000,&H00000000,&H00FFFFFF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [
        "Dialogue: 0,"
        f"{format_ass_time(box_start)},{format_ass_time(box_end)},Card,,0,0,0,,"
        f"{{\\an7\\pos({x},{y})\\p1\\bord{settings.outline}\\shad0\\1c&H000000&\\3c&HFFFFFF&}}{vector}"
    ]
    for cue in visible_cues:
        start = max(cue.start, window_start) - window_start
        end = min(cue.end, window_end) - window_start
        if end <= start + 1e-9:
            continue
        escaped = cue.text.replace("{", r"\{").replace("}", r"\}")
        lines.append(
            "Dialogue: 1,"
            f"{format_ass_time(start)},{format_ass_time(end)},Counter,,0,0,0,,"
            f"{{\\an5\\pos({center_x:.2f},{center_y:.2f})}}{escaped}"
        )
    return AssDocument.from_text(header + "\n".join(lines) + "\n")


def build_burst_style_preview_document(
    style: AssTextStyle,
    *,
    text: str = "13.00 SPS // 13 in 1.00s",
    width: int = 720,
    height: int = 180,
    burst_color_mode: str = "single",
    burst_base_color: str = "&H0000FF&",
    burst_alt_color: str = "&H0080FF&",
    burst_hue_offset: float = 30.0,
    burst_pulse_hz: float = 2.0,
    font_offset_y: int = 0,
) -> AssDocument:
    """Build a real-libass preview displaying the SPS card and sample burst syllables."""
    style.validate()
    escaped = text.replace("{", r"\{").replace("}", r"\}")

    show_sample_karaoke = height >= 180
    if show_sample_karaoke:
        card_y = 12
        card_h = min(70, int(height * 0.35))
        box_width, box_height = max(1, width - 50), card_h
        counter_y = card_y + card_h / 2.0 + font_offset_y
        karaoke_y = card_y + card_h + max(20, int((height - (card_y + card_h)) / 2.0))
    else:
        card_y = 25
        card_h = max(1, height - 50)
        box_width, box_height = max(1, width - 50), card_h
        counter_y = height / 2.0 + font_offset_y
        karaoke_y = 0

    vector = f"m 0 0 l {box_width} 0 l {box_width} {box_height} l 0 {box_height}"
    lines = [
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Card,,0,0,0,,{{\\an7\\pos(25,{card_y})\\p1\\bord5\\shad0\\1c&H000000&\\3c&HFFFFFF&}}{vector}",
        f"Dialogue: 1,0:00:00.00,0:00:01.00,Counter,,0,0,0,,{{\\an5\\pos({width / 2:.2f},{counter_y:.2f})}}{escaped}",
    ]

    if show_sample_karaoke:
        base = normalize_ass_colour(burst_base_color)
        alt = normalize_ass_colour(burst_alt_color)
        mode = burst_color_mode or "single"
        words = ["Бёрст ", "слог ", "раз ", "два ", "три "]
        sample_parts = []
        k = len(words)
        total_dur_ms = 1000
        accum_ms = 0
        dur_ms = 200
        for idx, w in enumerate(words):
            if mode == "alternate":
                c = base if (idx % 2 == 0) else alt
                tag = rf"\1c{c}"
            elif mode == "gradient":
                t = (idx / (k - 1)) if k > 1 else 0.0
                c = interpolate_cube_surface(base, alt, t)
                tag = rf"\1c{c}"
            elif mode == "dynamic":
                init_tag, anim = generate_burst_pulse_tags(
                    base, alt,
                    start_ms=accum_ms,
                    end_ms=total_dur_ms,
                    hz=burst_pulse_hz,
                    phase_offset_ms=0,
                )
                tag = init_tag + anim
                accum_ms += dur_ms
            else:  # single
                tag = rf"\1c{base}"
            sample_parts.append(rf"{{\k20{tag}}}{w}")
        sample_parts.append(r"{\k20\1c}текст")
        sample_text = "".join(sample_parts)
        fs = min(float(style.font_size), 36.0)
        lines.append(
            f"Dialogue: 2,0:00:00.00,0:00:01.00,Counter,,0,0,0,,{{\\an5\\pos({width / 2:.2f},{karaoke_y:.2f})\\fs{fs:.1f}}}{sample_text}"
        )

    payload = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {int(width)}\n"
        f"PlayResY: {int(height)}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style.ass_line(name='Counter')}\n"
        "Style: Card,Arial,10,&H00000000,&H00000000,&H00FFFFFF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(lines) + "\n"
    )
    return AssDocument.from_text(payload)


def padded_crop(
    bbox: CropRect,
    canvas_width: int,
    canvas_height: int,
    settings: RenderLayoutSettings,
) -> CropRect:
    total_w = bbox.width + settings.padding_left + settings.padding_right
    total_h = bbox.height + settings.padding_top + settings.padding_bottom

    if total_w <= canvas_width:
        cx = (bbox.x + bbox.right) / 2.0
        x0 = max(0, min(canvas_width - total_w, int(round(cx - total_w / 2.0))))
        x1 = x0 + total_w
    else:
        x0 = max(0, bbox.x - settings.padding_left)
        x1 = min(canvas_width, bbox.right + settings.padding_right)

    if total_h <= canvas_height:
        cy = (bbox.y + bbox.bottom) / 2.0
        y0 = max(0, min(canvas_height - total_h, int(round(cy - total_h / 2.0))))
        y1 = y0 + total_h
    else:
        y0 = max(0, bbox.y - settings.padding_top)
        y1 = min(canvas_height, bbox.bottom + settings.padding_bottom)

    rect = CropRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
    if settings.even_dimensions:
        rect = make_even_crop(rect, canvas_width, canvas_height)
    return rect


def make_even_crop(rect: CropRect, canvas_width: int, canvas_height: int) -> CropRect:
    rect = rect.clamp(canvas_width, canvas_height)
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    if w % 2:
        if x + w < canvas_width:
            w += 1
        elif x > 0:
            x -= 1
            w += 1
        elif w > 1:
            w -= 1
    if h % 2:
        if y + h < canvas_height:
            h += 1
        elif y > 0:
            y -= 1
            h += 1
        elif h > 1:
            h -= 1
    return CropRect(x, y, max(1, w), max(1, h)).clamp(canvas_width, canvas_height)


def dialogue_line_count(document: AssDocument) -> int:
    """Return the largest explicit row count among Dialogue events on track 0."""
    track0_dialogues = [
        event for event in document.events()
        if event.kind == "Dialogue" and _is_track0_event(event)
    ]
    if not track0_dialogues:
        track0_dialogues = [event for event in document.events() if event.kind == "Dialogue"]
    counts = [
        1 + len(_LINE_BREAK_RE.findall(event.text))
        for event in track0_dialogues
    ]
    return max(counts, default=1)


def vertical_viewport_crop(
    crop: CropRect,
    content_bbox: CropRect,
    line_count: int,
    visible_lines: int,
    canvas_width: int,
    canvas_height: int,
    *,
    base_crop: Optional[CropRect] = None,
    even_dimensions: bool = True,
) -> CropRect:
    """Size a vertical viewport while retaining the measured side padding."""
    crop = crop.clamp(canvas_width, canvas_height)
    line_count = max(1, int(line_count))
    visible_lines = max(1, min(int(visible_lines), line_count))
    pad_reference = base_crop.clamp(canvas_width, canvas_height) if base_crop is not None else crop
    vertical_padding = max(0, pad_reference.height - content_bbox.height)
    if visible_lines >= line_count:
        ref_h = min(canvas_height, content_bbox.height + vertical_padding)
        y = max(0, min(canvas_height - ref_h, pad_reference.y))
        result = CropRect(crop.x, y, crop.width, ref_h).clamp(canvas_width, canvas_height)
        return make_even_crop(result, canvas_width, canvas_height) if even_dimensions else result
    line_pitch = content_bbox.height / line_count
    height = min(canvas_height, max(1, int(math.ceil(line_pitch * visible_lines + vertical_padding))))
    start_y = max(crop.y, int(round(content_bbox.y + line_pitch - height)))
    y = max(crop.y, min(crop.bottom - height, start_y))
    viewport = CropRect(crop.x, y, crop.width, height).clamp(canvas_width, canvas_height)
    if even_dimensions:
        viewport = make_even_crop(viewport, canvas_width, canvas_height)
    return viewport


def build_vertical_follow_plan(
    document: AssDocument,
    content_bbox: CropRect,
    crop: CropRect,
    canvas_width: int,
    canvas_height: int,
    settings: VerticalFollowSettings,
    *,
    base_crop: Optional[CropRect] = None,
) -> VerticalFollowPlan:
    """Map first-syllable timings per row to smooth vertical crop targets."""
    settings.validate()
    line_count = dialogue_line_count(document)
    if not settings.enabled:
        return VerticalFollowPlan(
            crop, ((0.0, crop.y),), settings.easing_seconds, settings.continuous,
            settings.smooth_percent,
        )
    viewport = vertical_viewport_crop(
        crop, content_bbox, line_count, settings.visible_lines,
        canvas_width, canvas_height,
        base_crop=base_crop,
    )
    if settings.visible_lines >= line_count:
        return VerticalFollowPlan(
            viewport, ((0.0, viewport.y),), settings.easing_seconds, settings.continuous,
            settings.smooth_percent,
        )

    dialogues = [
        event for event in document.events()
        if event.kind == "Dialogue" and _is_track0_event(event)
    ]
    if not dialogues:
        dialogues = [event for event in document.events() if event.kind == "Dialogue"]
    if not dialogues:
        return VerticalFollowPlan(
            viewport, ((0.0, viewport.y),), settings.easing_seconds, settings.continuous,
            settings.smooth_percent,
        )
    tracked = max(dialogues, key=lambda event: len(_LINE_BREAK_RE.findall(event.text)))
    syllables = [
        syllable for syllable in document.karaoke_syllables()
        if getattr(syllable, "track", 0) == 0
        and syllable.event_line_index == tracked.line_index
        and syllable.visible_text.strip()
    ]
    line_pitch = content_bbox.height / max(1, line_count)
    bound_ref = crop.clamp(canvas_width, canvas_height)
    min_bound = bound_ref.y
    max_bound = max(min_bound, bound_ref.bottom - viewport.height)
    start_y = max(min_bound, int(round(content_bbox.y + line_pitch - viewport.height)))
    end_y = min(max_bound, int(round(content_bbox.bottom - line_pitch)))
    end_y = max(start_y, end_y)

    frames: list[tuple[float, int]] = []
    seen_lines: set[int] = set()
    for syllable in syllables:
        prefix = tracked.text[:syllable.tag_block_start]
        line = min(line_count - 1, len(_LINE_BREAK_RE.findall(prefix)))
        if line in seen_lines:
            continue
        seen_lines.add(line)
        if line_count > 1:
            progress = line / (line_count - 1)
            target_y = int(round(start_y + progress * (end_y - start_y)))
        else:
            target_y = start_y
        y = max(min_bound, min(max_bound, target_y))
        if frames and frames[-1][1] == y:
            continue
        frames.append((max(0.0, syllable.start), y))
    if not frames:
        frames.append((0.0, viewport.y))
    elif frames[0][0] > 0:
        frames.insert(0, (0.0, frames[0][1]))
    return VerticalFollowPlan(
        viewport, tuple(frames), settings.easing_seconds, settings.continuous,
        settings.smooth_percent,
    )


def measure_render_layout(
    document: AssDocument,
    settings: RenderLayoutSettings,
    *,
    ffmpeg: str | Path = "ffmpeg",
    render_range: Optional[ResolvedRenderRange] = None,
) -> RenderMeasurement:
    geometry_doc, dynamic = prepare_geometry_document(document, settings, render_range=render_range)
    source_x, source_y = ass_playres(geometry_doc)
    width, height = source_x, source_y
    previous_bbox: Optional[CropRect] = None
    max_dimension = 16384

    # A single Dialogue may contain dozens of explicit \N rows.  Rendering it
    # at the source PlayRes first clips the rows above/below the frame, after
    # which alpha-bbox can only measure the small visible remnant.  Grow a
    # render-only canvas until the visible bounds stop touching an edge.  A
    # stable edge-touch on two canvases means intentional edge alignment, not
    # clipping, so it is safe to stop as well.
    for _attempt in range(8):
        attempt_doc = AssDocument.from_text(geometry_doc.dumps())
        attempt_doc.bom = geometry_doc.bom
        _set_ass_playres(attempt_doc, width, height)
        materialize_romanization_overlays(attempt_doc, ffmpeg=ffmpeg, layout=settings)
        rgba, width, height = render_rgba_frame(
            attempt_doc, ffmpeg=ffmpeg, width=width, height=height, timestamp=5.0
        )
        bbox = alpha_bbox(rgba, width, height)
        if bbox is None:
            raise RuntimeError("libass rendered no visible subtitle pixels")
        touches_x = bbox.x <= 1 or bbox.right >= width - 1
        touches_y = bbox.y <= 1 or bbox.bottom >= height - 1
        if not touches_x and not touches_y:
            break
        stable = (
            previous_bbox is not None
            and abs(previous_bbox.width - bbox.width) <= 2
            and abs(previous_bbox.height - bbox.height) <= 2
        )
        if stable:
            break
        next_width = min(max_dimension, width * 2) if touches_x else width
        next_height = min(max_dimension, height * 2) if touches_y else height
        if (next_width, next_height) == (width, height):
            raise RuntimeError(
                f"Subtitle geometry is still clipped at the {width}x{height} preview limit"
            )
        previous_bbox = bbox
        width, height = next_width, next_height
    else:
        raise RuntimeError("Could not find an unclipped subtitle preview canvas")

    crop = padded_crop(bbox, width, height, settings)
    return RenderMeasurement(
        width, height, bbox, crop, rgba, dynamic,
        source_playres_x=source_x, source_playres_y=source_y,
        line_count=dialogue_line_count(geometry_doc),
    )


def scaled_crop_rect(
    crop: CropRect,
    canvas_width: int,
    canvas_height: int,
    scale: float,
    *,
    even_dimensions: bool = False,
) -> CropRect:
    """Map a crop from ASS canvas coordinates to the scaled video canvas."""
    scale = float(scale)
    if scale <= 0:
        raise ValueError("scale must be positive")
    scaled_width = max(2, int(round(canvas_width * scale)))
    scaled_height = max(2, int(round(canvas_height * scale)))
    crop = crop.clamp(canvas_width, canvas_height)
    ratio_x = scaled_width / canvas_width
    ratio_y = scaled_height / canvas_height
    x0 = int(round(crop.x * ratio_x))
    y0 = int(round(crop.y * ratio_y))
    x1 = int(round(crop.right * ratio_x))
    y1 = int(round(crop.bottom * ratio_y))
    result = CropRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)).clamp(
        scaled_width, scaled_height
    )
    if even_dimensions:
        result = make_even_crop(result, scaled_width, scaled_height)
    return result


def max_dialogue_end(document: AssDocument) -> float:
    values = [event.end for event in document.events() if event.kind == "Dialogue"]
    return max(values, default=0.0)


def probe_video_frame_size(
    media: str | Path, ffmpeg: str | Path,
) -> Optional[tuple[int, int]]:
    """Read the encoded first video stream size using the paired ffprobe."""
    ffprobe = resolve_ffprobe(ffmpeg)
    if ffprobe is None:
        return None
    try:
        proc = subprocess.run(
            [
                str(ffprobe), "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                str(Path(media).resolve()),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", timeout=15, check=False,
            env=media_tool_subprocess_env(ffprobe),
        )
        if proc.returncode != 0:
            return None
        width_raw, height_raw = (proc.stdout or "").strip().split("x", 1)
        width, height = int(width_raw), int(height_raw)
        if width > 0 and height > 0:
            return width, height
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return None


def _vertical_crop_y_expression(
    plan: VerticalFollowPlan,
    *,
    source_height: int,
    scaled_height: int,
    output_height: int,
) -> str:
    """Build a per-frame FFmpeg expression with cubic smoothstep easing."""
    ratio = scaled_height / source_height
    max_y = max(0, scaled_height - output_height)
    frames: list[tuple[float, int]] = []
    for timestamp, source_y in plan.keyframes:
        y = max(0, min(max_y, int(round(source_y * ratio))))
        if frames and frames[-1][1] == y:
            continue
        frames.append((max(0.0, float(timestamp)), y))
    if len(frames) <= 1:
        return str(frames[0][1] if frames else 0)

    def number(value: float) -> str:
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"

    def _build_balanced_tree(segments: list[tuple[float, float, str]]) -> str:
        if len(segments) == 1:
            return segments[0][2]
        mid = len(segments) // 2
        split_t = segments[mid][0]
        left = _build_balanced_tree(segments[:mid])
        right = _build_balanced_tree(segments[mid:])
        return f"if(lt(t\\,{number(split_t)})\\,{left}\\,{right})"

    if plan.continuous:
        p = max(0.0, min(100.0, float(plan.smooth_percent)))
        t0, y0 = frames[0]
        tn, yn = frames[-1]
        v_global = (yn - y0) / max(0.000001, tn - t0)

        if p >= 99.999:
            lin = f"({y0}+{number(v_global)}*(t-{number(t0)}))"
            return f"if(lt(t\\,{number(t0)})\\,{y0}\\,if(lt(t\\,{number(tn)})\\,{lin}\\,{yn}))"

        n = len(frames)
        velocities = []
        durations = []
        for i in range(n - 1):
            dur = max(0.000001, frames[i + 1][0] - frames[i][0])
            durations.append(dur)
            velocities.append((frames[i + 1][1] - frames[i][1]) / dur)

        gamma = min(1.0, p / 50.0)
        taus = [0.0] * n
        for i in range(1, n - 1):
            max_tau = 0.5 * min(durations[i - 1], durations[i])
            taus[i] = gamma * max_tau

        intervals: list[tuple[float, float, str]] = []
        for i in range(n - 1):
            ti, yi = frames[i]
            t_next, y_next = frames[i + 1]
            vi = velocities[i]
            tau_start = taus[i]
            tau_end = taus[i + 1]

            lin_start = ti + tau_start
            lin_end = t_next - tau_end
            if lin_end - lin_start > 0.000001:
                lin_expr = f"({yi}+{number(vi)}*(t-{number(ti)}))"
                intervals.append((lin_start, lin_end, lin_expr))

            if i < n - 2 and tau_end > 0.000001:
                t_trans_start = t_next - tau_end
                t_trans_end = t_next + tau_end
                v_curr = vi
                v_next = velocities[i + 1]
                two_tau = 2.0 * tau_end
                u_str = f"((t-{number(t_trans_start)})/{number(two_tau)})"
                int_str = f"({u_str}*{u_str}*{u_str}*(1-0.5*{u_str}))"
                dv = v_next - v_curr
                y_trans_start = y_next - v_curr * tau_end
                trans_expr = (
                    f"({number(y_trans_start)}+{number(two_tau)}*("
                    f"{number(v_curr)}*{u_str}+{number(dv)}*{int_str}))"
                )
                intervals.append((t_trans_start, t_trans_end, trans_expr))

        beta = max(0.0, (p - 50.0) / 50.0) if p > 50.0 else 0.0
        processed_intervals: list[tuple[float, float, str]] = []
        for start, end, expr in intervals:
            if beta > 0.000001:
                lin_expr = f"({y0}+{number(v_global)}*(t-{number(t0)}))"
                expr = f"((1-{number(beta)})*{expr}+{number(beta)}*{lin_expr})"
            processed_intervals.append((start, end, expr))

        if not processed_intervals:
            return str(frames[-1][1])

        segments = [(-float("inf"), processed_intervals[0][0], str(frames[0][1]))]
        segments.extend(processed_intervals)
        segments.append((processed_intervals[-1][1], float("inf"), str(frames[-1][1])))
        return _build_balanced_tree(segments)

    segments = []
    current_t = -float("inf")
    for index in range(1, len(frames)):
        start, target = frames[index]
        previous = frames[index - 1][1]
        next_start = frames[index + 1][0] if index + 1 < len(frames) else None
        duration = plan.easing_seconds
        if next_start is not None:
            duration = min(duration, max(0.0, next_start - start))
        if index == 1:
            segments.append((-float("inf"), start, str(previous)))
            current_t = start
        else:
            if start > current_t:
                segments.append((current_t, start, str(previous)))
                current_t = start
        if duration > 0.000001:
            end = start + duration
            u = f"((t-{number(start)})/{number(duration)})"
            smooth = f"({u}*{u}*(3-2*{u}))"
            eased = f"({previous}+({target - previous})*{smooth})"
            segments.append((start, end, eased))
            current_t = end
        else:
            current_t = start
    segments.append((current_t, float("inf"), str(frames[-1][1])))
    return _build_balanced_tree(segments)


def build_render_command(
    *,
    ffmpeg: str | Path,
    ass_filename: str,
    playres_x: int,
    playres_y: int,
    crop: CropRect,
    duration: float,
    output: str | Path,
    output_settings: RenderOutputSettings,
    audio_source: str | Path | None = None,
    render_range: Optional[ResolvedRenderRange] = None,
    has_audio: bool = True,
    vertical_follow: Optional[VerticalFollowPlan] = None,
    burst_ass_filename: Optional[str] = None,
) -> list[str]:
    """Build a tight standalone karaoke render from an already measured canvas."""
    output_settings.validate()
    if duration <= 0:
        raise ValueError("No positive subtitle duration is available")
    scale = float(output_settings.resolution_scale)
    canvas_x = max(2, int(round(playres_x * scale)))
    canvas_y = max(2, int(round(playres_y * scale)))
    effective_crop = vertical_follow.crop if vertical_follow is not None else crop
    output_crop = scaled_crop_rect(
        effective_crop, playres_x, playres_y, scale,
        even_dimensions=output_settings.profile == "black_mp4",
    )
    crop_y = str(output_crop.y)
    if vertical_follow is not None and len(vertical_follow.keyframes) > 1:
        crop_y = _vertical_crop_y_expression(
            vertical_follow,
            source_height=playres_y,
            scaled_height=canvas_y,
            output_height=output_crop.height,
        )
    crop_filter = (
        f"crop={output_crop.width}:{output_crop.height}:"
        f"{output_crop.x}:{crop_y}"
    )
    # The information card intentionally comes after the moving crop.  This
    # keeps it pinned to the bottom-right corner of the *output* frame while
    # the karaoke canvas moves behind it.
    burst_filter = f",subtitles={burst_ass_filename}:alpha=1" if burst_ass_filename else ""
    base = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]
    if output_settings.profile == "transparent_mov":
        base += [
            "-f", "lavfi", "-i",
            f"color=c=black@0.0:s={canvas_x}x{canvas_y}:r={output_settings.fps:g}:d={duration:.6f},format=rgba",
        ]
        vf = f"subtitles={ass_filename}:alpha=1,{crop_filter}{burst_filter},format=argb"
    else:
        base += [
            "-f", "lavfi", "-i",
            f"color=c=black:s={canvas_x}x{canvas_y}:r={output_settings.fps:g}:d={duration:.6f}",
        ]
        vf = f"subtitles={ass_filename}:alpha=1,{crop_filter}{burst_filter},format=yuv420p"

    use_audio = audio_source is not None and has_audio
    if use_audio:
        if render_range is not None:
            base += ["-ss", f"{render_range.render_start:.6f}"]
        base += ["-i", str(Path(audio_source).resolve())]

    base += ["-map", "0:v:0"]
    if use_audio:
        base += ["-map", "1:a:0"]
    base += ["-vf", vf]
    if output_settings.profile == "transparent_mov":
        base += ["-c:v", "qtrle", "-pix_fmt", "argb"]
    else:
        base += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]

    if use_audio:
        fades: list[str] = []
        if render_range is not None:
            if render_range.pre_roll > 0:
                fades.append(f"afade=t=in:st=0:d={render_range.pre_roll:.6f}")
            if render_range.post_roll > 0:
                fade_out_start = max(0.0, duration - render_range.post_roll)
                fades.append(f"afade=t=out:st={fade_out_start:.6f}:d={render_range.post_roll:.6f}")
        if fades:
            base += ["-af", ",".join(fades)]
        # Always transcode: arbitrary source codecs (FLAC/Opus/etc.) are not
        # necessarily legal in the selected container. MOV gets lossless PCM;
        # MP4 gets broadly compatible AAC.
        if output_settings.profile == "transparent_mov":
            base += ["-c:a", "pcm_s16le"]
        else:
            base += ["-c:a", "aac", "-b:a", "192k"]
        base += ["-map_metadata", "1"]
    else:
        base += ["-an"]
    base += ["-t", f"{duration:.6f}"]
    if Path(output).suffix.lower() in {".mp4", ".m4v", ".mov"}:
        base += ["-movflags", "+faststart"]
    base.append(str(output))
    return base


def render_karaoke_video(
    document: AssDocument,
    layout: RenderLayoutSettings,
    output: str | Path,
    *,
    crop: CropRect,
    base_crop: Optional[CropRect] = None,
    render_canvas: Optional[tuple[int, int]] = None,
    ffmpeg: str | Path = "ffmpeg",
    output_settings: RenderOutputSettings = RenderOutputSettings(),
    render_range: Optional[ResolvedRenderRange] = None,
    audio_source: str | Path | None = None,
    vertical_follow_settings: Optional[VerticalFollowSettings] = None,
    burst_counter_settings: Optional[BurstCounterSettings] = None,
    burst_timing_overrides: Optional[Mapping[str, tuple[float, float]]] = None,
    content_bbox: Optional[CropRect] = None,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Render the measured subtitle crop, optionally with transcoded source audio."""
    render_doc = prepare_render_document(document, layout, render_range=render_range)
    playres_x, playres_y = ass_playres(render_doc)
    if render_canvas is not None:
        canvas_x, canvas_y = map(int, render_canvas)
        if canvas_x < playres_x or canvas_y < playres_y:
            raise ValueError("Render canvas cannot be smaller than the source PlayRes")
        _set_ass_playres(render_doc, canvas_x, canvas_y)
        playres_x, playres_y = canvas_x, canvas_y
    materialize_romanization_overlays(render_doc, ffmpeg=ffmpeg, layout=layout)
    crop = crop.clamp(playres_x, playres_y)
    follow_plan: Optional[VerticalFollowPlan] = None
    if vertical_follow_settings is not None and vertical_follow_settings.enabled:
        if content_bbox is None:
            raise ValueError("content_bbox is required for vertical follow rendering")
        follow_plan = build_vertical_follow_plan(
            render_doc, content_bbox, crop, playres_x, playres_y,
            vertical_follow_settings,
            base_crop=base_crop,
        )
        if log:
            motion = (
                "continuous time-proportional glide"
                if vertical_follow_settings.continuous
                else f"cubic easing {follow_plan.easing_seconds:g} s"
            )
            log(
                f"Vertical follow crop: {follow_plan.crop.width}x{follow_plan.crop.height}; "
                f"{len(follow_plan.keyframes)} targets; "
                f"{motion}"
            )
    duration = render_range.duration if render_range is not None else max_dialogue_end(render_doc)
    target = Path(output).resolve()
    source_audio: Optional[Path] = None
    has_audio = False
    if audio_source is not None:
        source_audio = Path(audio_source).resolve()
        if not source_audio.exists():
            raise FileNotFoundError(source_audio)
        if source_audio == target:
            raise ValueError("Output file must differ from the source media")
        has_audio = probe_audio_bounds(source_audio, ffmpeg) is not None
        if log:
            if has_audio:
                codec = "PCM s16le" if output_settings.profile == "transparent_mov" else "AAC 192 kbps"
                log(f"Audio: {source_audio} -> {codec}")
            else:
                log(f"Audio: no audio stream found in {source_audio}; rendering video without audio")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="karaoke-render-video-") as td:
        _write_temp_ass(render_doc, td, "render.ass")
        burst_ass_filename: Optional[str] = None
        if burst_counter_settings is not None:
            burst_counter_settings.validate()
            source_style = burst_counter_settings.text_style or karaoke_text_style(document)
            burst_counter_settings = replace(
                burst_counter_settings,
                text_style=scale_ass_text_style(
                    source_style, output_settings.resolution_scale
                ),
            )
            # Build from the unmodified ASS so exact-SPS sidecar IDs still
            # match. A ranged render is then clipped and zero-based exactly as
            # the karaoke copy and source audio are.
            plan_duration = render_range.render_end if render_range is not None else duration
            counter_plan = build_burst_counter_plan(
                document,
                duration=plan_duration,
                tick_seconds=burst_counter_settings.tick_seconds,
                timing_overrides=burst_timing_overrides,
                round_summary_seconds=burst_counter_settings.round_summary_seconds,
                custom_summary=burst_counter_settings.custom_summary,
            )
            if render_range is not None:
                counter_plan = slice_burst_counter_plan(
                    counter_plan, render_range.render_start, render_range.render_end
                )
            if not counter_plan.regions:
                raise ValueError(
                    "Show burst SPS включён, но в ASS нет слогов, окрашенных как burst"
                )
            effective_crop = follow_plan.crop if follow_plan is not None else crop
            output_crop = scaled_crop_rect(
                effective_crop,
                playres_x,
                playres_y,
                output_settings.resolution_scale,
                even_dimensions=output_settings.profile == "black_mp4",
            )
            available_width = output_crop.width - burst_counter_settings.frame_margin * 2
            available_height = output_crop.height - burst_counter_settings.frame_margin * 2
            if available_width <= 0 or available_height <= 0:
                raise ValueError("Rendered frame is too small for the Burst SPS card margins")
            counter_layout = measure_burst_counter_layout(
                counter_plan,
                ffmpeg=ffmpeg,
                settings=burst_counter_settings,
                max_width=available_width,
                max_height=available_height,
            )
            counter_doc = build_burst_counter_document(
                counter_plan,
                counter_layout,
                frame_width=output_crop.width,
                frame_height=output_crop.height,
                settings=burst_counter_settings,
                bottom_right=True,
            )
            burst_ass_filename = "burst-counter.ass"
            _write_temp_ass(counter_doc, td, burst_ass_filename)
            if log:
                log(
                    f"Burst SPS: {len(counter_plan.regions)} region(s); "
                    f"card {counter_layout.outer_width}x{counter_layout.outer_height}; "
                    f"post-crop bottom-right margin {burst_counter_settings.frame_margin}px; "
                    f"exact timing overrides {len(burst_timing_overrides or {})}"
                )
        cmd = build_render_command(
            ffmpeg=ffmpeg,
            ass_filename="render.ass",
            playres_x=playres_x,
            playres_y=playres_y,
            crop=crop,
            duration=duration,
            output=target,
            output_settings=output_settings,
            audio_source=source_audio,
            render_range=render_range,
            has_audio=has_audio,
            vertical_follow=follow_plan,
            burst_ass_filename=burst_ass_filename,
        )
        _run_ffmpeg_progress(
            cmd, cwd=td, duration=duration, progress=progress, log=log,
            stage="FFmpeg: standalone karaoke render",
            cancel_event=cancel_event,
        )
    # Verify the muxed frame itself; this catches stale/full-frame render paths
    # and codec rounding instead of reporting a misleading successful crop.
    effective_crop = follow_plan.crop if follow_plan is not None else crop
    expected_crop = scaled_crop_rect(
        effective_crop, playres_x, playres_y, output_settings.resolution_scale,
        even_dimensions=output_settings.profile == "black_mp4",
    )
    expected_size = (expected_crop.width, expected_crop.height)
    ffprobe = resolve_ffprobe(ffmpeg)
    if ffprobe is not None:
        actual_size = probe_video_frame_size(target, ffmpeg)
        if actual_size is None:
            raise RuntimeError("ffprobe could not verify the rendered video frame size")
        if actual_size != expected_size:
            raise RuntimeError(
                f"Rendered video has unexpected size {actual_size[0]}x{actual_size[1]}; "
                f"expected measured crop {expected_size[0]}x{expected_size[1]}"
            )
        if has_audio and probe_audio_bounds(target, ffmpeg) is None:
            raise RuntimeError("Rendered video is missing the expected source audio track")
        if log:
            audio_note = " + audio verified" if has_audio else ""
            log(f"Verified output: {actual_size[0]}x{actual_size[1]}{audio_note}")
    return target


def render_burst_counter_video(
    document: AssDocument,
    output: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    output_settings: RenderOutputSettings = RenderOutputSettings(),
    settings: BurstCounterSettings = BurstCounterSettings(),
    duration: Optional[float] = None,
    active_interval_only: bool = False,
    burst_timing_overrides: Optional[Mapping[str, tuple[float, float]]] = None,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Render only the Burst SPS card at the card's native frame size."""
    output_settings.validate()
    settings.validate()
    settings = replace(
        settings,
        text_style=settings.text_style or karaoke_text_style(document),
    )
    plan = build_burst_counter_plan(
        document,
        duration=duration,
        tick_seconds=settings.tick_seconds,
        timing_overrides=burst_timing_overrides,
        round_summary_seconds=settings.round_summary_seconds,
        custom_summary=settings.custom_summary,
    )
    if not plan.regions:
        raise ValueError("В ASS нет слогов, окрашенных как burst")
    layout = measure_burst_counter_layout(plan, ffmpeg=ffmpeg, settings=settings)

    frame_width = layout.outer_width
    frame_height = layout.outer_height
    if output_settings.profile == "black_mp4":
        frame_width += frame_width % 2
        frame_height += frame_height % 2
    window_start = plan.first_start if active_interval_only else 0.0
    window_end = plan.duration
    counter_doc = build_burst_counter_document(
        plan,
        layout,
        frame_width=frame_width,
        frame_height=frame_height,
        settings=settings,
        window_start=window_start,
        window_end=window_end,
        bottom_right=False,
    )
    render_duration = window_end - window_start
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    # A separate counter is already measured in output pixels.  Applying the
    # main karaoke resolution multiplier would make the video larger than the
    # information card, contrary to this export mode's contract.
    native_output = replace(output_settings, resolution_scale=1.0)
    crop = CropRect(0, 0, frame_width, frame_height)
    with tempfile.TemporaryDirectory(prefix="karaoke-burst-counter-") as td:
        _write_temp_ass(counter_doc, td, "counter.ass")
        cmd = build_render_command(
            ffmpeg=ffmpeg,
            ass_filename="counter.ass",
            playres_x=frame_width,
            playres_y=frame_height,
            crop=crop,
            duration=render_duration,
            output=target,
            output_settings=native_output,
        )
        if log:
            mode = "table interval" if active_interval_only else "full song"
            log(
                f"Separate Burst SPS: {frame_width}x{frame_height}; "
                f"{mode}; {render_duration:.3f}s"
            )
        _run_ffmpeg_progress(
            cmd,
            cwd=td,
            duration=render_duration,
            progress=progress,
            log=log,
            stage="FFmpeg: Burst SPS counter",
            cancel_event=cancel_event,
        )
    ffprobe = resolve_ffprobe(ffmpeg)
    if ffprobe is not None:
        actual_size = probe_video_frame_size(target, ffmpeg)
        expected_size = (frame_width, frame_height)
        if actual_size != expected_size:
            raise RuntimeError(
                f"Burst counter video has unexpected size {actual_size}; "
                f"expected {frame_width}x{frame_height}"
            )
        if log:
            log(f"Verified separate counter: {frame_width}x{frame_height}")
    return target



def build_direct_video_command(
    *,
    ffmpeg: str | Path,
    source_media: str | Path,
    ass_filename: str,
    output: str | Path,
    settings: DirectVideoSettings = DirectVideoSettings(),
    render_range: Optional[ResolvedRenderRange] = None,
    has_audio: bool = True,
) -> list[str]:
    """Build an FFmpeg command that burns ASS into the source frame.

    With ``render_range`` the input is accurately trimmed to the requested
    syllable window plus pre/post-roll. Audio fades across those padding
    intervals. Applying fades requires re-encoding audio, so ``copy`` is
    automatically promoted to AAC only for ranged renders that actually fade.
    """
    settings.validate()
    source = Path(source_media).resolve()
    target = Path(output).resolve()
    scale = float(settings.resolution_scale)
    # Keep dimensions compatible with chroma-subsampled encoders even when the
    # source has an odd side. Scaling precedes libass for a crisp high-res title.
    vf = (
        f"scale=ceil(iw*{scale:g}/2)*2:ceil(ih*{scale:g}/2)*2:flags=lanczos,"
        f"subtitles={ass_filename}"
    )
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]
    if render_range is not None:
        cmd += ["-ss", f"{render_range.render_start:.6f}"]
    cmd += ["-i", str(source)]
    if render_range is not None:
        cmd += ["-t", f"{render_range.duration:.6f}"]
    cmd += [
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", vf,
        "-c:v", settings.video_codec,
        "-crf", str(int(settings.crf)),
        "-preset", settings.preset,
        "-pix_fmt", settings.pixel_format,
    ]

    fades: list[str] = []
    if render_range is not None and has_audio and settings.audio_mode != "none":
        if render_range.pre_roll > 0:
            fades.append(f"afade=t=in:st=0:d={render_range.pre_roll:.6f}")
        if render_range.post_roll > 0:
            fade_out_start = max(0.0, render_range.duration - render_range.post_roll)
            fades.append(f"afade=t=out:st={fade_out_start:.6f}:d={render_range.post_roll:.6f}")
    if render_range is not None and has_audio and settings.audio_mode != "none":
        if fades:
            cmd += ["-af", ",".join(fades)]
        # A ranged render is intentionally re-encoded even when the UI says
        # "copy": packet-level stream copy cannot guarantee syllable-accurate
        # cuts, and fades require filtering anyway.
        cmd += ["-c:a", "aac", "-b:a", f"{int(settings.audio_bitrate_kbps)}k"]
    elif settings.audio_mode == "copy":
        cmd += ["-c:a", "copy"]
    elif settings.audio_mode == "aac":
        cmd += ["-c:a", "aac", "-b:a", f"{int(settings.audio_bitrate_kbps)}k"]
    else:
        cmd += ["-an"]
    cmd += ["-map_metadata", "0"]
    if target.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        cmd += ["-movflags", "+faststart"]
    cmd.append(str(target))
    return cmd


def render_karaoke_on_source(
    document: AssDocument,
    layout: RenderLayoutSettings,
    source_media: str | Path,
    output: str | Path,
    *,
    ffmpeg: str | Path = "ffmpeg",
    settings: DirectVideoSettings = DirectVideoSettings(),
    render_range: Optional[ResolvedRenderRange] = None,
    progress: Optional[ProgressCallback] = None,
    log: Optional[LogCallback] = None,
) -> Path:
    """Burn the render-only ASS copy into the source video or a syllable fragment."""
    source = Path(source_media).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    target = Path(output).resolve()
    if source == target:
        raise ValueError("Output file must differ from the source media")
    target.parent.mkdir(parents=True, exist_ok=True)
    render_doc = prepare_render_document(document, layout, render_range=render_range)
    materialize_romanization_overlays(render_doc, ffmpeg=ffmpeg, layout=layout)
    audio_bounds = probe_audio_bounds(source, ffmpeg)
    with tempfile.TemporaryDirectory(prefix="karaoke-burn-video-") as td:
        _write_temp_ass(render_doc, td, "render.ass")
        cmd = build_direct_video_command(
            ffmpeg=ffmpeg, source_media=source, ass_filename="render.ass",
            output=target, settings=settings, render_range=render_range,
            has_audio=audio_bounds is not None,
        )
        if render_range is not None and log:
            log(
                f"Fragment: {render_range.render_start:.3f}–{render_range.render_end:.3f} s "
                f"({render_range.duration:.3f} s); fade in/out "
                f"{render_range.pre_roll:.3f}/{render_range.post_roll:.3f} s"
            )
            if settings.audio_mode == "copy" and audio_bounds is not None:
                log("Audio copy -> AAC: ranged render needs accurate trimming; fade filters are applied when pre/post-roll > 0")
        duration = render_range.duration if render_range is not None else probe_media_duration(source, ffmpeg)
        _run_ffmpeg_progress(
            cmd, cwd=td, duration=duration, progress=progress, log=log,
            stage="FFmpeg: вжиг karaoke в исходное видео",
        )
    return target


def export_render_ass(
    document: AssDocument,
    layout: RenderLayoutSettings,
    output: str | Path,
    *,
    render_range: Optional[ResolvedRenderRange] = None,
    ffmpeg: str | Path = "ffmpeg",
) -> Path:
    render_doc = prepare_render_document(document, layout, render_range=render_range)
    materialize_romanization_overlays(render_doc, ffmpeg=ffmpeg, layout=layout)
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    render_doc.save(target)
    return target


def composite_rgba_to_ppm(
    rgba: bytes,
    width: int,
    height: int,
    *,
    checker: int = 16,
    subsample: int = 1,
) -> bytes:
    """Composite an RGBA preview onto a neutral checkerboard for Tk PhotoImage."""
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA byte count does not match dimensions")
    subsample = max(1, int(subsample))
    preview_width = (width + subsample - 1) // subsample
    preview_height = (height + subsample - 1) // subsample
    rgb = bytearray(preview_width * preview_height * 3)
    dst = 0
    for y in range(0, height, subsample):
        for x in range(0, width, subsample):
            src = (y * width + x) * 4
            r, g, b, a = rgba[src], rgba[src + 1], rgba[src + 2], rgba[src + 3]
            bg = 58 if ((x // checker) + (y // checker)) % 2 == 0 else 78
            inv = 255 - a
            rgb[dst] = (r * a + bg * inv) // 255
            rgb[dst + 1] = (g * a + bg * inv) // 255
            rgb[dst + 2] = (b * a + bg * inv) // 255
            dst += 3
    header = f"P6\n{preview_width} {preview_height}\n255\n".encode("ascii")
    return header + bytes(rgb)
