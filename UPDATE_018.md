# Update 018 — actual portable FFmpeg path hotfix

Base: Update 017.

The real bundled FFmpeg layout is:

`work/hz/ffmpeg/bin/ffmpeg.exe`

Update 017 supported `work/hz/ffmpeg.exe` and `work/hz/bin/ffmpeg.exe` but missed this extra `ffmpeg/` directory. The resolver now checks the real path first, before the older fallback layouts and before PATH/Conda FFmpeg.

`ffprobe.exe` and `ffplay.exe` are automatically resolved next to the selected `ffmpeg.exe`, so the same `work/hz/ffmpeg/bin/` bundle is used for probing and playback as well.
