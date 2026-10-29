from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import base64
import os
import re
from typing import Iterable, Iterator, Optional


class KaraokeTagType(str, Enum):
    K = "k"       # abrupt fill
    CAPITAL_K = "K"  # alias of kf in ASS renderers
    KF = "kf"     # progressive fill
    KO = "ko"     # abrupt fill + outline behaviour


_KARAOKE_RE = re.compile(r"\\(kf|ko|K|k)(\d+)")


def unspoken_spans(raw: str) -> tuple[tuple[int, int], ...]:
    """Return ``[text]`` spans outside ASS override blocks.

    Brackets are application-owned source markup. They deliberately stay
    inside their existing karaoke syllable, so the enclosed text never becomes
    another SPS unit. Nested or unbalanced brackets are rejected instead of
    producing a render-only colour leak.
    """
    spans: list[tuple[int, int]] = []
    opened: int | None = None
    i = 0
    while i < len(raw):
        if raw[i] == "{":
            close = raw.find("}", i + 1)
            if close >= 0:
                i = close + 1
                continue
        if raw[i] == "[":
            if opened is not None:
                raise ValueError("Непроизнесённый фрагмент не может содержать вложенные скобки")
            opened = i
        elif raw[i] == "]":
            if opened is None:
                raise ValueError("Закрывающая ] не имеет парной открывающей [")
            if i == opened + 1:
                raise ValueError("Непроизнесённый фрагмент [] не может быть пустым")
            spans.append((opened, i + 1))
            opened = None
        i += 1
    if opened is not None:
        raise ValueError("Для непроговорённого фрагмента не хватает закрывающей ]")
    return tuple(spans)


_OVERRIDE_RE = re.compile(r"\{[^{}]*\}")
# Parse commands only as far as we need for semantic state.  The source text is
# never reconstructed from this parser, so unknown commands remain byte-for-byte
# untouched.
_PRIMARY_COLOUR_RE = re.compile(r"\\(?:1?c)(?:&H([0-9A-Fa-f]+)&?)?(?=\\|\}|$)", re.IGNORECASE)
_RESET_RE = re.compile(r"\\r(?:[^\\}]*)?", re.IGNORECASE)
# Application-owned, render-invisible metadata.  The value is URL-safe base64
# without padding, so it cannot terminate or inject an ASS override block.
_ROMANIZATION_RE = re.compile(r"\\_kr([A-Za-z0-9_-]+)")


