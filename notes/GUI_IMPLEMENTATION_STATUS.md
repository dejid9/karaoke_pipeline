# GUI implementation status after update 003

## Implemented in 3A (update 002)

- Shared Tkinter application with **Karaoke** and **SPS Measurement** tabs.
- One-click Karaoke -> SPS transfer with automatic burst detection immediately
  before transfer.
- Separate navigation overview and zoomable detail timeline in both tabs.
- Cool-to-hot burst-speed map only on the SPS navigation overview.
- Manual red burst regions remain separate from automatic candidates.
- Burst candidate table and cross-navigation between SPS and Karaoke.

## Implemented in 3B-1 (update 003)

- Real waveform extraction from audio/video through FFmpeg. The source media is
  read-only and is never rewritten.
- Compact `.wfm` peak cache (100 bins/s by default). Project mode stores it below
  `cache/waveform`; without a project the cache goes to the OS temp directory.
- The same waveform can be viewed in both Karaoke and SPS detail timelines.
- SPS syllables now show the original karaoke interval plus an independent
  perceptual measurement interval.
- A single selected SPS syllable gets draggable **start** and **end** handles.
  Dragging is intentionally inward-only: it trims the measurement but does not
  change the karaoke interval or neighbouring syllables.
- Adjacent measured syllables are allowed to have gaps. Nothing snaps or
  normalizes them together.
- Manually changed measurement syllables use a distinct teal/cyan visual state.
- Numeric Start/End editing is available in seconds with 6 decimal places.
- Selection statistics show `count / measured span = SPS`.
- Reset really removes a measurement override instead of storing source timing as
  a fake change (fixes an update-001 core bug).
- Measurement edits autosave outside the ASS:
  - project: `cache/sps_measurements.json`;
  - no project: `<subtitle-name>.sps-measurements.json` beside the ASS.
- Partial Karaoke -> SPS transfers merge their measurement edits into the sidecar
  instead of deleting measurements belonging to syllables outside the transfer.
- Existing sidecar measurements are restored automatically on the next transfer.
- Selected measured intervals can be played through `ffplay`; Stop terminates the
  current playback process. `ffplay` is searched next to configured FFmpeg first,
  then in `PATH`.
- Viewport/zoom/scroll are preserved when a measurement changes; editing does not
  jump back to the beginning.

## Explicitly deferred to 3B-2

- spectrogram rendering;
- pitch-range presets (low / mid / high voice);
- expected-SPS presets controlling time/frequency trade-off;
- FFT/window length, overlap/hop, window function and dB range controls;
- switching/overlaying waveform and spectrogram without losing the current view.

## Later Karaoke-editor work

The Karaoke tab now has waveform/navigation infrastructure, but editing karaoke
syllables (insert/merge/split/delete, `\\k`/`\\kf`/`\\ko` switching) is still a
later stage. SPS measurement sidecar editing is deliberately kept independent
from those future ASS edits.

## Implemented in 3B-2 (update 004)

- SPS Measurement can display **Waveform**, **Spectrogram**, or **Both** without
  changing the navigation overview or losing the current zoom/viewport.
- Spectrogram analysis is cached separately below `cache/spectrogram` in project
  mode, or in the OS temp directory without a project. Source media remains
  read-only.
- The STFT cache stores track-relative dB energy, so changing frequency range,
  dB floor/ceiling, frequency scale, or colour display does **not** rerun FFmpeg
  or FFT analysis.
- Analysis settings that do require a new cache are sample rate, FFT/window size,
  overlap/hop and window function.
- Voice presets are display presets:
  - low: 50–5000 Hz;
  - medium: 80–7000 Hz;
  - high: 120–10000 Hz;
  - full: 20–11000 Hz.
- Expected-speed presets use progressively shorter FFT windows:
  - ≤6 SPS: 2048 samples;
  - 6–12 SPS: 1024 samples;
  - 12–20 SPS: 512 samples;
  - >20 SPS: 256 samples.
  At the default 22050 Hz these correspond to ~92.9, 46.4, 23.2 and 11.6 ms.
