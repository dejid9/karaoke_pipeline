# Update 032 — independent Play bounds, reliable return, 1x speed dead zone

Install over Update 031.

## Ordinary Play bounds are now independent from In/Out

The previous In/Out implementation was useful for auditioning a fixed range,
but it did not match the intended normal-transport workflow. Update 032 keeps
In/Out and adds a separate pair of persistent bounds for ordinary Play/Space:

- **Старт от** — always start a fresh ordinary Play from the beginning of the
  selected syllable. This marker may exist by itself.
- **Стоп после** — stop ordinary Play after the end of the selected syllable.
  This marker may exist by itself.
- `×S` and `×E` clear only the corresponding bound.
- `Ctrl+I` and `Ctrl+O` set Start/Stop by default; all shortcuts remain fully
  configurable in Settings. `Ctrl+Shift+Backspace` clears both ordinary-Play
  bounds.
- With no Start marker, Space starts **exactly at the current playhead**. It no
  longer jumps implicitly to the current syllable selection.
- With no Stop marker, playback continues to media EOF.
- Existing `I`, `O`, `↔`, and `▶ I–O` remain a separate audition range.

Start is drawn as a green dashed `▶` marker and Stop as a red dashed `■`
marker on both overview and detailed timelines. In/Out remains yellow.

When both ordinary-Play bounds form a valid syllable segment, its fastest
precise burst is shown next to the transport bounds. The result uses only the
user-facing **Legacy 1–2 s** SPS calculation. SPS measurement boundaries are
used in the Precise SPS tab.

## Return playhead to transport origin

The `После Stop/окончания вернуть полосу к точке старта` setting now tracks an
immutable **user transport origin**. It is stored only after the backend accepts
the Play request. Internal PortAudio restarts caused by speed changes or audio
device rebinding do not replace it.

Manual Stop and natural end now use the same transport finalizer, so both paths
return to the exact position from which that Play action began when the option
is enabled.

## 97–103% = 100%

Playback speed now has a centre dead zone:

- `0.97x` through `1.03x`, inclusive, is normalized to exactly `1.00x`;
- values outside the dead zone remain unchanged;
- normalization is applied by the UI, saved preferences, PortAudio transport,
  non-pitch-preserving resampling, and pitch-preserving `atempo` playback.

This also keeps the fast direct PCM path active when the slider is only a few
percent away from its centre by accident.

## Small scheduler cleanup

A duplicated initial scheduling call for the playhead poller was removed. The
single self-rescheduling UI playhead loop from Update 028 remains in place.
