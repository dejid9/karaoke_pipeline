@echo off

REM =====================================================
REM STEP 1 - CONVERT TO WAV
REM =====================================================

"C:\Users\dejid\Downloads\ffmpeg-8.0.1-full_build-shared\bin\ffmpeg.exe" -y ^
-i input\input.mp4 ^
-ac 1 ^
-ar 16000 ^
work\audio.wav


REM =====================================================
REM STEP 2 - TRANSCRIBE
REM =====================================================

REM "C:\Users\dejid\AppData\Roaming\Subtitle Edit\Whisper\Purfview-Whisper-Faster\faster-whisper-xxl.exe" ^
REM --model large-v3-turbo ^
REM --language ru ^
REM --output_format txt ^
REM --output_dir work ^
REM --max_line_width=42 ^
REM --max_line_count=2 ^
REM --max_comma_cent=70 ^
REM --sentence ^
REM work\audio.wav


REM =====================================================
REM STEP 3 - COPY FOR MFA
REM =====================================================

if not exist work\corpus mkdir work\corpus

copy /Y work\audio.wav work\corpus\audio.wav
copy /Y work\audio.txt work\corpus\audio.txt


echo.
echo ==============================================
echo NOW EDIT work\corpus\audio.txt MANUALLY
"C:\Program Files\Notepad++\notepad++.exe" "C:\Users\dejid\Desktop\karaoke_pipeline\work\corpus\audio.txt"
pause


REM =====================================================
REM STEP 4 - MFA ALIGNMENT
REM =====================================================

call conda activate mfa

mfa align ^
work\corpus ^
japanese_mfa ^
japanese_mfa ^
work\aligned ^
--clean --beam 2000 --retry_beam 8000 --single_speaker


REM =====================================================
REM STEP 5 - ASS EXPORT
REM =====================================================

python scripts\textgrid_to_ass.py
python scripts\fix_subs.py

echo.
echo ==============================================
echo DONE
pause