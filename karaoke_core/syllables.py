from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
import re
from typing import Sequence

from .ass import AssDocument, KaraokeSyllable, KaraokeTagType, format_ass_time
from .language import LanguageProfile, profile_for_language


class SyllableConversionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TextRestorationReport:
    karaoke_units: int
    normalized_characters: int
    match_ratio: float


@dataclass(frozen=True, slots=True)
class SyllabificationReport:
    input_units: int
    output_units: int
    dialogue_lines: int
    language: str


_LEXEME_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_OVERRIDE_RE = re.compile(r"\{[^{}]*\}")
_OPENING_PUNCT = set("«„“¿¡([{")
_SYMMETRIC_QUOTES = {'"'}

_VOWELS = {
    "en": "aeiouy",
    "ru": "аеёиоуыэюя",
    "de": "aeiouyäöü",
    "pl": "aąeęioóuy",
    "tr": "aeıioöuü",
    "hu": "aáeéiíoóöőuúüű",
    "pt": "aáâãeéêiíoóôõuúü",
}


@lru_cache(maxsize=None)
def _pyphen_dictionary(language: str):
    profile = profile_for_language(language)
    if not profile.pyphen_language:
        return None
    try:
        import pyphen  # type: ignore

        return pyphen.Pyphen(lang=profile.pyphen_language)
    except Exception:
        return None


def _fallback_positions(word: str, profile: LanguageProfile) -> list[int]:
    vowels = set(_VOWELS.get(profile.code, _VOWELS["en"]))
    lowered = word.casefold()
    nuclei: list[tuple[int, int]] = []
    i = 0
    while i < len(lowered):
        if lowered[i] not in vowels:
            i += 1
            continue
        start = i
        i += 1
        while i < len(lowered) and lowered[i] in vowels:
            i += 1
        nuclei.append((start, i))
    if len(nuclei) <= 1:
        return []
    positions: list[int] = []
    for (_, previous_end), (next_start, _) in zip(nuclei, nuclei[1:]):
        consonants = max(0, next_start - previous_end)
        # Keep one consonant with the following vowel where possible: hello ->
        # hel-lo, amount -> a-mount.  Pyphen remains the preferred implementation.
        boundary = next_start - (1 if consonants >= 2 else consonants)
        boundary = max(previous_end, min(next_start, boundary))
        if 0 < boundary < len(word):
            positions.append(boundary)
    return sorted(set(positions))


def _word_break_positions(word: str, profile: LanguageProfile) -> list[int]:
    if profile.code == "ja" or len(word) < 2:
        return []
    dictionary = _pyphen_dictionary(profile.code)
    if dictionary is not None:
        try:
            return [int(pos) for pos in dictionary.positions(word) if 0 < int(pos) < len(word)]
        except Exception:
            pass
    return _fallback_positions(word, profile)


def split_text_syllables(value: str, language: str | LanguageProfile) -> list[str]:
    """Split visible text while retaining its exact punctuation and spelling."""

    if not value:
        return [""]
    profile = profile_for_language(language)
    boundaries: set[int] = set()
    for match in _LEXEME_RE.finditer(value):
        word = match.group(0)
        for position in _word_break_positions(word, profile):
            boundaries.add(match.start() + position)
    cuts = [0, *sorted(pos for pos in boundaries if 0 < pos < len(value)), len(value)]
    return [value[cuts[i]:cuts[i + 1]] for i in range(len(cuts) - 1)] or [value]


def _escape_ass_text(value: str) -> str:
    return value.replace("{", r"\{").replace("}", r"\}").replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\N")


def _normalize_characters(value: str) -> str:
    return "".join(ch.casefold() for ch in value if ch.isalnum())


def _nearest_syllable(syllable_map: Sequence[tuple[int, str]], source_pos: int) -> int | None:
    if source_pos > 0:
        return syllable_map[source_pos - 1][0]
    if source_pos < len(syllable_map):
        return syllable_map[source_pos][0]
    return None


