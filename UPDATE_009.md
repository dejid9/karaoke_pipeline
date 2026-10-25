# Update 009 — SPS graph 6A

Apply after Updates 001–008 by extracting this archive over the project root.

## What changed

The SPS Measurement tab now contains a dedicated SPS graph synchronized with the
waveform/spectrogram timeline. It can show the original ASS timing, perceptually
trimmed exact-SPS timing, or both at once.

Available metrics:

- **Strict contained** — exact fixed window; counts syllables fully contained in
  the window.
- **Strict onset** — exact fixed window; counts syllable onsets in the window.
- **Legacy 1–2 s** — reproduces the archived `count / actual duration` approach.

The strict window length is configurable and defaults to 1.000 seconds.
Display smoothing is optional and does not alter tooltip/CSV measurement values.

The graph and detailed SPS timeline share one viewport. Zooming/panning either
one therefore cannot desynchronize the time scales. Clicking a graph point
selects the syllables belonging to the corresponding SPS window.

The **ASS** curve always uses karaoke timing. The **Measured** curve uses the
independently trimmed perceptual start/end where the user changed a syllable and
falls back to karaoke timing for untouched syllables. Editing measurement
handles refreshes the graph immediately and never edits the ASS.

`Export CSV…` writes both selected graph series with source, metric, point time,
SPS, syllable count, window start/end/duration, syllable IDs and text.

The old `scripts/sps_from_subs_2_test.py` PyQtGraph prototype was also switched
to the same core `sps_graph_points()` helper, so the experiment and GUI no longer
maintain separate graph math.

## Verification

- 46/46 unit tests pass.
- GUI smoke test under a virtual display produced both ASS and Measured series,
  rendered graph canvas elements and preserved the shared viewport during zoom.
- No ASS or media writes are introduced by this update.
