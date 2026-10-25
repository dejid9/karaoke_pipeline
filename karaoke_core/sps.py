from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite
from statistics import median
from typing import Iterable, Optional, Sequence

from .ass import KaraokeSyllable


@dataclass(slots=True, frozen=True)
class TimelineSyllable:
    id: str
    start: float
    end: float
    text: str
    burst_marked: bool = False
    source: Optional[KaraokeSyllable] = None
    measured_start: Optional[float] = None
    measured_end: Optional[float] = None
    is_gap: bool = False
    track: int = 0

    @property
    def effective_start(self) -> float:
        return self.measured_start if self.measured_start is not None else self.start

    @property
    def effective_end(self) -> float:
        return self.measured_end if self.measured_end is not None else self.end

    @property
    def measurement_changed(self) -> bool:
        return self.measured_start is not None or self.measured_end is not None

    def with_measurement(self, start: Optional[float], end: Optional[float]) -> "TimelineSyllable":
        if start is None and end is None:
            return replace(self, measured_start=None, measured_end=None)
        start = self.start if start is None else float(start)
        end = self.end if end is None else float(end)
        if not isfinite(start) or not isfinite(end):
            raise ValueError("Measured boundaries must be finite numbers")
        # Start and End are semantic markers, not an automatically sorted span.
        # A reversed pair reproduces the archived Audacity leading-"-" label
        # convention and is meaningful at the edges of Legacy 1–2 s windows.
        # Deliberately do NOT constrain the measurement to touch neighbouring
        # syllables. Audacity-style perceptual trims may leave gaps.
        return replace(self, measured_start=start, measured_end=end)


@dataclass(slots=True)
class MeasurementTimeline:
    syllables: list[TimelineSyllable]

    @classmethod
    def from_karaoke(cls, syllables: Iterable[KaraokeSyllable]) -> "MeasurementTimeline":
        return cls(
            [
                TimelineSyllable(
                    id=s.id,
                    start=s.start,
                    end=s.end,
                    text=s.visible_text,
                    burst_marked=s.burst_marked,
                    source=s,
                    is_gap=not bool(s.visible_text.strip()),
                    track=getattr(s, "track", 0),
                )
                for s in syllables
            ]
        )

    def set_measurement(self, syllable_id: str, start: Optional[float], end: Optional[float]) -> TimelineSyllable:
        for i, syl in enumerate(self.syllables):
            if syl.id == syllable_id:
                updated = syl.with_measurement(start, end)
                self.syllables[i] = updated
                return updated
        raise KeyError(syllable_id)

    def clear_measurement(self, syllable_id: str) -> TimelineSyllable:
        return self.set_measurement(syllable_id, None, None)

    def changed(self) -> list[TimelineSyllable]:
        return [s for s in self.syllables if s.measurement_changed]


@dataclass(slots=True, frozen=True)
class SPSWindow:
    start: float
    end: float
    count: int
    speed: float
    syllable_ids: tuple[str, ...]
    text: str
    mode: str

    @property
    def duration(self) -> float:
        return self.end - self.start




@dataclass(slots=True, frozen=True)
class SPSGraphPoint:
    time: float
    speed: float
    count: int
    window_start: float
    window_end: float
    syllable_ids: tuple[str, ...]
    text: str
    metric: str
    measured: bool = False

    @property
    def duration(self) -> float:
        return self.window_end - self.window_start

    @property
    def source_label(self) -> str:
        return "Measured" if self.measured else "ASS"


@dataclass(slots=True, frozen=True)
class BurstCandidate:
    start: float
    end: float
    peak_sps: float
    mean_sps: float
    syllable_ids: tuple[str, ...]
    text: str
    source: str = "auto"
    heat: float = 0.0  # GUI-ready scalar: 0=cool, 1=hot



def _coerce(items: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable], *, measured: bool = False) -> list[TimelineSyllable]:
    if isinstance(items, Sequence) and (not items or isinstance(items[0], TimelineSyllable)):
        return list(items)  # type: ignore[arg-type]
    result: list[TimelineSyllable] = []
    for s in items:  # type: ignore[assignment]
        result.append(
            TimelineSyllable(
                id=s.id,
                start=s.start,
                end=s.end,
                text=s.visible_text,
                burst_marked=s.burst_marked,
                source=s,
                is_gap=not bool(s.visible_text.strip()),
            )
        )
    return result