def romanization_from_override_block(block: str) -> str:
    matches = list(_ROMANIZATION_RE.finditer(block))
    if not matches:
        return ""
    token = matches[-1].group(1)
    try:
        padding = "=" * (-len(token) % 4)
        return base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def romanization_override_command(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    token = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    return r"\_kr" + token


def replace_romanization_override(block: str, value: str) -> str:
    """Replace application romanization metadata in one ASS override block."""
    if not (block.startswith("{") and block.endswith("}")):
        raise ValueError("Invalid ASS override block")
    cleaned = _ROMANIZATION_RE.sub("", block)
    command = romanization_override_command(value)
    return cleaned[:-1] + command + "}"


def parse_ass_time(value: str) -> float:
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def format_ass_time(seconds: float) -> str:
    # ASS timestamps have centisecond precision.  Round once here and carry into
    # minutes/hours instead of formatting 59.999 as 60.00.
    total_cs = max(0, int(round(seconds * 100)))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _split_lines_keep_style(text: str) -> tuple[list[str], str, bool]:
    newline = "\r\n" if "\r\n" in text else "\n"
    terminal_newline = text.endswith(("\n", "\r"))
    # splitlines() deliberately removes the terminators; we retain the dominant
    # style and terminal-newline bit for exact normal round-trips.
    return text.splitlines(), newline, terminal_newline


def _hex_ass_colour_is_red(value: str) -> bool:
    """Return True for a red-dominant ASS BGR colour.

    ASS colours are stored as BBGGRR.  This correctly distinguishes the user's
    shorthand ``&HFF`` (red) from ``&HFFFFFF`` (white), unlike substring checks.
    """
    if not value:
        return False
    try:
        number = int(value, 16) & 0xFFFFFF
    except ValueError:
        return False
    red = number & 0xFF
    green = (number >> 8) & 0xFF
    blue = (number >> 16) & 0xFF
    return red >= 0xC0 and green <= 0x60 and blue <= 0x60


@dataclass(slots=True)
class AssEvent:
    document: "AssDocument"
    line_index: int
    kind: str
    layer: str
    start_raw: str
    end_raw: str
    style: str
    name: str
    margin_l: str
    margin_r: str
    margin_v: str
    effect: str
    text: str

    @property
    def start(self) -> float:
        return parse_ass_time(self.start_raw)

    @property
    def end(self) -> float:
        return parse_ass_time(self.end_raw)

    def _serialize(self) -> str:
        body = ",".join(
            [
                self.layer,
                self.start_raw,
                self.end_raw,
                self.style,
                self.name,
                self.margin_l,
                self.margin_r,
                self.margin_v,
                self.effect,
                self.text,
            ]
        )
        return f"{self.kind}: {body}"

    def commit(self) -> None:
        self.document.lines[self.line_index] = self._serialize()


@dataclass(slots=True, frozen=True)
class KaraokeSyllable:
    id: str
    event_line_index: int
    event_ordinal: int
    syllable_ordinal: int
    tag_type: KaraokeTagType
    duration_cs: int
    start: float
    end: float
    raw_text: str
    visible_text: str
    romanization: str
    burst_marked: bool
    tag_block_start: int
    tag_block_end: int
    tag_value_start: int
    tag_value_end: int
    track: int = 0

    @property
    def duration(self) -> float:
        return self.duration_cs / 100.0


class AssDocument:
    """Lossless-enough ASS document wrapper.

    Unmodified files are emitted exactly (line endings and final newline included).
    Edited event lines are re-serialized only for that event.  Unknown override
    tags are not normalized or discarded.
    """

    def __init__(self, text: str, source_path: Optional[Path] = None, *, bom: bool = False):
        self.lines, self.newline, self.terminal_newline = _split_lines_keep_style(text)
        self.source_path = source_path
        self.bom = bom

    @classmethod
    def load(cls, path: str | Path) -> "AssDocument":
        p = Path(path)
        data = p.read_bytes()
        bom = data.startswith(b"\xef\xbb\xbf")
        return cls(data.decode("utf-8-sig"), source_path=p, bom=bom)

    @classmethod
    def from_text(cls, text: str) -> "AssDocument":
        return cls(text)

    def dumps(self) -> str:
        text = self.newline.join(self.lines)
        if self.terminal_newline:
            text += self.newline
        return text

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.source_path
        if target is None:
            raise ValueError("No output path supplied and document has no source path")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.dumps().encode("utf-8")
        if self.bom:
            payload = b"\xef\xbb\xbf" + payload
        # Atomic replace prevents a crash/interruption from leaving a half-written
        # subtitle file.  Explicit backup policy belongs to a later UI update.
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, target)
        self.source_path = target
        return target

    def events(self) -> list[AssEvent]:
        result: list[AssEvent] = []
        in_events = False
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_events = stripped.lower() == "[events]"
                continue
            if not in_events:
                continue
            if not (line.startswith("Dialogue:") or line.startswith("Comment:")):
                continue
            kind, body = line.split(":", 1)
            body = body.lstrip(" ")
            parts = body.split(",", 9)
            if len(parts) != 10:
                continue
            result.append(
                AssEvent(
                    document=self,
                    line_index=i,
                    kind=kind,
                    layer=parts[0],
                    start_raw=parts[1],
                    end_raw=parts[2],
                    style=parts[3],
                    name=parts[4],
                    margin_l=parts[5],
                    margin_r=parts[6],
                    margin_v=parts[7],
                    effect=parts[8],
                    text=parts[9],
                )
            )
        return result

    def karaoke_syllables(self, include_comments: bool = False) -> list[KaraokeSyllable]:
        result: list[KaraokeSyllable] = []
        event_ordinal = 0
        for event in self.events():
            if event.kind == "Comment" and not include_comments:
                continue
            result.extend(_parse_event_karaoke(event, event_ordinal))
            event_ordinal += 1
        return result

    def set_karaoke_type(self, syllable: KaraokeSyllable, new_type: KaraokeTagType | str) -> KaraokeSyllable:
        new_type = KaraokeTagType(new_type)
        event = next((e for e in self.events() if e.line_index == syllable.event_line_index), None)
        if event is None:
            raise KeyError(f"Event line {syllable.event_line_index} no longer exists")
        source = event.text
        old_fragment = source[syllable.tag_value_start:syllable.tag_value_end]
        m = _KARAOKE_RE.fullmatch(old_fragment)
        if not m:
            raise RuntimeError("Karaoke tag position is stale; reparse the document before editing")
        replacement = f"\\{new_type.value}{syllable.duration_cs}"
        event.text = source[:syllable.tag_value_start] + replacement + source[syllable.tag_value_end:]
        event.commit()
        # Offsets can change (kf -> k), so return the reparsed matching ordinal.
        candidates = [s for s in self.karaoke_syllables() if s.event_line_index == syllable.event_line_index]
        return candidates[syllable.syllable_ordinal]

    def set_karaoke_duration(self, syllable: KaraokeSyllable, duration_cs: int) -> KaraokeSyllable:
        if duration_cs < 0:
            raise ValueError("duration_cs must be >= 0")
        event = next((e for e in self.events() if e.line_index == syllable.event_line_index), None)
        if event is None:
            raise KeyError(f"Event line {syllable.event_line_index} no longer exists")
        source = event.text
        old_fragment = source[syllable.tag_value_start:syllable.tag_value_end]
        m = _KARAOKE_RE.fullmatch(old_fragment)
        if not m:
            raise RuntimeError("Karaoke tag position is stale; reparse the document before editing")
        replacement = f"\\{m.group(1)}{duration_cs}"
        event.text = source[:syllable.tag_value_start] + replacement + source[syllable.tag_value_end:]
        event.commit()
        candidates = [s for s in self.karaoke_syllables() if s.event_line_index == syllable.event_line_index]
        return candidates[syllable.syllable_ordinal]


