from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Iterable, Mapping, Optional, Sequence

from .ass import (
    AssDocument, AssEvent, KaraokeSyllable, KaraokeTagType,
    replace_romanization_override, unspoken_spans,
)


class KaraokeEditError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class KaraokeEditResult:
    action: str
    selected_ids: tuple[str, ...] = ()
    focus_time: Optional[float] = None


def _event_for_line(document: AssDocument, line_index: int) -> AssEvent:
    event = next((item for item in document.events() if item.line_index == line_index), None)
    if event is None:
        raise KaraokeEditError(f"Dialogue/Comment at line {line_index} no longer exists")
    return event


def _lookup(document: AssDocument) -> dict[str, KaraokeSyllable]:
    return {s.id: s for s in document.karaoke_syllables()}


def _selected(document: AssDocument, ids: Iterable[str]) -> list[KaraokeSyllable]:
    lookup = _lookup(document)
    wanted = list(dict.fromkeys(ids))
    missing = [sid for sid in wanted if sid not in lookup]
    if missing:
        raise KaraokeEditError(f"Karaoke selection is stale: {', '.join(missing[:3])}")
    return [lookup[sid] for sid in wanted]


def _consecutive_same_event(items: Sequence[KaraokeSyllable], *, minimum: int = 1) -> list[KaraokeSyllable]:
    if len(items) < minimum:
        raise KaraokeEditError(f"Select at least {minimum} karaoke syllable(s)")
    ordered = sorted(items, key=lambda s: (s.event_line_index, s.syllable_ordinal))
    line = ordered[0].event_line_index
    if any(s.event_line_index != line for s in ordered):
        raise KaraokeEditError("The selected syllables must belong to one ASS event")
    ordinals = [s.syllable_ordinal for s in ordered]
    if ordinals != list(range(ordinals[0], ordinals[0] + len(ordinals))):
        raise KaraokeEditError("The selected syllables must be adjacent")
    return ordered


def _apply_replacements(source: str, replacements: Sequence[tuple[int, int, str]]) -> str:
    """Apply non-overlapping source-coordinate replacements right-to-left."""
    result = source
    last_start = len(source) + 1
    for start, end, replacement in sorted(replacements, key=lambda item: (item[0], item[1]), reverse=True):
        if start < 0 or end < start or end > len(source):
            raise KaraokeEditError("Internal ASS edit range is invalid")
        if end > last_start:
            raise KaraokeEditError("Internal ASS edits overlap")
        result = result[:start] + replacement + result[end:]
        last_start = start
    return result


def _karaoke_replacement(syllable: KaraokeSyllable, *, tag_type: Optional[KaraokeTagType] = None, duration_cs: Optional[int] = None) -> str:
    tag = tag_type or syllable.tag_type
    duration = syllable.duration_cs if duration_cs is None else int(duration_cs)
    if duration < 0:
        raise KaraokeEditError("Karaoke duration cannot be negative")
    return f"\\{tag.value}{duration}"


def _tag_removal_range(event_text: str, syllable: KaraokeSyllable) -> tuple[int, int, str]:
    """Remove only the karaoke command, or its whole block when it is empty.

    This deliberately preserves colour/origin/rotation/etc. commands sharing the
    same override block with the karaoke command.
    """
    block = event_text[syllable.tag_block_start:syllable.tag_block_end]
    local_start = syllable.tag_value_start - syllable.tag_block_start
    local_end = syllable.tag_value_end - syllable.tag_block_start
    without = block[:local_start] + block[local_end:]
    # Romanization belongs to the removed syllable, unlike visual positioning
    # and colour commands which intentionally survive Merge/Delete.
    without = replace_romanization_override(without, "")
    if without.startswith("{") and without.endswith("}") and not without[1:-1].strip():
        return syllable.tag_block_start, syllable.tag_block_end, ""
    return syllable.tag_value_start, syllable.tag_value_end, ""


def _keep_override_blocks(raw: str) -> str:
    return "".join(re.findall(r"\{[^{}]*\}", raw))


def _is_cluster_extend(ch: str) -> bool:
    code = ord(ch)
    return (
        bool(unicodedata.combining(ch))
        or 0xFE00 <= code <= 0xFE0F
        or 0xE0100 <= code <= 0xE01EF
        or 0x1F3FB <= code <= 0x1F3FF
    )


