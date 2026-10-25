# Update 030 — In/Out transport, Legacy-only precise SPS, configurable hotkeys/settings

Install over Update 029.

## Playback transport

- After manual Stop or natural end of playback the playhead returns to the point
  where that playback run began by default. This can be disabled in Settings.
- Karaoke and Precise SPS each have independent **In / Out** syllable markers.
- `I` and `O` set the corresponding marker from the current syllable; `↔` takes
  the first/last syllables of the current selection; `▶ I–O` plays the whole
  contiguous syllable range.
- The In/Out range is drawn on both the overview and detailed timeline.
- Stale markers are discarded after structural edits/transfers instead of being
  reused for another syllable accidentally.

## Precise SPS

The only user-facing exact SPS definition is now the archived **Legacy 1–2 s**
method: consecutive spoken syllables with a real span from 1.000 to 2.000 s,
`SPS = count / actual span`.

- Strict contained/onset modes were removed from the GUI and normal SPS CLI.
- They remain internal implementation helpers for automatic burst-candidate
  discovery, where fixed windows are useful as a heuristic.
- In Precise SPS, the current selection shows its fastest Legacy 1–2 s window
  (speed, count/duration, time and text), with a button to select that burst.
- An In/Out range also shows its maximum Legacy SPS in the transport bar.
- ASS and Measured graph series both use Legacy 1–2 s only.

## Configurable hotkeys

Settings → **Горячие клавиши** now controls transport and syllable operations.
Defaults:

- Space — Play/Pause
- Ctrl+Space — play current syllable selection
- Shift+Space — play In–Out range
- Esc — Stop
- I / O — set In / Out
- Ctrl+Shift+Space — In–Out from selection
- Ctrl+Left / Ctrl+Right — previous / next syllable
- Ctrl+Shift+I — insert karaoke syllable
- Ctrl+Shift+K — split karaoke syllable
- Ctrl+Shift+M — merge karaoke syllables
- Delete — delete karaoke syllable
- Ctrl+Shift+R — reset precise SPS bounds

Shortcuts can be changed or disabled. Duplicate assignments and conflicts with
fixed editor shortcuts (Save, Undo/Redo, F2, Ctrl+,) are rejected.
Transport shortcuts are installed before ttk class bindings so Space does not
activate the previously focused button or combobox. Text input fields keep normal
keyboard editing behavior.

## Detailed Settings

A unified Settings window (`Ctrl+,`) contains:

- General: theme, Simple/Advanced, FFmpeg shortcut;
- Playback: speed, preserve-pitch mode, return-to-start, playhead correction,
  fallback warm-up/tail;
- Precise SPS: graph source/smoothing and the fixed Legacy method explanation;
- Hotkeys: all configurable bindings and reset-to-defaults.

These values are persisted in the global UI preference file and restored on the
next launch.

## Compatibility

- The retired `playback_cursor_delay_ms` preference remains readable for old
  helper code/tests but no longer drives PortAudio playhead timing.
- No ASS files, measurement sidecars or media are rewritten by this update.
