from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import math
import re
import shlex
import unicodedata
from typing import Iterable, Optional, Sequence

from .ass import AssDocument, KaraokeTagType, format_ass_time
from .language import detect_language_profile, profile_for_language
from .syllables import flatten_ass_dialogues, restore_ass_text, split_text_syllables


class AlignmentError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class TextGridInterval:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True, frozen=True)
class TextGridTier:
    name: str
    intervals: tuple[TextGridInterval, ...]


@dataclass(slots=True, frozen=True)
class ParsedTextGrid:
    xmin: float
    xmax: float
    tiers: tuple[TextGridTier, ...]

    def tier(self, *names: str) -> Optional[TextGridTier]:
        wanted = {name.casefold() for name in names}
        return next((tier for tier in self.tiers if tier.name.casefold() in wanted), None)

    @property
    def tier_names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.tiers)


@dataclass(slots=True)
class AlignmentConversionSettings:
    word_tier: str = "words"
    phone_tier: str = "phones"
    karaoke_tag: KaraokeTagType = KaraokeTagType.KF
    max_words_per_line: int = 8
    max_gap_seconds: float = 0.65
    max_line_seconds: float = 8.0
    play_res_x: int = 1920
    play_res_y: int = 1080
    font_name: str = "Heading Pro Variable"
    font_size: int = 72
    style_name: str = "Default"
    use_phone_boundaries: bool = True
    syllabify: bool = False
    language: str = "en"
    flatten_dialogues: bool = False
    restore_transcript_text: bool = True


@dataclass(slots=True, frozen=True)
class AlignmentConversionReport:
    output_path: Path
    words: int
    lines: int
    visible_syllables: int
    timing_gaps: int
    phone_tier_used: bool
    transcript_tokens_used: bool
    warnings: tuple[str, ...] = ()
    language: str = ""
    syllabified: bool = False
    text_restored: bool = False
    text_match_ratio: float | None = None


@dataclass(slots=True, frozen=True)
class MFACommandSettings:
    executable: str = "mfa"
    mode: str = "hf"  # hf | legacy
    model: str = ""
    dictionary: str = ""
    dialect: str = ""
    use_g2p: bool = False
    num_jobs: Optional[int] = None
    beam: int = 10
    retry_beam: int = 40
    single_speaker: bool = True
    clean_textgrids: bool = True


def build_mfa_align_command(
    corpus_directory: str | Path,
    output_directory: str | Path,
    settings: MFACommandSettings,
) -> list[str]:
    """Build an explicit MFA 3.x alignment command without language fallback.

    HF mode maps to ``mfa align_hf CORPUS MODEL OUTPUT``. Legacy mode maps to
    ``mfa align CORPUS DICTIONARY MODEL OUTPUT``. A missing model/dictionary is
    an error rather than silently substituting English (the old project bug).
    """
    corpus = str(Path(corpus_directory))
    output = str(Path(output_directory))
    exe = settings.executable.strip() or "mfa"
    mode = settings.mode.casefold().strip()
    if not settings.model.strip():
        raise AlignmentError("MFA model is not configured")
    if mode == "hf":
        cmd = [exe, "align_hf", corpus, settings.model.strip(), output]
        if settings.dialect.strip():
            cmd += ["--dialect", settings.dialect.strip()]
        if settings.use_g2p:
            cmd.append("--use_g2p")
    elif mode == "legacy":
        if not settings.dictionary.strip():
            raise AlignmentError("Legacy MFA mode requires an explicit dictionary; no fallback is used")
        cmd = [exe, "align", corpus, settings.dictionary.strip(), settings.model.strip(), output]
    else:
        raise AlignmentError("MFA mode must be 'hf' or 'legacy'")
    if settings.beam < 1:
        raise AlignmentError("beam must be >= 1")
    if settings.retry_beam <= settings.beam:
        raise AlignmentError("retry_beam must be greater than beam")
    cmd += ["--beam", str(settings.beam), "--retry_beam", str(settings.retry_beam)]
    cmd += ["--output_format", "long_textgrid"]
    if settings.num_jobs is not None:
        if settings.num_jobs < 1:
            raise AlignmentError("num_jobs must be >= 1")
        cmd += ["--num_jobs", str(settings.num_jobs)]
    if settings.single_speaker:
        cmd.append("--single_speaker")
    cmd.append("--cleanup_textgrids" if settings.clean_textgrids else "--no_cleanup_textgrids")
    cmd.append("--clean")
    return cmd


