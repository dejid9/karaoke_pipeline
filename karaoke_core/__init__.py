"""Core primitives for the karaoke/SPS pipeline.

The package intentionally has no GUI or third-party dependencies.  GUI code can
consume these objects later without teaching every widget how ASS works.
"""

from .ass import AssDocument, AssEvent, KaraokeSyllable, KaraokeTagType
from .project import ProjectConfig, create_project, load_project
from .audacity import AudacityLabel, load_audacity_labels, legacy_label_windows
from .sps import (
    BurstCandidate,
    MeasurementTimeline,
    SPSWindow,
    SPSGraphPoint,
    detect_bursts,
    find_strict_windows,
    legacy_windows,
    manual_bursts,
    sps_profile,
    sps_graph_points,
)

__all__ = [
    "AssDocument",
    "AssEvent",
    "KaraokeSyllable",
    "KaraokeTagType",
    "ProjectConfig",
    "create_project",
    "load_project",
    "AudacityLabel",
    "load_audacity_labels",
    "legacy_label_windows",
    "BurstCandidate",
    "MeasurementTimeline",
    "SPSWindow",
    "SPSGraphPoint",
    "detect_bursts",
    "find_strict_windows",
    "legacy_windows",
    "manual_bursts",
    "sps_profile",
    "sps_graph_points",
    "CropRect",
    "RenderLayoutSettings",
    "RenderMeasurement",
    "RenderOutputSettings",
    "DirectVideoSettings",
    "ass_playres",
    "measure_render_layout",
    "prepare_render_document",
    "render_karaoke_video",
    "render_karaoke_on_source",
    "build_direct_video_command",
    "TextPreprocessError", "TextPreprocessSettings", "TextPreprocessReport",
    "normalize_text", "strip_punctuation_tokens", "prepare_text_local",
    "probe_python_packages", "tokenize_japanese_sudachi",
    "HealthCheck", "HealthReport", "run_health_checks",
]

# Render/layout helpers (Update 007)
from .render import (
    CropRect, RenderLayoutSettings, RenderMeasurement, RenderOutputSettings, DirectVideoSettings,
    ass_playres, measure_render_layout, prepare_render_document, render_karaoke_video,
    render_karaoke_on_source, build_direct_video_command,
)

# MFA runner helpers (Update 011)
from .mfa import (
    MFAError, MFAInstallation, MFAWorkspace, MFAAlignmentResult, MFAProcess, CondaEnvironment,
    detect_mfa_installation, build_runtime_align_command, prepare_mfa_workspace,
    find_textgrid, adopt_textgrid, build_conda_mfa_prefix, parse_conda_mfa_launcher,
    list_conda_environments, build_validate_command, build_find_oovs_command,
    find_oov_artifacts, read_oov_summary, build_model_command,
)

# Final language preprocessing / diagnostics (Update 013)
from .textprep import (
    TextPreprocessError, TextPreprocessSettings, TextPreprocessReport,
    normalize_text, strip_punctuation_tokens, prepare_text_local,
    probe_python_packages, tokenize_japanese_sudachi,
)
from .doctor import HealthCheck, HealthReport, run_health_checks
