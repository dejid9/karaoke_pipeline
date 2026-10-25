"""Project archive import and export for Karaoke Mobile and PC compatibility."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import zipfile

from .ass import AssDocument
from .measurements import MeasurementRecord, apply_measurements, read_measurements
from .sps import MeasurementTimeline


@dataclass
class ProjectBundle:
    """In-memory representation of an imported or prepared project."""

    name: str = "karaoke_project"
    ass_text: Optional[str] = None
    transcript: str = ""
    measurements: Dict[str, MeasurementRecord] = field(default_factory=dict)
    burst_settings: Dict[str, Any] = field(default_factory=dict)
    audio_filename: Optional[str] = None
    audio_bytes: Optional[bytes] = None


def export_project_zip(
    target_path: Optional[str | Path] = None,
    *,
    project_name: str = "karaoke_project",
    doc: Optional[AssDocument] = None,
    timeline: Optional[MeasurementTimeline] = None,
    transcript: str = "",
    burst_settings: Optional[Dict[str, Any]] = None,
    audio_path: Optional[str | Path] = None,
    audio_bytes: Optional[bytes] = None,
    audio_filename: Optional[str] = None,
) -> Path | bytes:
    """Package current project state into a portable .kproj / .zip archive or return bytes."""
    buf: Optional[io.BytesIO] = None
    if target_path is not None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        sink = target
    else:
        buf = io.BytesIO()
        sink = buf

    burst_cfg = burst_settings or {
        "mode": "dynamic",
        "base_color": "#FF0000",
        "alt_color": "#FF8000",
        "pulse_hz": 2.0,
    }

    # Prepare project metadata
    audio_name = audio_filename
    if not audio_name and audio_path:
        audio_name = Path(audio_path).name

    meta = {
        "version": 1,
        "name": project_name,
        "subtitles_filename": "subtitles.ass" if doc else None,
        "transcript_filename": "transcript.txt" if transcript else None,
        "measurements_filename": "sps_measurements.json" if (timeline and timeline.changed()) else None,
        "audio_filename": audio_name,
        "has_audio": bool(audio_path or audio_bytes),
        "burst_settings": burst_cfg,
    }

    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Project config
        zf.writestr("project.json", json.dumps(meta, ensure_ascii=False, indent=2))

        # 2. Subtitles ASS
        if doc is not None:
            zf.writestr("subtitles.ass", doc.dumps())

        # 3. Transcript
        if transcript:
            zf.writestr("transcript.txt", transcript)

        # 4. SPS Measurements
        if timeline is not None:
            changed_records = [
                {
                    "syllable_id": s.id,
                    "measured_start": s.effective_start,
                    "measured_end": s.effective_end,
                }
                for s in timeline.changed()
            ]
            if changed_records:
                payload = {"version": 1, "measurements": changed_records}
                zf.writestr("sps_measurements.json", json.dumps(payload, ensure_ascii=False, indent=2))

        # 5. Audio data
        if audio_bytes and audio_name:
            zf.writestr(audio_name, audio_bytes)
        elif audio_path and os.path.exists(audio_path):
            with open(audio_path, "rb") as af:
                zf.writestr(audio_name or "audio.wav", af.read())

    if buf is not None:
        return buf.getvalue()
    return target


def import_project_zip(source_path_or_bytes: str | Path | bytes) -> ProjectBundle:
    """Extract and load a project bundle (.kproj / .zip) into a ProjectBundle."""
    bundle = ProjectBundle()

    if isinstance(source_path_or_bytes, bytes):
        zip_source = io.BytesIO(source_path_or_bytes)
    else:
        zip_source = Path(source_path_or_bytes)

    with zipfile.ZipFile(zip_source, "r") as zf:
        namelist = zf.namelist()

        # Check project.json
        meta: Dict[str, Any] = {}
        for candidate in ("project.json", "config.json"):
            if candidate in namelist:
                try:
                    meta = json.loads(zf.read(candidate).decode("utf-8"))
                    break
                except Exception:
                    pass

        bundle.name = str(meta.get("name") or "karaoke_project")
        bundle.burst_settings = meta.get("burst_settings", {})

        # Subtitles ASS
        sub_name = meta.get("subtitles_filename") or "subtitles.ass"
        if sub_name in namelist:
            bundle.ass_text = zf.read(sub_name).decode("utf-8", errors="replace")
        else:
            # Fallback search for any .ass file in archive
            for name in namelist:
                if name.endswith(".ass") and not name.startswith("__"):
                    bundle.ass_text = zf.read(name).decode("utf-8", errors="replace")
                    break

        # Transcript TXT
        tr_name = meta.get("transcript_filename") or "transcript.txt"
        if tr_name in namelist:
            bundle.transcript = zf.read(tr_name).decode("utf-8", errors="replace")
        else:
            for name in namelist:
                if name.endswith(".txt") and "transcript" in name.lower():
                    bundle.transcript = zf.read(name).decode("utf-8", errors="replace")
                    break

        # SPS Measurements JSON
        meas_name = meta.get("measurements_filename") or "sps_measurements.json"
        if meas_name in namelist:
            try:
                meas_data = json.loads(zf.read(meas_name).decode("utf-8"))
                for item in meas_data.get("measurements", []):
                    rec = MeasurementRecord(
                        str(item["syllable_id"]),
                        float(item["measured_start"]),
                        float(item["measured_end"]),
                    )
                    bundle.measurements[rec.syllable_id] = rec
            except Exception:
                pass
        else:
            # Search for any .sps-measurements.json
            for name in namelist:
                if "measurement" in name.lower() and name.endswith(".json"):
                    try:
                        meas_data = json.loads(zf.read(name).decode("utf-8"))
                        for item in meas_data.get("measurements", []):
                            rec = MeasurementRecord(
                                str(item["syllable_id"]),
                                float(item["measured_start"]),
                                float(item["measured_end"]),
                            )
                            bundle.measurements[rec.syllable_id] = rec
                        break
                    except Exception:
                        pass

        # Audio file
        audio_name = meta.get("audio_filename")
        if audio_name and audio_name in namelist:
            bundle.audio_filename = audio_name
            bundle.audio_bytes = zf.read(audio_name)
        else:
            for name in namelist:
                ext = Path(name).suffix.lower()
                if ext in {".wav", ".mp3", ".m4a", ".ogg", ".flac"}:
                    bundle.audio_filename = Path(name).name
                    bundle.audio_bytes = zf.read(name)
                    break

    return bundle
