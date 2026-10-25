# Update 033 — marker transport, blank ASS timing, playhead split

Install over Update 032.

## Shared Start/Finish markers and dedicated transport buttons

The previous separate ordinary-Play bounds and In/Out controls have been
collapsed into one pair of syllable markers. Both **Karaoke** and **Точный SPS**
show the same transport layout:

- `|←` — put the Start marker at the selected syllable;
- `|▶` — play from Start and continue to media EOF;
- `→|` — put the Finish marker after the selected syllable;
- `▶|` — play from the current playhead and stop at Finish;
- `|▶|` — play from Start through Finish;
- `↔` — set both markers from the current syllable selection;
- `×` — clear both markers.

The play glyph is the plain Unicode **U+25B6 BLACK RIGHT-POINTING TRIANGLE**,
without an emoji variation selector.

Ordinary Space/Play is intentionally independent of these markers. If Space is
pressed while a marker-bounded transport is active, that special playback is
cancelled and the cursor stays at the interruption point; the next Space starts
ordinary playback from there.

The fastest burst shown for a valid Start–Finish segment is calculated only by
the user-facing Legacy 1–2 s method. Precise SPS uses measurement/effective
syllable boundaries.

## Reliable playhead return

`После Stop/окончания вернуть полосу к точке старта` now stores a dedicated
return target only after a user playback command has been accepted by the audio
backend. Manual Stop and natural completion use one finalizer. A deferred
`after_idle` guard reapplies the final cursor once, so a stale queued playback
paint cannot overwrite the returned position after Stop.

Internal PortAudio restarts do not replace this user transport origin.

## Unnumbered tabs

The main tabs are now named simply:

- `Подготовка`
- `Караоке`
- `Точный SPS`
- `Рендер`
- `Логи`

## Blank ASS workflow

`Файл → Новый пустой ASS…` and the `ASS+` toolbar button create a new unsaved
ASS even when lyrics are unknown. The document starts with one invisible empty
karaoke timing span covering the known media duration. This seed is deliberate:
it gives the user something that can immediately be split at the playback
cursor. If no media duration can be determined, the GUI asks for it.

The user can therefore time a song first, save the ASS normally, and fill in
text later.

## Split/Insert at the playback cursor

GUI timing edits no longer divide duration 50/50:

- **Split** cuts the syllable at the current playback playhead;
- **Insert** cuts timing at the playhead, leaves the original text on the left,
  and creates an empty syllable on the right;
- **Split at text cursor** uses the text caret for the text boundary but still
  uses the playback playhead for the timing boundary.

For normal Split, visible text is divided in the same proportion as the timing.
ASS override blocks such as `{\\c&H...&}` are not counted as characters and are
never cut in half. `\\N`, `\\n` and `\\h` count as one visible unit; basic
combining/variation/ZWJ character clusters are kept intact. Empty syllables are
valid and can be repeatedly split, which is required by the blank-ASS workflow.

The split point is snapped to ASS centiseconds and must leave at least one
centisecond on each side.

## Undo / Redo

Document history shortcuts are available before ttk widget class bindings:

- `Ctrl+Z` — Undo;
- `Ctrl+Shift+Z` — Redo;
- `Ctrl+Y` — Redo.

Real text-entry widgets keep their local text undo behaviour; elsewhere these
shortcuts operate on karaoke document edits.
