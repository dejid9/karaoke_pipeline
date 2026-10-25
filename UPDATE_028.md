# Update 028 — Tk UI scheduler / minimize-restore hotfix

Apply over Update 027.

## Fixed

- Fixed an unbounded Tk `after()` timer leak introduced in Update 027.
  `_poll_task_ui()` accidentally started another self-rescheduling playback cursor
  poller every 120 ms.  The number of 25–30 FPS callbacks therefore grew for as
  long as the program stayed open, eventually starving Tk while PortAudio kept
  playing normally.
- Audio output priming is now one-shot instead of being re-scheduled by the task
  UI poller.
- Task UI and playback cursor pollers now have explicit job IDs and are cancelled
  on shutdown.
- Playback playhead polling is limited to one loop at 25 FPS (40 ms), which is
  ample for the cursor and leaves more time for Tk window management.
- Hidden Notebook pages and minimized canvases no longer perform expensive
  waveform/spectrogram/SPS redraws.  A single pending redraw is remembered and
  flushed when the canvas becomes visible again.
- Hidden timeline playheads are not updated as Canvas objects every frame; their
  time is stored and rendered once when the tab becomes visible.
- SPS graph follows the same hidden-page redraw policy.
- The Logs Tree/Text widgets are only refreshed while the Logs tab is visible;
  log data itself continues to accumulate in the thread-safe TaskCenter.
- Added a Notebook-tab activation hook that refreshes only the newly visible
  heavy view.
- Resize debounce increased slightly for heavy canvases to avoid restore/resize
  event storms.

## Verification

- Scheduler regression: pending Tk jobs remain bounded (2 stable periodic jobs)
  instead of continuously increasing.
- Minimize/restore and hidden-tab redraw regression tests added.
- 42 affected GUI/playback/waveform/spectrogram/theme tests passed under Xvfb.
