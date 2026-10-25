"""Mobile Core Primitives for Karaoke/SPS pipeline.

Pure Python, zero-GUI core logic for ASS parsing, syllable manipulations,
burst identification, RGB cube gradient interpolations, dynamic sinusoidal pulsing,
and multi-language IPA phonetic mapping.
"""

from .ass import AssDocument, AssEvent, KaraokeSyllable, KaraokeTagType
from .sps import (
    BurstCandidate,
    MeasurementTimeline,
    SPSWindow,
    SPSGraphPoint,
    detect_bursts,
    manual_bursts,
    sps_graph_points,
)
from .render import (
    CropRect,
    RenderLayoutSettings,
    RenderMeasurement,
    RenderOutputSettings,
    DirectVideoSettings,
    ass_playres,
    interpolate_cube_surface,
    generate_burst_pulse_tags,
    burst_syllable_style,
    apply_render_burst_styling,
    prepare_render_document,
)
from .editor import (
    KaraokeEditError,
    KaraokeEditResult,
    colour_burst,
    uncolour_burst,
    set_syllable_text,
    set_syllable_texts,
    set_syllable_romanization,
    set_tag_type,
    split_syllable_at_time,
    split_syllable_at_raw_offset,
    redistribute_boundary,
)
from .multilang import (
    clean_multilingual_transcript,
    ru_word_to_mfa_ipa,
    CUSTOM_RAP_PRONUNCIATIONS,
)

__all__ = [
    "AssDocument",
    "AssEvent",
    "KaraokeSyllable",
    "KaraokeTagType",
    "BurstCandidate",
    "MeasurementTimeline",
    "SPSWindow",
    "SPSGraphPoint",
    "detect_bursts",
    "manual_bursts",
    "sps_graph_points",
    "CropRect",
    "RenderLayoutSettings",
    "RenderMeasurement",
    "RenderOutputSettings",
    "DirectVideoSettings",
    "ass_playres",
    "interpolate_cube_surface",
    "generate_burst_pulse_tags",
    "burst_syllable_style",
    "apply_render_burst_styling",
    "prepare_render_document",
    "KaraokeEditError",
    "KaraokeEditResult",
    "colour_burst",
    "uncolour_burst",
    "set_syllable_text",
    "set_syllable_texts",
    "set_syllable_romanization",
    "set_tag_type",
    "split_syllable_at_time",
    "split_syllable_at_raw_offset",
    "redistribute_boundary",
    "clean_multilingual_transcript",
    "ru_word_to_mfa_ipa",
    "CUSTOM_RAP_PRONUNCIATIONS",
]
