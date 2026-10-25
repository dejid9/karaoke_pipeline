# Update 021 — spectrogram/timeline performance + theme consistency

Install on top of Update 020.

## Spectrogram quality
- Zoomed-in spectrograms now use linear interpolation on both time and frequency axes instead of nearest-neighbour block repetition.
- Zoomed-out views remain peak-preserving so short consonants/transients are not averaged away.
- Added power-of-two time LOD cache for high-overlap STFT data; wide views no longer rescan the full-resolution matrix on every pan.
- Replaced repeated multi-mask colour mapping with a compact 256-entry LUT.
- The Tk PhotoImage for a viewport is cached (small 4-entry cache), so selection/text redraws do not rerasterize an unchanged spectrogram.

## Timeline/UI performance
- Mouse/touchpad navigation is throttled to one pending UI frame instead of redrawing synchronously for every event.
- Window/canvas resize redraw is debounced by 70 ms, preventing expensive spectrogram rebuilds for every intermediate resize event.
- Waveform drawing now uses 2 polylines / one envelope instead of one Canvas object per horizontal pixel.
- Dense whole-song karaoke/SPS views use a lightweight syllable LOD: one lane plus only selected/changed/burst segments. Click hit-testing still works by timeline time.
- SPS graph redraw is throttled and very dense curves are display-decimated without changing the underlying SPS data or CSV export.
- Timeline and SPS graph continue to share the same viewport and wheel/Shift+wheel behaviour from Update 020.

## Theme consistency
- Dark theme input surfaces now inherit the actual selected theme family instead of using the same navy input colour for every night theme.
- Styled separators, menubuttons, scales, scrollbars and vertical progress bars.
- Combobox pop-down Listboxes now follow background/foreground/accent colours from the selected theme.
- Spectrogram settings and crop-preview top-level windows explicitly inherit the application background.
- Scientific/semantic heat maps (spectrogram palette and burst-temperature colours) intentionally remain independent of UI accent colour.

## Verification
- Python compile checks pass for all changed modules.
- 19/19 focused unit tests pass for spectrogram rendering/LOD, theme catalogue, SPS graph geometry and timeline maths.
- Tk/Xvfb stress smoke tested a 5000-syllable timeline in Waveform+Spectrogram mode and all 14 themes.
- In the stress smoke, dense mode reduced the detailed timeline to a few dozen Canvas objects rather than thousands; repeated cached redraws were only a few milliseconds, while new zoomed spectrogram viewports were around tens of milliseconds in this environment.
