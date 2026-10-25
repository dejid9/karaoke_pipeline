# Update 003 — GUI 3B-1: waveform + perceptual SPS trimming

Apply this archive **after Update 001 and Update 002** by extracting it over the
project root. It contains only files added or changed by this update.

## Main changes

- real waveform generation from audio/video via FFmpeg;
- compact cached waveform envelope;
- waveform displayed in both detailed timelines;
- independent draggable SPS measurement start/end handles;
- changed measured syllables have a distinct visual state;
- exact numeric Start/End fields and live `count / span = SPS` summary;
- measurement autosave/load in a sidecar, never in the ASS;
- sidecar merging is safe for partial SPS transfers;
- actual measurement reset fixed;
- selected measured range playback via ffplay;
- edit/navigation state no longer jumps back to the beginning after trim.

## Data safety

Update 003 does not write to the opened ASS when measuring SPS. Waveform creation
also does not modify the media file. Measurement overrides are kept in
`cache/sps_measurements.json` for projects, or in a sibling
`<name>.sps-measurements.json` when working without a project.

## Waveform cache

The default envelope is 100 bins/s (10 ms per peak bin) from mono 8 kHz decoding.
This is not the future spectrogram analysis; it is only an efficient waveform
representation for navigation and boundary trimming.

## Playback

Playback uses `ffplay`. The app first looks next to the configured/resolved
FFmpeg executable, then falls back to `PATH`.

## Deferred to Update 004 / 3B-2

Spectrogram rendering and its low/mid/high voice + expected-SPS presets are not in
this package. See `notes/GUI_IMPLEMENTATION_STATUS.md` and
`notes/FUTURE_GUI_NOTES.md`.