def _opening_symmetric_quote_positions(text: str) -> set[int]:
    """Classify straight double quotes as opening or closing punctuation.

    A straight quote cannot be classified from its code point alone.  Toggle
    paired quotes across the original transcript, but also treat a quote after
    an alphanumeric character as a closing quote even when the excerpt starts
    mid-quotation.  Closing quotes must stay with the preceding syllable so a
    sequence such as ``ет\", он`` is not restored as ``ет, \"он``.
    """
    openings: set[int] = set()
    active = False
    for index, ch in enumerate(text):
        if ch not in _SYMMETRIC_QUOTES:
            continue
        previous = next((text[pos] for pos in range(index - 1, -1, -1) if not text[pos].isspace()), "")
        following = next((text[pos] for pos in range(index + 1, len(text)) if not text[pos].isspace()), "")
        if active:
            active = False
            continue
        if previous.isalnum():
            # An unmatched quote at the beginning of an excerpt is still a
            # closing quote when it immediately follows a word character.
            continue
        if following:
            openings.add(index)
            active = True
    return openings


def _restored_buckets(
    syllables: Sequence[KaraokeSyllable],
    original_text: str,
    *,
    minimum_ratio: float,
) -> tuple[list[str], float, int]:
    syllable_map: list[tuple[int, str]] = []
    for index, syllable in enumerate(syllables):
        for ch in syllable.visible_text:
            if ch.isalnum():
                syllable_map.append((index, ch.casefold()))
    karaoke_plain = "".join(ch for _, ch in syllable_map)
    original_text = original_text.replace("\r\n", "\n").replace("\r", "\n")
    text_positions = [index for index, ch in enumerate(original_text) if ch.isalnum()]
    text_plain = "".join(original_text[index].casefold() for index in text_positions)
    if not karaoke_plain:
        raise SyllableConversionError("В ASS нет видимого буквенно-цифрового karaoke-текста")
    matcher = SequenceMatcher(None, karaoke_plain, text_plain, autojunk=False)
    ratio = matcher.ratio()
    if ratio < minimum_ratio:
        raise SyllableConversionError(
            f"Текст ASS слишком сильно отличается от исходного TXT (совпадение {ratio:.1%}, требуется {minimum_ratio:.0%}). "
            "Убедитесь, что выбран TextGrid именно от этого текста и что MFA alignment завершился успешно."
        )
    position_to_syllable: list[int | None] = [None] * len(original_text)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(j2 - j1):
                position_to_syllable[text_positions[j1 + offset]] = syllable_map[i1 + offset][0]
        elif tag in {"replace", "insert"}:
            source_length = i2 - i1
            target_length = j2 - j1
            if source_length <= 0:
                syllable_index = _nearest_syllable(syllable_map, i1)
                for j in range(j1, j2):
                    position_to_syllable[text_positions[j]] = syllable_index
            else:
                for offset in range(target_length):
                    source_offset = min(source_length - 1, int((offset + 0.5) * source_length / max(1, target_length)))
                    position_to_syllable[text_positions[j1 + offset]] = syllable_map[i1 + source_offset][0]

    previous: list[int | None] = [None] * len(original_text)
    following: list[int | None] = [None] * len(original_text)
    symmetric_quote_openings = _opening_symmetric_quote_positions(original_text)
    last: int | None = None
    for index, ch in enumerate(original_text):
        if ch.isalnum() and position_to_syllable[index] is not None:
            last = position_to_syllable[index]
        previous[index] = last
    last = None
    for index in range(len(original_text) - 1, -1, -1):
        ch = original_text[index]
        if ch.isalnum() and position_to_syllable[index] is not None:
            last = position_to_syllable[index]
        following[index] = last

    bucket_items: list[list[tuple[int, str]]] = [[] for _ in syllables]
    for index, ch in enumerate(original_text):
        if ch.isalnum():
            syllable_index = position_to_syllable[index]
            if syllable_index is not None:
                bucket_items[syllable_index].append((index, ch))
        elif ch in _OPENING_PUNCT or index in symmetric_quote_openings:
            syllable_index = following[index] if following[index] is not None else previous[index]
            if syllable_index is not None:
                bucket_items[syllable_index].append((index, ch))
        else:
            syllable_index = previous[index] if previous[index] is not None else following[index]
            if syllable_index is not None:
                bucket_items[syllable_index].append((index, ch))
    buckets = ["".join(ch for _, ch in sorted(items)) for items in bucket_items]
    return buckets, ratio, len(text_plain)


