"""Unit tests for ui_alt view resolver, fallback mechanism, and dual-UI configuration."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

# Ensure mobile src is on sys.path
mobile_src = Path(__file__).resolve().parent.parent / "karaoke_mobile" / "src"
if str(mobile_src) not in sys.path:
    sys.path.insert(0, str(mobile_src))

from ui.display_settings import DisplaySettings
from ui.view_resolver import get_active_views, is_alt_ui_enabled
from ui.views.editor_view import EditorView as DefaultEditorView


class TestUIAltFallback(unittest.TestCase):
    def setUp(self):
        self.orig_env = os.environ.get("KARAOKE_UI_ALT")

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["KARAOKE_UI_ALT"] = self.orig_env
        else:
            os.environ.pop("KARAOKE_UI_ALT", None)

    def test_default_env_returns_standard_ui(self):
        os.environ.pop("KARAOKE_UI_ALT", None)
        with patch("ui.display_settings.get_display_settings", return_value=DisplaySettings(use_alt_ui=False)):
            self.assertFalse(is_alt_ui_enabled())
            mfa, editor, sps, burst, export, is_alt = get_active_views()
            self.assertFalse(is_alt)
            self.assertIs(editor, DefaultEditorView)

    def test_env_enabled_returns_alt_flag(self):
        os.environ["KARAOKE_UI_ALT"] = "1"
        self.assertTrue(is_alt_ui_enabled())

        # If ui_alt doesn't have an editor_view yet, it gracefully falls back to default
        mfa, editor, sps, burst, export, is_alt = get_active_views()
        self.assertTrue(is_alt)
        # Fallback to DefaultEditorView because ui_alt/views/editor_view is not yet created
        self.assertIs(editor, DefaultEditorView)

    def test_env_disabled_overrides_settings(self):
        os.environ["KARAOKE_UI_ALT"] = "0"
        with patch("ui.display_settings.get_display_settings", return_value=DisplaySettings(use_alt_ui=True)):
            self.assertFalse(is_alt_ui_enabled())

    def test_display_settings_use_alt_ui_flag(self):
        os.environ.pop("KARAOKE_UI_ALT", None)
        ds = DisplaySettings(use_alt_ui=True)
        self.assertTrue(ds.use_alt_ui)
        with patch("ui.display_settings.get_display_settings", return_value=ds):
            self.assertTrue(is_alt_ui_enabled())


if __name__ == "__main__":
    unittest.main()
