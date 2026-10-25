# Update 016 — progress center and unified logs

This update is applied on top of Update 015.

## UI

- Added a global background-task strip below the main notebook:
  - current source/task;
  - current stage;
  - percentage when known;
  - indeterminate animation when a subprocess cannot provide a meaningful percentage.
- Added `5. Логи` tab.
  - running/completed/error/cancelled task table;
  - source, stage, percent and elapsed time;
  - combined process/application log;
  - source filter;
  - autoscroll;
  - clear and save-to-file actions.
- The task/log backend is thread-safe. Worker threads never write directly to Tk widgets; the GUI polls snapshots on the Tk thread.

## Progress-enabled operations

- Waveform
  - cache check/load;
  - FFmpeg decode;
  - peak-envelope construction;
  - cache write.
  - When ffprobe is available (normally beside ffmpeg), decode percentage is based on decoded media time.
- Spectrogram
  - cache check/load;
  - FFmpeg audio decode;
  - first FFT pass;
  - dB quantization / second FFT pass;
  - cache write.
- SPS transfer / automatic burst search
  - preparation;
  - SPS-window calculation;
  - candidate construction.
- TextGrid -> ASS
  - source validation;
  - tier/timing conversion;
  - ASS write.
- MFA / Conda operations
  - corpus preparation through FFmpeg;
  - MFA status stages;
  - percent values found in MFA output are reflected in the global task progress;
  - coarse MFA stages are used when the installed MFA version does not print a numeric progress value;
  - validation, OOV/model commands and diagnostics are recorded in the unified log.
- FFmpeg karaoke render
  - standalone overlay and burn-in render use FFmpeg's machine-readable `-progress` protocol;
  - percentage is calculated against the known output/source duration;
  - command and FFmpeg errors are written to the unified log.
- libass bbox measurement is represented as a staged FFmpeg task.

## Logging

The unified log records operations launched by the GUI. It includes command lines where useful, MFA stdout/stderr, FFmpeg errors, cache events and task completion/errors. Manually launched scripts outside the GUI naturally cannot be captured by the running GUI.

## Compatibility

No ASS timing semantics, SPS formulas, measurement sidecars or project paths were changed by this update.
