"""Google Colab MFA Alignment Server.

FastAPI server designed to run inside Google Colab (or any remote GPU/CPU server)
to provide high-performance Montreal Forced Alignment for the Mobile Karaoke app.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mfa_server")

app = FastAPI(
    title="Karaoke Mobile MFA Alignment Server",
    description="High-speed phonetic alignment API powered by Montreal Forced Aligner",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AlignmentResponse(BaseModel):
    success: bool
    message: str
    duration_seconds: float = 0.0
    words: List[Dict] = []
    oovs: List[str] = []
    ass_content: Optional[str] = None


@app.get("/")
def get_status():
    """Health check and available models probe."""
    mfa_ver = "unknown"
    try:
        proc = subprocess.run(["mfa", "version"], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            mfa_ver = proc.stdout.strip()
    except Exception:
        pass

    # Check available MFA models in ~/.mfa
    mfa_dir = Path.home() / "Documents" / "MFA"
    models = []
    if mfa_dir.exists():
        for p in mfa_dir.glob("*/*"):
            models.append(p.name)

    return {
        "status": "online",
        "mfa_version": mfa_ver,
        "models": models,
        "default_languages": ["russian", "english", "japanese", "multilingual"],
    }


def _convert_audio_to_pcm(source_path: Path, target_path: Path) -> float:
    """Convert any audio format to 16kHz mono 16-bit PCM wav via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", str(source_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(target_path)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg audio conversion failed: {proc.stderr}")

    # Probe duration
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(target_path)
    ]
    probe = subprocess.run(probe_cmd, capture_output=True, text=True)
    try:
        return float(probe.stdout.strip())
    except ValueError:
        return 0.0


def _parse_textgrid(textgrid_path: Path) -> List[Dict]:
    """Parse Praat TextGrid file into word and phone intervals."""
    words: List[Dict] = []
    if not textgrid_path.exists():
        return words

    lines = textgrid_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    i = 0
    in_word_tier = False
    in_phone_tier = False
    curr_tier = ""

    while i < len(lines):
        line = lines[i].strip()
        if 'name = "words"' in line:
            curr_tier = "words"
        elif 'name = "phones"' in line:
            curr_tier = "phones"
        elif line.startswith("intervals ["):
            # read interval block
            xmin, xmax, text = 0.0, 0.0, ""
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("intervals [") and not lines[i].strip().startswith("item ["):
                sub = lines[i].strip()
                if sub.startswith("xmin ="):
                    try:
                        xmin = float(sub.split("=")[1].strip())
                    except ValueError:
                        pass
                elif sub.startswith("xmax ="):
                    try:
                        xmax = float(sub.split("=")[1].strip())
                    except ValueError:
                        pass
                elif sub.startswith("text ="):
                    text = sub.split("=")[1].strip().strip('"')
                i += 1
            if text and text != "<eps>":
                if curr_tier == "words":
                    words.append({"word": text, "start": xmin, "end": xmax, "phones": []})
            continue
        i += 1
    return words


def _build_aligned_ass(words: List[Dict], total_duration: float) -> str:
    """Build a standard karaoke ASS document from aligned word intervals."""
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,52,&H00FFFFFF&,&H000000FF&,&H00000000&,&H00000000,1,0,0,0,100,100,0,0,1,3,0,5,20,20,20,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if not words:
        return "\n".join(lines)

    # Group words into lines based on pauses (>0.75s) or line count
    groups: List[List[Dict]] = []
    cur_group: List[Dict] = []
    last_end = 0.0

    for w in words:
        if cur_group and (w["start"] - last_end > 0.75 or len(cur_group) >= 8):
            groups.append(cur_group)
            cur_group = []
        cur_group.append(w)
        last_end = w["end"]
    if cur_group:
        groups.append(cur_group)

    def _fmt(sec: float) -> str:
        cs = int(round(sec * 100))
        m, s = divmod(cs // 100, 60)
        h, m = divmod(m, 60)
        c = cs % 100
        return f"{h}:{m:02d}:{s:02d}.{c:02d}"

    for g in groups:
        start_s = max(0.0, g[0]["start"] - 0.1)
        end_s = g[-1]["end"] + 0.2
        text_parts = []
        for w in g:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100.0)))
            text_parts.append(rf"{{\k{dur_cs}}}{w['word']}")
        dialogue_text = " ".join(text_parts)
        lines.append(f"Dialogue: 0,{_fmt(start_s)},{_fmt(end_s)},Default,,0,0,0,,{dialogue_text}")

    return "\n".join(lines)


@app.post("/align", response_model=AlignmentResponse)
async def align_audio(
    audio: UploadFile = File(...),
    transcript: str = Form(...),
    language: str = Form("russian"),
):
    """Run Montreal Forced Aligner on uploaded audio and transcript."""
    logger.info(f"Received alignment request for {audio.filename}, language={language}")

    with tempfile.TemporaryDirectory(prefix="colab-mfa-") as td:
        work_dir = Path(td)
        corpus_dir = work_dir / "corpus"
        output_dir = work_dir / "output"
        corpus_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)

        # 1. Save uploaded audio
        raw_audio_path = work_dir / f"raw_{audio.filename}"
        with raw_audio_path.open("wb") as f:
            shutil.copyfileobj(audio.file, f)

        # 2. Convert to 16kHz mono wav
        wav_path = corpus_dir / "track.wav"
        duration = _convert_audio_to_pcm(raw_audio_path, wav_path)

        # 3. Clean transcript and save .lab
        cleaned_transcript = " ".join(transcript.strip().split())
        lab_path = corpus_dir / "track.lab"
        lab_path.write_text(cleaned_transcript, encoding="utf-8")

        # 4. Resolve MFA dictionary and acoustic model
        lang = language.lower().strip()
        if lang in ("ru", "russian"):
            dictionary = "russian_mfa"
            acoustic_model = "russian_mfa"
        elif lang in ("en", "english"):
            dictionary = "english_mfa"
            acoustic_model = "english_mfa"
        elif lang in ("ja", "japanese"):
            dictionary = "japanese_mfa"
            acoustic_model = "japanese_mfa"
        else:
            dictionary = "russian_mfa"
            acoustic_model = "russian_mfa"

        # 5. Run MFA align command
        cmd = [
            "mfa", "align",
            str(corpus_dir),
            dictionary,
            acoustic_model,
            str(output_dir),
            "--clean",
            "--single_speaker",
            "--num_jobs", "4",
        ]
        logger.info(f"Running MFA command: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True)

        textgrid_path = output_dir / "track.TextGrid"
        if not textgrid_path.exists():
            logger.error(f"MFA Alignment failed. Stderr:\n{proc.stderr}")
            return AlignmentResponse(
                success=False,
                message=f"MFA Alignment failed: {proc.stderr[:1000]}",
                duration_seconds=duration,
            )

        # 6. Parse TextGrid
        words = _parse_textgrid(textgrid_path)
        logger.info(f"MFA successfully aligned {len(words)} words in {duration:.2f}s of audio")

        # 7. Generate ASS karaoke output
        ass_content = _build_aligned_ass(words, duration)

        return AlignmentResponse(
            success=True,
            message=f"Aligned {len(words)} words successfully",
            duration_seconds=duration,
            words=words,
            ass_content=ass_content,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