def _bounds(s: TimelineSyllable, measured: bool) -> tuple[float, float]:
    return (s.effective_start, s.effective_end) if measured else (s.start, s.end)


def _spoken(items: Sequence[TimelineSyllable]) -> list[TimelineSyllable]:
    """Exclude timing-only empty karaoke tags from SPS counts.

    TextGrid import uses empty ``{\\k..}`` segments to preserve real pauses
    without stretching the previous spoken syllable. Those timing carriers must
    remain visible/editable on the karaoke timeline but are not syllables per
    second.
    """
    return [item for item in items if not item.is_gap and bool(item.text.strip())]


def selection_audition_bounds(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    measured: bool = False,
    fallback_seconds: float = 0.25,
) -> tuple[float, float, bool]:
    """Return forward-playback bounds without changing Start/End roles.

    A legacy leading-``-`` measurement may put the formal End before the
    formal Start.  Audio cannot run backwards, but sorting the two markers is
    wrong: it makes playback stop at Start.  In that case audition from the
    original beginning of the first syllable (or a short pre-roll) and still
    stop at the formal End.

    The boolean result reports whether this reversed-boundary fallback was
    needed.
    """
    items = _coerce(syllables)
    if not items:
        raise ValueError("At least one syllable is required for audition")
    formal_start = _bounds(items[0], measured)[0]
    formal_end = _bounds(items[-1], measured)[1]
    if formal_end > formal_start:
        return formal_start, formal_end, False
    pre_roll = max(0.0, float(fallback_seconds))
    source_start = float(items[0].start)
    fallback_start = source_start if source_start < formal_end else formal_end - pre_roll
    return max(0.0, fallback_start), formal_end, True


def _make_window(group: Sequence[TimelineSyllable], start: float, end: float, mode: str) -> SPSWindow:
    duration = end - start
    speed = len(group) / duration if duration > 0 else 0.0
    return SPSWindow(
        start=start,
        end=end,
        count=len(group),
        speed=speed,
        syllable_ids=tuple(s.id for s in group),
        text=" ".join(s.text.strip() for s in group if s.text.strip()),
        mode=mode,
    )


def legacy_windows(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    min_duration: float = 1.0,
    max_duration: float = 2.0,
    measured: bool = False,
    best_per_start: bool = False,
) -> list[SPSWindow]:
    """Reproduce the archived ``sps.py``/``sps_from_subs.py`` metric.

    Groups are consecutive syllables whose span is between 1 and 2 seconds and
    speed is ``count / actual_span``.  ``measured=True`` uses perceptually trimmed
    independent boundaries.
    """
    items = _spoken(_coerce(syllables))
    windows: list[SPSWindow] = []
    for i in range(len(items)):
        start = _bounds(items[i], measured)[0]
        local: list[SPSWindow] = []
        for j in range(i, len(items)):
            end = _bounds(items[j], measured)[1]
            diff = end - start
            if diff < min_duration:
                continue
            if diff > max_duration:
                break
            local.append(_make_window(items[i:j + 1], start, end, "legacy-measured" if measured else "legacy"))
        if best_per_start and local:
            windows.append(max(local, key=lambda w: w.speed))
        else:
            windows.extend(local)
    return windows


def fastest_legacy_window(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    measured: bool = False,
    min_duration: float = 1.0,
    max_duration: float = 2.0,
) -> Optional[SPSWindow]:
    """Return the fastest user-facing SPS window for a segment.

    Precise SPS measurement intentionally uses only the archived 1–2 second
    method (count / actual span).  Strict fixed windows remain private building
    blocks for automatic burst-candidate discovery.
    """
    rows = legacy_windows(
        syllables, min_duration=min_duration, max_duration=max_duration, measured=measured
    )
    return max(rows, key=lambda row: (row.speed, row.count, -row.duration), default=None)


