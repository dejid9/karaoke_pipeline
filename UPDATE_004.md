# Update 004 — GUI 3B-2: Spectrogram

Apply this archive **after updates 001, 002 and 003** by extracting it over the
project root. It contains only files added or changed for 3B-2.

## What changed

- Added cached STFT spectrogram generation from the project's audio/video via
  FFmpeg + NumPy. Original media is never rewritten.
- SPS Measurement audio display can be switched between Waveform,
  Spectrogram, and Both. The burst-speed navigation overview remains separate.
- Added a spectrogram settings dialog and the same actions under the `Точный SPS`
  application menu.
- Added low / medium / high / full voice-range presets.
- Added expected-SPS presets that shorten the FFT window as articulation gets
  faster, improving time resolution for dense bursts.
- Added manual sample-rate, FFT-size, overlap, window-function, frequency-range,
  dB-range and linear/log-frequency controls.
- Display-only changes do not regenerate the STFT cache. Analysis changes use a
  settings-specific cache. `Перестроить` forces regeneration.
- Spectrogram caches are stored in `cache/spectrogram` for a project, or the OS
  temporary directory when no project is open.
- Added core/cache/render tests and GUI rendering smoke coverage.

## Default presets

At 22050 Hz sample rate and 75% overlap:

- <= 6 SPS: FFT 2048 (~92.9 ms window)
- 6–12 SPS: FFT 1024 (~46.4 ms)
- 12–20 SPS: FFT 512 (~23.2 ms)
- > 20 SPS: FFT 256 (~11.6 ms)

Voice display presets:

- low: 50–5000 Hz
- medium: 80–7000 Hz
- high: 120–10000 Hz
- full: 20–11000 Hz

These are starting points, not assumptions about a singer. Every value can be
changed manually.

## Dependency

The spectrogram path requires NumPy. Existing waveform/SPS/ASS functionality can
still start without NumPy; attempting to build a spectrogram will show a clear
error. `requirements-spectrogram.txt` contains the dependency line.

## Validation

- 20/20 automated tests pass after this update.
- A Tk GUI smoke test under a virtual display confirmed that the spectrogram is
  actually rendered into the detailed SPS timeline and that Waveform /
  Spectrogram / Both can be switched without recreating the timeline.
- Synthetic audio was used for signal tests; archived user media was not decoded
  for this update.
