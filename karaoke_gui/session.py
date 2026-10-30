from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from datetime import datetime
import os
import shutil
from typing import Iterable, Optional, Sequence

from karaoke_core.ass import AssDocument, KaraokeSyllable, KaraokeTagType, format_ass_time
from karaoke_core.editor import (
    KaraokeEditResult, colour_burst, delete_syllable, insert_after, insert_after_at_time, merge_syllables,
    redistribute_boundary, set_syllable_contents, set_syllable_romanization,
    set_syllable_text, set_syllable_texts, set_syllable_visible_texts,
    set_syllable_timing, set_tag_type, uncolour_burst,
    split_syllable, split_syllable_at_raw_offset, split_syllable_at_time,
)
from karaoke_core.project import ProjectConfig, create_project, find_portable_ffmpeg, load_project, save_project
from karaoke_core.measurements import load_measurements, save_measurements, update_measurements
from karaoke_core.sps import BurstCandidate, MeasurementTimeline, detect_bursts, manual_bursts


def _portable_project_path(root: Path, value: Path) -> str:
    """Prefer a project-relative path without guessing across drives."""
    root = root.resolve()
    value = value.resolve()
    try:
        return value.relative_to(root).as_posix()
    except ValueError:
        return str(value)


@dataclass(slots=True)
class TransferResult:
    timeline: MeasurementTimeline
    candidates: list[BurstCandidate]
    manual_regions: list[BurstCandidate]
    scope: str




def build_sps_transfer(
    source: Sequence,
    *,
    syllable_ids: Optional[Iterable[str]] = None,
    min_peak_sps: float = 6.0,
    max_candidates: int = 20,
) -> TransferResult:
    """Pure transfer builder used by both synchronous code and GUI workers."""
    items = list(source)
    scope = "all"
    if syllable_ids is not None:
        wanted = set(syllable_ids)
        items = [s for s in items if s.id in wanted]
        if not items:
            raise ValueError("The selected syllables are no longer present in the open ASS")
        scope = "selection"
    source_karaoke: list[KaraokeSyllable] = [
        s.source for s in items
        if s.source is not None and getattr(s.source, "track", 0) == 0
    ]
    if not source_karaoke:
        raise ValueError("No karaoke syllables on track 0 are available for SPS transfer")
    raw_timeline = MeasurementTimeline.from_karaoke(source_karaoke)
    import re
    cleaned_items = []
    for ts in raw_timeline.syllables:
        cleaned_text = re.sub(r"\{\\(?:remap|id\d+:\d+)[^}]*\}", "", ts.text)
        cleaned_text = re.sub(r"\\(?:remap|id\d+:\d+)\b", "", cleaned_text)
        cleaned_items.append(replace(ts, text=cleaned_text, is_gap=not bool(cleaned_text.strip())))
    timeline = MeasurementTimeline(cleaned_items)
    candidates = detect_bursts(
        timeline.syllables,
        min_peak_sps=min_peak_sps,
        max_candidates=max_candidates,
    )
    return TransferResult(timeline, candidates, manual_bursts(timeline.syllables), scope)


