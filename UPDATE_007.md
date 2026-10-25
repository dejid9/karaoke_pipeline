# Update 007 — Render 5A (libass layout + exact crop)

Apply this archive **after Updates 001–006** by extracting it over the project root.

## Render tab

A new **Render** tab renders the current in-memory ASS without modifying the source
file. Pending Karaoke text drafts are first committed to the in-memory document so
preview/render sees exactly what is currently edited; Save remains a separate action.

### Render-only layout

- Optional maximum words per line (`0` = keep existing line layout).
- Configurable extra line spacing in pixels.
- The user's existing distant-origin technique is used for line spacing:
  `\\org(-2000000,0)` + a tiny `\\frz`.
- Unlike the legacy fixed `ANGLE_PER_PIXEL`, the angle is derived from the actual
  PlayRes centre and requested displacement, so e.g. 20 px at a -2,000,000 origin
  is calculated rather than approximated.
- Existing immediate `\\org` + `\\fr/\\frz` line-shift blocks are not duplicated.
- Wrapping and line-spacing tags exist only in the render copy; the editable ASS
  remains unchanged.

## Exact automatic size

The automatic size is no longer estimated from character count/font metrics.
The app:

1. creates a render-only ASS copy;
2. temporarily makes all Dialogue rows visible in one technical geometry frame;
3. renders that frame at native ASS `PlayResX/PlayResY` through FFmpeg/libass on a
   transparent RGBA canvas;
4. scans the real alpha channel for the content bbox;
5. adds user padding and optional even-dimension correction;
6. renders the final video at native PlayRes first and crops afterwards.

This avoids the circular scaling problem that appears when subtitles are rerendered
directly at an already-cropped small resolution.

`\\move` and `\\t` are detected. They trigger a warning because one static geometry
frame cannot guarantee the entire animated path.

## Manual crop preview

The **Manual crop** dialog shows the real libass technical frame on a checkerboard.
It supports:

- moving the crop rectangle;
- corner resize;
- numeric X/Y/W/H;
- returning to the automatic bbox + padding;
- centering the current crop on measured content;
- forcing even W/H;
- keeping the crop centre fixed while resizing.

This is the fallback for unusual ASS layouts and also allows intentionally tighter or
larger framing.

## Output

Two standalone profiles are included:

- **Transparent MOV / qtrle / ARGB** — useful as an overlay in an editor;
- **MP4 H.264 / black background** — convenient normal preview/export.

FPS is configurable. The render-layout ASS can also be exported separately for
inspection in Aegisub.

No new Python package is required for Update 007. FFmpeg must contain the `subtitles`
filter/libass; the application reports an FFmpeg error otherwise.

## Safety

- source ASS is not rewritten by layout, bbox measurement or render;
- unknown inline tags and red burst colour tags are kept in the render copy;
- the crop operation does not change ASS PlayRes or font scaling;
- existing Karaoke/SPS behaviour from Updates 001–006 remains covered by regression
  tests.
