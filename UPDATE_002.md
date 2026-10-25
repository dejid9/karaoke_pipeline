# Update 002 — GUI foundation (stage 3A)

This is an **incremental update** and expects update 001 to be present.

## Run

```bat
python run_gui.py
```

Tkinter is part of the normal Windows Python installation; no new pip dependency
is required for this update.

## Added

- `karaoke_gui/session.py`: shared project/ASS/media state and Karaoke -> SPS
  transfer without mutating subtitle files.
- `karaoke_gui/timeline.py`: reusable two-level timeline (overview + detailed
  lane), zoom/scroll/pan/selection and overview heat mapping.
- `karaoke_gui/app.py`: project shell and the linked Karaoke / SPS Measurement
  tabs.
- `run_gui.py`: launcher.
- `tests/test_gui_foundation.py`: headless tests for session transfer, project
  attachment, viewport math and heat mapping.
- `notes/GUI_IMPLEMENTATION_STATUS.md`: exact 3A/3B boundary.

## Behaviour

Before material is sent to SPS Measurement, automatic burst candidates are
calculated.  Their speed is mapped to a cool-to-hot colour **only in the overview
navigation timeline**.  The detailed timeline remains semantically neutral.

The ASS file is read-only in this GUI stage.  Media is only attached by path;
there is no audio/video decoding in update 002.
