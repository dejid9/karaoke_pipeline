# Update 010 — Alignment 7A: TextGrid -> timing-exact ASS

Apply this archive over a project that already has Updates 001–009.

## Main changes

- Added `karaoke_core/alignment.py` with a Praat/MFA TextGrid parser and a new conversion engine.
- Added an **Alignment** GUI tab for inspecting a TextGrid and producing/opening ASS.
- Added CLI `scripts/textgrid_to_ass.py`.
- Fixed SPS treatment of timing-only pauses: empty karaoke tags preserve real gaps but no longer count as spoken syllables.
- Added an explicit MFA 3.x command builder (`align_hf` or legacy `align`) with no implicit language/model fallback.

## Timing behaviour

The converter no longer truncates every phone duration independently. It builds absolute/cumulative boundaries, rounds the line once to centiseconds, and derives each karaoke duration from those quantized boundaries. Therefore the sum of all karaoke tags exactly matches the ASS event duration.

Pauses between words inside one Dialogue are represented as empty `{\\kNN}` timing segments. This keeps the next word at its true start without assigning the silence to the previous visible syllable. The SPS engine detects these segments as gaps and excludes them from SPS counts, burst candidates, manual-burst statistics, and graph points.

## Text/phone mapping

When a transcript is supplied and its whitespace tokenization matches the MFA words tier (directly or by normalized punctuation/case matching), the transcript's spelling/punctuation is kept. Otherwise conversion explicitly reports a warning and falls back to the words-tier labels.

Within each word, visible grapheme groups are split across the word interval. If a phones tier exists and enough distinct phone boundaries are available, internal grapheme boundaries are snapped to the nearest phone boundaries. Otherwise proportional splitting is used rather than generating a run of zero-length segments.

## Scope

This is 7A only. It consumes an already generated TextGrid. Update 011/7B should add MFA process execution, corpus preparation, model/version handling, logs, cancellation, and automatic import of the produced TextGrid.