def restore_document_text(
    document: AssDocument,
    original_text: str,
    *,
    minimum_ratio: float = 0.9,
) -> TextRestorationReport:
    """Restore exact TXT case/punctuation/line breaks without render layout tags."""

    syllables = document.karaoke_syllables()
    if not syllables:
        raise SyllableConversionError("В ASS не найдены karaoke-теги")
    buckets, ratio, normalized_count = _restored_buckets(
        syllables, original_text, minimum_ratio=minimum_ratio
    )
    global_index = {syllable.id: index for index, syllable in enumerate(syllables)}
    for event in document.events():
        event_syllables = [s for s in syllables if s.event_line_index == event.line_index]
        if not event_syllables:
            continue
        prefix = event.text[:event_syllables[0].tag_block_start]
        parts = [prefix]
        for syllable in event_syllables:
            block = event.text[syllable.tag_block_start:syllable.tag_block_end]
            parts.append(block)
            parts.append(_escape_ass_text(buckets[global_index[syllable.id]]))
        event.text = "".join(parts)
        event.commit()

    visible = "".join(s.visible_text for s in document.karaoke_syllables())
    if _normalize_characters(visible) != _normalize_characters(original_text):
        raise SyllableConversionError("Восстановленный видимый текст не совпадает с исходным TXT")
    return TextRestorationReport(len(syllables), normalized_count, ratio)


def restore_ass_text(
    ass_path: str | Path,
    transcript_path: str | Path,
    output_path: str | Path | None = None,
    *,
    minimum_ratio: float = 0.9,
) -> TextRestorationReport:
    document = AssDocument.load(ass_path)
    original = Path(transcript_path).read_text(encoding="utf-8-sig")
    report = restore_document_text(document, original, minimum_ratio=minimum_ratio)
    document.save(output_path or ass_path)
    return report


def flatten_ass_dialogues(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    start_time: float | None = None,
    end_time: float | None = None,
) -> int:
    """Merge Dialogue events into one title and retain every pause as timing.

    Optional bounds make that single title span a complete TextGrid/audio range,
    including leading and trailing silence.
    """

    document = AssDocument.load(input_path)
    all_syllables = document.karaoke_syllables()
    event_lines = {syllable.event_line_index for syllable in all_syllables}
    events = [
        event for event in document.events()
        if event.kind == "Dialogue" and event.line_index in event_lines
    ]
    if not events:
        raise SyllableConversionError("В ASS не найдены Dialogue с karaoke-тегами")
    events.sort(key=lambda event: (event.start, event.line_index))
    first = events[0]
    merged_start = events[0].start if start_time is None else min(float(start_time), events[0].start)
    merged_end = max(event.end for event in events)
    if end_time is not None:
        merged_end = max(merged_end, float(end_time))
    pieces: list[str] = []
    leading_gap_cs = max(0, int(round((events[0].start - merged_start) * 100)))
    if leading_gap_cs:
        pieces.append(f"{{\\k{leading_gap_cs}}}")
    pieces.append(first.text)
    current_end = first.end
    for event in events[1:]:
        gap_cs = max(0, int(round((event.start - current_end) * 100)))
        if gap_cs:
            pieces.append(f"{{\\k{gap_cs}}}")
        if pieces and not re.search(r"(?:\s|\\[Nnh])$", pieces[-1]) and not re.match(r"^(?:\s|\\[Nnh])", event.text):
            pieces.append(" ")
        pieces.append(event.text)
        current_end = max(current_end, event.end)
    trailing_gap_cs = max(0, int(round((merged_end - current_end) * 100)))
    if trailing_gap_cs:
        pieces.append(f"{{\\k{trailing_gap_cs}}}")
    first.start_raw = format_ass_time(merged_start)
    first.end_raw = format_ass_time(merged_end)
    first.text = "".join(pieces)
    first.commit()
    remove_lines = {event.line_index for event in events[1:]}
    document.lines = [line for index, line in enumerate(document.lines) if index not in remove_lines]
    document.save(output_path or input_path)
    return len(events)