- Manual controls: sample rate, FFT size, overlap %, Hann/Hamming/Blackman/rect
  window, min/max frequency, dB floor/ceiling and linear/log frequency scale.
- A numeric expected-SPS field can choose the appropriate starting FFT size.
- When the timeline is compressed, spectrogram time columns are max-pooled so
  short high-energy consonants/events are less likely to disappear.
- `Перестроить` explicitly discards the current settings-specific spectrogram
  cache before recomputing it.
- Spectrogram rendering requires NumPy; the GUI gives a direct dependency error
  instead of failing at application startup when NumPy is unavailable.

## Next GUI stage

The next substantial stage is the actual **Karaoke waveform editor**: editing
karaoke boundaries and text segments, insert/merge/split/delete operations,
`\\k` / `\\kf` / `\\ko` selection, and undo/redo while preserving the viewport.
The SPS measurement timeline remains separate sidecar state.

## Update 005 / 4A — editable karaoke timing

Implemented:

- real ASS editing from the Karaoke tab (changes stay in memory until Save);
- `\\k`, `\\kf`, `\\ko`, `\\K` type selection for one or many selected syllables;
- draggable shared boundaries between adjacent syllables in the same ASS event;
- boundary edits are snapped to integer centiseconds and preserve the pair's total duration;
- Insert: selected duration `N` becomes `floor(N/2)` + `N-floor(N/2)`, original text stays in the first half and the new second syllable is empty;
- Split: same duration rule, visible content is split approximately in half while inline ASS override blocks remain in source order;
- Merge: adjacent syllables are collapsed into one and durations are summed; only removed karaoke commands are deleted, other commands in those blocks are retained;
- Delete: visible content is removed and duration is added to the following syllable (or the previous syllable when deleting the last one);
- undo/redo history (100 document snapshots) with Ctrl+Z / Ctrl+Y;
- atomic Save / Save As with a `.bak` of the previous on-disk ASS;
- unsaved-change marker and save/discard/cancel prompt before closing/opening another project/ASS;
- zoom, horizontal viewport and selection are preserved across edit refreshes rather than jumping to time zero;
- a timing/structural karaoke edit invalidates the current SPS transfer. Existing exact-SPS sidecars are moved to a timestamped `.stale-...json` file before such an edit so shifted syllable IDs cannot silently receive an old measurement. Tag-type-only changes do not invalidate measurements.

Still intentionally deferred to later updates:

- direct text-entry editing of syllable contents / split-at-text-caret;
- multi-syllable delete policy;
- waveform playback controls inside Karaoke itself;
- video rendering/layout and automatic crop calculation.

## Update 006 / 4B — karaoke text editing and caret split

Implemented:

- a dedicated syllable text editor in the Karaoke tab; the field edits the raw
  content between karaoke timing tags so hand-authored inline ASS commands stay
  explicit instead of being silently moved or discarded;
- pending text edits are kept as per-syllable drafts when navigating around the
  timeline; the window/ASS dirty marker includes those drafts;
- Ctrl+Enter applies the current text, F2 focuses the text editor, Enter inserts
  the ASS line-break escape `\\N` rather than a literal newline;
- all pending text drafts are materialized before Save and before any structural
  edit that could shift karaoke IDs;
- text-only edits leave the exact-SPS measurement sidecar valid because timing
  and karaoke IDs do not change;
- a new **Split at cursor** command divides timing with the same exact
  `floor(N/2)` + remainder rule as 4A, while dividing text at the actual editor
  caret position;
- split-at-caret refuses a caret inside an ASS `{...}` override command,
  `\\N`/`\\n`/`\\h` escape, combining sequence, or emoji ZWJ chain;
- an unapplied current text draft can be split directly: the draft and the
  structural split become one document edit/undo step;