def _visible_text(raw: str) -> str:
    # ASS hard spaces / linebreaks are converted only for display/analysis.  The
    # raw_text retained by KaraokeSyllable remains untouched.
    text = _OVERRIDE_RE.sub("", raw)
    return text.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")


def _apply_colour_state(block: str, current_red: bool) -> bool:
    # Process reset/colour commands in source order.  A bare \c is treated as a
    # reset to style colour, matching the hand-authored files in this project.
    commands: list[tuple[int, str, Optional[str]]] = []
    for m in _RESET_RE.finditer(block):
        commands.append((m.start(), "reset", None))
    for m in _PRIMARY_COLOUR_RE.finditer(block):
        commands.append((m.start(), "colour", m.group(1)))
    commands.sort(key=lambda x: x[0])
    for _, kind, value in commands:
        if kind == "reset":
            current_red = False
        elif value is None:
            current_red = False
        else:
            current_red = _hex_ass_colour_is_red(value)
    return current_red


def _parse_event_karaoke(event: AssEvent, event_ordinal: int) -> list[KaraokeSyllable]:
    text = event.text
    blocks = list(_OVERRIDE_RE.finditer(text))
    syllables: list[KaraokeSyllable] = []
    current_time = event.start
    current_red = False

    track = 0
    effect_str = str(getattr(event, "effect", "") or "").strip()
    if effect_str.startswith("track:"):
        try:
            track = int(effect_str.split("track:", 1)[1])
        except ValueError:
            track = 0

    active: Optional[dict] = None

    def finish_active(end_pos: int) -> None:
        nonlocal active
        if active is None:
            return
        raw = text[active["content_start"]:end_pos]
        idx = len(syllables)
        syllables.append(
            KaraokeSyllable(
                id=f"L{event.line_index}:S{idx}",
                event_line_index=event.line_index,
                event_ordinal=event_ordinal,
                syllable_ordinal=idx,
                tag_type=KaraokeTagType(active["tag_type"]),
                duration_cs=active["duration_cs"],
                start=active["start"],
                end=active["end"],
                raw_text=raw,
                visible_text=_visible_text(raw),
                romanization=str(active.get("romanization", "")),
                burst_marked=bool(active["burst"]),
                tag_block_start=active["block_start"],
                tag_block_end=active["block_end"],
                tag_value_start=active["tag_value_start"],
                tag_value_end=active["tag_value_end"],
                track=track,
            )
        )
        active = None

    for block_match in blocks:
        block = block_match.group(0)
        karaoke_matches = list(_KARAOKE_RE.finditer(block))

        # Colour-only blocks after a karaoke tag but before its visible text must
        # affect that already-active syllable (the user's {\kf6}{\c&HFF}the
        # pattern).  When colour and karaoke share one block, the colour belongs
        # to the *new* syllable, not the previous one.
        next_red = _apply_colour_state(block, current_red)
        if not karaoke_matches:
            if active is not None and next_red != current_red:
                # A colour block before any visible content styles the active
                # syllable. A reset after visible content terminates the colour
                # for what follows and must not retroactively unmark it.
                content_before_block = text[active["content_start"]:block_match.start()]
                if not _visible_text(content_before_block):
                    active["burst"] = next_red
            current_red = next_red
            continue

        # ASS technically permits more than one karaoke command in a block.  They
        # have no intervening text, so all but the final command become zero-text
        # syllables; preserving them is safer than silently dropping timing.
        for km in karaoke_matches:
            finish_active(block_match.start())
            tag_type = km.group(1)
            duration_cs = int(km.group(2))
            start = current_time
            end = start + duration_cs / 100.0
            current_time = end
            active = {
                "tag_type": tag_type,
                "duration_cs": duration_cs,
                "start": start,
                "end": end,
                "burst": next_red,
                "romanization": romanization_from_override_block(block),
                "block_start": block_match.start(),
                "block_end": block_match.end(),
                "tag_value_start": block_match.start() + km.start(),
                "tag_value_end": block_match.start() + km.end(),
                "content_start": block_match.end(),
            }
        current_red = next_red

    finish_active(len(text))
    return syllables