def command_for_display(command: Sequence[str]) -> str:
    # list2cmdline is Windows-specific but produces the most useful copy/paste
    # output for this project. POSIX quoting is still exposed when unavailable.
    try:
        import subprocess
        return subprocess.list2cmdline(list(command))
    except Exception:
        return shlex.join(command)


def _unquote_praat(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1].replace('""', '"')
    return value


def parse_textgrid_text(text: str) -> ParsedTextGrid:
    if "ooTextFile short" in text[:100]:
        return _parse_short_textgrid(text)
    return _parse_long_textgrid(text)


def load_textgrid(path: str | Path) -> ParsedTextGrid:
    source = Path(path)
    # Praat/MFA files are normally UTF-8, but utf-8-sig makes BOM harmless.
    return parse_textgrid_text(source.read_text(encoding="utf-8-sig"))


def _parse_long_textgrid(text: str) -> ParsedTextGrid:
    lines = text.splitlines()
    global_xmin = 0.0
    global_xmax = 0.0
    # First top-level xmin/xmax before item[] are the global range.
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("item []"):
            break
        if stripped.startswith("xmin") and "=" in stripped:
            global_xmin = float(stripped.split("=", 1)[1])
        elif stripped.startswith("xmax") and "=" in stripped:
            global_xmax = float(stripped.split("=", 1)[1])

    tiers: list[TextGridTier] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not re.match(r"item \[\d+\]:", stripped):
            i += 1
            continue
        i += 1
        tier_name = ""
        tier_class = ""
        intervals: list[TextGridInterval] = []
        while i < len(lines):
            s = lines[i].strip()
            if re.match(r"item \[\d+\]:", s):
                break
            if s.startswith("class") and "=" in s:
                tier_class = _unquote_praat(s.split("=", 1)[1])
            elif s.startswith("name") and "=" in s:
                tier_name = _unquote_praat(s.split("=", 1)[1])
            elif re.match(r"intervals \[\d+\]:", s):
                xmin = xmax = None
                label = ""
                i += 1
                while i < len(lines):
                    part = lines[i].strip()
                    if re.match(r"intervals \[\d+\]:", part) or re.match(r"item \[\d+\]:", part):
                        i -= 1
                        break
                    if part.startswith("xmin") and "=" in part:
                        xmin = float(part.split("=", 1)[1])
                    elif part.startswith("xmax") and "=" in part:
                        xmax = float(part.split("=", 1)[1])
                    elif part.startswith("text") and "=" in part:
                        label = _unquote_praat(part.split("=", 1)[1])
                    i += 1
                if xmin is not None and xmax is not None:
                    intervals.append(TextGridInterval(xmin, xmax, label))
            i += 1
        if tier_class == "IntervalTier":
            tiers.append(TextGridTier(tier_name, tuple(intervals)))
    if not tiers:
        raise AlignmentError("No IntervalTier found in TextGrid")
    if global_xmax <= global_xmin:
        starts = [v.start for t in tiers for v in t.intervals]
        ends = [v.end for t in tiers for v in t.intervals]
        if starts and ends:
            global_xmin, global_xmax = min(starts), max(ends)
    return ParsedTextGrid(global_xmin, global_xmax, tuple(tiers))


def _short_tokens(text: str) -> list[str]:
    result: list[str] = []
    for raw in text.splitlines():
        value = raw.strip()
        if not value or value.startswith("File type") or value.startswith("Object class"):
            continue
        if value in {'"ooTextFile short"', '"TextGrid"'}:
            continue
        result.append(value)
    return result