- double-clicking a syllable on the waveform focuses its text editor;
- previous/next navigation centers the waveform on the chosen syllable without
  resetting zoom;
- selected karaoke syllables can be auditioned directly through `ffplay`;
- Insert selects the newly created empty syllable and immediately makes it ready
  for text entry;
- fixed a redundant second call to `AssDocument.save()` that remained in the 4A
  session save path.

Still intentionally deferred:

- richer multi-syllable text operations / bulk text tools;
- karaoke video rendering, word wrapping/line-spacing layout and exact crop;
- MFA/TextGrid cleanup and replacement of the remaining legacy conversion tools.


## Update 007 / 5A — karaoke render and exact libass crop

Implemented:

- a third **Render** tab operating on the current in-memory ASS without rewriting
  the editable source;
- render-only word wrapping with a configurable maximum number of words per line;
- the existing distant-origin line-spacing technique is preserved and made more
  exact: each new ASS line gets `\org(far_x,0)` plus a tiny `\frz` angle derived
  from the requested pixel displacement and the actual PlayRes centre instead
  of a hard-coded angle-per-pixel approximation;
- existing authored `\org` + `\fr/\frz` immediately after a line break is not
  duplicated;
- exact automatic crop uses the alpha channel produced by **the same FFmpeg
  libass subtitles filter** used by the final render at native ASS PlayRes;
- for the static geometry pass every Dialogue is temporarily made visible in one
  technical frame. Karaoke colour progression does not change glyph geometry,
  so this measures all normal subtitle rows at once instead of guessing from
  font metrics or relying on the literal first video frame;
- user padding and even-dimension adjustment are applied after the measured
  content bbox;
- manual crop preview composites the transparent libass frame over a checkerboard,
  shows the measured content bbox, supports moving/resizing the crop rectangle,
  field entry, even-size correction, centering on content and optional centre
  lock during resize;
- `\\move`/`\\t` are detected and explicitly warned about because a single
  static geometry frame cannot guarantee the complete animated trajectory;
- final standalone render profiles:
  - transparent QuickTime MOV / qtrle / ARGB;
  - black-background MP4 / H.264 / yuv420p;
- final render first renders at native PlayRes and only then crops, so choosing a
  smaller output rectangle does not rescale the ASS font/effect geometry;
- render-layout ASS can be exported separately for inspection in Aegisub;
- no new Python dependency is required for this stage.

The source ASS remains unchanged by wrapping, line spacing, automatic geometry
measurement and video rendering. Only already-existing text drafts are committed
to the in-memory editor state before a preview/render, exactly as they would be
before Save.

Still deferred:

- direct compositing onto the source video / audio passthrough presets;
- a full SPS line graph in the GUI (the navigation heat map and candidates already
  exist, but not yet the dedicated graph view);
- MFA/TextGrid cleanup and replacement of remaining legacy conversion scripts.

## Update 008 / 5B — direct source-video render

Implemented:

- the Render tab now keeps the Update 007 standalone/cropped overlay path and adds
  a separate **burn into source video** workflow;
- the attached project media is used as the source and is never modified;
- direct burn keeps the full source frame and does not add crop, scale or forced
  FPS filters;
- first video + optional source audio are explicitly mapped, so original subtitle
  or data streams are not accidentally copied;
- H.264/libx264 and H.265/libx265 software encoding choices;
- configurable CRF and encoder preset;
- audio can be stream-copied, converted to AAC at a configurable bitrate, or
  omitted;
- MP4 and MKV destinations are offered; MP4 receives `+faststart`;
- the same temporary render-only ASS layout from 5A is used, including word wrap
  and the distant-`\\org` line-spacing technique;
- output is rejected if it points at the original source media;
- changing/attaching media refreshes the Render tab source label/default direct
  output path immediately.

Still deferred:

- dedicated encoding-progress/cancel UI and optional hardware encoders;
- the full SPS line graph in the GUI;
- MFA/TextGrid cleanup and replacement of remaining legacy conversion scripts.