def _visible_unit_spans(raw: str) -> list[tuple[int, int]]:
    """Approximate Unicode grapheme spans in raw ASS text without touching tags.

    Override blocks do not count as visible units. ASS escapes ``\\N``, ``\\n``
    and ``\\h`` count as one unit. Combining marks, variation selectors, emoji
    modifiers and basic ZWJ chains stay attached to their base character.
    """
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(raw)
    while i < n:
        if raw[i] == "{":
            close = raw.find("}", i + 1)
            if close >= 0:
                i = close + 1
                continue
        if raw[i] == "\\" and i + 1 < n and raw[i + 1] in "Nnh":
            spans.append((i, i + 2))
            i += 2
            continue
        start = i
        i += 1
        while i < n and _is_cluster_extend(raw[i]):
            i += 1
        while i < n and raw[i] == "\u200d":
            # Keep ZWJ + next base + its modifiers in the same cluster.
            i += 1
            if i < n:
                i += 1
                while i < n and _is_cluster_extend(raw[i]):
                    i += 1
        spans.append((start, i))
    return spans


def split_raw_text_half(raw: str) -> tuple[str, str]:
    spans = _visible_unit_spans(raw)
    if len(spans) < 2:
        raise KaraokeEditError("The syllable text has fewer than two visible units; use Insert instead")
    left_count = max(1, len(spans) // 2)
    split_at = spans[left_count - 1][1]
    return raw[:split_at], raw[split_at:]


def split_raw_text_ratio(raw: str, ratio: float) -> tuple[str, str]:
    r"""Split visible ASS text proportionally without counting override tags.

    ``ratio`` is the requested share of the syllable duration that remains on
    the left side.  ASS override blocks are ignored when counting visible
    units, as are the second bytes of ``\N``/``\n``/``\h`` escapes.  The
    split is always placed between complete visible/grapheme units, so an
    override block is never cut in half.

    Empty syllables are intentionally supported: this is what makes a blank
    karaoke template useful for timing a song before its lyrics are known.
    """
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        ratio = 0.5
    ratio = max(0.0, min(1.0, ratio))
    spans = _visible_unit_spans(raw)
    count = len(spans)
    if count == 0:
        # Preserve any non-visible formatting verbatim on the first half.
        return raw, ""
    if count == 1:
        # A single grapheme cannot be divided. Put the complete raw fragment on
        # the temporally larger side; this also keeps its surrounding tags with
        # the visible character they style.
        return (raw, "") if ratio >= 0.5 else ("", raw)
    left_count = int(count * ratio + 0.5)
    left_count = max(1, min(count - 1, left_count))
    split_at = spans[left_count - 1][1]
    return raw[:split_at], raw[split_at:]


_KARAOKE_IN_OVERRIDE_RE = re.compile(r"\\(?:kf|ko|k|K)\s*\d+", re.IGNORECASE)
_OVERRIDE_BLOCK_RE = re.compile(r"\{[^{}]*\}")
_PRIMARY_COLOUR_COMMAND_RE = re.compile(
    r"\\(?:1?c)(?:&H[0-9A-Fa-f]+&?)?(?=\\|\}|$)", re.IGNORECASE
)


def _replace_primary_colour(block: str, command: str) -> str:
    """Put one primary-colour command in an existing override block."""

    cleaned = _PRIMARY_COLOUR_COMMAND_RE.sub("", block)
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        raise KaraokeEditError("Invalid ASS override block")
    return cleaned[:-1] + command + "}"


def colour_burst(document: AssDocument, ids: Iterable[str]) -> KaraokeEditResult:
    r"""Colour one adjacent syllable range red using the legacy ASS markers.

    The opening marker is written into the first karaoke block as ``\c&Hff``.
    A bare ``\c`` is written into the following karaoke block, exactly like the
    archived scripts; when the range reaches the event end, ``{\c}`` is appended.
    """

    selected_items = _selected(document, ids)
    if not selected_items:
        raise KaraokeEditError("Select at least one karaoke syllable")
    selected_items = sorted(selected_items, key=lambda item: (item.event_line_index, item.syllable_ordinal))
    line_index = selected_items[0].event_line_index
    if any(item.event_line_index != line_index for item in selected_items):
        raise KaraokeEditError("The selected syllables must belong to one ASS event")
    event = _event_for_line(document, line_index)
    event_items = [
        item for item in document.karaoke_syllables()
        if item.event_line_index == line_index
    ]
    first_ordinal = selected_items[0].syllable_ordinal
    last_ordinal = selected_items[-1].syllable_ordinal
    selected_ids = {item.id for item in selected_items}
    # SPS calculations omit timing-only gap units. Permit those omissions while
    # still rejecting a discontinuous selection that skips a visible syllable.
    skipped_visible = [
        item.id for item in event_items[first_ordinal:last_ordinal + 1]
        if item.id not in selected_ids and item.visible_text.strip()
    ]
    if skipped_visible:
        raise KaraokeEditError("The selected syllables must form one continuous visible range")
    first = event_items[first_ordinal]
    last = event_items[last_ordinal]
    first_block = event.text[first.tag_block_start:first.tag_block_end]
    replacements: list[tuple[int, int, str]] = [
        (
            first.tag_block_start,
            first.tag_block_end,
            _replace_primary_colour(first_block, r"\c&Hff"),
        )
    ]
    next_ordinal = last.syllable_ordinal + 1
    if next_ordinal < len(event_items):
        following = event_items[next_ordinal]
        following_block = event.text[following.tag_block_start:following.tag_block_end]
        replacements.append(
            (
                following.tag_block_start,
                following.tag_block_end,
                _replace_primary_colour(following_block, r"\c"),
            )
        )
    else:
        end_of_last = last.tag_block_end + len(last.raw_text)
        replacements.append((end_of_last, end_of_last, r"{\c}"))
    event.text = _apply_replacements(event.text, replacements)
    event.commit()
    selected = tuple(item.id for item in selected_items)
    return KaraokeEditResult("colour-burst", selected, (first.start + last.end) / 2)


def uncolour_burst(document: AssDocument, ids: Iterable[str]) -> KaraokeEditResult:
    """Remove red burst state from selected syllables without changing timing.

    A bare ``\\c`` starts every removed span.  If the selection cuts a hole
    inside a longer burst, ``\\c&Hff`` is restored on the first following
    syllable so unselected red syllables keep their state.
    """
    selected_items = _selected(document, ids)
    if not selected_items:
        raise KaraokeEditError("Select at least one karaoke syllable")
    selected_ids = {item.id for item in selected_items}
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in selected_items:
        by_event.setdefault(item.event_line_index, []).append(item)

    changed: list[KaraokeSyllable] = []
    for line_index, selected_group in by_event.items():
        event = _event_for_line(document, line_index)
        event_items = [
            item for item in document.karaoke_syllables()
            if item.event_line_index == line_index
        ]
        marked_ordinals = {
            item.syllable_ordinal for item in selected_group if item.burst_marked
        }
        if not marked_ordinals:
            continue
        changed.extend(item for item in selected_group if item.burst_marked)
        starts = [
            ordinal for ordinal in sorted(marked_ordinals)
            if ordinal - 1 not in marked_ordinals
        ]
        ends = [
            ordinal for ordinal in sorted(marked_ordinals)
            if ordinal + 1 not in marked_ordinals
        ]
        replacements: list[tuple[int, int, str]] = []
        for ordinal in starts:
            first = event_items[ordinal]
            block = event.text[first.tag_block_start:first.tag_block_end]
            replacements.append((
                first.tag_block_start, first.tag_block_end,
                _replace_primary_colour(block, r"\c"),
            ))
        for ordinal in ends:
            next_ordinal = ordinal + 1
            if next_ordinal >= len(event_items):
                continue
            following = event_items[next_ordinal]
            # Only reopen red when the unselected continuation was red before
            # this edit. Existing non-red/reset/custom colour stays untouched.
            if following.id in selected_ids or not following.burst_marked:
                continue
            block = event.text[following.tag_block_start:following.tag_block_end]
            replacements.append((
                following.tag_block_start, following.tag_block_end,
                _replace_primary_colour(block, r"\c&Hff"),
            ))
        event.text = _apply_replacements(event.text, replacements)
        event.commit()

    selected = tuple(item.id for item in selected_items)
    focus = sum((item.start + item.end) / 2 for item in selected_items) / len(selected_items)
    return KaraokeEditResult("uncolour-burst", selected, focus)


def _validate_editable_raw_text(raw: str) -> str:
    """Validate content edited between two karaoke tags.

    Literal newlines cannot live inside one ASS event line, so the GUI inserts
    ``\\N`` explicitly instead.  Karaoke commands are intentionally rejected
    here: timing/segmentation must go through Insert/Split/Merge so IDs and
    sidecar measurements stay coherent. Other override tags are preserved.
    """
    if "\n" in raw or "\r" in raw:
        raise KaraokeEditError(r"Literal line breaks are not allowed inside one ASS event; use \N")
    for block in _OVERRIDE_BLOCK_RE.findall(raw):
        if _KARAOKE_IN_OVERRIDE_RE.search(block):
            raise KaraokeEditError("Do not type karaoke timing tags into the text field; use Insert/Split/Merge")
    try:
        unspoken_spans(raw)
    except ValueError as exc:
        raise KaraokeEditError(str(exc)) from exc
    return raw


def _plain_visible_to_ass(value: str) -> str:
    value = str(value).replace("\r\n", "\n").replace("\r", "\n")
    if "{" in value or "}" in value:
        raise KaraokeEditError(
            "В редакторе всего текста нельзя вводить {…}: inline ASS-теги редактируются в поле отдельного слога"
        )
    raw = value.replace("\n", r"\N")
    return _validate_editable_raw_text(raw)


def _replace_visible_text_preserving_overrides(raw: str, value: str) -> str:
    """Replace visible payload while retaining every existing override block.

    Override blocks are anchored to their relative visible-character position.
    This keeps trailing burst resets and user formatting intact even when the
    whole-text editor changes the length or line breaks of a syllable.
    """
    new_raw = _plain_visible_to_ass(value)
    old_units = _visible_unit_spans(raw)
    new_units = _visible_unit_spans(new_raw)
    old_count = len(old_units)
    blocks: list[tuple[int, str]] = []
    visible_before = 0
    cursor = 0
    for match in _OVERRIDE_BLOCK_RE.finditer(raw):
        visible_before += len(_visible_unit_spans(raw[cursor:match.start()]))
        blocks.append((visible_before, match.group(0)))
        cursor = match.end()
    if not blocks:
        return new_raw

    insertions: list[tuple[int, str]] = []
    new_count = len(new_units)
    for anchor, block in blocks:
        if old_count <= 0:
            new_anchor = 0
        elif anchor >= old_count:
            new_anchor = new_count
        else:
            new_anchor = max(0, min(new_count, int(round(anchor / old_count * new_count))))
        raw_position = len(new_raw) if new_anchor >= new_count else new_units[new_anchor][0]
        insertions.append((raw_position, block))
    result = new_raw
    for position, block in reversed(insertions):
        result = result[:position] + block + result[position:]
    return result


def set_syllable_visible_texts(
    document: AssDocument, values: Mapping[str, str],
) -> KaraokeEditResult:
    """Apply whole-text edits without changing karaoke tags or syllable IDs."""
    if not values:
        raise KaraokeEditError("No karaoke text changes supplied")
    items = _selected(document, values.keys())
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in items:
        by_event.setdefault(item.event_line_index, []).append(item)
    for line_index, group in by_event.items():
        event = _event_for_line(document, line_index)
        replacements: list[tuple[int, int, str]] = []
        for item in group:
            raw = _replace_visible_text_preserving_overrides(
                item.raw_text, str(values[item.id])
            )
            start = item.tag_block_end
            replacements.append((start, start + len(item.raw_text), raw))
        event.text = _apply_replacements(event.text, replacements)
        event.commit()
    selected = tuple(item.id for item in items)
    focus = sum((item.start + item.end) / 2 for item in items) / len(items)
    return KaraokeEditResult("visible-text-batch", selected, focus)


def _validate_romanization(value: str) -> str:
    value = str(value or "").strip()
    if len(value) > 256:
        raise KaraokeEditError("Romanization is limited to 256 characters per syllable")
    if any(ch in value for ch in "{}\\\r\n"):
        raise KaraokeEditError("Romanization cannot contain ASS tags, backslashes or line breaks")
    return value


def set_syllable_romanization(
    document: AssDocument, syllable_id: str, value: str,
) -> KaraokeEditResult:
    item = _selected(document, [syllable_id])[0]
    value = _validate_romanization(value)
    event = _event_for_line(document, item.event_line_index)
    block = event.text[item.tag_block_start:item.tag_block_end]
    replacement = replace_romanization_override(block, value)
    event.text = _apply_replacements(
        event.text, [(item.tag_block_start, item.tag_block_end, replacement)]
    )
    event.commit()
    return KaraokeEditResult("romanization", (item.id,), (item.start + item.end) / 2)


def set_syllable_contents(
    document: AssDocument,
    *,
    text_values: Mapping[str, str] | None = None,
    romanization_values: Mapping[str, str] | None = None,
) -> KaraokeEditResult:
    """Apply text and manual romanization as one undoable source edit."""
    text_values = dict(text_values or {})
    romanization_values = dict(romanization_values or {})
    wanted = list(dict.fromkeys([*text_values, *romanization_values]))
    if not wanted:
        raise KaraokeEditError("No karaoke content changes supplied")
    items = _selected(document, wanted)
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in items:
        by_event.setdefault(item.event_line_index, []).append(item)
    for line_index, group in by_event.items():
        event = _event_for_line(document, line_index)
        replacements: list[tuple[int, int, str]] = []
        for item in group:
            if item.id in text_values:
                raw = _validate_editable_raw_text(str(text_values[item.id]))
                start = item.tag_block_end
                replacements.append((start, start + len(item.raw_text), raw))
            if item.id in romanization_values:
                value = _validate_romanization(romanization_values[item.id])
                block = event.text[item.tag_block_start:item.tag_block_end]
                replacements.append((
                    item.tag_block_start, item.tag_block_end,
                    replace_romanization_override(block, value),
                ))
        event.text = _apply_replacements(event.text, replacements)
        event.commit()
    selected = tuple(item.id for item in items)
    focus = sum((item.start + item.end) / 2 for item in items) / len(items)
    return KaraokeEditResult("content", selected, focus)


def _validate_split_offset(raw: str, offset: int) -> int:
    offset = int(offset)
    if offset <= 0 or offset >= len(raw):
        raise KaraokeEditError("Place the text cursor inside the syllable; use Insert for an empty half")
    for match in _OVERRIDE_BLOCK_RE.finditer(raw):
        if match.start() < offset < match.end():
            raise KaraokeEditError("The split cursor is inside an ASS override block; move it before or after the {...} tag")
    # Do not split an ASS escape such as \N / \n / \h.
    if offset > 0 and offset < len(raw) and raw[offset - 1] == "\\" and raw[offset] in "Nnh":
        raise KaraokeEditError(r"The split cursor is inside an ASS escape (\N/\n/\h)")
    # Keep basic grapheme/emoji sequences intact.
    if offset < len(raw) and (_is_cluster_extend(raw[offset]) or raw[offset] == "\u200d"):
        raise KaraokeEditError("The split cursor is inside a combined Unicode character")
    if offset > 0 and raw[offset - 1] == "\u200d":
        raise KaraokeEditError("The split cursor is inside an emoji ZWJ sequence")
    return offset


def set_syllable_text(document: AssDocument, syllable_id: str, raw_text: str) -> KaraokeEditResult:
    item = _selected(document, [syllable_id])[0]
    raw_text = _validate_editable_raw_text(str(raw_text))
    event = _event_for_line(document, item.event_line_index)
    content_start = item.tag_block_end
    content_end = content_start + len(item.raw_text)
    event.text = _apply_replacements(event.text, [(content_start, content_end, raw_text)])
    event.commit()
    return KaraokeEditResult("text", (item.id,), (item.start + item.end) / 2)


def set_syllable_texts(document: AssDocument, values: dict[str, str]) -> KaraokeEditResult:
    if not values:
        raise KaraokeEditError("No karaoke text changes supplied")
    items = _selected(document, values.keys())
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in items:
        by_event.setdefault(item.event_line_index, []).append(item)
    for line_index, group in by_event.items():
        event = _event_for_line(document, line_index)
        replacements = []
        for item in group:
            raw = _validate_editable_raw_text(str(values[item.id]))
            start = item.tag_block_end
            replacements.append((start, start + len(item.raw_text), raw))
        event.text = _apply_replacements(event.text, replacements)
        event.commit()
    selected = tuple(item.id for item in items)
    focus = sum((item.start + item.end) / 2 for item in items) / len(items)
    return KaraokeEditResult("text-batch", selected, focus)


def split_syllable_at_raw_offset(
    document: AssDocument,
    syllable_id: str,
    raw_offset: int,
    *,
    raw_text: Optional[str] = None,
    new_type: KaraokeTagType | str | None = None,
    boundary_time: Optional[float] = None,
) -> KaraokeEditResult:
    """Split text exactly at the editor cursor.

    When ``boundary_time`` is supplied, timing is cut at that playhead position;
    otherwise the legacy 50/50 timing split is retained for API compatibility.
    ``raw_text`` lets the GUI commit an unapplied draft as one undoable edit.
    """
    item = _selected(document, [syllable_id])[0]
    raw = item.raw_text if raw_text is None else _validate_editable_raw_text(str(raw_text))
    offset = _validate_split_offset(raw, raw_offset)
    left_raw, right_raw = raw[:offset], raw[offset:]
    if boundary_time is None:
        left_cs = item.duration_cs // 2
        right_cs = item.duration_cs - left_cs
        snapped_time = item.start + left_cs / 100.0
    else:
        left_cs, right_cs, snapped_time = _split_duration_at_time(item, boundary_time)
    new_tag = KaraokeTagType(new_type) if new_type is not None else item.tag_type
    event = _event_for_line(document, item.event_line_index)
    content_start = item.tag_block_end
    content_end = content_start + len(item.raw_text)
    replacement_content = left_raw + "{\\%s%d}" % (new_tag.value, right_cs) + right_raw
    event.text = _apply_replacements(
        event.text,
        [
            (item.tag_value_start, item.tag_value_end, _karaoke_replacement(item, duration_cs=left_cs)),
            (content_start, content_end, replacement_content),
        ],
    )
    event.commit()
    left_id = item.id
    right_id = f"L{item.event_line_index}:S{item.syllable_ordinal + 1}"
    return KaraokeEditResult("split-cursor", (left_id, right_id), snapped_time)


def set_tag_type(document: AssDocument, ids: Iterable[str], tag_type: KaraokeTagType | str) -> KaraokeEditResult:
    tag_type = KaraokeTagType(tag_type)
    items = _selected(document, ids)
    if not items:
        raise KaraokeEditError("Select at least one karaoke syllable")
    by_event: dict[int, list[KaraokeSyllable]] = {}
    for item in items:
        by_event.setdefault(item.event_line_index, []).append(item)
    for line_index, group in by_event.items():
        event = _event_for_line(document, line_index)
        replacements = [
            (s.tag_value_start, s.tag_value_end, _karaoke_replacement(s, tag_type=tag_type))
            for s in group
        ]
        event.text = _apply_replacements(event.text, replacements)
        event.commit()
    selected = tuple(s.id for s in items)
    focus = sum((s.start + s.end) / 2 for s in items) / len(items)
    return KaraokeEditResult("set-type", selected, focus)


def redistribute_boundary(
    document: AssDocument,
    left_id: str,
    right_id: str,
    boundary_time: float,
) -> KaraokeEditResult:
    left, right = _consecutive_same_event(_selected(document, [left_id, right_id]), minimum=2)
    if left.id != left_id:
        left, right = right, left
    if right.syllable_ordinal != left.syllable_ordinal + 1:
        raise KaraokeEditError("Boundary editing requires two adjacent syllables in timeline order")
    total_cs = left.duration_cs + right.duration_cs
    # ASS karaoke durations are integer centiseconds. Snap relative to the left
    # start so the pair's total duration is preserved exactly.
    new_left_cs = int(round((float(boundary_time) - left.start) * 100.0))
    new_left_cs = max(0, min(total_cs, new_left_cs))
    new_right_cs = total_cs - new_left_cs
    event = _event_for_line(document, left.event_line_index)
    event.text = _apply_replacements(
        event.text,
        [
            (left.tag_value_start, left.tag_value_end, _karaoke_replacement(left, duration_cs=new_left_cs)),
            (right.tag_value_start, right.tag_value_end, _karaoke_replacement(right, duration_cs=new_right_cs)),
        ],
    )
    event.commit()
    boundary = left.start + new_left_cs / 100.0
    return KaraokeEditResult("boundary", (left.id, right.id), boundary)


def _split_duration_at_time(item: KaraokeSyllable, boundary_time: float) -> tuple[int, int, float]:
    if item.duration_cs < 2:
        raise KaraokeEditError("The syllable is shorter than 2 centiseconds and cannot be split")
    left_cs = int(round((float(boundary_time) - item.start) * 100.0))
    if left_cs <= 0 or left_cs >= item.duration_cs:
        raise KaraokeEditError("Place the playback cursor strictly inside the syllable before splitting")
    right_cs = item.duration_cs - left_cs
    snapped_time = item.start + left_cs / 100.0
    return left_cs, right_cs, snapped_time


def insert_after_at_time(
    document: AssDocument,
    syllable_id: str,
    boundary_time: float,
    *,
    new_type: KaraokeTagType | str | None = None,
) -> KaraokeEditResult:
    """Insert an empty syllable by cutting the selected timing at playhead.

    The original text stays on the left, preserving the established Insert
    semantics; only the duration split point changes from 50/50 to the supplied
    timeline position.
    """
    item = _selected(document, [syllable_id])[0]
    track0_before = [s for s in document.karaoke_syllables() if getattr(s, "track", 0) == 0]
    track0_idx = next((i + 1 for i, s in enumerate(track0_before) if s.id == item.id), None)
    event = _event_for_line(document, item.event_line_index)
    event_items = [s for s in document.karaoke_syllables() if s.event_line_index == item.event_line_index]
    next_item = next((s for s in event_items if s.syllable_ordinal == item.syllable_ordinal + 1), None)
    insert_at = next_item.tag_block_start if next_item is not None else len(event.text)
    left_cs, right_cs, snapped_time = _split_duration_at_time(item, boundary_time)
    new_tag = KaraokeTagType(new_type) if new_type is not None else item.tag_type
    event.text = _apply_replacements(
        event.text,
        [
            (item.tag_value_start, item.tag_value_end, _karaoke_replacement(item, duration_cs=left_cs)),
            (insert_at, insert_at, "{\\%s%d}" % (new_tag.value, right_cs)),
        ],
    )
    event.commit()
    if getattr(item, "track", 0) == 0 and track0_idx is not None:
        adjust_id_references_after_track0_insert(document, track0_idx + 1)
    new_id = f"L{item.event_line_index}:S{item.syllable_ordinal + 1}"
    return KaraokeEditResult("insert-time", (new_id,), snapped_time)


def insert_after(
    document: AssDocument,
    syllable_id: str,
    *,
    new_type: KaraokeTagType | str | None = None,
) -> KaraokeEditResult:
    item = _selected(document, [syllable_id])[0]
    # Keep the public legacy helper deterministic for scripts/tests; the GUI now
    # calls ``insert_after_at_time`` with its playhead.
    boundary = item.start + (item.duration_cs // 2) / 100.0
    return insert_after_at_time(document, syllable_id, boundary, new_type=new_type)


def split_syllable_at_time(
    document: AssDocument,
    syllable_id: str,
    boundary_time: float,
    *,
    new_type: KaraokeTagType | str | None = None,
) -> KaraokeEditResult:
    """Split duration at playhead and divide visible text by the same ratio.

    ASS override blocks do not count as characters and are never split. Empty
    text is valid, which supports timing a blank ASS before lyrics are known.
    """
    item = _selected(document, [syllable_id])[0]
    event = _event_for_line(document, item.event_line_index)
    left_cs, right_cs, snapped_time = _split_duration_at_time(item, boundary_time)
    ratio = left_cs / item.duration_cs
    left_raw, right_raw = split_raw_text_ratio(item.raw_text, ratio)
    new_tag = KaraokeTagType(new_type) if new_type is not None else item.tag_type
    content_start = item.tag_block_end
    content_end = content_start + len(item.raw_text)
    replacement_content = left_raw + "{\\%s%d}" % (new_tag.value, right_cs) + right_raw
    event.text = _apply_replacements(
        event.text,
        [
            (item.tag_value_start, item.tag_value_end, _karaoke_replacement(item, duration_cs=left_cs)),
            (content_start, content_end, replacement_content),
        ],
    )
    event.commit()
    left_id = item.id
    right_id = f"L{item.event_line_index}:S{item.syllable_ordinal + 1}"
    return KaraokeEditResult("split-time", (left_id, right_id), snapped_time)


def split_syllable(
    document: AssDocument,
    syllable_id: str,
    *,
    new_type: KaraokeTagType | str | None = None,
) -> KaraokeEditResult:
    item = _selected(document, [syllable_id])[0]
    boundary = item.start + (item.duration_cs // 2) / 100.0
    return split_syllable_at_time(document, syllable_id, boundary, new_type=new_type)


def merge_syllables(document: AssDocument, ids: Iterable[str]) -> KaraokeEditResult:
    items = _consecutive_same_event(_selected(document, ids), minimum=2)
    merged_romanization = "".join(item.romanization for item in items)
    event = _event_for_line(document, items[0].event_line_index)
    total_cs = sum(s.duration_cs for s in items)
    replacements: list[tuple[int, int, str]] = [
        (items[0].tag_value_start, items[0].tag_value_end, _karaoke_replacement(items[0], duration_cs=total_cs))
    ]
    for item in items[1:]:
        replacements.append(_tag_removal_range(event.text, item))
    event.text = _apply_replacements(event.text, replacements)
    event.commit()
    first_id = items[0].id
    if merged_romanization:
        set_syllable_romanization(document, first_id, merged_romanization)
    return KaraokeEditResult("merge", (first_id,), (items[0].start + items[-1].end) / 2)


def adjust_id_references_after_track0_delete(document: AssDocument, deleted_track0_id: int) -> None:
    if deleted_track0_id is None or deleted_track0_id <= 0:
        return
    id_pattern = re.compile(r"\\id0:(\d+)")
    events_to_delete = []
    for event in document.events():
        effect = str(getattr(event, "effect", "") or "").strip()
        if not effect.startswith("track:"):
            continue
        def repl(match):
            val = int(match.group(1))
            if val == deleted_track0_id:
                return "__DELETE_REF__"
            elif val > deleted_track0_id:
                return f"\\id0:{val - 1}"
            return match.group(0)

        new_text = id_pattern.sub(repl, event.text)
        if "__DELETE_REF__" in new_text:
            new_text = re.sub(r"\{[^{}]*__DELETE_REF__[^}]*\}[^{}]*", "", new_text)
            new_text = new_text.replace("__DELETE_REF__", "")
            if not _KARAOKE_IN_OVERRIDE_RE.search(new_text):
                events_to_delete.append(event.line_index)
                continue
        if new_text != event.text:
            event.text = new_text
            event.commit()
    for line_index in sorted(events_to_delete, reverse=True):
        del document.lines[line_index]


def adjust_id_references_after_track0_insert(document: AssDocument, inserted_track0_id: int) -> None:
    if inserted_track0_id is None or inserted_track0_id <= 0:
        return
    id_pattern = re.compile(r"\\id0:(\d+)")
    for event in document.events():
        effect = str(getattr(event, "effect", "") or "").strip()
        if not effect.startswith("track:"):
            continue
        def repl(match):
            val = int(match.group(1))
            if val >= inserted_track0_id:
                return f"\\id0:{val + 1}"
            return match.group(0)

        new_text = id_pattern.sub(repl, event.text)
        if new_text != event.text:
            event.text = new_text
            event.commit()


def set_syllable_timing(
    document: AssDocument,
    syllable_id: str,
    new_start: float,
    new_end: float,
) -> KaraokeEditResult:
    """Adjust a single syllable's timing by rewriting its karaoke duration.

    The syllable must stay inside its parent ASS event; neighbouring syllables
    in the same event are shifted to preserve the event's total duration and
    the relative timing of syllables outside the edited span.
    """
    s = _selected(document, [syllable_id])[0]
    event = _event_for_line(document, s.event_line_index)
    all_syllables = document.karaoke_syllables()
    event_syllables = [k for k in all_syllables if k.event_line_index == s.event_line_index]
    if not event_syllables:
        raise KaraokeEditError("No karaoke syllables found in parent event")

    # Compute new duration in centiseconds (ASS precision)
    new_duration_cs = max(1, int(round((new_end - new_start) * 100.0)))
    old_duration_cs = s.duration_cs
    delta_cs = new_duration_cs - old_duration_cs

    # Rebuild karaoke tags for all syllables in this event
    replacements: list[tuple[int, int, str]] = []
    cumulative_time = event.start
    for idx, k in enumerate(event_syllables):
        if k.id == s.id:
            dur_cs = new_duration_cs
            # If start shifted, we absorb the shift into the *previous* syllable's
            # duration when possible, otherwise into this syllable's start offset.
            start_shift_cs = int(round((new_start - k.start) * 100.0))
            if start_shift_cs != 0 and idx > 0:
                # Adjust previous syllable duration to absorb the shift
                prev = event_syllables[idx - 1]
                prev_new_dur = max(1, prev.duration_cs + start_shift_cs)
                # Update previous replacement if it exists
                for i, (start, end, repl) in enumerate(replacements):
                    if start == prev.tag_value_start:
                        replacements[i] = (
                            start,
                            end,
                            _karaoke_replacement(prev, duration_cs=prev_new_dur),
                        )
                        break
                # Compensate delta so this syllable gets correct final duration
                dur_cs = max(1, new_duration_cs - start_shift_cs)
            cumulative_time = new_start
        else:
            dur_cs = k.duration_cs
            if k.start > s.start and delta_cs != 0:
                # Shift later syllables by adjusting the one immediately after
                dur_cs = max(1, dur_cs + delta_cs)
                delta_cs = 0  # Only apply once
        replacements.append(
            (k.tag_value_start, k.tag_value_end, _karaoke_replacement(k, duration_cs=dur_cs))
        )
        cumulative_time += dur_cs / 100.0

    event.text = _apply_replacements(event.text, replacements)
    event.commit()
    return KaraokeEditResult("timing", (s.id,), new_start)


def delete_syllable(document: AssDocument, syllable_id: str) -> KaraokeEditResult:
    item = _selected(document, [syllable_id])[0]
    track0_before = [s for s in document.karaoke_syllables() if getattr(s, "track", 0) == 0]
    track0_idx = next((i + 1 for i, s in enumerate(track0_before) if s.id == item.id), None)
    event = _event_for_line(document, item.event_line_index)
    event_items = [s for s in document.karaoke_syllables() if s.event_line_index == item.event_line_index]
    if len(event_items) <= 1:
        if len(document.events()) > 1 or getattr(item, "track", 0) != 0:
            del document.lines[item.event_line_index]
            if getattr(item, "track", 0) == 0 and track0_idx is not None:
                adjust_id_references_after_track0_delete(document, track0_idx)
            return KaraokeEditResult("delete", (), item.start)
        raise KaraokeEditError("Cannot delete the only karaoke syllable in an ASS event")
    if item.syllable_ordinal + 1 < len(event_items):
        receiver = event_items[item.syllable_ordinal + 1]
        receiver_new_id = item.id  # ordinals shift left after deletion
    else:
        receiver = event_items[item.syllable_ordinal - 1]
        receiver_new_id = receiver.id

    replacements: list[tuple[int, int, str]] = []
    # Keep non-karaoke commands from both the karaoke block and raw content, but
    # remove the selected visible text itself.
    replacements.append(_tag_removal_range(event.text, item))
    content_start = item.tag_block_end
    content_end = content_start + len(item.raw_text)
    replacements.append((content_start, content_end, _keep_override_blocks(item.raw_text)))
    replacements.append(
        (
            receiver.tag_value_start,
            receiver.tag_value_end,
            _karaoke_replacement(receiver, duration_cs=receiver.duration_cs + item.duration_cs),
        )
    )
    # If receiver/item share a rare multi-karaoke override block, generic source
    # replacements overlap. Refuse rather than corrupting hand-authored tags.
    event.text = _apply_replacements(event.text, replacements)
    event.commit()
    if getattr(item, "track", 0) == 0 and track0_idx is not None:
        adjust_id_references_after_track0_delete(document, track0_idx)
    return KaraokeEditResult("delete", (receiver_new_id,), (item.start + item.end) / 2)
