# Update 014 — waveform/async error hotfix

Apply over Update 013.

## Fixed
- Tkinter deferred callbacks no longer capture Python exception variables after `except` cleanup. This fixes the reported `NameError: free variable 'exc' referenced before assignment` and the same latent bug in spectrogram, burst analysis and render callbacks.
- Waveform PCM peak extraction uses NumPy block processing when available instead of iterating every decoded sample in Python. A pure-Python fallback remains available.
- FFmpeg stderr is spooled to a temporary file while stdout is consumed, avoiding a potential stdout/stderr pipe deadlock on noisy/corrupt inputs.
- Waveform extraction explicitly maps the first audio stream and disables video/subtitle/data decoding for the waveform pass.

## Important
The previous Tkinter NameError hid the *original* waveform error. If waveform generation still fails after this update, the GUI status will now show the real FFmpeg/cache exception. Report that message if further diagnosis is needed.

## Verification
- Full suite: 75/75 tests pass.
- NumPy and pure-Python peak extractors are regression-tested to produce identical min/max bins.
