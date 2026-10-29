from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.ass import AssDocument, KaraokeSyllable
from core.editor import (
    colour_burst, delete_syllable, insert_after, merge_syllables,
    set_syllable_romanization, set_syllable_text, set_tag_type,
    split_syllable, split_syllable_at_time, uncolour_burst,
)

DEMO_ASS = '''[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,40,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:04.00,Default,,0,0,0,,{\\k100}Ka{\\k100}ra{\\k100}o{\\k100}ke\nDialogue: 0,0:00:04.00,0:00:08.00,Default,,0,0,0,,{\\k100}mo{\\k100}bi{\\k100}le\n'''


@dataclass
class Snapshot:
    text: str


class EditorState:
    def __init__(self, on_change: Callable[[], None] | None = None):
        self.document = AssDocument.from_text(DEMO_ASS)
        self.selected_id: str | None = None
        self.cursor = 0.0
        self.in_point: float | None = None
        self.out_point: float | None = None
        self.speed = 1.0
        self.audio_layer = "both"
        self._undo: list[Snapshot] = []
        self._redo: list[Snapshot] = []
        self.on_change = on_change

    @property
    def syllables(self) -> list[KaraokeSyllable]:
        return list(self.document.karaoke_syllables())

    @property
    def selected(self) -> KaraokeSyllable | None:
        return next((s for s in self.syllables if s.id == self.selected_id), None)

    def load_ass(self, text: str) -> None:
        self.document = AssDocument.from_text(text)
        self.selected_id = None
        self._undo.clear(); self._redo.clear(); self.changed()

    def dumps(self) -> str:
        return self.document.dumps()

    def changed(self) -> None:
        if self.on_change: self.on_change()

    def mutate(self, operation: Callable[[], object]) -> None:
        self._undo.append(Snapshot(self.dumps()))
        self._redo.clear()
        operation(); self.changed()

    def undo(self) -> None:
        if not self._undo: return
        self._redo.append(Snapshot(self.dumps()))
        self.document = AssDocument.from_text(self._undo.pop().text); self.changed()

    def redo(self) -> None:
        if not self._redo: return
        self._undo.append(Snapshot(self.dumps()))
        self.document = AssDocument.from_text(self._redo.pop().text); self.changed()

    def select_at(self, time: float) -> None:
        item = next((s for s in self.syllables if s.start <= time <= s.end), None)
        if item: self.selected_id = item.id; self.cursor = time; self.changed()

    def split_at_cursor(self) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: split_syllable_at_time(self.document, selected.id, self.cursor))

    def split_half(self) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: split_syllable(self.document, selected.id))

    def insert(self) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: insert_after(self.document, selected.id))

    def delete(self) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: delete_syllable(self.document, selected.id))

    def merge(self) -> None:
        if not self.selected: return
        items = self.syllables; i = next((i for i, s in enumerate(items) if s.id == self.selected_id), -1)
        if i >= 1: self.mutate(lambda: merge_syllables(self.document, [items[i-1].id, items[i].id]))

    def set_text(self, value: str) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: set_syllable_text(self.document, selected.id, value))

    def set_romanization(self, value: str) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: set_syllable_romanization(self.document, selected.id, value))

    def burst(self, enabled: bool) -> None:
        selected = self.selected
        if selected:
            fn = colour_burst if enabled else uncolour_burst
            self.mutate(lambda: fn(self.document, [selected.id]))

    def apply_tag(self, value: str) -> None:
        selected = self.selected
        if selected: self.mutate(lambda: set_tag_type(self.document, [selected.id], value))