def _parse_short_textgrid(text: str) -> ParsedTextGrid:
    tokens = _short_tokens(text)
    pos = 0
    try:
        xmin = float(tokens[pos]); pos += 1
        xmax = float(tokens[pos]); pos += 1
        exists = tokens[pos]; pos += 1
        if "exists" not in exists:
            raise ValueError
        tier_count = int(tokens[pos]); pos += 1
        tiers: list[TextGridTier] = []
        for _ in range(tier_count):
            tier_class = _unquote_praat(tokens[pos]); pos += 1
            name = _unquote_praat(tokens[pos]); pos += 1
            _tier_min = float(tokens[pos]); pos += 1
            _tier_max = float(tokens[pos]); pos += 1
            count = int(tokens[pos]); pos += 1
            if tier_class != "IntervalTier":
                # Short TextGrid TextTier points use number/mark pairs; consume
                # them conservatively but do not expose them to alignment logic.
                for _j in range(count):
                    pos += 2
                continue
            intervals: list[TextGridInterval] = []
            for _j in range(count):
                start = float(tokens[pos]); pos += 1
                end = float(tokens[pos]); pos += 1
                label = _unquote_praat(tokens[pos]); pos += 1
                intervals.append(TextGridInterval(start, end, label))
            tiers.append(TextGridTier(name, tuple(intervals)))
    except (IndexError, ValueError) as exc:
        raise AlignmentError("Malformed short TextGrid") from exc
    if not tiers:
        raise AlignmentError("No IntervalTier found in TextGrid")
    return ParsedTextGrid(xmin, xmax, tuple(tiers))


_SILENCE_LABELS = {"", "<eps>", "sil", "sp", "spn", "<sil>", "<unk>"}


def _is_silence_label(value: str) -> bool:
    return value.strip().casefold() in _SILENCE_LABELS


