# Update 019 — strict FFmpeg selection + flatter Windows 10 / Material UI

## FFmpeg: no automatic Conda/PATH fallback

The GUI now has an explicit FFmpeg source setting (`FFmpeg…` in the toolbar and File menu).

Modes:

- **Portable (default)** — only the repository-local bundle is used, primarily:
  `work/hz/ffmpeg/bin/ffmpeg.exe`.
- **Custom** — exactly the `ffmpeg.exe` selected by the user is used.

Automatic discovery through `PATH`, `$FFMPEG`, or the active Conda environment has been removed from the GUI/project resolver. `ffprobe.exe` and `ffplay.exe` must be siblings of the selected FFmpeg executable; they are no longer taken from PATH either.

Old project files that contain an `ffmpeg` path but do not contain the new `ffmpeg_mode` field default to `portable`, so a stale Conda FFmpeg path from older builds is ignored.

The selected source is stored in UI preferences and, when a project is open, in `project.json` (`ffmpeg_mode`, `ffmpeg`). Selecting portable mode clears the stale explicit project path.

## UI refresh

The theme engine was flattened toward a Windows 10 + Material 3 hybrid:

- borderless flat buttons;
- lighter hover/pressed states;
- borderless cards and group sections;
- flatter notebook tabs with accent text instead of full accent fill;
- thinner paned-window separators and progress bar;
- borderless Treeview and headings;
- text editor no longer has a permanent outline;
- menus are flat rather than boxed;
- existing 14 light/night palettes remain available.

No SPS, ASS timing, MFA alignment, or render mathematics were changed by the visual refresh.
