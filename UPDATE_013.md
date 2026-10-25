# Update 013 — final integration / 7C-2 + release cleanup

Apply this archive over a project that already has Updates 001–012.

This is the planned final update rather than another small feature slice.

## Language preprocessing

- Added optional transcript preprocessing before MFA corpus creation.
- Modes: no preprocessing, Unicode NFKC + whitespace normalization, Japanese Sudachi.
- Japanese Sudachi runs through the selected Conda environment, not through an unrelated global Python.
- Sudachi SplitMode A/B/C is selectable.
- Punctuation removal is optional and disabled by default.
- Preview shows original and prepared transcript before corpus generation.
- Dependency probe checks `sudachipy`, `sudachidict_core` and NumPy in the selected Conda environment.
- The source transcript is never overwritten. Prepared text is written only to the generated `.lab` and `alignment/mfa/prepared_transcript.txt`.

## Final environment / reproducibility work

- Added generic `build_conda_run_prefix()` so non-MFA tools can run in the same environment.
- Added `scripts/doctor.py` and core health-report helpers.
- Doctor checks project paths, Python/Tkinter, FFmpeg/ffplay, NumPy, Conda env, MFA and optional Sudachi packages.
- Added a Diagnostics button to Alignment.
- Added `requirements.txt`, `environment.example.yml`, `run_gui_conda.bat` and `FINAL_WORKFLOW.md`.
- Added `notes/LEGACY_SCRIPTS.md` mapping old experimental scripts to the canonical new modules without deleting user files.

## Compatibility

Existing projects default to `Без обработки`; their transcript is therefore not silently changed. New preprocessing settings are stored in `project.json` metadata.

This update intentionally does not delete old scripts or user data. It completes the new pipeline and leaves legacy files available for comparison/manual fallback.
