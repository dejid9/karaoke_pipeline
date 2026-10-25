# Future GUI requirements (recorded after update 001)

These are intentionally **not** implemented in update 001; the core exposes the
state they need so the GUI can be added without changing ASS parsing again.

## Two timelines in both editing tabs

Both **Karaoke Editor** and **SPS Measurement** need:

1. a zoomable/editable detailed timeline (waveform/syllable boundaries/tracks);
2. a separate navigation/overview timeline, like an NLE overview strip.

For SPS Measurement, automatic burst candidates are calculated immediately before
sending the current ASS/selection into the tab.  Their speed is shown **only on the
overview timeline** using a cool-to-hot temperature scale.  `BurstCandidate.heat`
(0..1) is already emitted by the engine for this purpose.

## SPS Measurement != karaoke timing

Measurement boundaries are sidecar data and do not overwrite karaoke timing.
Syllables manually trimmed in SPS Measurement must be visually distinct.  The
core exposes `TimelineSyllable.measurement_changed` for that state.

Unlike karaoke syllables, measured syllables **do not have to touch**: independent
left/right perceptual trimming may intentionally leave gaps between adjacent
syllables.  Never normalize these gaps away.

## Spectrogram

SPS Measurement should optionally render a spectrogram alongside/instead of the
waveform.  Provide presets and manual controls for at least:

- voice pitch range / displayed frequency range;
- expected SPS / time-frequency trade-off (FFT/window length);
- FFT size/window length and overlap/hop;
- window function;
- min/max dB and dynamic range.

Presets should be treated as starting points, not hard rules: a lower voice often
benefits from a lower displayed frequency range, while very fast syllables need
better time resolution (shorter analysis windows) at the expense of frequency
resolution.

## ASS rendering / line spacing note

The existing project emulates extra line spacing because ASS has no dedicated
per-line-spacing override tag. `fix_reg_punct_int.py` uses `LINE_SPACING`,
`ANGLE_PER_PIXEL`, and a very distant `\\org(-2000000,0)` plus tiny incremental
`\\fr` rotations after `\\N`.  The lossless ASS core must preserve those tags
verbatim.  Rendering/layout work is a later update.
