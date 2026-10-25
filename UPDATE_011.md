# Update 011 — Alignment 7B: MFA runner

Apply this archive over a project that already has Updates 001–010.

## Main changes

- Added a cancellable Montreal Forced Aligner runner to the **Alignment** tab.
- Added automatic MFA capability detection via `mfa version` + `mfa --help` instead of hard-coding one MFA release.
- Added runtime selection for HF/legacy command shapes, including the documented MFA 4.x transition to `align` + `align_legacy`.
- Added deterministic corpus preparation from the selected media + transcript.
- Added live merged stdout/stderr log, cancellation, installed-model listing and result adoption.
- Successful MFA output is automatically picked up as the current TextGrid and can optionally be converted directly to ASS.

## Corpus preparation

The runner creates a private workspace under:

`<project>/alignment/mfa/`

with:

- `corpus/<media-stem>.wav` — mono PCM S16LE, 16 kHz, produced via the configured FFmpeg;
- `corpus/<media-stem>.lab` — UTF-8 transcript with the same stem;
- `output/` — MFA's transient output.

The original media and transcript are never modified. A successful TextGrid is copied to:

`<project>/alignment/<media-stem>.TextGrid`

If that destination already exists, it is copied to `.TextGrid.bak` before replacement.

## MFA command compatibility

The GUI accepts either a direct executable/path (`mfa`, `C:\\...\\mfa.exe`) or a launcher command such as:

`conda run -n aligner mfa`

The runner probes the actual installation. In Auto mode it prefers HF alignment when the installed MFA advertises it, otherwise it uses legacy alignment. There is no language/model fallback.

HF mode requires an explicit model/Hugging Face ID. Legacy mode requires both an explicit pronunciation dictionary and acoustic model.

## Process behaviour

- MFA output is streamed into the Alignment log while the process is running.
- Cancel terminates the process group/tree, so Kaldi helper processes should not be left behind.
- A non-zero exit code is reported without importing a stale TextGrid.
- A zero exit code is still treated as an error if no TextGrid was actually produced.
- Runner settings are stored in `project.json` metadata.

## Scope

This update does not install MFA or download models automatically. The GUI can list locally visible acoustic/dictionary models and accepts model identifiers/paths. A richer model browser/downloader can be added later without changing the alignment core.
