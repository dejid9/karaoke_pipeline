# Update 017 — FFmpeg / Conda DLL isolation hotfix

This hotfix addresses Windows loader errors where FFmpeg launched from the GUI
inherits an activated MFA Conda environment and accidentally loads DLLs such as
`gdk_pixbuf-2.0-0.dll` / `libintl` from `<conda env>\\Library\\bin`.

## Changes

- Restored compatibility with the original large `work/hz` FFmpeg bundle that
  was intentionally omitted from the uploaded source archive. Resolution order
  is now: explicit project `ffmpeg` -> `$FFMPEG` -> project-local/bundled
  FFmpeg (`work/hz`, `tools/ffmpeg`, etc.) -> PATH.
- Loose-file mode (without a project.json) also searches `work/hz` relative to
  the application/current directory before PATH.
- On Windows, when a chosen FFmpeg/ffprobe/ffplay executable is outside the
  currently active `CONDA_PREFIX`, its child process receives a sanitized PATH:
  paths belonging to that Conda environment are removed and the media tool's
  own directory is prepended.
- The isolation is applied consistently to waveform, spectrogram, ffprobe,
  ffplay, libass rendering, direct video rendering, and MFA corpus WAV
  preparation. MFA itself still runs through the configured Conda environment.
- If FFmpeg itself is deliberately located inside the active Conda environment,
  its environment is left untouched.

## Why

The application is allowed to run from the MFA Conda environment, but a
standalone FFmpeg distribution should not resolve unrelated GTK/gettext DLLs
from that environment. The previous PATH-based auto-detection made this very
easy on Windows.

## Verification

84 unit/integration tests pass after the hotfix, including new tests for legacy
`work/hz` discovery and Conda PATH isolation.