def find_strict_windows(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    window: float = 1.0,
    mode: str = "contained",
    measured: bool = False,
) -> list[SPSWindow]:
    """Evaluate exact fixed-duration SPS windows.

    ``contained`` counts syllables whose effective interval is wholly within the
    window.  ``onset`` counts syllable starts in [start, start+window).  Candidate
    starts include every onset and every ``end-window`` boundary, so the maximum
    is not missed merely because the best window begins just before a syllable.
    """
    if window <= 0:
        raise ValueError("window must be > 0")
    if mode not in {"contained", "onset"}:
        raise ValueError("mode must be 'contained' or 'onset'")
    items = _spoken(_coerce(syllables))
    if not items:
        return []
    candidates: set[float] = set()
    for s in items:
        st, en = _bounds(s, measured)
        candidates.add(st)
        candidates.add(en - window)
    results: list[SPSWindow] = []
    for start in sorted(candidates):
        end = start + window
        if mode == "contained":
            group = [s for s in items if _bounds(s, measured)[0] >= start - 1e-9 and _bounds(s, measured)[1] <= end + 1e-9]
        else:
            group = [s for s in items if start - 1e-9 <= _bounds(s, measured)[0] < end - 1e-9]
        if group:
            results.append(_make_window(group, start, end, f"strict-{mode}{'-measured' if measured else ''}"))
    return results


def sps_profile(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    window: float = 1.0,
    mode: str = "contained",
    measured: bool = False,
) -> list[SPSWindow]:
    """Return the best fixed window associated with every syllable onset.

    This is suitable for the future overview timeline/graph.  GUI code can map
    ``speed`` to a heat colour without recomputing ASS timing.
    """
    items = _spoken(_coerce(syllables))
    all_windows = find_strict_windows(items, window=window, mode=mode, measured=measured)
    if not all_windows:
        return []
    result: list[SPSWindow] = []
    for s in items:
        t = _bounds(s, measured)[0]
        nearby = [w for w in all_windows if w.start <= t <= w.end]
        if nearby:
            result.append(max(nearby, key=lambda w: w.speed))
    return result


def manual_bursts(syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable]) -> list[BurstCandidate]:
    items = _spoken(_coerce(syllables))
    groups: list[list[TimelineSyllable]] = []
    current: list[TimelineSyllable] = []
    for s in items:
        if s.burst_marked:
            current.append(s)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    result: list[BurstCandidate] = []
    for group in groups:
        start, end = group[0].start, group[-1].end
        speed = len(group) / (end - start) if end > start else 0.0
        result.append(
            BurstCandidate(
                start=start,
                end=end,
                peak_sps=speed,
                mean_sps=speed,
                syllable_ids=tuple(s.id for s in group),
                text=" ".join(s.text.strip() for s in group if s.text.strip()),
                source="manual-red",
                heat=1.0,
            )
        )
    return result


def _window_density(items: Sequence[TimelineSyllable], center: float, window: float) -> float:
    start = center - window / 2
    end = center + window / 2
    count = sum(1 for s in items if s.start >= start - 1e-9 and s.end <= end + 1e-9)
    return count / window


def _expand_connected(
    items: Sequence[TimelineSyllable],
    seed: SPSWindow,
    *,
    window: float,
    relative_drop: float,
    max_gap: float,
    max_expansion: float,
) -> list[TimelineSyllable]:
    seed_ids = set(seed.syllable_ids)
    indices = [i for i, s in enumerate(items) if s.id in seed_ids]
    if not indices:
        return []
    left = min(indices)
    right = max(indices)
    peak = seed.speed
    seed_start, seed_end = seed.start, seed.end

    while left > 0:
        candidate = items[left - 1]
        neighbour = items[left]
        if neighbour.start - candidate.end > max_gap:
            break
        if seed_start - candidate.start > max_expansion:
            break
        center = (candidate.start + candidate.end) / 2
        if _window_density(items, center, window) < peak * relative_drop:
            break
        left -= 1

    while right + 1 < len(items):
        candidate = items[right + 1]
        neighbour = items[right]
        if candidate.start - neighbour.end > max_gap:
            break
        if candidate.end - seed_end > max_expansion:
            break
        center = (candidate.start + candidate.end) / 2
        if _window_density(items, center, window) < peak * relative_drop:
            break
        right += 1

    return list(items[left:right + 1])


