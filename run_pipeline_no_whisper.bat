@echo off

REM =====================================================
REM STEP 4 - MFA ALIGNMENT
REM =====================================================

call conda activate mfa

mfa align ^
work\corpus ^
english_mfa ^
english_mfa ^
work\aligned ^
--clean --beam 1000 --retry_beam 4000 --single_speaker

REM =====================================================
REM STEP 5 - ASS EXPORT
REM =====================================================

python scripts\textgrid_to_ass.py
python scripts\fix_subs.py

REM =====================================================
REM STEP 6 - BLACK VIDEO RENDER
REM =====================================================

"C:\Users\dejid\Downloads\ffmpeg-8.0.1-full_build-shared\bin\ffmpeg.exe" ^
-f lavfi ^
-i color=c=010101:s=1920x1080:r=30 ^
-i work\corpus\audio.wav ^
-shortest ^
-c:v libx264 ^
-pix_fmt yuv420p ^
-c:a aac ^
-b:a 320k ^
work\corpus\output.mp4 ^
-y

echo.
echo ==============================================
echo DONE

pause