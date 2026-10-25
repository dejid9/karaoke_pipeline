# Update 022 — waveform fill, overview scrubbing, short playback, SPS theme switch

Install on top of Update 021.

## Waveform rendering
- Fixed the filled waveform envelope polygon. The lower envelope is now reversed as `(x, y)` points instead of reversing the flattened scalar coordinate list, which previously produced large diagonal wedges/triangles.
- The fix applies to waveform-only mode; Waveform+Spectrogram mode keeps the lightweight outline rendering.

## Timeline navigation
- Removed the redundant horizontal ttk scrollbar below the detailed timeline.
- The navigation overview is now the scrub/pan control: click and hold-drag across it to continuously move the detailed viewport.
- Current zoom is displayed directly in the overview (`×N.N`).
- Wheel/touchpad zoom and Shift+wheel horizontal pan remain unchanged.

## Short-syllable playback
- ffplay playback now seeks slightly before the requested interval and performs sample-accurate trimming with `atrim`.
- A short silent device warm-up is inserted before the selected samples and a silent tail after them. This prevents very short syllables from ending before Windows/ffplay has actually started producing audible samples.
- Only the requested media interval is audible; the added warm-up/tail is silence.

## Theme switching in Exact SPS
- Switching theme no longer calls the SPS graph calculation pipeline again.
- Existing graph points are reused and only ASS/Measured display colours are updated.
- Timeline and graph theme repaint is deferred into one UI frame instead of blocking the theme combobox callback with immediate heavy redraws.

## Verification
- Python compile check passes for the changed modules.
- 51/51 relevant existing+new tests pass.
- 18/18 focused waveform/spectrogram/SPS/theme tests pass under Tk/Xvfb.
- Added regression checks for filled waveform point order, overview drag navigation, short-clip ffplay filtering and zero-recalculation SPS theme recolouring.
