# Update 001 — lossless ASS foundation + SPS/burst engine

This is an **update package**, not a full copy of the project.

## Added

- `karaoke_core/ass.py`
  - reads all Dialogue/Comment lines without flattening the ASS file;
  - parses `\\k`, `\\K`, `\\kf`, `\\ko`;
  - keeps unknown override tags verbatim;
  - correctly distinguishes red `\\c&HFF` / `\\c&H0000FF` from white
    `\\c&HFFFFFF`;
  - understands lowercase hex and bare `\\c` / `\\r` resets for burst state;
  - exposes safe single-tag type/duration editing instead of rebuilding all text.
- `karaoke_core/project.py`
  - project directories: `source`, `alignment`, `subtitles`, `cache`, `exports`;
  - relative project paths and optional FFmpeg discovery;
  - atomic `project.json` writes.
- `karaoke_core/sps.py`
  - archived 1–2 s metric for reproducibility;
  - exact fixed 1.000 s `contained` and `onset` metrics;
  - independent perceptual measurement boundaries;
  - manual-red burst extraction;
  - automatic connected burst expansion (no detached islands);
  - normalized `heat` scalar for a future overview timeline.
- `karaoke_core/audacity.py`
  - imports the old Audacity tab-separated labels, including the leading-`-` boundary convention used by `sps.py`;
  - reproduces its 1–2 s calculation exactly.
- `karaoke_core/measurements.py`
  - sidecar JSON for manual SPS trims; ASS timings remain untouched.
- `scripts/sps_cli.py`
  - command-line access to legacy/strict/burst analysis.
- `notes/FUTURE_GUI_NOTES.md`
  - recorded GUI requirements from the latest discussion.

## Changed

- `scripts/sps_from_subs.py` now uses the shared ASS/SPS core and accepts mixed
  karaoke override blocks correctly.
- `scripts/sps_from_subs_2_test.py` keeps the PyQtGraph prototype but now gets
  timings/SPS from the shared engine instead of its broken ASS regex.
- `scripts/bursts_to_audacity.py` now uses the real ASS colour state and connected
  burst algorithm. Default mode exports manual red marks; `--auto` exports
  automatically detected candidates.

## Apply

Extract this archive **over the root of the existing `karaoke_pipeline` folder**.
Only files listed in `UPDATE_MANIFEST.txt` are part of the update.

## Useful commands

```bat
python scripts\sps_cli.py "work\inutilis vaporized down6 and luc1dd upd.ass" --mode strict --top 20
python scripts\sps_cli.py megane_audacity_labels.txt --labels --mode legacy --top 1
python scripts\sps_cli.py "work\inutilis vaporized down6 and luc1dd upd.ass" --mode bursts
python scripts\bursts_to_audacity.py "work\inutilis vaporized down6 and luc1dd upd.ass"
python scripts\bursts_to_audacity.py "work\inutilis vaporized down6 and luc1dd upd.ass" --auto --min-sps 8
python -m unittest discover -s tests -v
```

No FFmpeg, audio, video, MFA, TextGrid, render, or GUI processing was added in this
update.