def detect_bursts(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    window: float = 1.0,
    min_peak_sps: float = 6.0,
    relative_drop: float = 0.70,
    max_gap: float = 0.35,
    max_expansion: float = 3.0,
    suppression_seconds: float = 0.75,
    max_candidates: int = 20,
) -> list[BurstCandidate]:
    """Find high-speed connected burst candidates.

    Seeds are exact one-second contained windows.  Expansion is strictly adjacent
    left/right, so the old 'similar-speed island several seconds away' bug cannot
    occur.  Results include a normalized ``heat`` value for the future navigation
    overview timeline.
    """
    items = _spoken(_coerce(syllables))
    if not items:
        return []
    windows = find_strict_windows(items, window=window, mode="contained")
    if not windows:
        return []
    ranked = sorted((w for w in windows if w.speed >= min_peak_sps), key=lambda w: (-w.speed, w.start))
    seeds: list[SPSWindow] = []
    for w in ranked:
        center = (w.start + w.end) / 2
        if any(abs(center - (s.start + s.end) / 2) < suppression_seconds for s in seeds):
            continue
        seeds.append(w)
        if len(seeds) >= max_candidates:
            break
    if not seeds:
        return []

    raw: list[BurstCandidate] = []
    for seed in seeds:
        group = _expand_connected(
            items,
            seed,
            window=window,
            relative_drop=relative_drop,
            max_gap=max_gap,
            max_expansion=max_expansion,
        )
        if not group:
            continue
        start, end = group[0].start, group[-1].end
        local_speeds = [_window_density(items, (s.start + s.end) / 2, window) for s in group]
        raw.append(
            BurstCandidate(
                start=start,
                end=end,
                peak_sps=seed.speed,
                mean_sps=sum(local_speeds) / len(local_speeds),
                syllable_ids=tuple(s.id for s in group),
                text=" ".join(s.text.strip() for s in group if s.text.strip()),
            )
        )

    # Deduplicate heavily-overlapping expansions, retaining the faster seed.
    deduped: list[BurstCandidate] = []
    for candidate in sorted(raw, key=lambda b: (-b.peak_sps, b.start)):
        ids = set(candidate.syllable_ids)
        duplicate = False
        for kept in deduped:
            overlap = len(ids.intersection(kept.syllable_ids))
            denom = max(1, min(len(ids), len(kept.syllable_ids)))
            if overlap / denom >= 0.65:
                duplicate = True
                break
        if not duplicate:
            deduped.append(candidate)

    if not deduped:
        return []
    lo = min(b.peak_sps for b in deduped)
    hi = max(b.peak_sps for b in deduped)
    span = hi - lo
    result = [
        replace(b, heat=(b.peak_sps - lo) / span if span > 1e-9 else 1.0)
        for b in sorted(deduped, key=lambda b: b.start)
    ]
    return result


def sps_graph_points(
    syllables: Sequence[TimelineSyllable] | Iterable[KaraokeSyllable],
    *,
    metric: str = "strict-contained",
    window: float = 1.0,
    measured: bool = False,
) -> list[SPSGraphPoint]:
    """Build timeline-anchored graph points using the same SPS engine as CLI.

    ``strict-contained`` and ``strict-onset`` associate every syllable onset
    with the fastest exact fixed window covering that onset. ``legacy`` keeps
    the archived 1–2 s metric and uses the best group starting at each syllable.
    Measured mode substitutes independent perceptual trim boundaries where they
    exist, while untouched syllables retain their original karaoke intervals.
    """
    items = _spoken(_coerce(syllables))
    if not items:
        return []
    if metric == "legacy":
        windows = legacy_windows(items, measured=measured, best_per_start=True)
        return [
            SPSGraphPoint(
                time=w.start, speed=w.speed, count=w.count,
                window_start=w.start, window_end=w.end,
                syllable_ids=w.syllable_ids, text=w.text, metric=metric, measured=measured,
            )
            for w in windows
        ]
    if metric not in {"strict-contained", "strict-onset"}:
        raise ValueError("metric must be strict-contained, strict-onset or legacy")
    strict_mode = metric.split("-", 1)[1]
    windows = find_strict_windows(items, window=window, mode=strict_mode, measured=measured)
    if not windows:
        return []
    points: list[SPSGraphPoint] = []
    for syl in items:
        onset = _bounds(syl, measured)[0]
        nearby = [w for w in windows if w.start - 1e-9 <= onset <= w.end + 1e-9]
        if not nearby:
            continue
        w = max(nearby, key=lambda row: (row.speed, -abs((row.start + row.end) / 2 - onset)))
        points.append(
            SPSGraphPoint(
                time=onset, speed=w.speed, count=w.count,
                window_start=w.start, window_end=w.end,
                syllable_ids=w.syllable_ids, text=w.text, metric=metric, measured=measured,
            )
        )
    return points
