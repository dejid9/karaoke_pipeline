# Update 025 — adjustable Windows playback warm-up

This hotfix keeps the sample-accurate FFmpeg extraction introduced in Update 023/024,
but makes the silent playback padding configurable instead of hard-coded.

## Changes

- Default Windows playback warm-up increased from 220 ms to 700 ms.
- Default tail silence increased from 180 ms to 250 ms.
- Added **Точный SPS → Настройки прослушивания…**.
- Warm-up and tail can be adjusted from 0 to 2000 ms in 50-ms steps.
- Values are stored in `~/.karaoke_sps_workbench_ui.json` and apply to both
  Karaoke and SPS auditioning.
- Padding remains silence outside the exact selected interval; it never changes
  the selected syllable timing or the generated ASS.
- MediaPlayer now uses per-instance padding settings with safe clamping.
