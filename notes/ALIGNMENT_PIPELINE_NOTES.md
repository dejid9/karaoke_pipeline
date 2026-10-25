# Alignment pipeline status — Update 010 (7A)

## Implemented

- Dependency-free parser for MFA/Praat long TextGrid and basic short TextGrid.
- Explicit words-tier selection (`words`/`word` fallback only) and phones-tier selection (`phones`/`phone`).
- TextGrid -> ASS conversion with selectable `\\k`, `\\kf`, `\\ko`, `\\K`.
- Optional transcript mapping that preserves punctuation/case when tokenization matches the MFA words tier.
- Phone-aware grapheme boundaries: proportional text boundaries are snapped to real phone boundaries when enough distinct boundaries exist.
- Cumulative centisecond quantization: line duration is rounded once and all karaoke durations sum exactly to that duration.
- Pauses inside one subtitle line are emitted as empty timing-only `{\\kNN}` segments rather than extending the previous spoken syllable.
- SPS engine marks empty timing-only segments as gaps and excludes them from syllable counts/burst detection/graphs.
- New Alignment GUI tab for inspecting tiers and converting an existing TextGrid.
- CLI: `python scripts/textgrid_to_ass.py input.TextGrid output.ass ...`.
- MFA command builder supports explicit HF (`align_hf`) and legacy (`align`) command shapes and refuses missing model/dictionary configuration; there is no English fallback.

## Deliberately not implemented yet (7B)

- Starting/stopping MFA from the GUI.
- Detecting the installed MFA version and choosing supported HF/legacy commands.
- Model download/list management.
- Building/validating the MFA corpus from the project's media + transcript.
- Streaming MFA logs/progress into the GUI.
- Cancellation and recovery of failed MFA jobs.
- Auto-importing the resulting TextGrid after an MFA run.

The split is intentional: Update 010 makes TextGrid conversion deterministic and testable before adding an external long-running MFA process.

## Update 011 / 7B — MFA runner

Implemented:

- `karaoke_core.mfa` with installation detection, runtime command selection, corpus preparation, output adoption and a cancellable process wrapper;
- installation probing uses `mfa version` and actual `mfa --help` subcommands instead of assuming one fixed MFA release;
- Auto/HF/Legacy modes;
- forward-compatible command selection for the MFA 3.4 HF transition and planned MFA 4.x `align` / `align_legacy` split;
- no implicit English fallback or implicit dictionary/model substitution;
- MFA command field accepts direct executables and launch prefixes such as `conda run -n aligner mfa`;
- project-local `alignment/mfa/corpus` workspace with matching `.wav` + `.lab` basenames;
- media conversion to mono 16 kHz PCM WAV via the project's configured FFmpeg;
- clean transient output directory per run so an old TextGrid cannot be mistaken for a fresh result;
- live combined stdout/stderr log in the Alignment tab;
- cancellation terminates the whole spawned process group/tree where the OS permits it;
- recursive TextGrid discovery after success and safe copy to `alignment/<stem>.TextGrid` with `.bak` of an existing destination;
- optional immediate TextGrid -> ASS conversion after successful alignment;
- local acoustic/dictionary model listing via `mfa model list`;
- runner settings persisted in `project.json` metadata.

Still intentionally deferred:

- downloading/browsing the remote MFA/Hugging Face model catalog from inside the app;
- corpus validation/OOV report UI before alignment;
- tokenization helpers for Japanese/Chinese and other language-specific preprocessing;
- batch/multi-file MFA projects (the current workbench prepares the one media + transcript pair used by the karaoke project);
- richer progress parsing beyond MFA's live textual log.

## Update 012 / 7C-1 — Conda-aware preflight

MFA is treated as a Conda-hosted tool by default. Projects now store the Conda
executable, environment name and the MFA executable separately instead of
requiring a hand-written `conda run ...` launcher string. Existing Update 011
launcher strings such as `conda run -n aligner mfa` are migrated by the GUI.

All MFA subprocesses (version/help probe, alignment, validation, OOV reports and
model management) use the same generated prefix:

    conda run --no-capture-output -n <environment> mfa ...

`--no-capture-output` is used so MFA output still streams to the live GUI log.

Preflight deliberately does not infer a pronunciation dictionary from an HF
model ID. MFA 3.x `validate` and `find_oovs` use explicit dictionary-based
signatures, so the Dictionary field must be supplied for those actions. This
avoids silently validating against a different language/dictionary than the
one the user intended.

The model manager supports `model list`, `model download` and `model inspect`
for acoustic, dictionary, G2P and tokenizer models. Downloads and inspection
happen inside the selected Conda environment as well.

## Update 013 / 7C-2 — final language preprocessing and release integration

The alignment pipeline is considered complete for the single-song workbench.
Transcript preprocessing is explicit and non-destructive: existing projects default
to no preprocessing, while Unicode normalization and Japanese Sudachi tokenization
can be enabled per project. Sudachi runs in the same selected Conda environment as
MFA. Prepared text is written only to the MFA workspace, never back to the source
transcript.

A final doctor command validates the project paths, Conda environment, MFA,
FFmpeg/ffplay, NumPy and optional Sudachi packages. See `FINAL_WORKFLOW.md` for the
canonical end-to-end workflow. Legacy scripts are retained but are no longer the
recommended path.
