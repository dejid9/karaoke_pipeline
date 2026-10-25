import subprocess
from pathlib import Path

from auto_language import detect_language

# =====================================================
# PATHS
# =====================================================

BASE_DIR = Path(r"C:\Users\dejid\Desktop\karaoke_pipeline")

CORPUS_DIR = BASE_DIR / "work" / "corpus"

CORPUS_TEXT = CORPUS_DIR / "audio.txt"
CORPUS_AUDIO = CORPUS_DIR / "audio.wav"

ALIGNED_DIR = BASE_DIR / "work" / "aligned"

TEXTGRID_TO_ASS = BASE_DIR / "scripts" / "textgrid_to_ass.py"
FIX_SUBS = BASE_DIR / "scripts" / "fix_subs.py"

FFMPEG = Path(
    r"C:\Users\dejid\Downloads\ffmpeg-8.0.1-full_build-shared\bin\ffmpeg.exe"
)

OUTPUT_VIDEO = CORPUS_DIR / "output.mp4"

# =====================================================
# MFA MODELS
# =====================================================

MFA_MODELS = {

    "english": {
        "dict": "english_us_arpa",
        "acoustic": "english_us_arpa"
    },

    "russian": {
        "dict": "russian_mfa",
        "acoustic": "russian_mfa"
    },

    "german": {
        "dict": "german_mfa",
        "acoustic": "german_mfa"
    },

    "polish": {
        "dict": "polish_mfa",
        "acoustic": "polish_mfa"
    },

    "turkish": {
        "dict": "turkish_mfa",
        "acoustic": "turkish_mfa"
    },

    "hungarian": {
        "dict": "hungarian_cv",
        "acoustic": "hungarian_cv"
    }
}

# =====================================================
# DETECT LANGUAGE
# =====================================================

with open(CORPUS_TEXT, "r", encoding="utf-8") as f:
    text = f.read()

lang = detect_language(text)

print(f"Detected language: {lang}")

model = MFA_MODELS.get(lang)

if model is None:

    print("Unsupported language -> fallback to english")

    model = MFA_MODELS["english"]

# =====================================================
# MFA ALIGN
# =====================================================

cmd = [
    "mfa",
    "align",
    str(CORPUS_DIR),
    model["dict"],
    model["acoustic"],
    str(ALIGNED_DIR),
    "--clean",
    "--beam", "3000",
    "--retry_beam", "12000",
    "--single_speaker"
]

print("\nRunning MFA:")
print(" ".join(cmd))

subprocess.run(cmd, check=True)

# =====================================================
# ASS EXPORT
# =====================================================

print("\nRunning textgrid_to_ass.py")

subprocess.run(
    ["python", str(TEXTGRID_TO_ASS)],
    check=True
)

print("\nRunning fix_subs.py")

subprocess.run(
    ["python", str(FIX_SUBS)],
    check=True
)

# =====================================================
# BLACK VIDEO RENDER
# =====================================================

ffmpeg_cmd = [
    str(FFMPEG),

    "-y",

    "-f", "lavfi",

    "-i",
    "color=c=010101:s=1920x1080:r=30",

    "-i",
    str(CORPUS_AUDIO),

    "-shortest",

    "-c:v", "libx264",

    "-pix_fmt", "yuv420p",

    "-c:a", "aac",

    "-b:a", "320k",

    str(OUTPUT_VIDEO)
]

print("\nRendering black video with audio:")

print(" ".join(ffmpeg_cmd))

subprocess.run(ffmpeg_cmd, check=True)

# =====================================================
# DONE
# =====================================================

print("\nDONE")
print("Output video:", OUTPUT_VIDEO)