## Update 009 / 6A — synchronized SPS graph

Implemented:

- a dedicated SPS graph panel in **SPS Measurement**, placed above the detailed
  waveform/spectrogram timeline;
- the graph and detailed timeline share the exact same horizontal `Viewport`, so
  zoom/pan/navigation in either view immediately applies to the other without a
  second independent time scale;
- graph source selector:
  - original **ASS timing**;
  - exact **Measured** timing using independent perceptual trim boundaries where
    present and original karaoke boundaries for untouched syllables;
  - both curves overlaid for direct comparison;
- metric selector using the same core SPS engine everywhere:
  - strict fixed-window `contained`;
  - strict fixed-window `onset`;
  - archived legacy 1–2 s `count / actual_span` mode;
- configurable strict-window duration (1.000 s by default);
- optional moving-average display smoothing. Smoothing changes only the drawn
  curve; hover/export values remain the unsmoothed SPS measurements;
- graph points are anchored to the song timeline rather than graph-list indices;
- hover displays source, SPS, syllable count, actual window duration, exact
  start/end and text;
- clicking a graph point selects the syllables belonging to that SPS window in
  the measurement timeline;
- measurement trim/reset immediately rebuilds the graph so the ASS and Measured
  curves can be compared while working;
- CSV export of all currently selected graph series with source, metric, time,
  SPS, count, window bounds/duration, syllable IDs and text;
- the old PyQtGraph experiment now calls the same `sps_graph_points()` core
  helper instead of duplicating strict/legacy association logic.

Still deferred:

- optional encoding progress/cancel and hardware video encoders;
- MFA/TextGrid alignment/conversion cleanup;
- richer bulk karaoke text tools and project-level workflow polish.

## Update 011 / 7B — MFA execution

Implemented in **Alignment**:

- project/media/transcript aware MFA runner;
- editable MFA launcher command (including `conda run ... mfa` forms);
- installation/version/subcommand probe;
- Auto / HF / Legacy selector;
- explicit model, dictionary, dialect, G2P and jobs fields;
- persisted runner settings in the project;
- one-click corpus preparation;
- one-click alignment with live process log;
- cancellation;
- local model listing;
- automatic adoption of the resulting TextGrid;
- optional immediate conversion/opening as karaoke ASS.

The TextGrid -> ASS controls from 7A remain below the runner and use the exact same resulting TextGrid, so there is no second manual import step unless the user wants one.

## Final status — Update 013

The planned workbench flow is now connected end-to-end: project/ASS core, Karaoke
editing, independent precise SPS measurement, waveform/spectrogram, burst heatmap,
SPS graphs, libass rendering, TextGrid conversion, Conda-hosted MFA preflight/run,
and optional Japanese Sudachi preprocessing. Remaining work should be treated as
future enhancement/UX polish rather than a missing stage of the original plan.

## Update 015 — Simple/Advanced UI + theme engine

- Workflow tabs are now ordered as: **Подготовка → Караоке → Точный SPS → Рендер**.
- The workbench starts in **Simple** mode on a fresh install. The top-bar `Advanced` switch restores the detailed controls without rebuilding tabs or clearing state.
- Simple mode hides fine-grained SPS graph controls, extra MFA/Conda diagnostics/model tools, TextGrid conversion tuning, and low-level render/layout/codec controls. Core editing, measurement, alignment and render actions remain available.
- Added a global palette engine that themes ttk widgets, menus, text editors, waveform/timelines, SPS graph and crop preview.
- Added 14 named themes: navy, purple, red, green, yellow, vaporwave and cappuccino, each in light and night variants.
- Theme and Advanced preference are stored in `~/.karaoke_sps_workbench_ui.json` and never block startup if the preferences file is missing or invalid.
- Burst speed heat colours intentionally remain theme-independent so the overview heat scale keeps the same semantic meaning in every palette.
