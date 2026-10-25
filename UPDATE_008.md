# Update 008 — Render 5B (burn karaoke into source video)

Apply this archive **after Updates 001–007** by extracting it over the project root.

## Direct source-video render

The Render tab now has a second output path in addition to the cropped standalone
karaoke layer from Update 007.

**Burn karaoke into source video**:

- uses the currently attached project media as the FFmpeg source;
- requires that media to contain a video stream;
- applies the same render-only ASS layout (word wrapping + distant-origin line
  spacing) without rewriting the editable ASS;
- renders over the **full source video frame**;
- does not insert crop, scale or frame-rate conversion filters;
- therefore lets source video timing, dimensions and frame cadence remain
  authoritative;
- maps the first video stream and optional source audio, while avoiding accidental
  copying of old subtitle/data streams into the new file.

The existing standalone modes remain unchanged:

- transparent cropped MOV / qtrle overlay;
- cropped black-background MP4 preview/export.

## Video encoding controls

Direct burn currently exposes two software encoders:

- H.264 / `libx264`;
- H.265 / `libx265`.

The user can set:

- CRF 0–51;
- x264/x265 preset from `ultrafast` through `veryslow`;
- output path (`.mp4` or `.mkv` are offered by the dialog).

No forced output FPS is used for direct burn. The separate standalone karaoke
layer still has its own explicit FPS setting from Update 007.

## Audio

Three policies are available:

- **Copy source audio** — `-c:a copy`, preserving the encoded audio bitstream when
  the selected output container accepts it;
- **AAC** — re-encode audio with configurable bitrate (default 192 kbit/s), useful
  when an MP4 container cannot accept the source audio codec;
- **No audio**.

If audio-copy is incompatible with the selected container (for example some WebM
codecs copied into MP4), FFmpeg reports the error and the user can switch to AAC
or choose MKV.

## Safety

- source media is never overwritten; the GUI rejects an output path equal to the
  attached source file;
- source ASS is not rewritten;
- layout modifications exist only in a temporary render ASS;
- red burst tags and other unknown inline override tags continue to pass through
  the render copy;
- direct render does not depend on the standalone automatic/manual crop.

## Validation

Update 008 adds command-level tests for source mapping, no-crop/no-scale/no-forced-
FPS behaviour and all audio modes, plus a real FFmpeg integration test that creates
synthetic 320x180 video + audio, burns the ASS into it, and verifies that the output
still contains 320x180 video and an audio stream.
