# Update 006 — Karaoke editor 4B (text + split at caret)

Apply this archive **after Updates 001–005** by extracting it over the project root.

## Syllable text editor

The Karaoke tab now contains a text editor for one selected syllable. It edits
only the ASS content between that syllable's karaoke tag and the next karaoke
tag. Inline override commands such as `\\c`, `\\bord`, `\\fr`, `\\org`, etc. are
shown explicitly and kept under user control rather than being silently
repositioned.

- `Ctrl+Enter` applies the current text.
- `F2` focuses the text editor.
- Enter inserts the ASS `\\N` line-break escape.
- Navigating to another syllable keeps an unapplied per-syllable draft.
- Pending drafts participate in the unsaved `*` marker and are applied before
  Save or before a structural edit that could shift syllable IDs.
- Karaoke timing commands typed manually inside the text field are rejected;
  Insert/Split/Merge remain the authoritative way to change segmentation.

A text-only edit does **not** archive/delete the exact-SPS measurement sidecar,
because syllable IDs and timings are unchanged.

## Split at cursor

`Разделить по курсору` uses the actual caret position in the current text.
Timing still follows the 4A exact integer-centisecond rule:

- left = `floor(N/2)`;
- right = `N - left`.

If the current text is still only a draft, the draft plus the split are applied
as one ASS document edit, so Undo restores the pre-edit state in one step.

The split is refused when the caret would cut through:

- an ASS override block `{...}`;
- `\\N`, `\\n` or `\\h`;
- a combining-character sequence;
- a common emoji ZWJ sequence.

## Waveform/text interaction

- Double-click a karaoke syllable to select it and focus the text editor.
- Previous/next buttons navigate syllables and center the detail timeline while
  preserving its zoom span.
- `▶ Слог` auditions the selected karaoke interval through `ffplay`.
- Insert from 4A now leaves the new empty syllable selected and ready for text.

## Safety fixes

- The 4A save path accidentally invoked `AssDocument.save()` twice; Update 006
  removes the redundant second call.
- Structural edits still stale/archive exact-SPS sidecars as in Update 005.
- Text-only edits preserve them.

## Test status

Update 006 adds regression coverage for text-only timing preservation, rejection
of embedded karaoke timing tags, cursor splits, inline-tag preservation, and SPS
sidecar safety. GUI smoke testing also covers draft navigation, caret split,
viewport retention with waveform loaded, empty-syllable entry, and Save.
