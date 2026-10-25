# Update 023 — syllable playback hotfix

Fixes the regression introduced in Update 022 where short syllable playback could become completely silent on some portable FFmpeg/ffplay builds.

## What changed

- Removed `atrim`, `adelay`, `apad`, `-ss` and `-t` from the `ffplay` command.
- Playback now has two explicit stages:
  1. the selected interval is decoded by the selected local `ffmpeg.exe` into a temporary stereo 48 kHz PCM WAV;
  2. `ffplay.exe` plays that WAV from time zero without seeking or audio filters.
- This also avoids the earlier problem where the beginning of a very short syllable could be lost during ffplay startup/seeking.
- The selected `ffmpeg.exe` is passed explicitly by the GUI, so playback uses the same portable/custom FFmpeg distribution as the rest of the application.
- FFmpeg extraction errors are now surfaced to the GUI instead of being hidden by ffplay.
- Temporary playback WAVs are deleted on Stop, on the next playback, and when the application closes.

## Verification

- Real FFmpeg extraction test: an 80 ms selection produced exactly 3840 samples at 48 kHz stereo (0.080 s).
- 14/14 targeted media/GUI tests pass under a virtual display.
