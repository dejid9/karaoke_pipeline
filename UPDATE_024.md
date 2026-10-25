# Update 024 — Windows short-syllable playback hotfix

This hotfix replaces ffplay as the primary backend for short syllable playback on Windows.

## Changes

- FFmpeg still performs the exact sample-accurate extraction to PCM WAV.
- The temporary WAV is padded with 220 ms of leading silence and 180 ms of trailing silence. The selected syllable itself is not expanded or shifted inside the useful interval.
- On Windows the WAV is played with the standard-library `winsound` backend (waveOut), avoiding ffplay/SDL audio-device startup for every 30–150 ms syllable.
- `ffplay` remains a fallback on non-Windows platforms or if native Windows playback cannot be started.
- Stop now also stops native Windows playback and safely cleans temporary WAV files.
- Added regression coverage for Windows-native playback and padded PCM duration.

The purpose of the silent preroll is to absorb output-device startup latency before the audible syllable begins.
