from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
from typing import Iterable, Mapping

from .sps import MeasurementTimeline


@dataclass(slots=True)
class MeasurementRecord:
    syllable_id: str
    measured_start: float
    measured_end: float


def read_measurements(path: str | Path) -> dict[str, MeasurementRecord]:
    source = Path(path)
    if not source.exists():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    result: dict[str, MeasurementRecord] = {}
    for item in data.get("measurements", []):
        record = MeasurementRecord(
            str(item["syllable_id"]),
            float(item["measured_start"]),
            float(item["measured_end"]),
        )
        result[record.syllable_id] = record
    return result


def apply_measurements(records: Mapping[str, MeasurementRecord], timeline: MeasurementTimeline) -> MeasurementTimeline:
    available = {s.id for s in timeline.syllables}
    for syllable_id, record in records.items():
        if syllable_id in available:
            timeline.set_measurement(syllable_id, record.measured_start, record.measured_end)
    return timeline


def replace_measurements(records: Mapping[str, MeasurementRecord], timeline: MeasurementTimeline) -> MeasurementTimeline:
    """Replace the complete measurement snapshot for the supplied timeline.

    Export files intentionally contain only syllables whose perceptual bounds
    differ from ASS timing.  Consequently, a missing record means "clear the
    measurement", rather than "keep whatever was loaded before".
    """
    for item in tuple(timeline.changed()):
        timeline.clear_measurement(item.id)
    return apply_measurements(records, timeline)


def save_measurements(path: str | Path, timeline: MeasurementTimeline) -> Path:
    target = Path(path)
    records = [
        MeasurementRecord(s.id, s.effective_start, s.effective_end)
        for s in timeline.changed()
    ]
    return _write_records(target, {r.syllable_id: r for r in records})


def update_measurements(
    path: str | Path,
    timeline: MeasurementTimeline,
    touched_ids: Iterable[str],
) -> Path:
    """Merge edits from a possibly partial SPS transfer into the sidecar.

    This prevents measuring a selected subset from erasing measurements for
    syllables that were not included in the current transfer.
    """
    target = Path(path)
    records = read_measurements(target)
    lookup = {s.id: s for s in timeline.syllables}
    for syllable_id in touched_ids:
        records.pop(syllable_id, None)
        item = lookup.get(syllable_id)
        if item is not None and item.measurement_changed:
            records[syllable_id] = MeasurementRecord(
                syllable_id,
                item.effective_start,
                item.effective_end,
            )
    return _write_records(target, records)


def load_measurements(path: str | Path, timeline: MeasurementTimeline) -> MeasurementTimeline:
    return apply_measurements(read_measurements(path), timeline)


def _write_records(path: Path, records: Mapping[str, MeasurementRecord]) -> Path:
    ordered = [records[key] for key in sorted(records)]
    payload = {"version": 1, "measurements": [asdict(r) for r in ordered]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