def _event_targets(plain: str, profile: LanguageProfile) -> list[tuple[int, int, str]]:
    targets: list[tuple[int, int, str]] = []
    cursor = 0
    for match in re.finditer(r"\S+", plain, re.UNICODE):
        prefix = plain[cursor:match.start()]
        pieces = split_text_syllables(match.group(0), profile)
        local = match.start()
        for index, piece in enumerate(pieces):
            start = local
            end = local + len(piece)
            text = (prefix if index == 0 else "") + piece
            targets.append((start - (len(prefix) if index == 0 else 0), end, text))
            local = end
        cursor = match.end()
    if not targets:
        return [(0, len(plain), plain)]
    if cursor < len(plain):
        start, end, text = targets[-1]
        targets[-1] = (start, len(plain), text + plain[cursor:])
    return targets


def _split_duration(duration: int, weights: Sequence[int]) -> list[int]:
    if not weights:
        return []
    total = max(1, sum(weights))
    boundaries = [0]
    cumulative = 0
    for weight in weights:
        cumulative += weight
        boundaries.append(int(round(duration * cumulative / total)))
    return [boundaries[index + 1] - boundaries[index] for index in range(len(weights))]


def _syllabify_event_text(event_text: str, units: Sequence[KaraokeSyllable], profile: LanguageProfile) -> str:
    if not units:
        return event_text
    plain = "".join(unit.visible_text for unit in units)
    targets = _event_targets(plain, profile)
    durations = [0] * len(targets)
    gaps: list[tuple[int, KaraokeSyllable]] = []
    position = 0
    for unit in units:
        length = len(unit.visible_text)
        if length == 0:
            gaps.append((position, unit))
            continue
        overlaps = [
            max(0, min(position + length, end) - max(position, start))
            for start, end, _ in targets
        ]
        indexes = [index for index, weight in enumerate(overlaps) if weight > 0]
        shares = _split_duration(unit.duration_cs, [overlaps[index] for index in indexes])
        for index, share in zip(indexes, shares):
            durations[index] += share
        position += length

    prefix = event_text[:units[0].tag_block_start]
    result = [prefix]
    gap_cursor = 0
    for target_index, (start, _end, text) in enumerate(targets):
        while gap_cursor < len(gaps) and gaps[gap_cursor][0] <= start:
            gap = gaps[gap_cursor][1]
            result.append(f"{{\\{gap.tag_type.value}{gap.duration_cs}}}")
            gap_cursor += 1
        tag = next((unit.tag_type for unit in units if unit.visible_text), KaraokeTagType.KF)
        result.append(f"{{\\{tag.value}{durations[target_index]}}}{_escape_ass_text(text)}")
    while gap_cursor < len(gaps):
        gap = gaps[gap_cursor][1]
        result.append(f"{{\\{gap.tag_type.value}{gap.duration_cs}}}")
        gap_cursor += 1
    return "".join(result)


def convert_ass_to_syllables(
    input_path: str | Path,
    output_path: str | Path,
    language: str | LanguageProfile,
    *,
    transcript_path: str | Path | None = None,
    flatten: bool = False,
) -> SyllabificationReport:
    profile = profile_for_language(language)
    document = AssDocument.load(input_path)
    original_count = len(document.karaoke_syllables())
    for event in document.events():
        units = [s for s in document.karaoke_syllables() if s.event_line_index == event.line_index]
        if not units:
            continue
        event.text = _syllabify_event_text(event.text, units, profile)
        event.commit()
    document.save(output_path)
    if flatten:
        flatten_ass_dialogues(output_path)
    if transcript_path is not None:
        restore_ass_text(output_path, transcript_path)
    result_document = AssDocument.load(output_path)
    return SyllabificationReport(
        input_units=original_count,
        output_units=len(result_document.karaoke_syllables()),
        dialogue_lines=sum(1 for event in result_document.events() if event.kind == "Dialogue"),
        language=profile.code,
    )
