from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sps import SPSWindow


@dataclass(slots=True, frozen=True)
class AudacityLabel:
    start: float
    end: float
    text: str


def load_audacity_labels(path: str | Path) -> list[AudacityLabel]:
    """Load the tab-separated labels accepted by the archived ``sps.py``.

    A leading ``-`` reproduces the old script exactly: start/end are swapped and
    the marker is removed from the visible text.  This odd convention is retained
    for backwards compatibility with the user's existing measurements.
    """
    items: list[AudacityLabel] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue
            start = float(parts[0])
            end = float(parts[1])
            text = parts[2]
            if text.startswith("-"):
                start, end = end, start
                text = text[1:]
            items.append(AudacityLabel(start, end, text))
    return items


def legacy_label_windows(
    labels: list[AudacityLabel],
    *,
    min_duration: float = 1.0,
    max_duration: float = 2.0,
) -> list[SPSWindow]:
    """Exact window enumeration used by the archived standalone ``sps.py``."""
    groups: list[SPSWindow] = []
    n = len(labels)
    for i in range(n):
        start_time = labels[i].start
        for j in range(i, n):
            end_time = labels[j].end
            diff = end_time - start_time
            if diff < min_duration:
                continue
            if diff > max_duration:
                break
            group = labels[i:j + 1]
            count = len(group)
            groups.append(
                SPSWindow(
                    start=start_time,
                    end=end_time,
                    count=count,
                    speed=count / diff,
                    syllable_ids=tuple(f"label:{k}" for k in range(i, j + 1)),
                    text=" ".join(x.text for x in group),
                    mode="legacy-audacity-labels",
                )
            )
    return groups
