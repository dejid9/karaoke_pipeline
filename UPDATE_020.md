# Update 020 — timeline gestures + syllable-range render

Install over Update 019.

## Timeline navigation

- Mouse wheel / vertical touchpad gesture: zoom around pointer.
- Precision touchpad deltas are handled continuously instead of as one fixed notch.
- Shift + wheel / Shift + vertical touchpad gesture: horizontal pan.
- The same navigation semantics apply to the Karaoke/SPS detail timeline, overview, and SPS graph (shared viewport stays synchronized).
- Middle-button drag and the horizontal scrollbar remain available.

## Render a syllable fragment

The Render tab now has a common **Render fragment** section for standalone overlay and source-video burn-in:

- choose first and last visible karaoke syllable;
- or fill both bounds from the current Karaoke selection;
- optional seconds before the first syllable (pre-roll);
- optional seconds after the last syllable (post-roll).

The render-only ASS contains only the chosen contiguous karaoke interval. Text outside the selected syllables is not shown, even when the boundary falls inside a larger Dialogue event. The editable ASS is never changed.

### Source-video behaviour

- Input video is trimmed to `first syllable start - pre-roll` through `last syllable end + post-roll`.
- Subtitle timing is shifted to a zero-based output timeline.
- The first audio stream is checked with the ffprobe located next to the selected FFmpeg.
- If requested pre/post-roll would cross the beginning/end of available media/audio, rendering is refused and the dialog reports the maximum allowed value.
- Ranged audio is encoded to AAC for frame/timestamp-accurate cutting. If pre-roll > 0, audio fades in over the entire pre-roll. If post-roll > 0, it fades out over the entire post-roll.
- The existing full-video render remains unchanged when fragment mode is disabled.

## Validation

- Full suite: 86/86 tests pass.
- Real FFmpeg ranged burn-in test verifies output trimming and retained audio.
- GUI smoke test verifies range-from-selection and wheel/Shift+wheel viewport operations.