def _normalize_token(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(ch for ch in value if ch.isalnum() or unicodedata.category(ch).startswith("L"))


def _transcript_tokens(text: str) -> list[str]:
    # Keep punctuation attached to its word. MFA's words tier generally loses or
    # normalizes punctuation, so this lets the generated ASS retain lyrics text.
    return [token for token in re.split(r"\s+", text.strip()) if token]


def _map_transcript_tokens(words: Sequence[TextGridInterval], transcript: Optional[str]) -> tuple[list[str], bool, list[str]]:
    fallback = [w.text.strip() for w in words]
    if transcript is None or not transcript.strip():
        return fallback, False, []
    tokens = _transcript_tokens(transcript)
    warnings: list[str] = []
    if len(tokens) == len(words) and all(
        _normalize_token(w.text) == _normalize_token(t) for w, t in zip(words, tokens)
    ):
        return tokens, True, warnings

    # Sequential normalized matching handles punctuation/case but intentionally
    # refuses to invent mappings when tokenization materially differs.
    mapped: list[str] = []
    cursor = 0
    for word in words:
        target = _normalize_token(word.text)
        found = None
        for j in range(cursor, min(len(tokens), cursor + 4)):
            if _normalize_token(tokens[j]) == target:
                found = j
                break
        if found is None:
            warnings.append(
                f"Transcript tokenization does not match words tier near '{word.text}'; words-tier text was used instead"
            )
            return fallback, False, warnings
        mapped.append(tokens[found])
        cursor = found + 1
    if cursor != len(tokens):
        warnings.append("Transcript contains extra tokens; words-tier text was used instead")
        return fallback, False, warnings
    return mapped, True, warnings


def _graphemes(value: str) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    current = ""
    join_next = False
    for ch in value:
        cp = ord(ch)
        combining = unicodedata.combining(ch) != 0 or 0xFE00 <= cp <= 0xFE0F or 0x1F3FB <= cp <= 0x1F3FF
        if not current:
            current = ch
        elif combining or join_next or ch == "\u200d":
            current += ch
        else:
            result.append(current)
            current = ch
        join_next = ch == "\u200d"
    if current:
        result.append(current)
    return result


def _timed_text_clusters(value: str) -> list[str]:
    gs = _graphemes(value)
    if not gs:
        return [""]
    timed: list[str] = []
    leading = ""
    for g in gs:
        base = next((ch for ch in g if ch != "\u200d" and not unicodedata.combining(ch)), g[0])
        cat = unicodedata.category(base)
        # Spaces and punctuation do not receive their own SPS unit. Attach them
        # to a neighbouring spoken cluster instead.
        if cat.startswith("P") or cat.startswith("Z"):
            if timed:
                timed[-1] += g
            else:
                leading += g
        else:
            timed.append(leading + g)
            leading = ""
    if leading:
        if timed:
            timed[-1] += leading
        else:
            timed = [leading]
    return timed or [value]


def _phones_for_word(word: TextGridInterval, phone_tier: Optional[TextGridTier]) -> list[TextGridInterval]:
    if phone_tier is None:
        return []
    result = []
    for phone in phone_tier.intervals:
        if _is_silence_label(phone.text):
            continue
        overlap = min(word.end, phone.end) - max(word.start, phone.start)
        if overlap > 1e-6:
            result.append(phone)
    return result


def _cluster_boundaries(word: TextGridInterval, cluster_count: int, phones: Sequence[TextGridInterval]) -> list[float]:
    if cluster_count <= 1:
        return [word.start, word.end]
    duration = max(0.0, word.end - word.start)
    if duration <= 0:
        return [word.start] * cluster_count + [word.end]
    candidates = sorted({max(word.start, min(word.end, p.end)) for p in phones if word.start < p.end < word.end})
    # Snap proportional grapheme boundaries to phone boundaries only when enough
    # distinct boundaries exist; otherwise proportional splitting avoids a run of
    # zero-duration graphemes.
    if len(candidates) >= cluster_count - 1:
        selected: list[float] = []
        lo_index = 0
        for k in range(1, cluster_count):
            remaining = cluster_count - k - 1
            max_index = len(candidates) - remaining - 1
            target = word.start + duration * (k / cluster_count)
            region = range(lo_index, max_index + 1)
            best = min(region, key=lambda idx: abs(candidates[idx] - target))
            selected.append(candidates[best])
            lo_index = best + 1
        return [word.start, *selected, word.end]
    return [word.start + duration * (k / cluster_count) for k in range(cluster_count + 1)]


@dataclass(slots=True)
class _RawPiece:
    start: float
    end: float
    text: str
    gap: bool = False


def _word_pieces(
    word: TextGridInterval,
    display_text: str,
    phones: Sequence[TextGridInterval],
    *,
    prefix_space: bool,
    syllable_language: str | None = None,
) -> list[_RawPiece]:
    clusters = (
        split_text_syllables(display_text, syllable_language)
        if syllable_language
        else _timed_text_clusters(display_text)
    )
    boundaries = _cluster_boundaries(word, len(clusters), phones)
    pieces: list[_RawPiece] = []
    for idx, cluster in enumerate(clusters):
        text = cluster
        if idx == 0 and prefix_space:
            text = " " + text
        pieces.append(_RawPiece(boundaries[idx], boundaries[idx + 1], text, False))
    return pieces


def _group_words(words: Sequence[TextGridInterval], settings: AlignmentConversionSettings) -> list[list[TextGridInterval]]:
    if settings.max_words_per_line < 1:
        raise AlignmentError("max_words_per_line must be >= 1")
    groups: list[list[TextGridInterval]] = []
    current: list[TextGridInterval] = []
    for word in words:
        if not current:
            current = [word]
            continue
        gap = max(0.0, word.start - current[-1].end)
        line_duration = word.end - current[0].start
        if (
            len(current) >= settings.max_words_per_line
            or gap > settings.max_gap_seconds
            or line_duration > settings.max_line_seconds
        ):
            groups.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        groups.append(current)
    return groups


def _quantize_pieces(pieces: Sequence[_RawPiece], line_start: float, line_end: float) -> list[tuple[int, _RawPiece]]:
    """Quantize absolute cumulative boundaries once so durations sum exactly.

    Start and end are rounded as absolute ASS timestamps first. Every internal
    boundary is then rounded in that same absolute centisecond grid. This avoids
    both per-phone truncation drift and the one-centisecond discrepancy possible
    when rounding ``(end-start)`` independently from the event timestamps.
    """
    if not pieces:
        return []
    start_abs_cs = int(round(line_start * 100))
    end_abs_cs = max(start_abs_cs, int(round(line_end * 100)))
    total_cs = end_abs_cs - start_abs_cs
    result: list[tuple[int, _RawPiece]] = []
    prev_cs = 0
    for idx, piece in enumerate(pieces):
        if idx == len(pieces) - 1:
            end_cs = total_cs
        else:
            end_cs = int(round(piece.end * 100)) - start_abs_cs
            end_cs = max(prev_cs, min(total_cs, end_cs))
        duration_cs = end_cs - prev_cs
        result.append((duration_cs, piece))
        prev_cs = end_cs
    return result


def _ass_escape_text(value: str) -> str:
    # Lyrics are text, not ASS override syntax. Protect literal braces while
    # retaining the standard explicit linebreak sequences if present.
    return value.replace("{", r"\{").replace("}", r"\}")


def convert_textgrid_to_ass(
    textgrid_path: str | Path,
    output_path: str | Path,
    *,
    transcript_path: str | Path | None = None,
    settings: AlignmentConversionSettings | None = None,
) -> AlignmentConversionReport:
    settings = settings or AlignmentConversionSettings()
    if settings.restore_transcript_text and transcript_path is None:
        raise AlignmentError(
            "Для восстановления регистра, пунктуации и переносов требуется исходный TXT"
        )
    grid = load_textgrid(textgrid_path)
    word_tier = grid.tier(settings.word_tier)
    if word_tier is None and settings.word_tier.casefold() in {"words", "word"}:
        # MFA usually uses words/phones; accept the singular/common default only.
        # A genuinely custom tier name must exist rather than silently selecting
        # a different tier.
        word_tier = grid.tier("words", "word")
    if word_tier is None:
        raise AlignmentError(
            f"Word tier '{settings.word_tier}' not found. Available tiers: {', '.join(grid.tier_names)}"
        )
    phone_tier = grid.tier(settings.phone_tier)
    if phone_tier is None and settings.phone_tier.casefold() in {"phones", "phone"}:
        phone_tier = grid.tier("phones", "phone")
    words = [w for w in word_tier.intervals if not _is_silence_label(w.text) and w.end > w.start]
    if not words:
        raise AlignmentError("The words tier contains no non-empty intervals")
    transcript_text = None
    if transcript_path is not None:
        p = Path(transcript_path)
        if p.is_file():
            transcript_text = p.read_text(encoding="utf-8-sig")
    requested_language = settings.language.strip().casefold()
    if requested_language == "auto":
        profile = detect_language_profile(transcript_text or "")
    else:
        profile = profile_for_language(settings.language)
    if settings.restore_transcript_text and transcript_text:
        display_tokens, transcript_used, warnings = _map_transcript_tokens(words, transcript_text)
    else:
        display_tokens = [w.text.strip() for w in words]
        transcript_used = False
        warnings = []
    lines = _group_words(words, settings)

    ass_lines = [
        "[Script Info]",
        "; Generated by Karaoke SPS Workbench TextGrid importer",
        "ScriptType: v4.00+",
        f"PlayResX: {settings.play_res_x}",
        f"PlayResY: {settings.play_res_y}",
        # Smart wrapping. Explicit lyric line breaks restored from TXT remain
        # \N, while libass may intelligently wrap an overlong visual line.
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        # Preserve the original measurement workflow style.  In particular the
        # secondary karaoke colour is translucent white, not red; red remains
        # reserved for explicit burst override tags (\c&HFF).
        f"Style: {settings.style_name},{settings.font_name},{settings.font_size},&H00FFFFFF,&H80FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,2,0,5,30,30,50,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    visible_count = 0
    gap_count = 0
    phone_used = False

    word_index = {id(word): i for i, word in enumerate(words)}
    for group in lines:
        line_start = group[0].start
        line_end = group[-1].end
        pieces: list[_RawPiece] = []
        cursor = line_start
        for local_idx, word in enumerate(group):
            if word.start > cursor + 1e-6:
                pieces.append(_RawPiece(cursor, word.start, "", True))
            phones = _phones_for_word(word, phone_tier) if settings.use_phone_boundaries else []
            if phones:
                phone_used = True
            display = display_tokens[word_index[id(word)]]
            wp = _word_pieces(
                word,
                display,
                phones,
                prefix_space=local_idx > 0,
                syllable_language=profile.code if settings.syllabify else None,
            )
            pieces.extend(wp)
            cursor = word.end
        if cursor < line_end - 1e-6:
            pieces.append(_RawPiece(cursor, line_end, "", True))
        quantized = _quantize_pieces(pieces, line_start, line_end)
        text_parts: list[str] = []
        for duration_cs, piece in quantized:
            tag = settings.karaoke_tag.value if not piece.gap else "k"
            text_parts.append(f"{{\\{tag}{duration_cs}}}{_ass_escape_text(piece.text)}")
            if piece.gap:
                gap_count += 1
            else:
                visible_count += 1
        event_start_cs = int(round(line_start * 100))
        event_end_cs = max(event_start_cs, int(round(line_end * 100)))
        event_duration_cs = sum(duration for duration, _ in quantized)
        # The cumulative quantizer guarantees this by construction. Keep the
        # explicit check close to serialization so regressions fail loudly.
        if event_duration_cs != event_end_cs - event_start_cs:
            raise AlignmentError("Internal centisecond quantization mismatch")
        start_raw = format_ass_time(event_start_cs / 100)
        end_raw = format_ass_time(event_end_cs / 100)
        ass_lines.append(
            f"Dialogue: 0,{start_raw},{end_raw},{settings.style_name},,0,0,0,,{''.join(text_parts)}"
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(ass_lines) + "\n"
    staging = output.with_name(output.name + ".building")
    restoration = None
    try:
        staging.write_text(payload, encoding="utf-8")
        if settings.flatten_dialogues:
            # The legacy measurement format is one title for the complete audio
            # range, including any silence before the first/after the last word.
            flatten_ass_dialogues(staging, start_time=grid.xmin, end_time=grid.xmax)
        if settings.restore_transcript_text and transcript_path is not None:
            restoration = restore_ass_text(staging, transcript_path)
        final_document = AssDocument.load(staging)
        final_units = final_document.karaoke_syllables()
        final_visible_count = sum(1 for unit in final_units if unit.visible_text.strip())
        final_gap_count = len(final_units) - final_visible_count
        final_line_count = sum(1 for event in final_document.events() if event.kind == "Dialogue")
        # Publish only after every mandatory stage, especially exact TXT
        # restoration, has succeeded. A failed conversion leaves the old ASS.
        staging.replace(output)
    finally:
        staging.unlink(missing_ok=True)
    return AlignmentConversionReport(
        output_path=output,
        words=len(words),
        lines=final_line_count,
        visible_syllables=final_visible_count,
        timing_gaps=final_gap_count,
        phone_tier_used=phone_used,
        transcript_tokens_used=transcript_used,
        warnings=tuple(warnings),
        language=profile.code,
        syllabified=settings.syllabify,
        text_restored=restoration is not None,
        text_match_ratio=restoration.match_ratio if restoration is not None else None,
    )
