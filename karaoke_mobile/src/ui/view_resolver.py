"""View resolver supporting seamless switching between standard ui and alternative ui_alt."""

from __future__ import annotations

import os
from typing import Tuple, Type

# Default standard views
from ui.views.burst_view import BurstView as DefaultBurstView
from ui.views.editor_view import EditorView as DefaultEditorView
from ui.views.export_view import ExportView as DefaultExportView
from ui.views.mfa_view import MFAView as DefaultMFAView
from ui.views.sps_view import SPSView as DefaultSPSView


def is_alt_ui_enabled() -> bool:
    """Check if alternative UI mode is enabled via environment variable or display settings."""
    env_val = os.getenv("KARAOKE_UI_ALT", "").strip().lower()
    if env_val in ("1", "true", "yes", "on"):
        return True
    if env_val in ("0", "false", "no", "off"):
        return False
    try:
        from ui.display_settings import get_display_settings
        return bool(get_display_settings().use_alt_ui)
    except Exception:
        return False


def get_active_views() -> Tuple[
    Type[DefaultMFAView],
    Type[DefaultEditorView],
    Type[DefaultSPSView],
    Type[DefaultBurstView],
    Type[DefaultExportView],
    bool,
]:
    """Resolve and return active view classes with graceful fallback to standard ui.

    Returns:
        (MFAViewClass, EditorViewClass, SPSViewClass, BurstViewClass, ExportViewClass, is_alt_mode)
    """
    if not is_alt_ui_enabled():
        return (
            DefaultMFAView,
            DefaultEditorView,
            DefaultSPSView,
            DefaultBurstView,
            DefaultExportView,
            False,
        )

    mfa_cls = DefaultMFAView
    editor_cls = DefaultEditorView
    sps_cls = DefaultSPSView
    burst_cls = DefaultBurstView
    export_cls = DefaultExportView

    try:
        from ui_alt.views.editor_view import EditorView as AltEditorView
        editor_cls = AltEditorView
    except (ImportError, AttributeError):
        pass

    try:
        from ui_alt.views.sps_view import SPSView as AltSPSView
        sps_cls = AltSPSView
    except (ImportError, AttributeError):
        pass

    try:
        from ui_alt.views.mfa_view import MFAView as AltMFAView
        mfa_cls = AltMFAView
    except (ImportError, AttributeError):
        pass

    try:
        from ui_alt.views.burst_view import BurstView as AltBurstView
        burst_cls = AltBurstView
    except (ImportError, AttributeError):
        pass

    try:
        from ui_alt.views.export_view import ExportView as AltExportView
        export_cls = AltExportView
    except (ImportError, AttributeError):
        pass

    return mfa_cls, editor_cls, sps_cls, burst_cls, export_cls, True