@dataclass(slots=True)
class KaraokeSession:
    """GUI-independent state shared by Karaoke and SPS tabs.

    Navigation and transfer never mutate ASS content. The SPS timeline is an
    independent sidecar copy whose future perceptual trims can diverge from
    karaoke timing.
    """

    project_root: Optional[Path] = None
    project: Optional[ProjectConfig] = None
    subtitle_path: Optional[Path] = None
    media_path: Optional[Path] = None
    document: Optional[AssDocument] = None
    karaoke_timeline: Optional[MeasurementTimeline] = None
    sps_timeline: Optional[MeasurementTimeline] = None
    sps_candidates: list[BurstCandidate] = field(default_factory=list)
    manual_regions: list[BurstCandidate] = field(default_factory=list)
    undo_stack: list[str] = field(default_factory=list)
    redo_stack: list[str] = field(default_factory=list)
    measurement_undo_stack: list[tuple[str, Optional[float], Optional[float]]] = field(default_factory=list)
    measurement_redo_stack: list[tuple[str, Optional[float], Optional[float]]] = field(default_factory=list)
    dirty: bool = False
    _saved_text: Optional[str] = None
    last_measurement_archive: Optional[Path] = None
    # GUI-controlled media tool source.  Never falls back to PATH/Conda.
    ffmpeg_mode: str = "portable"
    ffmpeg_override: Optional[Path] = None

    def new_project(self, root: str | Path, name: Optional[str] = None) -> ProjectConfig:
        root = Path(root).resolve()
        self.project = create_project(root, name=name, exist_ok=True)
        self.project_root = root
        self.subtitle_path = None
        self.media_path = None
        self.document = None
        self.karaoke_timeline = None
        self._clear_sps()
        self._reset_edit_history()
        return self.project

    def attach_project(self, root: str | Path, name: Optional[str] = None) -> ProjectConfig:
        """Attach the current session to a new project without clearing it.

        This is the session-level counterpart of ``Save project as``.  Media
        and subtitle files are referenced rather than copied, so large source
        files are not duplicated unexpectedly.  Existing SPS measurements are
        carried over to the new project's cache.
        """
        root = Path(root).resolve()
        previous_sidecar = self.measurement_sidecar_path()
        project = create_project(root, name=name, exist_ok=True)
        self.project_root = root
        self.project = project
        if self.media_path is not None:
            project.media = _portable_project_path(root, self.media_path)
        if self.subtitle_path is not None:
            project.subtitles = _portable_project_path(root, self.subtitle_path)
        save_project(root, project)

        sidecar = self.measurement_sidecar_path()
        if sidecar is not None and previous_sidecar is not None and previous_sidecar.exists():
            if previous_sidecar.resolve() != sidecar.resolve():
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(previous_sidecar, sidecar)
        if sidecar is not None and self.sps_timeline is not None:
            if sidecar.exists():
                update_measurements(sidecar, self.sps_timeline, (s.id for s in self.sps_timeline.syllables))
            else:
                save_measurements(sidecar, self.sps_timeline)
        return project

    def open_project(self, root: str | Path) -> ProjectConfig:
        root = Path(root)
        if root.is_file() and root.name.lower() == "project.json":
            root = root.parent
        root = root.resolve()
        project = load_project(root)
        self.project_root = root
        self.project = project
        self.subtitle_path = None
        self.media_path = None
        self.document = None
        self.karaoke_timeline = None
        self._clear_sps()
        self._reset_edit_history()

        media = project.resolve(root, project.media)
        if media and media.exists():
            self.media_path = media
        subtitles = project.resolve(root, project.subtitles)
        if subtitles and subtitles.exists():
            self.open_subtitles(subtitles, attach=False)
        return project

    def new_blank_subtitles(self, duration_seconds: float) -> AssDocument:
        """Create an unsaved, visually empty ASS ready for timing by playhead.

        A single empty karaoke timing span covers the requested duration.  It is
        intentionally invisible but gives the editor something that can be split
        repeatedly even before the lyrics are known.
        """
        duration_cs = max(2, int(round(float(duration_seconds) * 100.0)))
        duration = duration_cs / 100.0
        end = format_ass_time(duration)
        text = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\n"
            "PlayResY: 1080\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n"
            "\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Heading Pro Variable,72,&H00FFFFFF,&H80FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,2,0,5,30,30,50,1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,{end},Default,,0,0,0,,{{\\kf{duration_cs}}}\n"
        )
        self.subtitle_path = None
        self.document = AssDocument.from_text(text)
        syllables = self.document.karaoke_syllables()
        self.karaoke_timeline = MeasurementTimeline.from_karaoke(syllables)
        self.manual_regions = manual_bursts(self.karaoke_timeline.syllables)
        self._clear_sps(keep_manual=True)
        self._saved_text = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = True
        return self.document

    def open_subtitles(self, path: str | Path, *, attach: bool = True) -> AssDocument:
        path = Path(path).resolve()
        document = AssDocument.load(path)
        syllables = document.karaoke_syllables()
        self.subtitle_path = path
        self.document = document
        self.karaoke_timeline = MeasurementTimeline.from_karaoke(syllables)
        self.manual_regions = manual_bursts(self.karaoke_timeline.syllables)
        self._clear_sps(keep_manual=True)
        self._saved_text = document.dumps()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False
        if attach and self.project is not None and self.project_root is not None:
            self.project.subtitles = _portable_project_path(self.project_root, path)
            save_project(self.project_root, self.project)
        return document

    def set_media(self, path: str | Path, *, attach: bool = True) -> Path:
        path = Path(path).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        self.media_path = path
        if attach and self.project is not None and self.project_root is not None:
            self.project.media = _portable_project_path(self.project_root, path)
            save_project(self.project_root, self.project)
        return path

    @property
    def syllables(self):
        return self.karaoke_timeline.syllables if self.karaoke_timeline else []

    def subtitle_bounds(self) -> tuple[float, float]:
        items = self.syllables
        if not items:
            return (0.0, 1.0)
        return (min(s.start for s in items), max(s.end for s in items))

    def measurement_sidecar_path(self) -> Optional[Path]:
        if self.project_root is not None:
            return self.project_root / "cache" / "sps_measurements.json"
        if self.subtitle_path is not None:
            return self.subtitle_path.with_name(self.subtitle_path.stem + ".sps-measurements.json")
        return None

    def waveform_cache_root(self) -> Optional[Path]:
        if self.project_root is not None:
            return self.project_root / "cache" / "waveform"
        return None

    def spectrogram_cache_root(self) -> Optional[Path]:
        if self.project_root is not None:
            return self.project_root / "cache" / "spectrogram"
        return None

    def playback_cache_root(self) -> Optional[Path]:
        if self.project_root is not None:
            return self.project_root / "cache" / "playback"
        return None

    def configure_ffmpeg(self, mode: str = "portable", path: str | Path | None = None) -> None:
        mode = (mode or "portable").strip().lower()
        if mode not in {"portable", "custom"}:
            mode = "portable"
        self.ffmpeg_mode = mode
        if path:
            try:
                self.ffmpeg_override = Path(path).expanduser().resolve()
            except Exception:
                self.ffmpeg_override = None
        else:
            self.ffmpeg_override = None

    def resolved_ffmpeg(self) -> Optional[Path]:
        # The GUI selection has precedence over project.json so a stale project
        # value from an older release cannot silently re-select Conda FFmpeg.
        if self.ffmpeg_mode == "custom":
            p = self.ffmpeg_override
            return p if p is not None and p.is_file() else None

        # Portable mode is strict: repository/work folder only.  No PATH, no
        # $FFMPEG, no Conda discovery.
        roots: list[Path] = []
        if self.project_root is not None:
            roots.append(self.project_root)
        roots.extend((Path.cwd(), Path(__file__).resolve().parents[1]))
        seen: set[Path] = set()
        for root in roots:
            try:
                resolved = root.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            local = find_portable_ffmpeg(resolved)
            if local is not None:
                return local
        return None

    def ffmpeg_preference_from_project(self) -> tuple[str, str]:
        if self.project is None or self.project_root is None:
            return self.ffmpeg_mode, str(self.ffmpeg_override or "")
        mode = (getattr(self.project, "ffmpeg_mode", "portable") or "portable").strip().lower()
        if mode != "custom":
            return "portable", ""
        raw = self.project.ffmpeg or ""
        resolved = self.project.resolve(self.project_root, raw) if raw else None
        return "custom", str(resolved or raw)

    def persist_ffmpeg_preference(self) -> None:
        if self.project is None or self.project_root is None:
            return
        self.project.ffmpeg_mode = self.ffmpeg_mode
        if self.ffmpeg_mode == "custom" and self.ffmpeg_override is not None:
            self.project.ffmpeg = _portable_project_path(self.project_root, self.ffmpeg_override)
        else:
            # Clear stale paths from older builds (especially Conda ffmpeg).
            self.project.ffmpeg = None
        save_project(self.project_root, self.project)

    def adopt_transfer_result(self, result: TransferResult) -> TransferResult:
        sidecar = self.measurement_sidecar_path()
        if sidecar is not None and sidecar.exists():
            load_measurements(sidecar, result.timeline)
        self.sps_timeline = result.timeline
        self.sps_candidates = list(result.candidates)
        self.manual_regions = list(result.manual_regions)
        self.measurement_undo_stack.clear()
        self.measurement_redo_stack.clear()
        return result

    def _measurement_item(self, syllable_id: str):
        if self.sps_timeline is None:
            raise RuntimeError("No SPS material is open")
        item = next((value for value in self.sps_timeline.syllables if value.id == syllable_id), None)
        if item is None:
            raise KeyError(syllable_id)
        return item

    def _persist_all_measurements(self) -> None:
        sidecar = self.measurement_sidecar_path()
        if sidecar is not None and self.sps_timeline is not None:
            save_measurements(sidecar, self.sps_timeline)

    def reset_measurement_history(self) -> None:
        self.measurement_undo_stack.clear()
        self.measurement_redo_stack.clear()

    def transfer_to_sps(
        self,
        *,
        syllable_ids: Optional[Iterable[str]] = None,
        min_peak_sps: float = 6.0,
        max_candidates: int = 20,
    ) -> TransferResult:
        if self.karaoke_timeline is None:
            raise RuntimeError("No ASS subtitles are open")
        result = build_sps_transfer(
            self.karaoke_timeline.syllables,
            syllable_ids=syllable_ids,
            min_peak_sps=min_peak_sps,
            max_candidates=max_candidates,
        )
        return self.adopt_transfer_result(result)

    def set_measurement(self, syllable_id: str, start: float, end: float):
        if self.sps_timeline is None:
            raise RuntimeError("No SPS material is open")
        before = self._measurement_item(syllable_id)
        updated = self.sps_timeline.set_measurement(syllable_id, start, end)
        if (updated.measured_start, updated.measured_end) != (before.measured_start, before.measured_end):
            self.measurement_undo_stack.append(
                (syllable_id, before.measured_start, before.measured_end)
            )
            del self.measurement_undo_stack[:-100]
            self.measurement_redo_stack.clear()
        sidecar = self.measurement_sidecar_path()
        if sidecar is not None:
            update_measurements(sidecar, self.sps_timeline, [syllable_id])
        return updated

    def clear_measurement(self, syllable_id: str):
        if self.sps_timeline is None:
            raise RuntimeError("No SPS material is open")
        before = self._measurement_item(syllable_id)
        updated = self.sps_timeline.clear_measurement(syllable_id)
        if before.measurement_changed:
            self.measurement_undo_stack.append(
                (syllable_id, before.measured_start, before.measured_end)
            )
            del self.measurement_undo_stack[:-100]
            self.measurement_redo_stack.clear()
        sidecar = self.measurement_sidecar_path()
        if sidecar is not None:
            update_measurements(sidecar, self.sps_timeline, [syllable_id])
        return updated

    def undo_measurement(self) -> Optional[str]:
        if self.sps_timeline is None or not self.measurement_undo_stack:
            return None
        syllable_id, start, end = self.measurement_undo_stack.pop()
        current = self._measurement_item(syllable_id)
        self.measurement_redo_stack.append(
            (syllable_id, current.measured_start, current.measured_end)
        )
        self.sps_timeline.set_measurement(syllable_id, start, end)
        self._persist_all_measurements()
        return syllable_id

    def redo_measurement(self) -> Optional[str]:
        if self.sps_timeline is None or not self.measurement_redo_stack:
            return None
        syllable_id, start, end = self.measurement_redo_stack.pop()
        current = self._measurement_item(syllable_id)
        self.measurement_undo_stack.append(
            (syllable_id, current.measured_start, current.measured_end)
        )
        self.sps_timeline.set_measurement(syllable_id, start, end)
        self._persist_all_measurements()
        return syllable_id

    def _reset_edit_history(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False
        self._saved_text = self.document.dumps() if self.document is not None else None

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def _restore_document_text(self, text: str) -> None:
        if self.document is None:
            raise RuntimeError("No ASS subtitles are open")
        self.document = AssDocument(text, source_path=self.subtitle_path, bom=self.document.bom)
        self._rebuild_karaoke_after_edit()
        self.dirty = self._saved_text is None or self.document.dumps() != self._saved_text

    def _rebuild_karaoke_after_edit(self) -> None:
        if self.document is None:
            self.karaoke_timeline = None
            self.manual_regions = []
            self._clear_sps()
            return
        syllables = self.document.karaoke_syllables()
        self.karaoke_timeline = MeasurementTimeline.from_karaoke(syllables)
        self.manual_regions = manual_bursts(self.karaoke_timeline.syllables)
        # SPS material is derived from karaoke timing. Never keep a live transfer
        # after an ASS edit because its IDs/times may now be stale.
        self._clear_sps(keep_manual=True)

    def _archive_measurement_sidecar(self) -> Optional[Path]:
        sidecar = self.measurement_sidecar_path()
        if sidecar is None or not sidecar.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = sidecar.with_name(f"{sidecar.stem}.stale-{stamp}{sidecar.suffix}")
        counter = 2
        while candidate.exists():
            candidate = sidecar.with_name(f"{sidecar.stem}.stale-{stamp}-{counter}{sidecar.suffix}")
            counter += 1
        os.replace(sidecar, candidate)
        return candidate

    def _apply_document_edit(self, operation, *, invalidate_measurements: bool = False) -> KaraokeEditResult:
        if self.document is None:
            raise RuntimeError("No ASS subtitles are open")
        before = self.document.dumps()
        self.last_measurement_archive = None
        try:
            result = operation(self.document)
        except Exception:
            # Editor functions are intended to be transactional, but restoring
            # the snapshot here makes that guarantee explicit for GUI callers.
            if self.document.dumps() != before:
                self.document = AssDocument(before, source_path=self.subtitle_path, bom=self.document.bom)
            raise
        after = self.document.dumps()
        if after != before:
            if invalidate_measurements:
                self.last_measurement_archive = self._archive_measurement_sidecar()
            self.undo_stack.append(before)
            if len(self.undo_stack) > 100:
                del self.undo_stack[:-100]
            self.redo_stack.clear()
            self._rebuild_karaoke_after_edit()
            self.dirty = self._saved_text is None or after != self._saved_text
        return result

    def edit_tag_type(self, ids: Iterable[str], tag_type: KaraokeTagType | str) -> KaraokeEditResult:
        wanted = tuple(ids)
        return self._apply_document_edit(lambda doc: set_tag_type(doc, wanted, tag_type))

    def edit_burst_colour(self, ids: Iterable[str]) -> KaraokeEditResult:
        wanted = tuple(ids)
        # Colour-only markup leaves timings, IDs and measurement sidecars valid.
        return self._apply_document_edit(lambda doc: colour_burst(doc, wanted))

    def edit_burst_uncolour(self, ids: Iterable[str]) -> KaraokeEditResult:
        wanted = tuple(ids)
        return self._apply_document_edit(lambda doc: uncolour_burst(doc, wanted))

    def edit_ass_style(self, style_name: str, style) -> KaraokeEditResult:
        """Update visual ASS style without invalidating timing measurements."""
        if self.document is None:
            raise RuntimeError("No ASS subtitles are open")
        from karaoke_core.render import replace_ass_text_style

        before = self.document.dumps()
        replace_ass_text_style(self.document, style_name, style)
        after = self.document.dumps()
        if after != before:
            self.undo_stack.append(before)
            if len(self.undo_stack) > 100:
                del self.undo_stack[:-100]
            self.redo_stack.clear()
            self.dirty = self._saved_text is None or after != self._saved_text
        return KaraokeEditResult("style", (), None)

    def edit_text(self, syllable_id: str, raw_text: str) -> KaraokeEditResult:
        # Text-only edits do not invalidate timing-sidecar measurements. IDs and
        # karaoke boundaries stay unchanged. The live SPS transfer is rebuilt on
        # the next explicit transfer, but the precise sidecar remains valid.
        return self._apply_document_edit(lambda doc: set_syllable_text(doc, syllable_id, raw_text))

    def edit_texts(self, values: dict[str, str]) -> KaraokeEditResult:
        copied = dict(values)
        return self._apply_document_edit(lambda doc: set_syllable_texts(doc, copied))

    def edit_visible_texts(self, values: dict[str, str]) -> KaraokeEditResult:
        copied = dict(values)
        # Only text payload changes. Karaoke tags, IDs and precise measurement
        # sidecars remain valid.
        return self._apply_document_edit(
            lambda doc: set_syllable_visible_texts(doc, copied)
        )

    def edit_romanization(self, syllable_id: str, value: str) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: set_syllable_romanization(doc, syllable_id, value)
        )

    def edit_contents(
        self,
        *,
        text_values: dict[str, str] | None = None,
        romanization_values: dict[str, str] | None = None,
    ) -> KaraokeEditResult:
        copied_text = dict(text_values or {})
        copied_romanization = dict(romanization_values or {})
        return self._apply_document_edit(
            lambda doc: set_syllable_contents(
                doc,
                text_values=copied_text,
                romanization_values=copied_romanization,
            )
        )

    def edit_split_at_cursor(
        self, syllable_id: str, raw_offset: int, *, raw_text: str | None = None,
        new_type: KaraokeTagType | str | None = None, boundary_time: float | None = None,
    ) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: split_syllable_at_raw_offset(
                doc, syllable_id, raw_offset, raw_text=raw_text, new_type=new_type, boundary_time=boundary_time
            ),
            invalidate_measurements=True,
        )

    def set_syllable_timing(self, syllable_id: str, new_start: float, new_end: float) -> KaraokeEditResult:
        from karaoke_core.editor import set_syllable_timing
        return self._apply_document_edit(
            lambda doc: set_syllable_timing(doc, syllable_id, new_start, new_end),
            invalidate_measurements=True,
        )

    def edit_boundary(self, left_id: str, right_id: str, boundary_time: float) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: redistribute_boundary(doc, left_id, right_id, boundary_time),
            invalidate_measurements=True,
        )

    def edit_insert(self, syllable_id: str, *, new_type: KaraokeTagType | str | None = None) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: insert_after(doc, syllable_id, new_type=new_type), invalidate_measurements=True
        )

    def edit_insert_at_time(
        self, syllable_id: str, boundary_time: float, *, new_type: KaraokeTagType | str | None = None
    ) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: insert_after_at_time(doc, syllable_id, boundary_time, new_type=new_type),
            invalidate_measurements=True,
        )

    def edit_insert_track_syllable(
        self,
        track: int,
        start_time: float,
        duration_cs: int = 50,
        text: str = "",
        *,
        ref_track0_seq: int | None = None,
        tag_type: KaraokeTagType | str | None = None,
    ) -> KaraokeEditResult:
        def op(doc: AssDocument) -> KaraokeEditResult:
            tag_name = KaraokeTagType(tag_type).value if tag_type is not None else "kf"
            dur = max(1, int(duration_cs))
            if ref_track0_seq is not None:
                tag_content = "{\\%s%d\\id0:%d}%s" % (tag_name, dur, ref_track0_seq, text)
            else:
                tag_content = "{\\%s%d}%s" % (tag_name, dur, text)
            end_time = start_time + dur / 100.0
            st_str = format_ass_time(start_time)
            et_str = format_ass_time(end_time)
            style = "Default"
            last_ev = None
            for ev in doc.events():
                if ev.style:
                    style = ev.style
                last_ev = ev
            raw_line = f"Dialogue: 0,{st_str},{et_str},{style},,0,0,0,track:{track},{tag_content}"
            if last_ev is not None:
                insert_idx = last_ev.line_index + 1
                doc.lines.insert(insert_idx, raw_line)
                new_line_idx = insert_idx
            else:
                doc.lines.append(raw_line)
                new_line_idx = len(doc.lines) - 1
            new_id = f"L{new_line_idx}:S0"
            return KaraokeEditResult("insert-track", (new_id,), start_time)

        return self._apply_document_edit(op, invalidate_measurements=True)

    def edit_add_track(
        self,
        track_id: int,
        duration_seconds: float,
        *,
        tag_type: KaraokeTagType | str | None = None,
    ) -> KaraokeEditResult:
        def op(doc: AssDocument) -> KaraokeEditResult:
            tag_name = KaraokeTagType(tag_type).value if tag_type is not None else "kf"
            dur_cs = max(2, int(round(float(duration_seconds) * 100.0)))
            st_str = "0:00:00.00"
            et_str = format_ass_time(dur_cs / 100.0)
            style = "Default"
            last_ev = None
            for ev in doc.events():
                if ev.style:
                    style = ev.style
                last_ev = ev
            raw_line = f"Dialogue: 0,{st_str},{et_str},{style},,0,0,0,track:{track_id},{{\\{tag_name}{dur_cs}}}"
            if last_ev is not None:
                insert_idx = last_ev.line_index + 1
                doc.lines.insert(insert_idx, raw_line)
                new_line_idx = insert_idx
            else:
                doc.lines.append(raw_line)
                new_line_idx = len(doc.lines) - 1
            new_id = f"L{new_line_idx}:S0"
            return KaraokeEditResult("add-track", (new_id,), 0.0)

        return self._apply_document_edit(op, invalidate_measurements=True)

    def edit_split(self, syllable_id: str, *, new_type: KaraokeTagType | str | None = None) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: split_syllable(doc, syllable_id, new_type=new_type), invalidate_measurements=True
        )

    def edit_split_at_time(
        self, syllable_id: str, boundary_time: float, *, new_type: KaraokeTagType | str | None = None
    ) -> KaraokeEditResult:
        return self._apply_document_edit(
            lambda doc: split_syllable_at_time(doc, syllable_id, boundary_time, new_type=new_type),
            invalidate_measurements=True,
        )

    def edit_merge(self, ids: Iterable[str]) -> KaraokeEditResult:
        wanted = tuple(ids)
        return self._apply_document_edit(lambda doc: merge_syllables(doc, wanted), invalidate_measurements=True)

    def edit_delete(self, syllable_id: str) -> KaraokeEditResult:
        return self._apply_document_edit(lambda doc: delete_syllable(doc, syllable_id), invalidate_measurements=True)

    def undo(self) -> bool:
        if self.document is None or not self.undo_stack:
            return False
        current = self.document.dumps()
        previous = self.undo_stack.pop()
        self.redo_stack.append(current)
        self._restore_document_text(previous)
        return True

    def redo(self) -> bool:
        if self.document is None or not self.redo_stack:
            return False
        current = self.document.dumps()
        following = self.redo_stack.pop()
        self.undo_stack.append(current)
        self._restore_document_text(following)
        return True

    def save_subtitles(self, path: str | Path | None = None, *, backup: bool = True) -> Path:
        if self.document is None:
            raise RuntimeError("No ASS subtitles are open")
        target = Path(path).resolve() if path is not None else self.subtitle_path
        if target is None:
            raise RuntimeError("No ASS output path is available")
        target.parent.mkdir(parents=True, exist_ok=True)
        if backup and target.exists():
            backup_path = target.with_name(target.name + ".bak")
            shutil.copy2(target, backup_path)
            try:
                backups_dir = target.parent / "backups"
                backups_dir.mkdir(parents=True, exist_ok=True)
                bak5 = backups_dir / f"{target.name}.bak5"
                if bak5.exists():
                    bak5.unlink()
                for i in range(4, 0, -1):
                    src_bak = backups_dir / f"{target.name}.bak{i}"
                    dst_bak = backups_dir / f"{target.name}.bak{i + 1}"
                    if src_bak.exists():
                        src_bak.rename(dst_bak)
                shutil.copy2(target, backups_dir / f"{target.name}.bak1")
            except Exception:
                pass
        self.document.save(target)
        self.subtitle_path = target
        self._saved_text = self.document.dumps()
        self.dirty = False
        if self.project is not None and self.project_root is not None:
            self.project.subtitles = _portable_project_path(self.project_root, target)
            save_project(self.project_root, self.project)
        return target

    def _clear_sps(self, *, keep_manual: bool = False) -> None:
        self.sps_timeline = None
        self.sps_candidates = []
        self.measurement_undo_stack.clear()
        self.measurement_redo_stack.clear()
        if not keep_manual:
            self.manual_regions = []
