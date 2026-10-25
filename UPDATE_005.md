# Update 005 — Karaoke editor 4A

Apply this archive **after Updates 001–004** by extracting it over the project root.

## What changed

The Karaoke tab is now an actual ASS karaoke timing editor rather than a read-only timeline.

### Karaoke tag types

Selected syllables can be switched between:

- `\\k` — abrupt fill;
- `\\kf` — progressive fill;
- `\\ko` — abrupt fill with outline behaviour;
- `\\K` — progressive-fill alias retained as `\\K` when explicitly selected.

Changing a type rewrites only the karaoke command itself. Other override commands in the same block are retained.

### Timing boundary editing

Selecting one syllable shows yellow handles on editable shared boundaries with its adjacent syllables from the same ASS event. Dragging a handle:

- snaps to 0.01 s because ASS karaoke duration is stored in centiseconds;
- changes both adjacent durations;
- keeps their summed duration exactly unchanged;
- does not reset the current zoom/scroll position.

### Insert / Split / Merge / Delete

For duration `N` centiseconds, Insert and Split use:

- left = `floor(N/2)`;
- right = `N - left`.

Thus odd durations never lose a centisecond.

**Insert** keeps the selected syllable text in the first half and creates an empty second syllable.

**Split** divides both duration and visible content. The splitter skips ASS override blocks and keeps combining marks / common emoji ZWJ sequences with their base character as one visual unit.

**Merge** requires adjacent syllables in one ASS event. It sums durations and removes only the redundant karaoke commands. Colour, `\\org`, `\\fr`, `\\bord`, and other commands sharing those override blocks are retained.

**Delete** removes the selected visible content, then adds its duration to the following syllable. For the last syllable of an event, duration goes to the previous one. Deleting the only karaoke syllable in an event is refused because there is no neighbour that can preserve the timing.

### Safety / history

- `Ctrl+Z`: Undo.
- `Ctrl+Y` or `Ctrl+Shift+Z`: Redo.
- `Ctrl+S`: Save.
- `Ctrl+Shift+S`: Save As.
- Save is still atomic and writes `<file>.ass.bak` before replacing an existing ASS.
- Unsaved ASS changes are marked with `*` and prompt before closing/opening another file/project.
- Structural/timing karaoke changes clear the live SPS transfer. If an exact-SPS measurement sidecar exists, it is moved to a timestamped `.stale-...json` file before the edit so shifted karaoke IDs cannot silently pick up incorrect old measurements. A tag-type-only edit leaves SPS measurements valid.

## Test status

Update 005 adds karaoke-edit regression tests on top of all previous tests, including preservation of red colour tags and the far-origin/rotation-style override commands used elsewhere in this project.
